"""Exercise native archive creation with independent Python decoders."""

import base64
import binascii
import bz2
import errno
import gzip
import hashlib
import io
import lzma
import os
import pathlib
import random
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import xml.etree.ElementTree
import zipfile
import zlib


EXECUTABLE = pathlib.Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None

# Suffixes that select an xxfclib writer in core.c, and the kind it reports.
SUFFIX_WRITERS = ((".tar", "tar"), (".tar.gz", "tar.gz"), (".tgz", "tar.gz"),
                  (".tar.bz2", "tar.bz2"), (".tbz2", "tar.bz2"), (".tar.xz", "tar.xz"),
                  (".txz", "tar.xz"), (".tar.zst", "tar.zst"), (".tar.lz4", "tar.lz4"),
                  (".zip", "zip"), (".cpio", "cpio"), (".7z", "7z"), (".wim", "wim"))
# Spell out the self-contained stored mode used by the xxfclib-only build.
SUFFIX_ARGUMENTS = {".wim": ("--compression=stored",)}


def windows_extended_path(path):
    """Address a long local path without depending on the MAX_PATH policy."""
    path = os.path.abspath(os.fspath(path))
    if os.name != "nt" or path.startswith("\\\\?\\"):
        return pathlib.Path(path)
    if path.startswith("\\\\"):
        return pathlib.Path("\\\\?\\UNC\\" + path[2:])
    return pathlib.Path("\\\\?\\" + path)


def cleanup_temporary(temporary, root):
    try:
        temporary.cleanup()
    except OSError:
        if os.name != "nt":
            raise
        shutil.rmtree(windows_extended_path(root))
        temporary.cleanup()


def displayed_source_path(name):
    """Writer progress shows source paths with the host separator."""
    folder = name.endswith("/")
    name = name[:-1] if folder else name
    return name.replace("/", os.sep) + ("/" if folder else "")


def stage_files(folder):
    """Writer and reader stages: ".xfu-<8 hex>-<n>.tmp" and earlier names."""
    return sorted(path.name for path in pathlib.Path(folder).iterdir()
                  if path.name.startswith(".xfu-") or ".xfu-native-" in path.name)


def ar_members(content):
    """(name, data) of each member of an ar archive, without symbol tables."""
    assert content.startswith(b"!<arch>\n")
    position, members, table = 8, [], b""
    while position < len(content):
        header = content[position:position + 60]
        name, size = header[:16].rstrip(b" "), int(header[48:58])
        data = content[position + 60:position + 60 + size]
        position += 60 + size + (size & 1)
        if name == b"//":
            table = data
            continue
        if name.startswith(b"#1/"):
            length = int(name[3:])
            name, data = data[:length], data[length:]
        elif name.startswith(b"/") and name[1:].isdigit():
            start = int(name[1:])
            name = table[start:table.index(b"/\n", start)]
        members.append((name.rstrip(b"/").decode(), data))
    return members


class NativeWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xfu-native-writers-")
        self.root = pathlib.Path(self.temp.name)
        self.addCleanup(cleanup_temporary, self.temp, self.root)
        self.payload = b"native writer round trip\n" + bytes(range(256)) * 8
        (self.root / "alpha.txt").write_bytes(self.payload)

    def run_xfu(self, *arguments, success=True):
        command = [str(EXECUTABLE), *map(str, arguments)]
        if os.name != "nt":  # POSIX names are bytes: keep any that are not UTF-8.
            command = [os.fsencode(argument) for argument in command]
        completed = subprocess.run(
            command, cwd=self.root,
            encoding="utf-8", errors="surrogateescape", capture_output=True, timeout=60,
        )
        if success:
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        else:
            self.assertNotEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        return completed

    def test_tar_and_zip_contents(self):
        self.run_xfu("a", "sample.tar", "alpha.txt", "--format=pax")
        with tarfile.open(self.root / "sample.tar") as archive:
            self.assertEqual(archive.extractfile("alpha.txt").read(), self.payload)
        self.run_xfu("a", "sample.zip", "alpha.txt", "--format=zip",
                     "--compression=bzip2", "--compression-level=9")
        with zipfile.ZipFile(self.root / "sample.zip") as archive:
            self.assertEqual(archive.read("alpha.txt"), self.payload)

    def test_tar_wire_variants_and_long_names(self):
        # Keep the host path under MAX_PATH on Windows while making the leaf
        # too long for a classic TAR name field.
        long_name = (("directory/" if os.name == "nt" else "directory-" + "a" * 100 + "/") +
                     "b" * 120 + ".txt")
        long_path = self.root / long_name
        accessible_long_path = windows_extended_path(long_path)
        accessible_long_path.parent.mkdir()
        accessible_long_path.write_bytes(self.payload)
        signatures = {
            "ustar": (257, b"ustar\0"),
            "pax": (156, b"x"),
            "gnutar": (257, b"ustar  "),
            "v7tar": (257, b"\0" * 7),
        }
        for variant, (offset, signature) in signatures.items():
            with self.subTest(variant=variant):
                output = "variant-" + variant + ".tar"
                self.run_xfu("a", output, "alpha.txt", "--format=" + variant)
                self.assertEqual((self.root / output).read_bytes()[offset:offset + len(signature)],
                                 signature)
                with tarfile.open(self.root / output) as archive:
                    self.assertEqual(archive.extractfile("alpha.txt").read(), self.payload)
                self.run_xfu("t", output, "--reader=native")
        for variant in ("pax", "pax_restricted", "gnutar"):
            with self.subTest(long_name=variant):
                output = "long-" + variant + ".tar"
                self.run_xfu("a", output, long_name, "--format=" + variant)
                with tarfile.open(self.root / output) as archive:
                    self.assertEqual(archive.extractfile(long_name).read(), self.payload)
                self.run_xfu("t", output, "--reader=native")

    def test_independent_tar_filters(self):
        for extension, filter_name in (("gz", "gzip"), ("bz2", "bzip2"),
                                       ("xz", "xz")):
            with self.subTest(filter=filter_name):
                output = f"sample.tar.{extension}"
                self.run_xfu("a", output, "alpha.txt", "--format=pax",
                             "--filter=" + filter_name, "--compression-level=6")
                with tarfile.open(self.root / output, "r:*") as archive:
                    self.assertEqual(archive.extractfile("alpha.txt").read(),
                                     self.payload)

    def test_raw_filters(self):
        decoders = {
            "gzip": gzip.decompress,
            "bzip2": bz2.decompress,
            "xz": lzma.decompress,
            "lzma": lambda data: lzma.decompress(data, format=lzma.FORMAT_ALONE),
        }
        for filter_name, decoder in decoders.items():
            with self.subTest(filter=filter_name):
                output = "raw-" + filter_name
                self.run_xfu("a", output, "alpha.txt", "--format=raw",
                             "--filter=" + filter_name)
                self.assertEqual(decoder((self.root / output).read_bytes()),
                                 self.payload)

    def test_additional_outer_filters(self):
        for filter_name in ("lz4", "lzip", "lzop", "compress"):
            with self.subTest(filter=filter_name):
                output = "sample-" + filter_name
                self.run_xfu("a", output, "alpha.txt", "--format=pax",
                             "--filter=" + filter_name)
                self.run_xfu("t", output, "--reader=native")
                self.run_xfu("x", output, "--reader=native", "-oout-" + filter_name)
                self.assertEqual((self.root / ("out-" + filter_name) /
                                  "alpha.txt").read_bytes(), self.payload)

    def test_text_outer_filters_have_decodable_tar_payload(self):
        for filter_name in ("uuencode", "b64encode"):
            with self.subTest(filter=filter_name):
                output = "sample-" + filter_name
                self.run_xfu("a", output, "alpha.txt", "--format=pax",
                             "--filter=" + filter_name)
                lines = (self.root / output).read_bytes().splitlines()
                if filter_name == "uuencode":
                    self.assertEqual(lines[0], b"begin 644 payload")
                    self.assertEqual(lines[-2:], [b"`", b"end"])
                    decoded = b"".join(binascii.a2b_uu(line)
                                       for line in lines[1:-2])
                else:
                    self.assertEqual(lines[0], b"begin-base64 644 payload")
                    self.assertEqual(lines[-1], b"====")
                    decoded = base64.b64decode(b"".join(lines[1:-1]),
                                               validate=True)
                with tarfile.open(fileobj=io.BytesIO(decoded), mode="r:") as archive:
                    self.assertEqual(archive.extractfile("alpha.txt").read(),
                                     self.payload)

    def test_cpio_cp437_header_name(self):
        name = "café.txt"
        (self.root / name).write_bytes(self.payload)
        self.run_xfu("a", "legacy.cpio", name, "--format=newc",
                     "--options=cpio:hdrcharset=CP437")
        archive = (self.root / "legacy.cpio").read_bytes()
        self.assertIn(b"caf\x82.txt\0", archive)
        self.assertNotIn(name.encode("utf-8") + b"\0", archive)
        unrepresentable = "emoji-😀.txt"
        (self.root / unrepresentable).write_bytes(self.payload)
        self.run_xfu("a", "legacy.cpio", unrepresentable, "--format=newc",
                     "--options=cpio:hdrcharset=CP437", success=False)
        self.assertEqual((self.root / "legacy.cpio").read_bytes(), archive)

    def test_native_cpio_and_sevenzip(self):
        self.run_xfu("a", "sample.cpio.gz", "alpha.txt", "--format=newc",
                     "--filter=gzip")
        self.assertTrue((self.root / "sample.cpio.gz").read_bytes().startswith(b"\x1f\x8b"))
        self.run_xfu("t", "sample.cpio.gz")
        self.run_xfu("a", "sample.7z", "alpha.txt", "--format=7zip",
                     "--compression=lzma2")
        self.run_xfu("t", "sample.7z")

    def test_zip_native_reader_with_each_method(self):
        for method in ("stored", "deflate", "bzip2", "lzma", "xz", "zstd"):
            with self.subTest(method=method):
                output = "method-" + method + ".zip"
                self.run_xfu("a", output, "alpha.txt", "--format=zip",
                             "--compression=" + method)
                self.run_xfu("t", output, "--reader=native")

    def make_tree(self):
        tree = self.root / "tree"
        (tree / "sub" / "deep").mkdir(parents=True)
        (tree / "empty").mkdir()
        (tree / "a.txt").write_bytes(b"alpha\n")
        (tree / "sub" / "b.txt").write_bytes(self.payload)
        (tree / "sub" / "deep" / "c.txt").write_bytes(b"")
        return ["tree/", "tree/a.txt", "tree/empty/", "tree/sub/", "tree/sub/b.txt",
                "tree/sub/deep/", "tree/sub/deep/c.txt"]

    def test_folder_inputs_are_walked(self):
        listed = self.make_tree()
        for variant in ("pax", "pax_restricted", "ustar", "gnutar", "v7tar", "zip", "7zip",
                        "newc", "cpio_odc", "cpio_bin", "iso9660", "xar", "mtree"):
            with self.subTest(format=variant):
                output = "walked-" + variant + ".bin"
                result = self.run_xfu("a", output, "tree", "--format=" + variant)
                self.assertEqual(result.stdout.splitlines(),
                                 ["  " + displayed_source_path(name) for name in listed] +
                                 [output + ": 3 file(s) and 4 folder(s) as " + variant])
                if variant == "mtree":
                    continue
                destination = self.root / ("walked-" + variant)
                self.run_xfu("x", output, "-o" + str(destination))
                for name in listed:
                    path = destination / name
                    if name.endswith("/"):
                        self.assertTrue(path.is_dir(), name)
                    else:
                        self.assertEqual(path.read_bytes(), (self.root / name).read_bytes())
        with tarfile.open(self.root / "walked-pax.bin") as archive:
            self.assertEqual([member.name + ("/" if member.isdir() else "") for member in archive],
                             listed)
        with zipfile.ZipFile(self.root / "walked-zip.bin") as archive:
            self.assertEqual(archive.namelist(), listed)

    def test_xar_folders_are_one_element_each(self):
        self.make_tree()
        self.run_xfu("a", "shared.xar", "tree/sub/b.txt", "tree/a.txt", "tree/sub/deep",
                     "--format=xar")
        content = (self.root / "shared.xar").read_bytes()
        length = struct.unpack(">Q", content[8:16])[0]
        toc = xml.etree.ElementTree.fromstring(zlib.decompress(content[28:28 + length]))
        ids = [element.get("id") for element in toc.iter("file")]
        self.assertEqual(len(ids), len(set(ids)))
        root = toc.find("toc")
        self.assertEqual([element.findtext("name") for element in root.findall("file")], ["tree"])
        tree = root.find("file")
        self.assertEqual(sorted(element.findtext("name") for element in tree.findall("file")),
                         ["a.txt", "sub"])
        destination = self.root / "shared-output"
        self.run_xfu("x", "shared.xar", "-o" + str(destination))
        self.assertEqual((destination / "tree" / "sub" / "b.txt").read_bytes(), self.payload)
        self.assertEqual((destination / "tree" / "a.txt").read_bytes(), b"alpha\n")
        self.assertTrue((destination / "tree" / "sub" / "deep").is_dir())

    def test_folders_are_refused_where_the_format_has_none(self):
        self.make_tree()
        output = self.root / "kept.bin"
        for variant, message in (("ar", "cannot store folders"), ("ar_svr4", "cannot store folders"),
                                 ("shar", "cannot store folders"), ("warc", "cannot store folders"),
                                 ("raw", "tree: a raw stream holds one file, not a folder; use an "
                                  "archive format such as --format=pax")):
            with self.subTest(format=variant):
                output.write_bytes(b"existing archive")
                result = self.run_xfu("a", output.name, "tree", "--format=" + variant, success=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
                self.assertEqual(output.read_bytes(), b"existing archive")

    def test_overlapping_inputs_are_written_once(self):
        listed = self.make_tree()
        for variant, inputs in (("zip", ("tree", "tree/a.txt")), ("pax", ("tree", "tree")),
                                ("cpio_odc", ("tree/sub", "tree")),
                                ("iso9660", ("tree", "./tree/sub/b.txt"))):
            with self.subTest(format=variant):
                output = "overlap-" + variant + ".bin"
                result = self.run_xfu("a", output, *inputs, "--format=" + variant)
                lines = result.stdout.splitlines()
                self.assertEqual(len(lines), len(set(lines)))
                self.assertTrue(lines[-1].endswith(": 3 file(s) and 4 folder(s) as " + variant))
                listing = self.run_xfu("l", output).stdout.splitlines()[1:-1]
                names = [line.split(None, 1)[1] for line in listing]
                self.assertEqual(len(names), len(set(names)), names)
                self.assertEqual(len(names), len(listed))
        self.run_xfu("a", "twice.pax", "alpha.txt", "./alpha.txt", "--format=pax")
        with tarfile.open(self.root / "twice.pax") as archive:
            self.assertEqual(archive.getnames(), ["alpha.txt"])

    def test_one_name_for_different_inputs_is_refused(self):
        self.make_tree()
        (self.root / "other").mkdir()
        (self.root / "other" / "a.txt").write_bytes(b"other\n")
        (self.root / "folder" / "a.txt").mkdir(parents=True)
        cases = (("pax", (self.root / "tree" / "a.txt", self.root / "other" / "a.txt"),
                  "duplicate archive member name: a.txt"),
                 ("zip", (self.root / "tree" / "a.txt", self.root / "folder" / "a.txt"),
                  "duplicate archive member name: a.txt"),
                 ("ar", (self.root / "tree" / "a.txt", self.root / "other" / "a.txt"),
                  "duplicate archive member name: a.txt"))
        for variant, inputs, message in cases:
            with self.subTest(format=variant):
                result = self.run_xfu("a", "clash.bin", *inputs, "--format=" + variant,
                                      success=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
                self.assertFalse((self.root / "clash.bin").exists())
        # "a.txt" as a file and as the folder of "a.txt/x".
        (self.root / "a.txt").mkdir()
        (self.root / "a.txt" / "x").write_bytes(b"x")
        result = self.run_xfu("a", "clash.bin", self.root / "tree" / "a.txt", "a.txt/x",
                              "--format=pax", success=False)
        self.assertEqual(result.stderr.splitlines(), ["a.txt: the name is both a file and a folder"])
        self.assertFalse((self.root / "clash.bin").exists())

    def test_ar_keeps_equal_file_names_of_different_paths(self):
        # ar stores file names only; as with GNU ar (static libraries), a/x
        # and b/x are both kept.
        self.make_tree()
        (self.root / "other").mkdir()
        (self.root / "other" / "a.txt").write_bytes(b"other\n")
        for variant in ("ar", "ar_svr4"):
            with self.subTest(format=variant):
                output = "leaves-" + variant + ".a"
                result = self.run_xfu("a", output, "tree/a.txt", "other/a.txt", "--format=" + variant)
                self.assertEqual(result.stdout.splitlines(),
                                 ["  tree/a.txt", "  other/a.txt", output + ": 2 file(s) as " + variant])
                self.assertEqual(result.stderr, "")
                self.assertEqual(ar_members((self.root / output).read_bytes()),
                                 [("a.txt", b"alpha\n"), ("a.txt", b"other\n")])
                listing = self.run_xfu("l", output).stdout.splitlines()
                self.assertEqual(listing[-1], "2 member(s)")

    def test_suffix_writers_walk_folders(self):
        listed = self.make_tree()
        for suffix, kind in SUFFIX_WRITERS:
            with self.subTest(suffix=suffix):
                output = "walked" + suffix
                # A file named again, or found again in a named folder, is
                # written once.
                result = self.run_xfu("a", output, "tree", "alpha.txt", "tree/a.txt", "./alpha.txt",
                                      *SUFFIX_ARGUMENTS.get(suffix, ()))
                self.assertEqual(result.stdout.splitlines(),
                                 ["  " + displayed_source_path(name) for name in listed] +
                                 ["  alpha.txt", output + ": 4 file(s) and 4 folder(s) as " + kind])
                self.assertEqual(result.stderr, "")
                destination = self.root / ("walked-" + suffix[1:])
                self.run_xfu("t", output)
                self.run_xfu("x", output, "-o" + str(destination))
                for name in listed + ["alpha.txt"]:
                    path = destination / name
                    if name.endswith("/"):
                        self.assertTrue(path.is_dir(), name)
                    else:
                        self.assertEqual(path.read_bytes(), (self.root / name).read_bytes())
                if kind in ("tar", "tar.gz", "tar.bz2", "tar.xz"):
                    with tarfile.open(self.root / output, "r:*") as archive:
                        self.assertEqual([member.name + ("/" if member.isdir() else "")
                                          for member in archive], listed + ["alpha.txt"])
                elif kind == "zip":
                    with zipfile.ZipFile(self.root / output) as archive:
                        self.assertEqual(archive.namelist(), listed + ["alpha.txt"])
                        self.assertIsNone(archive.testzip())

    def test_suffix_writers_keep_the_destination_on_failure(self):
        self.make_tree()
        (self.root / ("n" * 101)).write_bytes(b"too long for the ustar name field\n")
        missing = "missing.txt: cannot read the input: " + os.strerror(2)
        cases = [(suffix, ("alpha.txt", "missing.txt") + SUFFIX_ARGUMENTS.get(suffix, ()),
                  missing, 2) for suffix, _ in SUFFIX_WRITERS]
        cases += [(suffix, ("tree",), "tree: %s stream holds one file, not a folder; use .tar.%s"
                   % (stream, kind), 2) for suffix, stream, kind in (
                       (".gz", "a gzip", "gz"), (".bz2", "a bzip2", "bz2"), (".xz", "an xz", "xz"))]
        cases += [(".gz", ("missing.txt",), missing, 2),
                  (".tar", ("alpha.txt", "n" * 101), "n" * 101 + ": the name does not fit the "
                   "ustar header of tar (100 bytes, or 256 split at a '/' into 155 and 100); "
                   "--format=pax stores it", 2)]
        for suffix, inputs, message, code in cases:
            with self.subTest(suffix=suffix, inputs=inputs):
                output = self.root / ("kept" + suffix)
                output.write_bytes(b"existing archive")
                result = self.run_xfu("a", output.name, *inputs, success=False)
                self.assertEqual(result.returncode, code)
                self.assertEqual(result.stderr.splitlines(), [message])
                self.assertEqual(result.stdout, "")
                self.assertEqual(output.read_bytes(), b"existing archive")
                self.assertEqual(stage_files(self.root), [])
        # A new destination is not created by a failed run.
        result = self.run_xfu("a", "new.zip", "tree", "missing.txt", success=False)
        self.assertFalse((self.root / "new.zip").exists())

    def test_suffix_writers_refuse_one_name_for_different_files(self):
        self.make_tree()
        (self.root / "other").mkdir()
        (self.root / "other" / "a.txt").write_bytes(b"other\n")
        for suffix, _ in SUFFIX_WRITERS:
            with self.subTest(suffix=suffix):
                result = self.run_xfu("a", "clash" + suffix, self.root / "tree" / "a.txt",
                                      self.root / "other" / "a.txt",
                                      *SUFFIX_ARGUMENTS.get(suffix, ()), success=False)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr.splitlines(), ["duplicate archive member name: a.txt"])
                self.assertFalse((self.root / ("clash" + suffix)).exists())

    def test_a_refusal_is_one_line(self):
        if os.name == "nt":
            self.skipTest("':' cannot be part of a Windows file name")
        (self.root / "co").mkdir()
        (self.root / "co" / "a:b.txt").write_bytes(b"x")
        for variant, article in (("iso9660", "an"), ("xar", "an"), ("cpio_odc", "a"),
                                 ("cpio_bin", "a"), ("mtree", "an")):
            with self.subTest(format=variant):
                result = self.run_xfu("a", "co.bin", "co", "--format=" + variant, success=False)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr.splitlines(),
                                 ["co/a:b.txt: the name contains ':', which %s %s archive cannot "
                                  "store" % (article, variant)])
                self.assertFalse((self.root / "co.bin").exists())
        # The reason is given, and the ar variants are "ar".
        (self.root / "ctl\x01.txt").write_bytes(b"x")
        for variant, label in (("iso9660", "an iso9660"), ("xar", "an xar"), ("ar", "an ar"),
                               ("ar_bsd", "an ar"), ("ar_svr4", "an ar")):
            with self.subTest(control=variant):
                result = self.run_xfu("a", "co.bin", "ctl\x01.txt", "--format=" + variant,
                                      success=False)
                # The console shows the control character escaped.
                self.assertEqual(result.stderr.splitlines(),
                                 ["ctl\\x01.txt: the name contains a control character, which %s "
                                  "archive cannot store" % label])
        (self.root / ("v" * 101)).write_bytes(b"x")
        (self.root / ("i" * 176)).write_bytes(b"x")
        for variant, name, message in (
                ("v7tar", "v" * 101, ": the name does not fit a v7tar header (100 bytes); "
                 "--format=pax stores it"),
                ("iso9660", "i" * 176,
                 ": a name component is longer than 175 bytes, which iso9660 cannot store")):
            with self.subTest(format=variant):
                result = self.run_xfu("a", "long.bin", name, "--format=" + variant, success=False)
                self.assertEqual(result.stderr.splitlines(), [name + message])
                self.assertFalse((self.root / "long.bin").exists())

    @unittest.skipIf(os.name == "nt", "the source tree exceeds MAX_PATH")
    def test_xar_depth_limit_matches_the_reader(self):
        # xxfclib reads XAR member paths of at most 252 components.
        for top, depth in (("fits", 251), ("deep", 252)):
            folder = self.root.joinpath(top, *["x"] * (depth - 1))
            folder.mkdir(parents=True)
            (folder / "f").write_bytes(b"leaf\n")
        result = self.run_xfu("a", "fits.xar", "fits", "--format=xar")
        self.assertTrue(result.stdout.endswith("fits.xar: 1 file(s) and 251 folder(s) as xar\n"))
        self.run_xfu("t", "fits.xar")
        destination = self.root / "fits-output"
        self.run_xfu("x", "fits.xar", "-o" + str(destination))
        self.assertEqual(destination.joinpath("fits", *["x"] * 250, "f").read_bytes(), b"leaf\n")
        result = self.run_xfu("a", "deep.xar", "deep", "--format=xar", success=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.splitlines(),
                         ["deep/" + "x/" * 251 + "f: the name has more than 252 components, "
                          "which xar cannot store"])
        self.assertFalse((self.root / "deep.xar").exists())
        self.run_xfu("a", "deep.tar", "deep", "--format=pax")

    def test_parent_and_current_folder_inputs_have_no_dot_dot_member(self):
        self.make_tree()
        for variant, inputs in (("pax", ("tree/sub/..",)), ("zip", ("tree/sub/..",)),
                                ("ustar", (".",))):
            with self.subTest(format=variant, inputs=inputs):
                output = "dots-" + variant + ".bin"
                self.run_xfu("a", output, *inputs, "--format=" + variant)
                listing = self.run_xfu("l", output).stdout.splitlines()[1:-1]
                names = [line.split(None, 1)[1] for line in listing]
                self.assertIn("sub/b.txt" if inputs[0] != "." else "tree/sub/b.txt", names)
                self.assertFalse([name for name in names if ".." in name.split("/")], names)

    def test_links_inside_folders_are_refused(self):
        self.make_tree()
        try:
            (self.root / "tree" / "link").symlink_to("a.txt")
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links are unavailable for this account")
        result = self.run_xfu("a", "linked.tar", "tree", "--format=pax", success=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("links and special files cannot be added", result.stderr)
        self.assertFalse((self.root / "linked.tar").exists())

    def symlink_or_skip(self, link, target, folder=False):
        try:
            link.symlink_to(target, target_is_directory=folder)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links are unavailable for this account")

    def test_named_links_are_followed(self):
        listed = self.make_tree()
        self.symlink_or_skip(self.root / "link.txt", "alpha.txt")
        # A link named as an input is stored as the file it names, as the
        # suffix writers did before they walked folders.
        writers = [(suffix, SUFFIX_ARGUMENTS.get(suffix, ())) for suffix, _ in SUFFIX_WRITERS]
        writers += [(".bin", ("--format=" + variant,)) for variant in (
            "pax", "ustar", "gnutar", "v7tar", "zip", "7zip", "newc", "cpio_odc", "cpio_bin",
            "ar", "shar", "warc", "xar", "iso9660")]
        writers += [(".gz", ()), (".xz", ()), (".raw", ("--format=raw", "--filter=gzip"))]
        for index, (suffix, arguments) in enumerate(writers):
            with self.subTest(suffix=suffix, arguments=arguments):
                output = "followed%d%s" % (index, suffix)
                result = self.run_xfu("a", output, "link.txt", *arguments)
                self.assertEqual(result.stdout.splitlines()[0], "  link.txt")
                if suffix in (".gz", ".raw"):
                    self.assertEqual(gzip.decompress((self.root / output).read_bytes()), self.payload)
                    continue
                if arguments == ("--format=shar",):  # A shell script: binary data uuencoded.
                    self.assertIn(b"uudecode -o 'link.txt'", (self.root / output).read_bytes())
                if suffix == ".xz":
                    self.assertEqual(lzma.decompress((self.root / output).read_bytes()), self.payload)
                    continue
                destination = self.root / ("followed%d" % index)
                self.run_xfu("x", output, "-o" + str(destination))
                self.assertEqual((destination / "link.txt").read_bytes(), self.payload)
        with tarfile.open(self.root / "followed0.tar") as archive:
            self.assertTrue(archive.getmember("link.txt").isfile())
        # A link to a folder is walked as the folder; links in it are refused.
        self.symlink_or_skip(self.root / "treelink", "tree", folder=True)
        for suffix, arguments in ((".tar", ()), (".zip", ()), (".bin", ("--format=pax",))):
            with self.subTest(folder=suffix):
                result = self.run_xfu("a", "treelink" + suffix, "treelink", *arguments)
                self.assertEqual(result.stdout.splitlines()[:-1],
                                 ["  " + displayed_source_path("treelink" + name[4:])
                                  for name in listed])
        (self.root / "tree" / "inner").symlink_to("a.txt")
        for suffix, _ in SUFFIX_WRITERS:
            with self.subTest(inner=suffix):
                result = self.run_xfu("a", "inner" + suffix, "treelink",
                                      *SUFFIX_ARGUMENTS.get(suffix, ()), success=False)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr.splitlines(),
                                 [str(pathlib.PurePath("treelink", "inner")) +
                                  ": links and special files cannot be added"])
                self.assertFalse((self.root / ("inner" + suffix)).exists())

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_a_replaced_archive_keeps_its_permissions(self):
        writers = [(suffix, SUFFIX_ARGUMENTS.get(suffix, ())) for suffix, _ in SUFFIX_WRITERS]
        writers += [(".gz", ()), (".pax", ()), (".iso", ()), (".bin", ("--format=zip",)),
                    (".bin", ("--format=ar",))]
        # A write-protected archive is refused, as open(O_TRUNC), GNU tar and
        # zip refuse it, unless this account may write it anyway.
        protected = os.geteuid() != 0
        for suffix, arguments in writers:
            for mode in (0o600, 0o640, 0o444):
                with self.subTest(suffix=suffix, arguments=arguments, mode=oct(mode)):
                    output = self.root / ("private" + suffix)
                    output.write_bytes(b"existing archive")
                    os.chmod(output, mode)
                    refused = protected and mode == 0o444
                    result = self.run_xfu("a", output.name, "alpha.txt", *arguments,
                                          success=not refused)
                    self.assertEqual(stat.S_IMODE(os.stat(output).st_mode), mode)
                    if refused:
                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(result.stderr.splitlines(),
                                         [output.name + ": cannot create the archive: " +
                                          os.strerror(13)])
                        self.assertEqual(output.read_bytes(), b"existing archive")
                    else:
                        self.assertNotEqual(output.read_bytes(), b"existing archive")
                    os.chmod(output, 0o644)
                    output.unlink()
        self.assertEqual(stage_files(self.root), [])
        # A new archive is created as any new file is.
        umask = os.umask(0)
        os.umask(umask)
        self.run_xfu("a", "fresh.zip", "alpha.txt")
        self.assertEqual(stat.S_IMODE(os.stat(self.root / "fresh.zip").st_mode), 0o666 & ~umask)

    @unittest.skipIf(os.name == "nt", "Windows refuses a link destination")
    def test_a_link_destination_is_followed(self):
        real = self.root / "real.tar"
        real.write_bytes(b"existing archive")
        os.chmod(real, 0o640)
        self.symlink_or_skip(self.root / "link.tar", "real.tar")
        self.run_xfu("a", "link.tar", "alpha.txt")
        self.assertTrue((self.root / "link.tar").is_symlink())
        self.assertEqual(stat.S_IMODE(os.stat(real).st_mode), 0o640)
        with tarfile.open(real) as archive:
            self.assertEqual(archive.extractfile("alpha.txt").read(), self.payload)
        # A relative link beside the link, a dangling one (its file is
        # created), and a chain ending in an absolute path.
        (self.root / "sub").mkdir()
        (self.root / "sub" / "link.pax").symlink_to("../made/real.pax")
        (self.root / "sub" / "link.zip").symlink_to("../chain.zip")
        (self.root / "chain.zip").symlink_to(self.root / "real.zip")
        self.run_xfu("a", "sub/link.pax", "alpha.txt")
        self.run_xfu("a", "sub/link.zip", "alpha.txt")
        self.assertTrue((self.root / "sub" / "link.pax").is_symlink())
        self.assertTrue((self.root / "chain.zip").is_symlink())
        with tarfile.open(self.root / "made" / "real.pax") as archive:
            self.assertEqual(archive.getnames(), ["alpha.txt"])
        with zipfile.ZipFile(self.root / "real.zip") as archive:
            self.assertEqual(archive.read("alpha.txt"), self.payload)
        # The archive is never its own input, through the link either.
        result = self.run_xfu("a", "link.tar", "real.tar", success=False)
        self.assertEqual(result.returncode, 2)
        (self.root / "loop1.zip").symlink_to("loop2.zip")
        (self.root / "loop2.zip").symlink_to("loop1.zip")
        result = self.run_xfu("a", "loop1.zip", "alpha.txt", success=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.splitlines(),
                         ["loop1.zip: cannot follow the symbolic link to the archive"])
        # A destination below a linked folder, and new folders below it.
        (self.root / "folder").mkdir()
        (self.root / "folderlink").symlink_to(self.root / "folder", target_is_directory=True)
        for name in ("folderlink/out.zip", "folderlink/out.tar", "folderlink/new/out.pax"):
            with self.subTest(destination=name):
                self.run_xfu("a", name, "alpha.txt")
                self.assertTrue((self.root / "folder" / name[len("folderlink/"):]).is_file())
        for folder in (self.root, self.root / "sub", self.root / "made", self.root / "folder"):
            self.assertEqual(stage_files(folder), [])

    def test_long_destination_names(self):
        name = "L" * 240
        if os.name == "nt" and len(str(self.root / name)) > 240:
            self.skipTest("The path would pass MAX_PATH")
        try:
            (self.root / (name + ".probe")).write_bytes(b"")
        except OSError:
            self.skipTest("The file system refuses 244-byte names")
        for suffix, arguments in ((".tar", ()), (".zip", ()), (".7z", ()), (".tgz", ()),
                                  (".gz", ()), (".pax", ()), (".bin", ("--format=ar",)),
                                  (".001", ())):
            with self.subTest(suffix=suffix):
                output = name + suffix
                self.run_xfu("a", output, "alpha.txt", *arguments)
                if suffix != ".001":  # A split series is never replaced.
                    self.run_xfu("a", output, "alpha.txt", *arguments)
                self.run_xfu("t", output)
                if suffix == ".001":
                    self.run_xfu("x", output, "-osplit-output")
                    self.assertEqual((self.root / "split-output" / name).read_bytes(), self.payload)
        self.assertEqual(stage_files(self.root), [])

    def test_stage_files_are_not_members(self):
        folder = self.root / "staged"
        folder.mkdir()
        (folder / "kept.txt").write_bytes(b"kept\n")
        stages = [".xfu-0123abcd-0.tmp", ".xfu-89b3a57a-127.tmp",
                  "out.tar.xz.xfu-native-0x7ffd5c3b1a20-1791734179-0.tmp",
                  "out.zip.xfu-native-000000000062FE10-1791734179-3.tmp"]
        lookalikes = [".xfu-0123abc-0.tmp", ".xfu-0123abcd-0.tmp.txt", ".xfu-0123ABCD-0.tmp",
                      ".xfu-0123abcd-1000.tmp", "a.xfu-0123abcd-0.tmp", ".xfu-native-0x1-2-3.tmp",
                      "x.xfu-native--1-0.tmp", "x.xfu-native-0x1-2-3.tmp.bak"]
        if os.name == "nt":
            # It is the same file as the lowercase stage name on a
            # case-insensitive file system.
            lookalikes.remove(".xfu-0123ABCD-0.tmp")
        for leaf in stages + lookalikes:
            (folder / leaf).write_bytes(b"partial archive\n")
        expected = sorted(displayed_source_path(name) for name in
                          ["staged/"] + ["staged/" + leaf for leaf in ["kept.txt"] + lookalikes])
        writers = [(suffix, SUFFIX_ARGUMENTS.get(suffix, ())) for suffix, _ in SUFFIX_WRITERS]
        writers += [(".pax", ()), (".bin", ("--format=xar",))]
        for suffix, arguments in writers:
            with self.subTest(suffix=suffix, arguments=arguments):
                result = self.run_xfu("a", "staged" + suffix, "staged", *arguments)
                self.assertEqual(sorted(line[2:] for line in result.stdout.splitlines()
                                        if line.startswith("  ")), expected)
        # A stage named as an input is stored.
        result = self.run_xfu("a", "named.tar", "staged/" + stages[0])
        self.assertEqual(result.stdout.splitlines()[0], "  staged/" + stages[0])

    @unittest.skipIf(os.name == "nt", "Windows cannot create these names")
    def test_names_xxfclib_refuses_are_refused_with_a_reason(self):
        pax = "; --format=pax stores it"
        cases = (("COM1", ".tar", "tar", 'has the Windows device name "COM1"', pax),
                 ("aux.txt", ".tgz", "tar.gz", 'has the Windows device name "aux"', pax),
                 ("q?x", ".tar.xz", "tar.xz", "contains '?'", pax),
                 ("ctl\x01x", ".tar", "tar", "contains a control character", pax),
                 ("trail.", ".cpio", "cpio", "has a component ending in '.'", ""),
                 ("nul ", ".cpio", "cpio", "has a component ending in a space", ""),
                 ("a:b.txt", ".cpio", "cpio", "contains ':'", ""),
                 ("a:b.txt", ".7z", "7z", "contains ':'", ""),
                 ("a:b.txt", ".wim", "wim", "contains ':'", ""),
                 # Off Windows a backslash is part of a name, which 7z would take
                 # for a separator.
                 ("end\\", ".7z", "7z", "ends in '\\' as a folder's does" if os.name == "nt"
                  else "contains '\\'", ""),
                 ("COM1", "-7zip.bin", "7zip", None, ""),
                 ("a:b.txt", "-7zip.bin", "7zip", "contains ':'", ""),
                 ("COM1", "-newc.bin", "newc", 'has the Windows device name "COM1"', ""))
        for leaf, suffix, kind, problem, hint in cases:
            with self.subTest(name=leaf, suffix=suffix):
                folder = self.root / "cc"
                if folder.exists():
                    for path in folder.iterdir():
                        path.unlink()
                    folder.rmdir()
                folder.mkdir()
                (folder / "ok.txt").write_bytes(b"ok\n")
                (folder / leaf).write_bytes(b"x\n")
                arguments = SUFFIX_ARGUMENTS.get(suffix, ())
                if suffix.endswith(".bin"):
                    arguments = ("--format=" + kind,)
                output = self.root / ("names" + suffix)
                output.write_bytes(b"existing archive")
                result = self.run_xfu("a", output.name, "cc", *arguments, success=problem is None)
                if problem is None:  # 7-Zip stores device names.
                    continue
                self.assertEqual(result.returncode, 2)
                shown = leaf.replace("\x01", "\\x01")
                self.assertEqual(result.stderr.splitlines(),
                                 ["cc/%s: the name %s, which %s cannot store%s"
                                  % (shown, problem, kind, hint)])
                self.assertEqual(result.stdout, "")
                self.assertEqual(output.read_bytes(), b"existing archive")
                self.assertEqual(stage_files(self.root), [])
        # What ZIP and the native PAX writer store.
        (self.root / "cc" / "COM1").write_bytes(b"device\n")
        (self.root / "cc" / "a:b.txt").write_bytes(b"colon\n")
        for output in ("names.zip", "names.pax"):
            result = self.run_xfu("a", output, "cc")
            self.assertIn("  cc/COM1", result.stdout.splitlines())
            self.assertIn("  cc/a:b.txt", result.stdout.splitlines())

    def test_ustar_names_of_256_bytes(self):
        name = "p" * 155 + "/" + "n" * 100
        if os.name == "nt" and len(str(self.root / name)) > 240:
            self.skipTest("The path would pass MAX_PATH")
        try:
            (self.root / name).parent.mkdir()
            (self.root / name).write_bytes(self.payload)
        except OSError:
            self.skipTest("The file system refuses these names")
        for output, arguments in (("u256.tar", ()), ("u256.tgz", ()), ("u256-ustar.bin", ("--format=ustar",)),
                                  ("u256-paxr.bin", ("--format=pax_restricted",))):
            with self.subTest(output=output):
                self.run_xfu("a", output, name, *arguments)
                with tarfile.open(self.root / output) as archive:
                    member = archive.getmembers()[0]
                    self.assertEqual(member.name, name)
                    self.assertEqual(member.pax_headers, {})
                    self.assertEqual(archive.extractfile(member).read(), self.payload)
                self.run_xfu("t", output)

    @unittest.skipUnless(sys.platform.startswith("linux"), "sparse files and RLIMIT_FSIZE")
    def test_files_too_large_for_the_header_are_refused_first(self):
        import resource
        probe = self.root / "probe.bin"
        with open(probe, "wb") as handle:
            handle.truncate(1 << 24)
        sparse = os.stat(probe).st_blocks * 512 < (1 << 20)
        probe.unlink()
        if not sparse:
            self.skipTest("The file system has no sparse files")

        def limited():
            # Should the check fail, the writer stops at 64 MiB.
            resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 26, 1 << 26))

        for size, output, arguments, text, kind in (
                (8 << 30, "big.tar", (), "8 GiB", "tar"),
                (4 << 30, "big.cpio", (), "4 GiB", "cpio"),
                (4 << 30, "big.bin", ("--format=newc",), "4 GiB", "newc"),
                # The native TAR and CPIO formats name the limit too.
                (8 << 30, "big.pax", (), "8 GiB", "the pax writer"),
                (8 << 30, "big.bin", ("--format=gnutar",), "8 GiB", "the gnutar writer"),
                (8 << 30, "big.bin", ("--format=ustar",), "8 GiB", "the ustar writer"),
                (8 << 30, "big.bin", ("--format=cpio_odc",), "8 GiB", "cpio_odc"),
                (4 << 30, "big.bin", ("--format=cpio_bin",), "4 GiB", "cpio_bin")):
            with self.subTest(output=output, arguments=arguments):
                big = self.root / "big.dat"
                with open(big, "wb") as handle:
                    handle.truncate(size)
                try:
                    completed = subprocess.run([str(EXECUTABLE), "a", output, "big.dat", *arguments],
                                               cwd=self.root, capture_output=True, text=True,
                                               timeout=60, preexec_fn=limited)
                finally:
                    big.unlink()
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertEqual(completed.stderr.splitlines(),
                                 ["big.dat: the file is %s or larger, which %s cannot store"
                                  % (text, kind)])
                self.assertFalse((self.root / output).exists())
                self.assertEqual(stage_files(self.root), [])

    def test_the_replaced_archive_is_not_its_own_member(self):
        self.make_tree()
        self.run_xfu("a", "tree/self.tar", "tree", "--format=pax")
        self.run_xfu("a", "tree/self.tar", "tree", "--format=pax")
        with tarfile.open(self.root / "tree" / "self.tar") as archive:
            self.assertNotIn("tree/self.tar", archive.getnames())

    @unittest.skipIf(os.name == "nt", "POSIX file names are bytes")
    def test_names_that_are_not_utf8(self):
        name = "caf\udce9.txt"  # b"caf\xe9.txt"
        try:
            (self.root / name).write_bytes(self.payload)
        except (OSError, UnicodeEncodeError):
            self.skipTest("The file system refuses names that are not UTF-8")
        for variant in ("zip", "7zip", "xar", "warc", "mtree"):
            with self.subTest(refused=variant):
                result = self.run_xfu("a", "bytes.bin", name, "--format=" + variant, success=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("is not valid UTF-8", result.stderr)
                self.assertFalse((self.root / "bytes.bin").exists())
        for variant in ("pax", "pax_restricted"):
            with self.subTest(stored=variant):
                output = "bytes-" + variant + ".tar"
                self.run_xfu("a", output, name, "--format=" + variant)
                with tarfile.open(self.root / output, encoding="utf-8",
                                  errors="surrogateescape") as archive:
                    member = archive.getmembers()[0]
                    self.assertEqual(member.name, name)
                    self.assertEqual(member.pax_headers.get("hdrcharset"), "BINARY")
        for variant in ("ustar", "gnutar", "newc", "cpio_odc", "ar", "iso9660"):
            with self.subTest(stored=variant):
                output = "bytes-" + variant + ".bin"
                destination = self.root / ("bytes-" + variant)
                self.run_xfu("a", output, name, "--format=" + variant)
                self.run_xfu("x", output, "-o" + str(destination))
                payloads = [path.read_bytes() for path in destination.rglob("*") if path.is_file()]
                self.assertEqual(payloads, [self.payload])
        # A raw stream stores no name at all.
        self.run_xfu("a", "bytes.xz", name, "--format=raw", "--filter=xz")
        self.assertEqual(lzma.decompress((self.root / "bytes.xz").read_bytes()), self.payload)
        # The suffix writers: xxfclib's TAR, ZIP and 7z writers store UTF-8
        # names only (ZIP marks every name UTF-8); CPIO keeps the bytes.
        for suffix in (".zip", ".tar", ".tar.gz", ".tar.xz", ".7z"):
            with self.subTest(suffix_refused=suffix):
                output = self.root / ("bytes-suffix" + suffix)
                output.write_bytes(b"existing archive")
                result = self.run_xfu("a", output.name, name, success=False)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(len(result.stderr.splitlines()), 1)
                self.assertIn("is not valid UTF-8, which " + suffix[1:] + " cannot store",
                              result.stderr)
                self.assertEqual(output.read_bytes(), b"existing archive")
        self.run_xfu("a", "bytes-suffix.cpio", name)
        destination = self.root / "bytes-suffix-cpio"
        self.run_xfu("x", "bytes-suffix.cpio", "-o" + str(destination))
        self.assertEqual((destination / name).read_bytes(), self.payload)
        self.run_xfu("a", "bytes-suffix.gz", name)
        self.assertEqual(gzip.decompress((self.root / "bytes-suffix.gz").read_bytes()), self.payload)

    def test_long_destination_paths_are_logged_whole(self):
        folder = pathlib.Path(*["d" * 200] * 11)
        try:
            (self.root / folder).mkdir(parents=True)
        except OSError:
            self.skipTest("Long paths are unavailable on this file system")
        for suffix, arguments in ((".pax", ("--format=pax",)), (".ar", ("--format=ar",)),
                                  (".tar", ()), (".zip", ()), (".gz", ()),
                                  (".001", ()), (".pea", ()), (".arc", ())):
            with self.subTest(suffix=suffix):
                archive = str(folder / ("out" + suffix))
                result = self.run_xfu("a", archive, "missing.txt", *arguments, success=False)
                lines = (result.stdout + result.stderr).splitlines()
                self.assertTrue(lines)
                for line in lines:
                    if "d" * 300 in line:
                        self.assertTrue(line.startswith(archive + ":"), line[-80:])
        result = self.run_xfu("a", "out.ar", str(folder / "x.txt"), "--format=ar", success=False)
        self.assertIn(str(folder / "x.txt") + ":", result.stderr)

    def test_small_iso_images_are_padded_for_other_readers(self):
        self.run_xfu("a", "small.iso", "alpha.txt")
        image = (self.root / "small.iso").read_bytes()
        self.assertGreaterEqual(len(image), 64 * 1024)
        self.assertEqual(struct.unpack("<I", image[16 * 2048 + 80:16 * 2048 + 84])[0] * 2048,
                         len(image))
        destination = self.root / "small-output"
        self.run_xfu("x", "small.iso", "-o" + str(destination))
        self.assertEqual((destination / "alpha.txt").read_bytes(), self.payload)

    def test_invalid_writer_preserves_destination(self):
        output = self.root / "keep.bin"
        for arguments in (("--format=unknown",), ("--format=zip", "--compression=bad"),
                          ("--format=pax", "--filter=unknown"),
                          ("--format=pax", "--options=unknown=1")):
            with self.subTest(arguments=arguments):
                output.write_bytes(b"existing archive")
                self.run_xfu("a", output.name, "alpha.txt", *arguments,
                             success=False)
                self.assertEqual(output.read_bytes(), b"existing archive")

    @unittest.skipIf(os.name == "nt", "':' cannot be part of a Windows file name")
    def test_a_leading_letter_and_colon_is_a_name_off_windows(self):
        (self.root / "9:00-meeting.txt").write_bytes(b"notes\n")
        (self.root / "a:").write_bytes(b"z")
        (self.root / "a:b.txt").write_bytes(b"x")
        (self.root / "b.txt").write_bytes(b"y")
        (self.root / "d:").mkdir()
        (self.root / "d:" / "in.txt").write_bytes(b"w\n")
        self.run_xfu("a", "m.zip", "9:00-meeting.txt", "a:", "d:")
        with zipfile.ZipFile(self.root / "m.zip") as archive:
            self.assertEqual(archive.namelist(), ["9:00-meeting.txt", "a:", "d:/", "d:/in.txt"])
            self.assertEqual(archive.read("a:"), b"z")
        result = self.run_xfu("a", "o.pax", "a:b.txt", "b.txt")
        self.assertEqual(result.stdout.splitlines()[-1], "o.pax: 2 file(s) as pax")
        with tarfile.open(self.root / "o.pax") as archive:
            self.assertEqual(archive.getnames(), ["a:b.txt", "b.txt"])
        # Writers that cannot store ':' refuse it, as later in a path.
        for output in ("o.tar", "o.7z", "o.cpio"):
            with self.subTest(output=output):
                result = self.run_xfu("a", output, "a:b.txt", "b.txt", success=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("a:b.txt: the name contains ':'", result.stderr)
                self.assertFalse((self.root / output).exists())

    def test_an_impossible_destination_is_refused_before_anything_is_written(self):
        (self.root / "folder.tar").mkdir()
        (self.root / "file").write_bytes(b"a file\n")
        long_name = "n" * 300
        cases = [(name, os.strerror(errno.EISDIR)) for name in ("folder.tar",)]
        cases += [(long_name + suffix, os.strerror(errno.ENAMETOOLONG))
                  for suffix in (".tar.gz", ".zip", ".pax", ".txt.xz")]
        cases += [("missing/" + long_name + ".tar", os.strerror(errno.ENAMETOOLONG))]
        if os.name != "nt":
            cases += [("file/x.tar", os.strerror(errno.ENOTDIR))]
        for output, reason in cases:
            with self.subTest(output=output[:40]):
                result = self.run_xfu("a", output, "alpha.txt", success=False)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr.splitlines(),
                                 [output + ": cannot create the archive: " + reason])
                self.assertEqual(result.stdout, "")
                self.assertEqual(stage_files(self.root), [])
        self.assertFalse((self.root / "missing").exists())
        self.assertTrue((self.root / "folder.tar").is_dir())

    @unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "POSIX permissions, not root")
    def test_read_only_folders_devices_and_fifos(self):
        folder = self.root / "ro"
        folder.mkdir()
        for suffix, arguments in ((".tar", ()), (".tar.gz", ()), (".zip", ()), (".7z", ()),
                                  (".gz", ()), (".pax", ()), (".iso", ()),
                                  (".bin", ("--format=zip",))):
            with self.subTest(suffix=suffix, arguments=arguments):
                archive, link = folder / ("a" + suffix), folder / ("b" + suffix)
                archive.write_bytes(b"existing archive")
                os.chmod(archive, 0o640)
                os.link(archive, link)
                os.chmod(folder, 0o555)
                try:
                    # The folder takes no stage: the archive is written in place.
                    result = self.run_xfu("a", "ro/a" + suffix, "alpha.txt", *arguments)
                    self.assertEqual(result.stdout.splitlines()[-1].split(":")[0], "ro/a" + suffix)
                    result = self.run_xfu("a", "ro/new" + suffix, "alpha.txt", *arguments,
                                          success=False)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stderr.splitlines(),
                                     ["ro/new%s: cannot create a staging file in ro/: %s"
                                      % (suffix, os.strerror(errno.EACCES))])
                finally:
                    os.chmod(folder, 0o755)
                self.assertNotEqual(archive.read_bytes(), b"existing archive")
                self.assertEqual(os.stat(archive).st_ino, os.stat(link).st_ino)
                self.assertEqual(stat.S_IMODE(os.stat(archive).st_mode), 0o640)
                self.run_xfu("t", "ro/a" + suffix)
                self.assertEqual(stage_files(folder), [])
                archive.unlink()
                link.unlink()
        # A link to a device is written through; the link stays.
        (self.root / "null.tar").symlink_to(os.devnull)
        self.run_xfu("a", "null.tar", "alpha.txt")
        self.assertTrue((self.root / "null.tar").is_symlink())
        # A FIFO is written as it is, and its reader gets the archive.
        import threading
        fifo, received = self.root / "pipe.zip", []
        os.mkfifo(fifo)
        reader = threading.Thread(target=lambda: received.append(fifo.read_bytes()))
        reader.start()
        try:
            self.run_xfu("a", "pipe.zip", "alpha.txt")
        finally:
            reader.join(30)
        self.assertTrue(stat.S_ISFIFO(os.stat(fifo).st_mode))
        with zipfile.ZipFile(io.BytesIO(received[0])) as archive:
            self.assertEqual(archive.read("alpha.txt"), self.payload)
        self.assertEqual(stage_files(self.root), [])

    @unittest.skipIf(os.name == "nt", "RLIMIT_FSIZE")
    def test_a_failed_write_keeps_the_previous_archive(self):
        import resource
        import signal
        (self.root / "big.bin").write_bytes(os.urandom(3_000_000))

        def limited(limit):
            def setup():
                signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
                resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
            return setup

        writers = [(suffix, SUFFIX_ARGUMENTS.get(suffix, ())) for suffix, _ in SUFFIX_WRITERS]
        writers += [(".pax", ()), (".iso", ()), (".ar", ()), (".txt.zst", ()), (".tar.Z", ()),
                    (".txt.gz", ()), (".txt.bz2", ()), (".txt.xz", ()),
                    (".bin", ("--format=zip",)), (".bin", ("--format=7zip",)),
                    (".bin", ("--format=ustar", "--filter=lz4"))]
        streams = (".txt.zst", ".txt.gz", ".txt.bz2", ".txt.xz")
        for suffix, arguments in writers:
            inputs = ("big.bin",) if suffix in streams else ("big.bin", "alpha.txt")
            full = self.root / ("full" + suffix)
            self.run_xfu("a", full.name, *inputs, *arguments)
            size = full.stat().st_size
            full.unlink()
            for limit in (1_000_000, size - 1):
                with self.subTest(suffix=suffix, arguments=arguments, limit=limit):
                    output = self.root / ("kept" + suffix)
                    if not output.exists():
                        self.run_xfu("a", output.name, "alpha.txt", *arguments)
                    previous = output.read_bytes()
                    completed = subprocess.run(
                        [str(EXECUTABLE), "a", output.name, *inputs, *arguments],
                        cwd=self.root, capture_output=True, text=True, timeout=120,
                        preexec_fn=limited(limit))
                    self.assertNotEqual(completed.returncode, 0, completed.stdout)
                    self.assertIn("the archive could not be written: " + os.strerror(errno.EFBIG),
                                  completed.stderr)
                    self.assertEqual(output.read_bytes(), previous)
                    self.assertEqual(stage_files(self.root), [])

    def test_permissions_and_times_are_stored(self):
        script = self.root / "run.sh"
        script.write_bytes(b"#!/bin/sh\necho hi\n")
        stamp = 1588665600  # 2020-05-05 08:00 UTC
        os.utime(script, (stamp, stamp))
        if os.name != "nt":
            os.chmod(script, 0o755)
        # Windows has no POSIX permission bits; the writer deliberately uses
        # the portable regular-file default in formats that require a mode.
        mode = 0o644 if os.name == "nt" else stat.S_IMODE(os.stat(script).st_mode)
        info = os.stat(script)
        owner = (info.st_uid, info.st_gid) if os.name != "nt" else (0, 0)
        for output in ("run.tar", "run.tgz", "run-pax.tar"):
            arguments = ("--format=pax",) if output == "run-pax.tar" else ()
            self.run_xfu("a", output, "run.sh", *arguments)
            with tarfile.open(self.root / output) as archive:
                member = archive.getmember("run.sh")
                self.assertEqual((member.mode, member.mtime), (mode, stamp), output)
                # The suffix writers store the owner too, as the native one does.
                self.assertEqual((member.uid, member.gid), owner, output)
        self.run_xfu("a", "run.cpio", "run.sh")
        header = (self.root / "run.cpio").read_bytes()[:110]
        self.assertEqual((int(header[14:22], 16), int(header[46:54], 16)),
                         (0o100000 | mode, stamp))
        local = time.localtime(stamp)
        for output, arguments in (("run.zip", ()), ("run-native.zip", ("--format=zip",))):
            self.run_xfu("a", output, "run.sh", *arguments)
            with zipfile.ZipFile(self.root / output) as archive:
                info = archive.getinfo("run.sh")
                self.assertEqual(info.date_time, tuple(local[:5]) + (local.tm_sec // 2 * 2,))
                self.assertEqual(info.external_attr >> 16, 0o100000 | mode)
                # Made on Unix, so unzip applies the mode (and the UTF-8 name).
                self.assertEqual(info.create_system, 0 if os.name == "nt" else 3)
        # 7-Zip: a FILETIME, and Windows attributes with the Unix mode.
        filetime = (stamp + 11644473600) * 10 ** 7
        attributes = 0x20 | ((0x8000 | ((0o100000 | mode) << 16)) if os.name != "nt" else 0)
        for output, arguments in (("run.7z", ()), ("run-native.7z", ("--format=7zip",))):
            self.run_xfu("a", output, "run.sh", *arguments)
            listing = self.run_xfu("l", output, "--advanced").stdout
            self.assertIn("Timestamp: %d" % filetime, listing)
            self.assertIn("Raw attributes: 0x%X" % attributes, listing)

    def test_an_empty_password_means_none(self):
        for output, arguments in (("e.7z", ()), ("e.zip", ()), ("e.bin", ("--format=7zip",)),
                                  ("f.bin", ("--format=zip",)), ("e.tar", ())):
            with self.subTest(output=output, arguments=arguments):
                self.run_xfu("a", output, "alpha.txt", "-p", *arguments)
                # Tested and extracted without a password.
                self.run_xfu("t", output)
                destination = self.root / ("plain-" + output)
                self.run_xfu("x", output, "-o" + str(destination))
                self.assertEqual((destination / "alpha.txt").read_bytes(), self.payload)
        with zipfile.ZipFile(self.root / "e.zip") as archive:
            self.assertFalse(archive.getinfo("alpha.txt").flag_bits & 1)
        result = self.run_xfu("t", "e.7z", "--verbose")
        self.assertIn("alpha.txt -- OK", result.stdout)

    @unittest.skipIf(os.name == "nt", "a POSIX shell")
    def test_a_shell_archive_recreates_each_file(self):
        files = {"shin/nonl.txt": b"abc", "shin/bin.dat": b"X\x00\x01\xff\n", "shin/zero": b"",
                 "shin/deep/er/t.txt": b"line1\nline2\n", "shin/utf8.txt": "caf\u00e9\n".encode(),
                 "shin/crlf.txt": b"crlf\r\nline\r\n", "shin/delim.txt": b"SHAR_END\nX\n",
                 "shin/latin1.txt": b"bad\xe9\n", "-dash.txt": b"dash\n",
                 # Shell characters in names: each name is one quoted word.
                 "shin/photo (1).txt": b"paren\n", "shin/[br]{c} #~!x=y%.dat": b"\x00odd",
                 "shin/sp ace.txt": b"space\n"}
        for name, data in files.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(data)
        os.chmod(self.root / "shin/deep/er/t.txt", 0o750)
        # uudecode is not installed everywhere: a small one stands in.
        tools = self.root / "tools"
        tools.mkdir()
        (tools / "uudecode").write_text(
            "#!%s\nimport binascii, os, sys\n"
            "out = sys.argv[sys.argv.index('-o') + 1]\n"
            "lines = sys.stdin.buffer.read().split(b'\\n')\n"
            "begin = next(i for i, line in enumerate(lines) if line.startswith(b'begin '))\n"
            "data = b''.join(binascii.a2b_uu(line) for line in lines[begin + 1:"
            "lines.index(b'end')] if line)\n"
            "open(out, 'wb').write(data)\n"
            "os.chmod(out, int(lines[begin].split()[1], 8))\n" % sys.executable)
        os.chmod(tools / "uudecode", 0o755)
        environment = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ.get("PATH", ""))
        for variant in ("shar", "shar_dump"):
            with self.subTest(format=variant):
                output = self.root / (variant + ".sh")
                self.run_xfu("a", output.name, *[("./" if name[0] == "-" else "") + name
                                                 for name in files], "--format=" + variant)
                target = self.root / ("sh-" + variant)
                target.mkdir()
                completed = subprocess.run(["sh", str(output)], cwd=target, env=environment,
                                           capture_output=True, timeout=60)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                destination = self.root / ("x-" + variant)
                self.run_xfu("x", output.name, "-o" + str(destination))
                for name, data in files.items():
                    self.assertEqual((target / name).read_bytes(), data, name)
                    self.assertEqual((destination / name).read_bytes(), data, name)
                self.assertEqual(stat.S_IMODE(os.stat(target / "shin/deep/er/t.txt").st_mode), 0o750)
        text = (self.root / "shar.sh").read_bytes()
        self.assertIn(b"mkdir -p 'shin/deep/er'\n", text)
        self.assertIn(b"sed 's/^X//' > 'shin/utf8.txt' << 'SHAR_END'\n", text)
        self.assertIn(b"uudecode -o 'shin/bin.dat' << 'SHAR_END'\nbegin %03o shin/bin.dat\n"
                      % stat.S_IMODE(os.stat(self.root / "shin/bin.dat").st_mode), text)
        # A name that starts with '-' is no option to chmod.
        self.assertIn(b" './-dash.txt'\n", text)
        self.assertIn(b"echo x 'shin/photo (1).txt'\n", text)

    @unittest.skipIf(os.name == "nt", "/dev/stdout")
    def test_an_archive_written_to_standard_output_keeps_the_log_apart(self):
        completed = subprocess.run([str(EXECUTABLE), "a", "/dev/stdout", "alpha.txt", "--format=pax"],
                                   cwd=self.root, capture_output=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(completed.stdout) % 512, 0)
        (self.root / "piped.tar").write_bytes(completed.stdout)
        with tarfile.open(self.root / "piped.tar") as archive:
            self.assertEqual(archive.extractfile("alpha.txt").read(), self.payload)
        self.assertEqual(completed.stderr.decode().splitlines(),
                         ["  alpha.txt", "/dev/stdout: 1 file(s) as pax"])

    def test_a_walk_leaves_out_extraction_stages(self):
        folder = self.root / "walked"
        (folder / "d").mkdir(parents=True)
        (folder / "kept.txt").write_bytes(b"kept")
        stages = [".xxfclib.tmp.0", "d/.xxfclib.tmp.17", ".xxfclib.tmp." + "0123456789abcdef" * 2,
                  ".xfu-0123abcd-0.tmp"]
        kept = [".xxfclib.tmp.1x", ".xxfclib.tmp." + "0" * 31, "big.bin.xxfclib.tmp.0"]
        for name in stages + kept:
            (folder / name).write_bytes(b"partial")
        self.run_xfu("a", "walked.zip", "walked")
        with zipfile.ZipFile(self.root / "walked.zip") as archive:
            names = sorted(archive.namelist())
        self.assertEqual(names, sorted(["walked/", "walked/d/", "walked/kept.txt"] +
                                       ["walked/" + name for name in kept]))

    @unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "POSIX permissions, not root")
    def test_an_unreadable_input_names_the_reason(self):
        locked = self.root / "locked.txt"
        locked.write_bytes(b"locked")
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o644)
        for output, arguments in (("o.tar", ()), ("o.zip", ()), ("o.txt.gz", ()), ("o.iso", ()),
                                  ("o.bin", ("--format=pax",)), ("o.bin", ("--format=shar",))):
            with self.subTest(output=output, arguments=arguments):
                result = self.run_xfu("a", output, "locked.txt", *arguments, success=False)
                self.assertEqual(result.stderr.splitlines(),
                                 ["locked.txt: cannot read the input: " + os.strerror(errno.EACCES)])
                self.assertFalse((self.root / output).exists())

    def test_a_7zip_archive_lists_its_modification_time(self):
        stamp = 1588665600  # 2020-05-05 08:00:00 UTC
        os.utime(self.root / "alpha.txt", (stamp, stamp))
        expected = "    Modified: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stamp))
        for output, arguments in (("native.bin", ("--format=7zip",)), ("suffix.7z", ())):
            with self.subTest(output=output):
                self.run_xfu("a", output, "alpha.txt", *arguments)
                listing = self.run_xfu("l", output, "--advanced").stdout.splitlines()
                self.assertIn(expected, listing)

    def test_mtree_escapes_name_bytes(self):
        name = "\u00fcn #=.txt"
        try:
            (self.root / name).write_bytes(b"x")
        except (OSError, UnicodeEncodeError):
            self.skipTest("The file system refuses this name")
        self.run_xfu("a", "names.mtree", name)
        text = (self.root / "names.mtree").read_bytes()
        self.assertIn(b"./\\303\\274n\\040\\043\\075.txt type=file", text)
        self.assertTrue(all(32 < byte < 127 or byte in b"\n " for byte in text))
        self.assertIn(name, self.run_xfu("l", "names.mtree").stdout)

    def test_a_folder_given_to_a_stream_names_the_fix(self):
        (self.root / "folder").mkdir()
        for output, arguments, expected in (
                ("o.xz", (), "an xz stream holds one file, not a folder; use .tar.xz"),
                ("o.lz4", (), "an lz4 stream holds one file, not a folder; use .tar.lz4"),
                ("o.zst", (), "a zstd stream holds one file, not a folder; use .tar.zst"),
                ("o.Z", (), "a compress stream holds one file, not a folder; use .tar.Z"),
                ("o.b64", (), "a Base64 stream holds one file, not a folder; use .tar.b64"),
                ("o.bin", ("--format=raw",), "a raw stream holds one file, not a folder; use an "
                 "archive format such as --format=pax")):
            with self.subTest(output=output):
                result = self.run_xfu("a", output, "folder", *arguments, success=False)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr.splitlines(), ["folder: " + expected])


def lzw_decode(data, libarchive=False):
    """An independent compress(1) (.Z) decoder: (data, CLEAR count, widest
    code). Codes are read from the low bit up, in groups of eight that start
    after the 3-byte header and again at each width change and CLEAR, as
    ncompress and gzip read them; with libarchive, as libarchive's reader
    reads them: no padding at a width change, and the group after a CLEAR
    counted in bytes from the last reset, the header's 3 bytes included."""
    assert data[:2] == b"\x1f\x9d", data[:3]
    maxbits, block = data[2] & 0x1F, data[2] & 0x80
    assert 9 <= maxbits <= 16 and block
    total, position, bits = len(data) * 8, 24, 9
    section = 0 if libarchive else 24  # libarchive: bytes; else bits.
    table = [bytes([i]) for i in range(256)] + [b""]
    free, old, clears, widest = 257, None, 0, 9
    out = bytearray()
    while True:
        if old is not None and free > (1 << bits) - 1 and bits < maxbits:
            if not libarchive:
                group = bits * 8
                position = section + -(-(position - section) // group) * group
                section = position
            else:
                assert position % 8 == 0, "a width change libarchive would misread"
                section = position // 8
            bits += 1
            widest = max(widest, bits)
        if position + bits > total:
            break
        code = int.from_bytes(data[position // 8:position // 8 + 4].ljust(4, b"\0"), "little")
        code = (code >> (position % 8)) & ((1 << bits) - 1)
        position += bits
        if code == 256:
            clears += 1
            if libarchive:
                fetched = -(-position // 8) - section
                position = (-(-position // 8) + (bits - fetched % bits) % bits) * 8
                section = position // 8
            else:
                group = bits * 8
                position = section + -(-(position - section) // group) * group
                section = position
            bits, free, old = 9, 257, None
            del table[257:]
            continue
        if old is None:
            assert code < 256, code
            out += table[code]
            old = code
            continue
        if code < free:
            entry = table[code]
            new = table[old] + entry[:1]
        else:
            assert code == free, (code, free)
            entry = new = table[old] + table[old][:1]
        out += entry
        if free < (1 << maxbits):
            table.append(new)
            free += 1
        old = code
    return bytes(out), clears, widest


class WriterFixesTests(unittest.TestCase):
    """Writers checked against the tools that read their output: compress(1)
    streams, XAR's table checksum, times a header cannot hold, '\\' in POSIX
    names, shell archive names and the publication of a new archive."""

    setUp = NativeWriterTests.setUp
    run_xfu = NativeWriterTests.run_xfu

    def test_compress_streams_are_what_compress_writes(self):
        rng = random.Random(34)
        version = subprocess.run(["compress", "-V"], capture_output=True, text=True,
                                 timeout=60) if shutil.which("compress") else None
        ncompress = version is not None and "(N)compress" in version.stdout + version.stderr
        # Text, then noise: once the table is full of the text's strings, the
        # ratio drops and compress clears the table.
        inputs = {"text.txt": b"".join(b"%d\n" % i for i in range(70000)),
                  "noise.bin": b"".join(b"%d\n" % i for i in range(40000)) +
                  bytes(rng.getrandbits(8) for _ in range(150000)),
                  "one.txt": b"a", "empty.txt": b"", "short.txt": b"abcabcabcabc\n" * 30}
        for name, data in inputs.items():
            with self.subTest(name=name):
                (self.root / name).write_bytes(data)
                self.run_xfu("a", name + ".Z", name)
                stream = (self.root / (name + ".Z")).read_bytes()
                self.assertEqual(stream[:3], b"\x1f\x9d\x90")
                for libarchive in (False, True):
                    decoded, clears, widest = lzw_decode(stream, libarchive)
                    self.assertEqual(decoded, data, (name, libarchive))
                if name == "text.txt":  # Compressed, with every width.
                    self.assertLess(len(stream), len(data) // 2)
                    self.assertEqual(widest, 16)
                if name == "noise.bin":
                    self.assertGreaterEqual(clears, 1)
                if ncompress:  # Byte for byte, ratio checks and CLEARs included.
                    completed = subprocess.run(["compress", "-c"], input=data,
                                               capture_output=True, timeout=60)
                    self.assertEqual(completed.stdout, stream)
                out = self.root / ("x-" + name)
                self.run_xfu("x", name + ".Z", "-o" + str(out))
                self.assertEqual([path.read_bytes() for path in out.iterdir()], [data])
                for tool in (["gzip", "-dc"], ["uncompress", "-c"], ["bsdcat"]):
                    if shutil.which(tool[0]) and (data or tool[0] != "bsdcat"):
                        completed = subprocess.run(tool, input=stream, capture_output=True,
                                                   timeout=60)
                        self.assertEqual((completed.returncode, completed.stdout), (0, data),
                                         tool)
        self.run_xfu("a", "t.tar.Z", "text.txt", "noise.bin")
        if shutil.which("bsdtar"):  # libarchive, the tar of macOS and the BSDs.
            completed = subprocess.run(["bsdtar", "-tf", "t.tar.Z"], cwd=self.root,
                                       capture_output=True, text=True, timeout=60)
            self.assertEqual((completed.returncode, completed.stdout.split()),
                             (0, ["text.txt", "noise.bin"]), completed.stderr)
        decoded = lzw_decode((self.root / "t.tar.Z").read_bytes(), True)[0]
        with tarfile.open(fileobj=io.BytesIO(decoded)) as archive:
            self.assertEqual(archive.extractfile("noise.bin").read(), inputs["noise.bin"])

    def test_xar_has_the_toc_checksum_and_times_xar_needs(self):
        stamp = 1709528767  # 2024-03-04 05:06:07 UTC
        (self.root / "d").mkdir()
        (self.root / "d" / "now.txt").write_bytes(b"now\n")
        os.utime(self.root / "d" / "now.txt", (stamp, stamp))
        self.run_xfu("a", "o.xar", "d", "alpha.txt")
        data = (self.root / "o.xar").read_bytes()
        magic, size, version, packed_size, plain_size, algorithm = \
            struct.unpack(">4sHHQQI", data[:28])
        self.assertEqual((magic, size, version, algorithm), (b"xar!", 28, 1, 1))
        packed = data[28:28 + packed_size]
        toc = zlib.decompress(packed)
        self.assertEqual(len(toc), plain_size)
        heap = 28 + packed_size
        # The heap starts with the SHA-1 of the packed table of contents.
        self.assertEqual(data[heap:heap + 20], hashlib.sha1(packed).digest())
        root = xml.etree.ElementTree.fromstring(toc).find("toc")
        checksum = root.find("checksum")
        self.assertEqual((checksum.get("style"), checksum.findtext("offset"),
                          checksum.findtext("size")), ("sha1", "0", "20"))
        self.assertRegex(root.findtext("creation-time"), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")
        folder = next(item for item in root.findall("file") if item.findtext("name") == "d")
        member = folder.find("file")
        self.assertEqual(member.findtext("mtime"), "2024-03-04T05:06:07Z")
        info = os.stat(self.root / "d" / "now.txt")
        if os.name != "nt":
            self.assertEqual((member.findtext("uid"), member.findtext("gid")),
                             (str(info.st_uid), str(info.st_gid)))
        offset, length = int(member.findtext("data/offset")), int(member.findtext("data/length"))
        self.assertGreaterEqual(offset, 20)
        self.assertEqual(data[heap + offset:heap + offset + length], b"now\n")
        self.run_xfu("t", "o.xar")
        if shutil.which("xar"):  # xar(1) refuses an archive without the checksum.
            target = self.root / "by-xar"
            target.mkdir()
            completed = subprocess.run(["xar", "-xf", str(self.root / "o.xar")], cwd=target,
                                       capture_output=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((target / "d" / "now.txt").read_bytes(), b"now\n")
            self.assertEqual((target / "alpha.txt").read_bytes(), self.payload)
            self.assertEqual(int(os.stat(target / "d" / "now.txt").st_mtime), stamp)

    def stamped(self, name, stamp):
        path = self.root / name
        path.write_bytes(name.encode() + b"\n")
        try:
            os.utime(path, (stamp, stamp))
        except (OverflowError, OSError, ValueError):
            self.skipTest("the file system cannot hold this time")
        if int(os.stat(path).st_mtime) != stamp:
            self.skipTest("the file system cannot hold this time")
        return path

    def test_times_a_format_cannot_hold_are_clamped_with_one_warning(self):
        old, future, mid = -302443200, 70372022400, 981158400  # 1960, 4200, 2001
        for name, stamp in (("old.txt", old), ("fut.txt", future), ("mid.txt", mid)):
            self.stamped(name, stamp)
        names = ("old.txt", "fut.txt", "mid.txt")
        # pax stores any time; --format=tar adds a header only where needed.
        for output, arguments in (("p.tar", ("--format=pax",)), ("r.tar", ("--format=tar",))):
            result = self.run_xfu("a", output, *names, *arguments)
            self.assertEqual(result.stderr, "")
            with tarfile.open(self.root / output) as archive:
                self.assertEqual([int(member.mtime) for member in archive.getmembers()],
                                 [old, future, mid])
                if output == "r.tar":
                    self.assertEqual(archive.getmember("mid.txt").pax_headers, {})
        result = self.run_xfu("a", "k.7z", *names)
        self.assertEqual(result.stderr, "")
        listing = self.run_xfu("l", "k.7z", "--advanced").stdout
        for stamp in (old, future, mid):
            self.assertIn("Timestamp: %d" % ((stamp + 11644473600) * 10 ** 7), listing)

        def warnings(label, low, high, given=("1960-06-01", "4200-01-01")):
            lines = []
            if low:
                lines.append("old.txt: its modification time (%s) is earlier than %s "
                             "can store; stored as %s" % (given[0], label, low))
            lines.append("fut.txt: its modification time (%s) is later than %s can "
                         "store; stored as %s" % (given[1], label, high))
            return lines
        # ZIP stores local time, and says so in local dates.
        try:
            local = tuple(time.strftime("%Y-%m-%d", time.localtime(stamp))
                          for stamp in (old, future))
        except (OverflowError, OSError, ValueError):
            # The Windows CRT cannot convert the full FILETIME range.
            local = ("1960-06-01", "4200-01-01")
        cases = (("c.tar", (), "tar", warnings("tar", "1970-01-01", "2242-03-16")),
                 ("c.tgz", (), "tar.gz", warnings("tar.gz", "1970-01-01", "2242-03-16")),
                 ("c.cpio", (), "cpio", warnings("cpio", "1970-01-01", "2106-02-07")),
                 ("c.zip", (), "zip", warnings("zip", "1980-01-01", "2107-12-31", local)),
                 ("u.tar", ("--format=ustar",), "ustar",
                  warnings("ustar", "1970-01-01", "2242-03-16")),
                 ("o.cpio", ("--format=cpio",), "cpio",
                  warnings("cpio_odc", "1970-01-01", "2242-03-16")),
                 ("c.iso", (), "iso9660", warnings("iso9660", None, "2155-12-31")))
        for output, arguments, label, expected in cases:
            with self.subTest(output=output):
                # One warning line each, and the archive is written.
                result = self.run_xfu("a", output, *names, *arguments)
                self.assertEqual(result.stderr.splitlines(), expected)
                self.assertEqual(result.stdout.splitlines()[-1],
                                 "%s: 3 file(s) as %s" % (output, label))
        for output in ("c.tar", "u.tar"):
            with tarfile.open(self.root / output) as archive:
                self.assertEqual([member.mtime for member in archive.getmembers()],
                                 [0, 0o77777777777, mid])
        newc = (self.root / "c.cpio").read_bytes()
        self.assertEqual(int(newc[46:54], 16), 0)
        with zipfile.ZipFile(self.root / "c.zip") as archive:
            self.assertEqual([info.date_time for info in archive.infolist()][:2],
                             [(1980, 1, 1, 0, 0, 0), (2107, 12, 31, 23, 59, 58)])

    def run_xfu_in(self, zone, *arguments):
        """xfu with TZ set to zone (ZIP stores local time)."""
        environment = dict(os.environ, TZ=zone)
        return subprocess.run([str(EXECUTABLE), *map(str, arguments)], cwd=self.root, text=True,
                              errors="surrogateescape", capture_output=True, timeout=60,
                              env=environment)

    @unittest.skipIf(os.name == "nt", "TZ names are POSIX ones")
    def test_time_warnings_name_the_direction_and_differ(self):
        # Near the DOS limits the local date decides: in Berlin 2107-12-31
        # 23:30 UTC is already 2108, in New York 1980-01-01 02:00 UTC is
        # still 1979.
        self.stamped("late.txt", 4354817400)  # 2107-12-31 23:30 UTC
        self.stamped("early.txt", 315540000)  # 1980-01-01 02:00 UTC
        for zone, name, expected in (
                ("Europe/Berlin", "late.txt",
                 "late.txt: its modification time (2108-01-01) is later than zip can store; "
                 "stored as 2107-12-31"),
                ("America/New_York", "early.txt",
                 "early.txt: its modification time (1979-12-31) is earlier than zip can "
                 "store; stored as 1980-01-01")):
            with self.subTest(zone=zone):
                if not os.path.exists("/usr/share/zoneinfo/" + zone):
                    self.skipTest("no time zone data")
                result = self.run_xfu_in(zone, "a", name + ".zip", name)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr.splitlines(), [expected])
            # Stored in UTC itself, neither time is clamped.
            result = self.run_xfu_in("UTC", "a", "u-" + name + ".zip", name)
            self.assertEqual((result.returncode, result.stderr), (0, ""))
        # A time one second past what a header holds: the times of day, as
        # both fall on the same day.
        self.stamped("l2.txt", 0o77777777777 + 1)
        result = self.run_xfu("a", "x.tar", "l2.txt")
        self.assertEqual(result.stderr.splitlines(),
                         ["l2.txt: its modification time (2242-03-16 12:56:32) is later than "
                          "tar can store; stored as 2242-03-16 12:56:31"])

    def test_warnings_wait_for_the_archive(self):
        # A run that fails writes nothing, so it says nothing was stored.
        self.stamped("old.txt", -315619200)  # 1960-01-01
        long_name = "n" * 120 + ".txt"
        (self.root / long_name).write_bytes(b"c\n")
        warning = ("old.txt: its modification time (1960-01-01) is earlier than %s can store; "
                   "stored as 1970-01-01")
        result = self.run_xfu("a", "y.ustar", "old.txt", long_name, success=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.splitlines(),
                         ["%s: the name does not fit a ustar header (100 bytes, or 256 split at "
                          "a '/' into 155 and 100); --format=pax stores it" % long_name])
        self.assertFalse((self.root / "y.ustar").exists())
        if os.name != "nt" and os.geteuid() != 0:  # Root reads a file of mode 000.
            unreadable = self.root / "noread.txt"
            unreadable.write_bytes(b"d\n")
            unreadable.chmod(0)
            self.addCleanup(unreadable.chmod, 0o644)
            for output in ("y.ustar", "y.zip", "y.cpio", "y.tar"):
                with self.subTest(output=output):
                    result = self.run_xfu("a", output, "old.txt", "noread.txt", success=False)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stderr.splitlines(),
                                     ["noread.txt: cannot read the input: Permission denied"])
                    self.assertFalse((self.root / output).exists())
        # Once the archive is written, the warning comes.
        result = self.run_xfu("a", "y.ustar", "old.txt")
        self.assertEqual(result.stderr.splitlines(), [warning % "ustar"])
        self.assertEqual(result.stdout.splitlines(), ["  old.txt", "y.ustar: 1 file(s) as ustar"])

    @unittest.skipIf(os.name == "nt" or not shutil.which("fakeroot"), "needs fakeroot")
    def test_owner_ids_a_ustar_header_cannot_hold(self):
        # Directory-service accounts have ids past seven octal digits.
        folder = self.root / "s"
        folder.mkdir()
        (folder / "huge").write_bytes(b"a\n")
        long_name = "s/" + "n" * 99  # Fits ustar's split name, not gnutar's 100 bytes.
        (self.root / long_name).write_bytes(b"l\n")
        runs = (("t.pax", "s --format=pax"), ("r.tar", "s --format=tar"), ("t.tar", "s"),
                ("t.tgz", "s"), ("u.ustar", "s"), ("v.tar", "s --format=v7tar"),
                ("g.tar", long_name + " --format=gnutar"), ("c.cpio", "s"))
        # setuid, which must never come back as root's.
        script = ["chown 3000000:4000000 s/huge && chown 7:4000000 %s && chmod 4755 s/huge "
                  "|| exit 77" % long_name]
        for output, inputs in runs:
            script.append('"$0" a %s %s > %s.out 2> %s.err; echo $? > %s.rc'
                          % (output, inputs, output, output, output))
        completed = subprocess.run(["fakeroot", "sh", "-c", "\n".join(script), str(EXECUTABLE)],
                                   cwd=self.root, capture_output=True, text=True, timeout=120)
        if completed.returncode == 77:
            self.skipTest("fakeroot cannot chown here")
        self.assertEqual(completed.returncode, 0, completed.stderr)

        def run(output):
            return (int((self.root / (output + ".rc")).read_text()),
                    (self.root / (output + ".err")).read_text().splitlines())
        # pax headers keep any id; --format=tar adds one only where needed.
        for output in ("t.pax", "r.tar"):
            with self.subTest(output=output):
                self.assertEqual(run(output), (0, []))
                with tarfile.open(self.root / output) as archive:
                    huge, long = archive.getmember("s/huge"), archive.getmember(long_name)
                    self.assertEqual((huge.uid, huge.gid, long.uid, long.gid),
                                     (3000000, 4000000, 7, 4000000))
                    self.assertEqual((huge.pax_headers["uid"], huge.pax_headers["gid"]),
                                     ("3000000", "4000000"))
                    self.assertNotIn("uid", long.pax_headers)
                # Readers without pax see nobody (65534) in both the pax and
                # the member's ustar header, not root.
                data = (self.root / output).read_bytes()
                payload = data.index(b"path=s/huge\n")
                payload -= payload % 512
                extension = data[payload - 512:payload]
                member = data[payload + 512 * -(-int(extension[124:135], 8) // 512):][:512]
                for header in (extension, member):
                    self.assertEqual((header[108:115], header[116:123]), (b"0177776",) * 2)
                self.assertEqual(member[156:157], b"0")
                self.run_xfu("t", output, "--reader=native")
        # The xxfclib TAR writers: nobody's, with one line each.
        for output, label in (("t.tar", "tar"), ("t.tgz", "tar.gz")):
            with self.subTest(output=output):
                self.assertEqual(run(output), (0, [
                    "s/huge: its owner and group ids (3000000, 4000000) are larger than %s can "
                    "store; stored as 65534 (nobody); --format=pax stores them" % label,
                    "%s: its group id (4000000) is larger than %s can store; stored as 65534 "
                    "(nobody); --format=pax stores it" % (long_name, label)]))
                with tarfile.open(self.root / output) as archive:
                    huge, long = archive.getmember("s/huge"), archive.getmember(long_name)
                    self.assertEqual((huge.uid, huge.gid, long.uid, long.gid),
                                     (65534, 65534, 7, 65534))
                    self.assertEqual(huge.mode, 0o4755)
        # The xxfclib CPIO writer: newc's 32-bit fields hold every id, so a
        # setuid file never comes back as root's.
        with self.subTest(output="c.cpio"):
            self.assertEqual(run("c.cpio"), (0, []))
            data = (self.root / "c.cpio").read_bytes()
            for name, ids in ((b"s/huge\0", (3000000, 4000000)), (long_name.encode() + b"\0", (7, 4000000))):
                header = data[data.index(b"070701", data.index(name) - 110):][:110]
                self.assertEqual((int(header[22:30], 16), int(header[30:38], 16)), ids)
                if name.startswith(b"s/huge"):
                    self.assertEqual(int(header[14:22], 16) & 0o7777, 0o4755)
        # ustar, v7tar and gnutar refuse the member by name, before any of
        # its headers (gnutar's long name) is written.
        for output, label, name in (("u.ustar", "ustar", "s/huge"), ("v.tar", "v7tar", "s/huge"),
                                    ("g.tar", "gnutar", long_name)):
            with self.subTest(output=output):
                self.assertEqual(run(output), (2, [
                    "%s: its owner or group id is larger than a %s header holds; --format=pax "
                    "stores it" % (name, label)]))
                self.assertFalse((self.root / output).exists())

    @unittest.skipIf(os.name == "nt", "'\\' separates folders on Windows")
    def test_a_backslash_in_a_posix_name_is_refused_or_kept(self):
        (self.root / "bs").mkdir()
        (self.root / "bs" / "back\\slash.txt").write_bytes(b"one file\n")
        pax = "; --format=pax stores it"
        for output, kind, hint in (("b.tar", "tar", pax), ("b.tgz", "tar.gz", pax),
                                   ("b.zip", "zip", ""), ("b.7z", "7z", ""),
                                   ("b.cpio", "cpio", ""), ("b.bin", "newc", "")):
            with self.subTest(output=output):
                arguments = ("--format=newc",) if kind == "newc" else ()
                for given in ("bs/back\\slash.txt", "bs"):  # The file, or its folder.
                    result = self.run_xfu("a", output, given, *arguments, success=False)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stderr.splitlines(),
                                     ["bs/back\\slash.txt: the name contains '\\', which %s "
                                      "cannot store%s" % (kind, hint)])
                    self.assertFalse((self.root / output).exists())
        # The native writers keep the name as the file system has it.
        self.run_xfu("a", "b.pax", "bs/back\\slash.txt", "--format=pax")
        with tarfile.open(self.root / "b.pax") as archive:
            self.assertEqual(archive.getnames(), ["bs/back\\slash.txt"])
        self.run_xfu("a", "b.ar", "bs/back\\slash.txt")
        self.assertEqual(ar_members((self.root / "b.ar").read_bytes()),
                         [("back\\slash.txt", b"one file\n")])
        # Except where xfu could not read the name back (XAR, WARC, mtree)
        # or Joliet cannot hold it (ISO9660).
        for output, label in (("b.xar", "an xar"), ("b.warc", "a warc"),
                              ("b.mtree", "an mtree"), ("b.iso", "an iso9660")):
            with self.subTest(output=output):
                result = self.run_xfu("a", output, "bs/back\\slash.txt", success=False)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr.splitlines(),
                                 ["bs/back\\slash.txt: the name contains '\\', which %s "
                                  "archive cannot store" % label])
                self.assertFalse((self.root / output).exists())

    def test_shar_refuses_the_names_its_reader_leaves_out(self):
        for name, problem in (("a*b.txt", "contains '*'"), ("a?b.txt", "contains '?'"),
                              ("it's.txt", "contains \"'\""), ("a$b.txt", "contains '$'"),
                              ("a;b.txt", "contains ';'"), ('a"b.txt', "contains '\"'")):
            with self.subTest(name=name):
                try:
                    (self.root / name).write_bytes(b"x\n")
                except OSError:
                    continue  # Not a name this file system takes.
                result = self.run_xfu("a", "n.shar", name, success=False)
                self.assertEqual(result.stderr.splitlines(),
                                 ["%s: the name %s, which a shell archive cannot store (xfu "
                                  "reads one without running it, and would leave the file "
                                  "out); --format=pax stores it" % (name, problem)])
                self.assertFalse((self.root / "n.shar").exists())
        # Shell characters the reader takes still go in, quoted.
        (self.root / "p (1)[x]#.txt").write_bytes(b"paren\n")
        self.run_xfu("a", "n.shar", "p (1)[x]#.txt")
        self.assertIn("p (1)[x]#.txt", self.run_xfu("l", "n.shar").stdout)

    def publish_shim(self):
        """An LD_PRELOAD library that disturbs the publication: XFU_SHIM=appear
        creates a file at the destination just before the stage is put there,
        swap replaces the complete stage by a link to $XFU_VICTIM once its size
        was checked (opened by name), before it is checked again and
        published, other renames another writer's file over the destination
        just after the stage was put there, eperm makes linkat fail as on a
        file system without hard links."""
        compiler = shutil.which("cc") or shutil.which("gcc")
        if not sys.platform.startswith("linux") or not compiler:
            self.skipTest("an LD_PRELOAD library needs Linux and a C compiler")
        source = self.root / "shim.c"
        source.write_text(r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static int stage(const char *p) { const char *b = strrchr(p, '/'); return !strncmp(b ? b + 1 : p, ".xfu-", 5); }
static int (*real_rename)(const char *, const char *);
static int mode(const char *name) { return getenv("XFU_SHIM") && !strcmp(getenv("XFU_SHIM"), name); }
static void act(const char *from, const char *to) {
    if (!real_rename) real_rename = (int (*)(const char *, const char *))dlsym(RTLD_NEXT, "rename");
    if (mode("appear") && stage(from)) {
        FILE *f = fopen(to, "wx");
        if (f) { fputs("APPEARED\n", f); fclose(f); }
    }
}
static void after(const char *from, const char *to, int result) {
    char other[4096];
    FILE *f;
    if (result != 0 || !mode("other") || !stage(from)) return;
    snprintf(other, sizeof other, "%s.other", to);
    if (!(f = fopen(other, "w"))) abort();
    fputs("OTHER WRITER\n", f);
    fclose(f);
    if (real_rename(other, to) != 0) abort();
}
static FILE *swap(const char *path, const char *how, FILE *file) {
    char aside[4096];
    static int done;
    if (!file || done || !mode("swap") || !stage(path) || how[0] != 'r') return file;
    done = 1;
    snprintf(aside, sizeof aside, "%s.aside", path);
    if (!real_rename) real_rename = (int (*)(const char *, const char *))dlsym(RTLD_NEXT, "rename");
    if (real_rename(path, aside) == 0 && symlink(getenv("XFU_VICTIM"), path) != 0) abort();
    return file;
}
FILE *fopen(const char *path, const char *how) {
    static FILE *(*real)(const char *, const char *);
    if (!real) real = (FILE *(*)(const char *, const char *))dlsym(RTLD_NEXT, "fopen");
    return swap(path, how, real(path, how));
}
FILE *fopen64(const char *path, const char *how) {
    static FILE *(*real)(const char *, const char *);
    if (!real) real = (FILE *(*)(const char *, const char *))dlsym(RTLD_NEXT, "fopen64");
    return swap(path, how, real(path, how));
}
int linkat(int a, const char *from, int b, const char *to, int flags) {
    static int (*real)(int, const char *, int, const char *, int);
    int result;
    if (!real) real = (int (*)(int, const char *, int, const char *, int))dlsym(RTLD_NEXT, "linkat");
    act(from, to);
    if (mode("eperm") && stage(from)) { errno = EPERM; return -1; }
    result = real(a, from, b, to, flags);
    after(from, to, result);
    return result;
}
int rename(const char *from, const char *to) {
    int result;
    act(from, to);
    result = real_rename(from, to);
    after(from, to, result);
    return result;
}
""")
        library = self.root / "shim.so"
        completed = subprocess.run([compiler, "-shared", "-fPIC", "-o", str(library), str(source),
                                    "-ldl"], capture_output=True, timeout=120)
        if completed.returncode:
            self.skipTest("the C compiler cannot build a shared library")
        return library

    def test_a_new_archive_never_replaces_what_appeared_at_its_name(self):
        library = self.publish_shim()
        victim = self.root / "victim.txt"
        victim.write_bytes(b"VICTIM\n")
        def run(mode, existing):
            archive = self.root / "a.tar"
            if archive.is_symlink() or archive.exists():
                archive.unlink()
            if existing:
                archive.write_bytes(b"OLD ARCHIVE")
            environment = dict(os.environ, LD_PRELOAD=str(library), XFU_SHIM=mode,
                               XFU_VICTIM=str(victim))
            return subprocess.run([str(EXECUTABLE), "a", "a.tar", "alpha.txt"], cwd=self.root,
                                  env=environment, capture_output=True, text=True, timeout=60)
        result = run("appear", False)
        if "ERROR: ld.so" in result.stderr or "runtime does not come first" in result.stderr:
            self.skipTest("this build cannot take an LD_PRELOAD library (a sanitizer build)")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr.splitlines(),
                         ["a.tar: cannot publish completed archive: another file was created at "
                          "its name meanwhile, and is left as it is"])
        self.assertEqual((self.root / "a.tar").read_bytes(), b"APPEARED\n")
        for existing in (False, True):
            result = run("swap", existing)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stderr.splitlines(),
                             ["a.tar: cannot publish completed archive: its staging file was "
                              "replaced"])
            # Never a link left as the archive, nor the victim written; an
            # archive that was there stays.
            self.assertFalse((self.root / "a.tar").is_symlink())
            if existing:
                self.assertEqual((self.root / "a.tar").read_bytes(), b"OLD ARCHIVE")
            else:
                self.assertFalse((self.root / "a.tar").exists())
            self.assertEqual(victim.read_bytes(), b"VICTIM\n")
            # Another writer's file put at the name just after publication
            # is left there, as with a plain rename.
            result = run("other", existing)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.root / "a.tar").read_bytes(), b"OTHER WRITER\n")
        result = run("eperm", False)  # No hard links: renamed instead.
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(self.root / "a.tar") as archive:
            self.assertEqual(archive.extractfile("alpha.txt").read(), self.payload)
        for leftover in stage_files(self.root):
            self.assertTrue(leftover.endswith(".aside"), leftover)  # Only the shim's own.


if __name__ == "__main__":
    if EXECUTABLE is None:
        raise SystemExit("usage: python test_native_writers.py /path/to/xfu")
    unittest.main()

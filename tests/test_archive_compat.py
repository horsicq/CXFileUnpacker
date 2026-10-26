"""Run native integration checks against an already built xfu executable."""

import gzip
import io
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import zipfile
import zlib

from test_archive_feature_contract import (
    FILTER_CREATE, FILTER_READ, FORMAT_CREATE, FORMAT_READ,
)


XFU = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None
WRITERS = (
    "7zip", "ar", "arbsd", "argnu", "arsvr4", "bin", "bsdtar",
    "cd9660", "cpio", "gnutar", "iso", "iso9660", "mtree",
    "mtree-classic", "newc", "odc", "oldtar", "pax", "paxr", "posix",
    "pwb", "raw", "rpax", "shar", "shardump", "ustar", "v7tar", "v7",
    "warc", "xar", "zip", "7z", "ar_gnu",
)
MANIFESTS = {"mtree", "mtree-classic", "mtree_classic"}
SHELL_ARCHIVES = {"shar", "shardump", "shar_dump"}


def windows_extended_path(path):
    """Address a long local path without depending on the MAX_PATH policy."""
    path = os.path.abspath(os.fspath(path))
    if os.name != "nt" or path.startswith("\\\\?\\"):
        return Path(path)
    if path.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + path[2:])
    return Path("\\\\?\\" + path)


def read_path_bytes(path):
    return windows_extended_path(path).read_bytes()

# Handmade zstd and LZ4 frames, with or without their sizes and checksums
# (Python has no zstd or LZ4 module here, and xfu's writers record sizes).

_M64 = (1 << 64) - 1
_P64 = (0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9, 0x85EBCA77C2B2AE63, 0x27D4EB2F165667C5)


def _rotl64(value, count):
    return ((value << count) | (value >> (64 - count))) & _M64


def _round64(accumulator, lane):
    accumulator = (accumulator + lane * _P64[1]) & _M64
    return (_rotl64(accumulator, 31) * _P64[0]) & _M64


def xxh64(data):
    """XXH64 with seed 0, as a zstd frame checksum takes its low 32 bits."""
    size, at = len(data), 0
    if size >= 32:
        lanes = [(_P64[0] + _P64[1]) & _M64, _P64[1], 0, (-_P64[0]) & _M64]
        while at + 32 <= size:
            for index in range(4):
                lanes[index] = _round64(lanes[index], int.from_bytes(data[at + 8 * index:at + 8 * index + 8], "little"))
            at += 32
        digest = (_rotl64(lanes[0], 1) + _rotl64(lanes[1], 7) + _rotl64(lanes[2], 12) + _rotl64(lanes[3], 18)) & _M64
        for lane in lanes:
            digest = ((digest ^ _round64(0, lane)) * _P64[0] + _P64[3]) & _M64
    else:
        digest = _P64[4]
    digest = (digest + size) & _M64
    while at + 8 <= size:
        digest ^= _round64(0, int.from_bytes(data[at:at + 8], "little"))
        digest = (_rotl64(digest, 27) * _P64[0] + _P64[3]) & _M64
        at += 8
    if at + 4 <= size:
        digest ^= (int.from_bytes(data[at:at + 4], "little") * _P64[0]) & _M64
        digest = (_rotl64(digest, 23) * _P64[1] + _P64[2]) & _M64
        at += 4
    while at < size:
        digest ^= (data[at] * _P64[4]) & _M64
        digest = (_rotl64(digest, 11) * _P64[0]) & _M64
        at += 1
    digest ^= digest >> 33
    digest = (digest * _P64[1]) & _M64
    digest ^= digest >> 29
    digest = (digest * _P64[2]) & _M64
    return digest ^ (digest >> 32)


_M32 = 0xFFFFFFFF
_P32 = (2654435761, 2246822519, 3266489917, 668265263, 374761393)


def _rotl32(value, count):
    return ((value << count) | (value >> (32 - count))) & _M32


def xxh32(data):
    """XXH32 with seed 0, as LZ4 frames use it."""
    size, at = len(data), 0
    if size >= 16:
        lanes = [(_P32[0] + _P32[1]) & _M32, _P32[1], 0, (-_P32[0]) & _M32]
        while at + 16 <= size:
            for index in range(4):
                lane = int.from_bytes(data[at + 4 * index:at + 4 * index + 4], "little")
                lanes[index] = (_rotl32((lanes[index] + lane * _P32[1]) & _M32, 13) * _P32[0]) & _M32
            at += 16
        digest = (_rotl32(lanes[0], 1) + _rotl32(lanes[1], 7) + _rotl32(lanes[2], 12) + _rotl32(lanes[3], 18)) & _M32
    else:
        digest = _P32[4]
    digest = (digest + size) & _M32
    while at + 4 <= size:
        digest = (_rotl32((digest + int.from_bytes(data[at:at + 4], "little") * _P32[2]) & _M32, 17) * _P32[3]) & _M32
        at += 4
    while at < size:
        digest = (_rotl32((digest + data[at] * _P32[4]) & _M32, 11) * _P32[0]) & _M32
        at += 1
    digest ^= digest >> 15
    digest = (digest * _P32[1]) & _M32
    digest ^= digest >> 13
    digest = (digest * _P32[2]) & _M32
    return digest ^ (digest >> 16)


def zstd_frame(data, sized, checksum):
    """One zstd frame of raw blocks of 128 KiB (a 128 KiB window), with or
    without its content size and checksum."""
    frame = bytearray(b"\x28\xb5\x2f\xfd")
    frame.append((0x80 if sized else 0) | (0x04 if checksum else 0))
    frame.append(7 << 3)  # a window of 2^(10 + 7) bytes
    if sized:
        frame += len(data).to_bytes(4, "little")
    blocks = [data[at:at + (128 << 10)] for at in range(0, len(data), 128 << 10)] or [b""]
    for index, block in enumerate(blocks):
        frame += ((len(block) << 3) | (1 if index == len(blocks) - 1 else 0)).to_bytes(3, "little") + block
    if checksum:
        frame += (xxh64(data) & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(frame)


def lz4_frame(data, sized, block_checksum, content_checksum):
    """One LZ4 frame of uncompressed independent blocks of 64 KiB."""
    descriptor = bytes([0x60 | (0x10 if block_checksum else 0) | (0x08 if sized else 0) | (0x04 if content_checksum else 0), 0x40])
    if sized:
        descriptor += len(data).to_bytes(8, "little")
    frame = bytearray(b"\x04\x22\x4d\x18" + descriptor + bytes([(xxh32(descriptor) >> 8) & 0xFF]))
    for at in range(0, len(data), 64 << 10):
        block = data[at:at + (64 << 10)]
        frame += (len(block) | 0x80000000).to_bytes(4, "little") + block
        if block_checksum:
            frame += xxh32(block).to_bytes(4, "little")
    frame += bytes(4)
    if content_checksum:
        frame += xxh32(data).to_bytes(4, "little")
    return bytes(frame)


class ArchiveCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XFU is None or not XFU.is_file():
            raise RuntimeError("Usage: python test_archive_compat.py /path/to/xfu")
        result = subprocess.run(
            [str(XFU), "--capabilities"], capture_output=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.report = result.stdout
        cls.capabilities = {"format": {}, "filter": {}}
        for kind, name, read, create in re.findall(
            r"^\s*(format|filter)\s+(\S+)\s+read=(yes|no)\s+create=(yes|no)",
            result.stdout, re.MULTILINE,
        ):
            cls.capabilities[kind][name] = (read == "yes", create == "yes")
        if not cls.capabilities["format"] or not cls.capabilities["filter"]:
            raise AssertionError("No parseable capability rows:\n" + result.stdout)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xfu-native-")
        self.root = Path(self.temporary.name)
        self.payload = b"native compatibility\n" + bytes(range(256)) * 8
        (self.root / "alpha.txt").write_bytes(self.payload)

    def tearDown(self):
        try:
            self.temporary.cleanup()
        except OSError:
            if os.name != "nt":
                raise
            # pathlib/shutil still use MAX_PATH when the host long-path
            # policy is disabled.  The extractor itself uses extended paths.
            shutil.rmtree(windows_extended_path(self.root))
            self.temporary.cleanup()

    def run_xfu(self, *arguments, success=True):
        result = subprocess.run(
            [str(XFU), *map(str, arguments)], cwd=self.root,
            capture_output=True, encoding="utf-8", errors="replace", timeout=90,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def require(self, kind, name, operation=1):
        self.assertTrue(
            self.capabilities[kind].get(name, (False, False))[operation],
            f"Required {kind} {name} operation is unavailable",
        )

    def check_round_trip(self, archive, reader="native", expected=None):
        listing = self.run_xfu("l", archive, "--reader", reader)
        self.assertTrue(listing.stdout.strip())
        self.run_xfu("t", archive, "--reader", reader, "--verbose")
        destination = self.root / ("out-" + archive.replace(".", "-"))
        self.run_xfu("x", archive, "--reader", reader, "-o" + str(destination))
        payloads = [p.read_bytes() for p in destination.rglob("*") if p.is_file()]
        self.assertIn(self.payload if expected is None else expected, payloads)

    def test_unpack_handle_selects_outer_stream_or_inner_archive(self):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w:") as output:
            for name, data in (("alpha.txt", self.payload), ("nested.txt", b"inner member\n")):
                item = tarfile.TarInfo(name)
                item.size = len(data)
                output.addfile(item, io.BytesIO(data))
        (self.root / "handles.tar.gz").write_bytes(gzip.compress(archive.getvalue(), mtime=0))
        for name in ("TAR_GZ", "tar.gz", "XX_HANDLE_TYPE_TAR_GZ", "auto"):
            with self.subTest(handle=name):
                listing = self.run_xfu("l", "handles.tar.gz", "--handle", name)
                self.assertIn("2 member(s)", listing.stdout)
                self.assertIn("nested.txt", listing.stdout)
        listing = self.run_xfu("l", "handles.tar.gz", "--handle=gzip")
        self.assertIn("1 member(s)", listing.stdout)
        self.assertNotIn("nested.txt", listing.stdout)

    def test_unpack_handle_rejects_inspection_types_and_reader_conflicts(self):
        for value in ("Binary", "PE32", "1", "4294967296", "unsupported-handle"):
            with self.subTest(handle=value):
                result = self.run_xfu("l", "missing.zip", "--handle=" + value, success=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("--handle:", result.stderr)
        for options in (("--handle=ZIP", "--reader=native"),
                        ("--reader=native", "--handle=ZIP"),
                        ("--handle=auto", "--handle=ZIP")):
            with self.subTest(options=options):
                result = self.run_xfu("l", "missing.zip", *options, success=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("--handle", result.stderr)

    def test_unpack_handle_rejects_a_different_executable_carrier(self):
        from create_unpack_handle_fixtures import pe32

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("payload.txt", b"self extracting payload\n")
        dos = bytearray(512)
        dos[:2] = b"MZ"
        struct.pack_into("<H", dos, 4, 1)
        struct.pack_into("<H", dos, 8, 4)
        struct.pack_into("<H", dos, 0x18, 0x40)
        dos[64] = 0xC3
        for name, stub, own, other in (
            ("pe.exe", pe32(), "PE_ZIPSFX", "MSDOS_ZIPSFX"),
            ("dos.exe", bytes(dos), "MSDOS_ZIPSFX", "PE_ZIPSFX"),
        ):
            with self.subTest(carrier=name):
                (self.root / name).write_bytes(stub + payload.getvalue())
                self.assertIn("payload.txt", self.run_xfu("l", name, "--handle=" + own).stdout)
                result = self.run_xfu("l", name, "--handle=" + other, success=False)
                self.assertEqual(result.returncode, 2)

    def test_unpack_handle_zip_authenticates_non_executable_leading_data(self):
        stream = io.BytesIO()
        payload = b"prefixed native zip payload\n"
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("payload.txt", payload)
        (self.root / "prefixed.bin").write_bytes(b"opaque non-executable prefix\0" +
                                                  bytes(range(1, 32)) + stream.getvalue())
        listing = self.run_xfu("l", "prefixed.bin", "--handle=ZIP")
        self.assertIn("payload.txt", listing.stdout)
        self.run_xfu("t", "prefixed.bin", "--handle=ZIP")
        self.run_xfu("x", "prefixed.bin", "--handle=ZIP", "-oprefixed-out")
        self.assertEqual((self.root / "prefixed-out" / "payload.txt").read_bytes(), payload)

    def test_capability_contract(self):
        for kind, read_names, create_names in (
            ("format", FORMAT_READ, FORMAT_CREATE),
            ("filter", FILTER_READ, FILTER_CREATE),
        ):
            for name in read_names:
                self.assertTrue(self.capabilities[kind].get(name, (False, False))[0],
                                f"Missing {kind} reader {name}")
            for name in create_names:
                self.assertTrue(self.capabilities[kind].get(name, (False, False))[1],
                                f"Missing {kind} writer {name}")
        for name in ("cab", "lha", "rar", "rar5"):
            if name in self.capabilities["format"]:
                self.assertFalse(self.capabilities["format"][name][1])

    def test_available_writer_selectors(self):
        tested = 0
        for name in sorted(FORMAT_CREATE):
            with self.subTest(format=name):
                archive = "writer-" + name + ".bin"
                self.run_xfu("a", archive, "alpha.txt", "--format=" + name)
                self.assertTrue((self.root / archive).is_file())
                if name in SHELL_ARCHIVES:
                    content = (self.root / archive).read_bytes()
                    self.assertIn(b"alpha.txt", content)
                    self.assertIn(b"sh", content[:256])
                elif name in MANIFESTS:
                    self.assertIn(b"alpha.txt", (self.root / archive).read_bytes())
                    self.run_xfu("l", archive, "--reader", "native")
                else:
                    reader = "native:raw" if name == "raw" else "native"
                    self.check_round_trip(archive, reader)
                tested += 1
        self.assertGreater(tested, 10, self.report)

    def test_writer_aliases(self):
        for name in WRITERS:
            with self.subTest(alias=name):
                self.run_xfu("a", "alias-" + name + ".bin", "alpha.txt", "--format=" + name)

    def test_available_filter_round_trips(self):
        self.require("format", "pax")
        tested = 0
        for name in sorted(FILTER_CREATE):
            with self.subTest(filter=name):
                archive = "filter-" + name + ".bin"
                self.run_xfu("a", archive, "alpha.txt", "--format=pax", "--filter=" + name)
                self.check_round_trip(archive)
                tested += 1
        self.assertGreater(tested, 3, self.report)

    def test_compressed_non_tar_container(self):
        self.require("format", "cpio_newc")
        self.require("filter", "gzip")
        self.run_xfu("a", "wrapped.bin", "alpha.txt", "--format=newc", "--filter=gzip")
        self.check_round_trip("wrapped.bin")
        self.run_xfu("t", "wrapped.bin")
        (self.root / "beta.txt").write_bytes(b"second member")
        self.run_xfu("a", "inferred.cpio.gz", "alpha.txt", "beta.txt")
        listing = self.run_xfu("l", "inferred.cpio.gz", "--reader", "native")
        self.assertIn("alpha.txt", listing.stdout)
        self.assertIn("beta.txt", listing.stdout)
        self.run_xfu("t", "inferred.cpio.gz")
        self.check_round_trip("inferred.cpio.gz")

    def test_nested_paths_and_explicit_empty_directories(self):
        name = "nested/caf\u00e9/alpha.txt"
        (self.root / "nested" / "caf\u00e9").mkdir(parents=True)
        (self.root / "empty-directory").mkdir()
        (self.root / name).write_bytes(self.payload)
        for format_name in ("iso9660", "xar", "cpio_odc", "cpio_bin", "cpio_pwb"):
            with self.subTest(format=format_name):
                archive = "nested-" + format_name + ".bin"
                destination = self.root / ("nested-out-" + format_name)
                self.run_xfu("a", archive, name, "empty-directory",
                             "--format=" + format_name)
                if format_name == "iso9660":
                    self.assertIn(b"RRIP_1991A", (self.root / archive).read_bytes())
                if format_name == "xar":
                    content = (self.root / archive).read_bytes()
                    toc_length = struct.unpack(">Q", content[8:16])[0]
                    toc = zlib.decompress(content[28:28 + toc_length])
                    self.assertIn(
                        b"<name>empty-directory</name><type>directory</type><mode>",
                        toc,
                    )
                listing = self.run_xfu("l", archive, "--reader", "native")
                self.assertIn(name, listing.stdout)
                self.assertIn("empty-directory", listing.stdout)
                self.run_xfu("t", archive, "--reader", "native")
                self.run_xfu("x", archive, "--reader", "native",
                             "-o" + str(destination))
                self.assertEqual((destination / name).read_bytes(), self.payload)
                self.assertTrue((destination / "empty-directory").is_dir())

    def test_wrapped_native_containers(self):
        for format_name, filter_name in (
            ("xar", "gzip"), ("xar", "xz"), ("cpio_odc", "gzip"),
            ("cpio_bin", "xz"), ("cpio_pwb", "zstd"), ("iso9660", "gzip"),
        ):
            with self.subTest(format=format_name, filter=filter_name):
                archive = "wrapped-" + format_name + "-" + filter_name + ".bin"
                self.run_xfu("a", archive, "alpha.txt",
                             "--format=" + format_name,
                             "--filter=" + filter_name)
                self.check_round_trip(archive)

    def test_two_layer_filter_wrappers(self):
        self.run_xfu("a", "inner.cpio", "alpha.txt", "--format=cpio_odc")
        (self.root / "inner.cpio.gz").write_bytes(
            gzip.compress((self.root / "inner.cpio").read_bytes(), mtime=0)
        )
        self.run_xfu("a", "base64-gzip-cpio.bin", "inner.cpio.gz",
                     "--format=raw", "--filter=b64encode")
        self.check_round_trip("base64-gzip-cpio.bin")

        self.run_xfu("a", "inner.tar", "alpha.txt", "--format=pax")
        self.run_xfu("a", "inner.tar.b64", "inner.tar",
                     "--format=raw", "--filter=b64encode")
        (self.root / "gzip-base64-tar.bin").write_bytes(
            gzip.compress((self.root / "inner.tar.b64").read_bytes(), mtime=0)
        )
        self.check_round_trip("gzip-base64-tar.bin")

    def test_cpio_writer_wire_variants(self):
        for format_name, signature in (
            ("cpio_odc", b"070707"),
            ("cpio_bin", b"\xc7\x71"),
            ("cpio_pwb", b"\xc7\x71"),
        ):
            with self.subTest(format=format_name):
                archive = "wire-" + format_name + ".cpio"
                self.run_xfu("a", archive, "alpha.txt",
                             "--format=" + format_name)
                self.assertTrue((self.root / archive).read_bytes().startswith(signature))
                self.check_round_trip(archive)

    def test_new_suffixes_and_automatic_reading(self):
        for suffix, name in ((".ar", "ar_bsd"), (".iso", "iso9660"),
                             (".warc", "warc"), (".xar", "xar"), (".mtree", "mtree")):
            with self.subTest(suffix=suffix):
                archive = "automatic" + suffix
                self.run_xfu("a", archive, "alpha.txt")
                self.run_xfu("l", archive)
                if name not in MANIFESTS:
                    self.run_xfu("t", archive)

    def test_unicode_names(self):
        name = "caf\u00e9-\u65e5\u672c.txt"
        (self.root / name).write_bytes(self.payload)
        for format_name in ("zip", "pax", "7zip", "iso9660", "xar", "ar_svr4",
                            "ar_bsd", "cpio_newc", "warc", "mtree", "mtree_classic"):
            with self.subTest(format=format_name):
                archive = "unicode-" + format_name + ".bin"
                destination = "unicode-" + format_name
                self.run_xfu("a", archive, name, "--format=" + format_name)
                listing = self.run_xfu("l", archive, "--reader", "native")
                self.assertIn(name, listing.stdout)
                if format_name in MANIFESTS:
                    continue
                self.run_xfu("x", archive, "--reader", "native", "-o" + destination)
                self.assertEqual((self.root / destination / name).read_bytes(), self.payload)

    def test_unflagged_cp437_zip_names(self):
        self.require("format", "zip", operation=0)
        archive = self.root / "legacy.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
            output.writestr("cafe.txt", self.payload)
        data = archive.read_bytes()
        self.assertEqual(data.count(b"cafe.txt"), 2)
        data = data.replace(b"cafe.txt", b"caf\x82.txt")
        archive.write_bytes(data)
        name = "caf\u00e9.txt"
        listing = self.run_xfu("l", archive.name, "--reader", "native")
        self.assertIn(name, listing.stdout)
        self.run_xfu("x", archive.name, "--reader", "native", "-olegacy-zip")
        self.assertEqual((self.root / "legacy-zip" / name).read_bytes(), self.payload)
        if self.capabilities["filter"].get("gzip", (False, False))[0]:
            (self.root / "legacy.zip.gz").write_bytes(gzip.compress(data, mtime=0))
            self.run_xfu("x", "legacy.zip.gz", "-owrapped-legacy-zip")
            self.assertEqual((self.root / "wrapped-legacy-zip" / name).read_bytes(), self.payload)

    def test_legacy_cpio_header_charset_override(self):
        self.require("format", "cpio_newc")
        name = "caf\u00e9.txt"
        (self.root / name).write_bytes(self.payload)
        self.run_xfu("a", "legacy.cpio", name, "--format=newc",
                     "--options=cpio:hdrcharset=CP437")
        listing = self.run_xfu("l", "legacy.cpio", "--reader", "native",
                               "--options=cpio:hdrcharset=CP437")
        self.assertIn(name, listing.stdout)
        self.run_xfu("x", "legacy.cpio", "--reader", "native", "-olegacy-cpio",
                     "--options=cpio:hdrcharset=CP437")
        self.assertEqual((self.root / "legacy-cpio" / name).read_bytes(), self.payload)

    def test_pax_long_filename(self):
        self.require("format", "pax")
        name = "long-" + "a" * 130 + ".txt"
        (self.root / name).write_bytes(self.payload)
        self.run_xfu("a", "long.tar", name, "--format=pax")
        self.run_xfu("x", "long.tar", "--reader", "native", "-olong")
        self.assertEqual((self.root / "long" / name).read_bytes(), self.payload)

    def test_gnu_ar_long_filename_table(self):
        self.require("format", "ar_svr4")
        name = "a-long-static-library-object-name.o"
        (self.root / name).write_bytes(self.payload)
        self.run_xfu("a", "long.ar", name, "--format=ar_svr4")
        listing = self.run_xfu("l", "long.ar", "--reader", "native")
        self.assertIn("1 member(s)", listing.stdout)
        self.run_xfu("t", "long.ar", "--reader", "native")
        self.run_xfu("x", "long.ar", "--reader", "native", "-olong-ar")
        self.assertEqual((self.root / "long-ar" / name).read_bytes(), self.payload)

    def test_ar_symbol_tables_are_not_extracted_members(self):
        self.require("format", "ar_svr4", operation=0)

        def record(name, data):
            header = (f"{name:<16}{0:<12}{0:<6}{0:<6}{'100644':<8}"
                      f"{len(data):<10}`\n").encode("ascii")
            return header + data + b"\n" * (len(data) % 2)

        content = b"!<arch>\n"
        for name in ("/", "/SYM64/", "__.SYMDEF", "__.SYMDEF SORTED"):
            content += record(name, b"\0" * 8)
        content += record("alpha.txt/", self.payload)
        (self.root / "symbols.ar").write_bytes(content)
        listing = self.run_xfu("l", "symbols.ar", "--reader", "native")
        self.assertIn("1 member(s)", listing.stdout)
        self.check_round_trip("symbols.ar")

    def test_uppercase_compress_suffix(self):
        self.require("filter", "compress")
        self.run_xfu("a", "legacy.tar.Z", "alpha.txt")
        self.check_round_trip("legacy.tar.Z")

    def test_zip_member_compression_methods(self):
        self.require("format", "zip")
        for method in ("stored", "deflate", "bzip2", "lzma", "xz", "zstd"):
            with self.subTest(compression=method):
                archive = "zip-" + method + ".zip"
                self.run_xfu("a", archive, "alpha.txt", "--format=zip",
                             "--compression=" + method)
                self.check_round_trip(archive)

    def test_7zip_member_compression_methods(self):
        self.require("format", "7zip")
        for method in ("stored", "deflate", "bzip2", "lzma1", "lzma2",
                       "zstd", "ppmd"):
            with self.subTest(compression=method):
                archive = "7zip-" + method + ".7z"
                self.run_xfu("a", archive, "alpha.txt", "--format=7zip",
                             "--compression=" + method)
                self.check_round_trip(archive)

    def test_pwb_binary_read_option(self):
        self.require("format", "cpio_pwb")
        self.run_xfu("a", "pwb.cpio", "alpha.txt", "--format=cpio_pwb")
        content = bytearray((self.root / "pwb.cpio").read_bytes())
        mode = int.from_bytes(content[6:8], "little") | 0o10000
        content[6:8] = mode.to_bytes(2, "little")
        (self.root / "pwb.cpio").write_bytes(content)
        self.run_xfu("t", "pwb.cpio", "--reader", "native", "--options=cpio:pwb=1")

    def test_big_endian_binary_cpio_reading(self):
        self.require("format", "cpio_bin_be", operation=0)

        def record(name, data, inode, mode):
            name = name.encode("ascii") + b"\0"
            header = struct.pack(">13H", 0o70707, 0, inode, mode, 0, 0, 1,
                                 0, 0, 0, len(name), len(data) >> 16, len(data) & 0xFFFF)
            return (header + name + b"\0" * (-len(name) % 2) +
                    data + b"\0" * (-len(data) % 2))

        content = record("alpha.txt", self.payload, 1, 0o100644)
        content += record("TRAILER!!!", b"", 0, 0)
        (self.root / "big-endian.cpio").write_bytes(content)
        self.check_round_trip("big-endian.cpio")

    def test_svr4_crc_cpio_reading(self):
        self.require("format", "cpio_crc", operation=0)

        def record(name, data, inode, mode):
            name = name.encode("ascii") + b"\0"
            fields = (inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0,
                      len(name), sum(data) & 0xFFFFFFFF)
            header = b"070702" + "".join(f"{value:08X}" for value in fields).encode("ascii")
            return (header + name + b"\0" * (-(len(header) + len(name)) % 4) +
                    data + b"\0" * (-len(data) % 4))

        content = record("alpha.txt", self.payload, 1, 0o100644)
        content += record("TRAILER!!!", b"", 0, 0)
        (self.root / "crc.cpio").write_bytes(content)
        self.check_round_trip("crc.cpio")

    def test_tar_hard_links_keep_their_data(self):
        self.require("format", "tar", operation=0)
        with tarfile.open(self.root / "links.tar", "w", format=tarfile.GNU_FORMAT) as output:
            entry = tarfile.TarInfo("d/first.txt")
            entry.size = len(self.payload)
            output.addfile(entry, io.BytesIO(self.payload))
            for name, target in (("d/second.txt", "d/first.txt"),
                                 ("./d/third.txt", "./d/first.txt")):
                entry = tarfile.TarInfo(name)
                entry.type = tarfile.LNKTYPE
                entry.linkname = target
                output.addfile(entry)
        self.run_xfu("t", "links.tar", "--reader", "native")
        self.run_xfu("x", "links.tar", "--reader", "native", "-olinks")
        for name in ("first.txt", "second.txt", "third.txt"):
            self.assertEqual((self.root / "links" / "d" / name).read_bytes(), self.payload)
        # A link to a member that is not stored before it has no data to give.
        with tarfile.open(self.root / "dangling.tar", "w", format=tarfile.GNU_FORMAT) as output:
            entry = tarfile.TarInfo("orphan.txt")
            entry.type = tarfile.LNKTYPE
            entry.linkname = "missing.txt"
            output.addfile(entry)
        result = self.run_xfu("x", "dangling.tar", "--reader", "native", "-odangling",
                              success=False)
        self.assertIn("orphan.txt -- FAILED", result.stdout + result.stderr)
        self.assertFalse((self.root / "dangling" / "orphan.txt").exists())

    def test_newc_hard_links_keep_their_data(self):
        self.require("format", "cpio_newc", operation=0)

        def record(name, data, inode, nlink):
            name = name.encode("ascii") + b"\0"
            fields = (inode, 0o100644, 0, 0, nlink, 0, len(data), 8, 1, 0, 0,
                      len(name), 0)
            header = b"070701" + "".join(f"{value:08X}" for value in fields).encode("ascii")
            return (header + name + b"\0" * (-(len(header) + len(name)) % 4) +
                    data + b"\0" * (-len(data) % 4))

        # GNU cpio stores the data once, with the last link of the inode.
        content = record("one.txt", b"", 7, 3) + record("two.txt", b"", 7, 3)
        content += record("three.txt", self.payload, 7, 3)
        content += record("empty.txt", b"", 9, 1)
        content += record("TRAILER!!!", b"", 0, 1)
        (self.root / "links.cpio").write_bytes(content)
        self.run_xfu("x", "links.cpio", "--reader", "native", "-olinks")
        for name in ("one.txt", "two.txt", "three.txt"):
            self.assertEqual((self.root / "links" / name).read_bytes(), self.payload)
        self.assertEqual((self.root / "links" / "empty.txt").read_bytes(), b"")

    def test_member_paths_longer_than_1023_bytes_extract(self):
        self.require("format", "pax", operation=0)
        if sys.platform.startswith("win"):
            self.skipTest("long POSIX paths only")
        if sys.platform == "darwin":
            # The limit is the system's path limit: 1024 bytes there.
            self.skipTest("macOS limits a path to 1024 bytes")
        name = "/".join(["p" * 100] * 14) + "/leaf.txt"
        with tarfile.open(self.root / "deep.tar", "w", format=tarfile.PAX_FORMAT) as output:
            entry = tarfile.TarInfo(name)
            entry.size = len(self.payload)
            output.addfile(entry, io.BytesIO(self.payload))
        self.run_xfu("x", "deep.tar", "--reader", "native", "-odeep")
        self.assertEqual((self.root / "deep" / name).read_bytes(), self.payload)

    def test_tar_hard_link_chains_and_targets_without_data(self):
        self.require("format", "tar", operation=0)

        def add(output, name, kind=tarfile.REGTYPE, link="", data=b""):
            entry = tarfile.TarInfo(name)
            entry.type = kind
            entry.linkname = link
            entry.size = len(data)
            output.addfile(entry, io.BytesIO(data) if data else None)

        with tarfile.open(self.root / "chains.tar", "w", format=tarfile.GNU_FORMAT) as output:
            add(output, "s1/f.txt", data=self.payload)
            add(output, "s1/cur", tarfile.SYMTYPE, "f.txt")
            add(output, "s1/d", tarfile.DIRTYPE)
            # cp -al / rsnapshot: hard links to a hard link, a symlink, a folder.
            add(output, "s1/g.txt", tarfile.LNKTYPE, "s1/f.txt")
            add(output, "s2/g.txt", tarfile.LNKTYPE, "./s1/g.txt")
            add(output, "s2/cur", tarfile.LNKTYPE, "s1/cur")
            add(output, "s2/d.lnk", tarfile.LNKTYPE, "s1/d/")
            # Stored before the member it names, as tar -r can leave it.
            add(output, "early.txt", tarfile.LNKTYPE, "late.txt")
            add(output, "late.txt", data=b"later\n")
            # A cycle and a missing source have no data anywhere.
            add(output, "x", tarfile.LNKTYPE, "y")
            add(output, "y", tarfile.LNKTYPE, "x")
            add(output, "gone", tarfile.LNKTYPE, "nothere")
        # Test fails the links that extraction fails, and only those.
        tested = self.run_xfu("t", "chains.tar", "--reader", "native", "--verbose", success=False)
        output = tested.stdout + tested.stderr
        self.assertEqual(output.count("FAILED"), 3, output)
        for name in ("x", "y", "gone"):
            self.assertRegex(output, r"(?m)^%s -- FAILED$" % name)
        result = self.run_xfu("x", "chains.tar", "--reader", "native", "-ochains", success=False)
        output = result.stdout + result.stderr
        for name in ("x", "y", "gone"):
            self.assertIn("  %s -- FAILED" % name, output)
            self.assertFalse((self.root / "chains" / name).exists())
        self.assertIn("12 member(s), 3 failed", output)
        out = self.root / "chains"
        for name in ("s1/f.txt", "s1/g.txt", "s2/g.txt"):
            self.assertEqual((out / name).read_bytes(), self.payload)
        for name in ("s1/cur", "s2/cur", "s2/d.lnk"):
            self.assertEqual((out / name).read_bytes(), b"")
        self.assertEqual((out / "early.txt").read_bytes(), b"later\n")

    def test_tar_hard_links_name_the_path_a_member_extracts_to(self):
        self.require("format", "tar", operation=0)

        def add(output, name, kind=tarfile.REGTYPE, link="", data=b""):
            entry = tarfile.TarInfo(name)
            entry.type = kind
            entry.linkname = link
            entry.size = len(data)
            output.addfile(entry, io.BytesIO(data) if data else None)

        with tarfile.open(self.root / "paths.tar", "w", format=tarfile.GNU_FORMAT) as output:
            add(output, "d/f", data=b"v1\n")
            add(output, "first", tarfile.LNKTYPE, "d/f")
            add(output, "d/f", data=b"v2\n")
            # Spellings of the same path, as tar -P and other writers leave them.
            add(output, "abs", tarfile.LNKTYPE, "/d/f")
            add(output, "dots", tarfile.LNKTYPE, "./d/./f")
            add(output, "slashes", tarfile.LNKTYPE, "d//f")
            add(output, "self", tarfile.LNKTYPE, "self")
            # A chain longer than any fixed depth, each link naming the next.
            for index in range(60):
                add(output, "c%d" % index, tarfile.LNKTYPE, "c%d" % (index + 1))
            add(output, "c60", data=b"end\n")
        tested = self.run_xfu("t", "paths.tar", "--verbose", success=False)
        output = tested.stdout + tested.stderr
        self.assertEqual(output.count("FAILED"), 1, output)
        self.assertRegex(output, r"(?m)^self -- FAILED$")
        self.run_xfu("x", "paths.tar", "-opaths", success=False)
        out = self.root / "paths"
        self.assertEqual((out / "first").read_bytes(), b"v1\n")
        for name in ("d/f", "abs", "dots", "slashes"):
            self.assertEqual((out / name).read_bytes(), b"v2\n", name)
        for index in (0, 30, 59):
            self.assertEqual((out / ("c%d" % index)).read_bytes(), b"end\n")
        self.assertFalse((out / "self").exists())

    def test_tar_symlinks_to_any_target_are_placeholders(self):
        self.require("format", "tar", operation=0)
        # A symbolic link's target is a path from its own folder and is never
        # followed: "../lib/x" (Debian packages, npm .bin links), ".", ".."
        # and "/etc/passwd" alike give an empty placeholder, and Test passes
        # them, as for CPIO.  A hard link to "../x" names no member and fails.
        targets = {"bin/tool": "../lib/tool.so", "node_modules/.bin/cli": "../pkg/cli.js",
                   "up": "..", "self": ".", "abs": "/etc/passwd", "dots": "name.",
                   "plain": "lib/tool.so"}
        with tarfile.open(self.root / "links.tar", "w", format=tarfile.GNU_FORMAT) as output:
            entry = tarfile.TarInfo("lib/tool.so")
            entry.size = len(self.payload)
            output.addfile(entry, io.BytesIO(self.payload))
            for name, target in targets.items():
                entry = tarfile.TarInfo(name)
                entry.type = tarfile.SYMTYPE
                entry.linkname = target
                output.addfile(entry)
        tested = self.run_xfu("t", "links.tar", "--verbose")
        for name in targets:
            self.assertIn(name + " -- OK", tested.stdout + tested.stderr)
        self.run_xfu("x", "links.tar", "-olinks")
        out = self.root / "links"
        self.assertEqual((out / "lib/tool.so").read_bytes(), self.payload)
        for name in targets:
            self.assertFalse((out / name).is_symlink(), name)
            self.assertEqual((out / name).read_bytes(), b"", name)
        with tarfile.open(self.root / "hard.tar", "w", format=tarfile.GNU_FORMAT) as output:
            entry = tarfile.TarInfo("d/up")
            entry.type = tarfile.LNKTYPE
            entry.linkname = "../d/x"
            output.addfile(entry)
        tested = self.run_xfu("t", "hard.tar", "--verbose", success=False)
        self.assertIn("d/up -- FAILED", tested.stdout + tested.stderr)

    def test_cpio_symlinks_are_link_placeholders(self):
        self.require("format", "cpio_newc", operation=0)

        def record(name, data, inode, mode, nlink=1):
            name = name.encode("ascii") + b"\0"
            fields = (inode, mode, 0, 0, nlink, 0, len(data), 8, 1, 0, 0, len(name), 0)
            header = b"070701" + "".join(f"{value:08X}" for value in fields).encode("ascii")
            return (header + name + b"\0" * (-(len(header) + len(name)) % 4) +
                    data + b"\0" * (-len(data) % 4))

        # A hard-linked symbolic link stores its target once, with the last link.
        content = record("f.txt", self.payload, 5, 0o100644)
        content += record("s1/cur", b"", 6, 0o120777, 2) + record("s2/cur", b"f.txt", 6, 0o120777, 2)
        content += record("TRAILER!!!", b"", 0, 0)
        (self.root / "links.cpio").write_bytes(content)
        tested = self.run_xfu("t", "links.cpio", "--reader", "native", "--verbose")
        self.assertNotIn("FAILED", tested.stdout + tested.stderr)
        self.run_xfu("x", "links.cpio", "--reader", "native", "-olinks")
        self.assertEqual((self.root / "links" / "f.txt").read_bytes(), self.payload)
        for name in ("s1/cur", "s2/cur"):
            path = self.root / "links" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_bytes(), b"")

    def test_large_plain_compressed_stream_is_not_copied(self):
        self.require("filter", "gzip")
        # 300 MB that compress well but look like random data: Test once
        # copied the whole stream into its 256 MiB of RAM to look for an
        # archive in it, and failed.
        block = bytes((index * 2654435761 >> 13) & 0xFF for index in range(16384))
        with gzip.GzipFile(self.root / "big.bin.gz", "wb", compresslevel=1, mtime=0) as output:
            for _ in range(300 * 1024 * 1024 // len(block)):
                output.write(block)
        for command in ("t", "l"):
            with self.subTest(command=command):
                result = self.run_xfu(command, "big.bin.gz")
                output = result.stdout + result.stderr
                self.assertNotIn("could not be decoded", output)
                self.assertNotIn("in-memory verification failed", output)
        self.assertIn("1 member(s)", self.run_xfu("l", "big.bin.gz").stdout)

    def test_several_base64_envelopes_are_several_members(self):
        def envelope(name, data):
            import base64
            return b"begin-base64 644 " + name + b"\n" + base64.b64encode(data) + b"\n====\n"

        cases = {
            "two.b64": (envelope(b"a.txt", b"hello\n") + envelope(b"b.txt", b"world\n"),
                        {"a.txt": b"hello\n", "b.txt": b"world\n"}),
            "same.b64": (envelope(b"a.txt", b"hello\n") + envelope(b"a.txt", b"world\n"),
                         {"a.txt": b"hello\n", "a%_2.txt": b"world\n"}),
            "gap.b64": (envelope(b"a.txt", b"hello\n") + b"\nsigned off\n\n" +
                        envelope(b"b.txt", b"world\n"), {"a.txt": b"hello\n", "b.txt": b"world\n"}),
        }
        for archive, (data, members) in cases.items():
            with self.subTest(archive=archive):
                (self.root / archive).write_bytes(data)
                self.assertIn("%d member(s)" % len(members), self.run_xfu("l", archive).stdout)
                self.run_xfu("t", archive)
                destination = self.root / ("out-" + archive)
                self.run_xfu("x", archive, "-o" + str(destination))
                self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, members)
        # A damaged second envelope is a member that fails, not one dropped.
        (self.root / "damaged.b64").write_bytes(
            envelope(b"a.txt", b"hello\n") + b"begin-base64 644 b.txt\n!!! not base64 !!!\n====\n")
        result = self.run_xfu("t", "damaged.b64", "--verbose", success=False)
        self.assertIn("b.txt -- FAILED", result.stdout + result.stderr)

    def test_text_that_starts_like_an_envelope_is_text(self):
        for name, data in (("meeting.txt", b"begin the meeting at 10\nthen lunch\n"),
                           ("header.txt", b"begin-base64 is a header\nhello\n")):
            with self.subTest(name=name):
                (self.root / name).write_bytes(data)
                result = self.run_xfu("l", name, success=False)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 2, output)
                self.assertIn(name + ": Text cannot be opened as an archive", output)
                self.assertNotIn("envelope", output)
        # A well-formed header with a damaged body is still an error.
        (self.root / "damaged.uue").write_bytes(b"begin 644 notes.txt\nnot uuencoded at all\n")
        result = self.run_xfu("l", "damaged.uue", success=False)
        self.assertIn("encoded envelope could not be decoded", result.stdout + result.stderr)

    def test_base64_envelope_headers_follow_one_set_of_rules(self):
        import base64

        def envelope(name, data, mode=b"644"):
            return (b"begin-base64 " + mode + b" " + name + b"\n" +
                    base64.encodebytes(data) + b"====\n")

        hello, world, third = b"hello\n", b"world\n", b"third\n"
        cases = {
            # sharutils prints the mode with %o: 100644 has six digits.
            "mode6.b64": (envelope(b"a.txt", hello) + envelope(b"b.txt", world, b"100644"),
                          {"a.txt": hello, "b.txt": world}, ()),
            "mode6first.b64": (envelope(b"a.txt", hello, b"100644") + envelope(b"b.txt", world),
                               {"a.txt": hello, "b.txt": world}, ()),
            "crlf.b64": ((envelope(b"a.txt", hello) + envelope(b"b.txt", world, b"100644"))
                         .replace(b"\n", b"\r\n"), {"a.txt": hello, "b.txt": world}, ()),
            # A name that is no file name gives the default one.
            "control.b64": (envelope(b"a.txt", hello) + envelope(b"b\x1b[2J.txt", world),
                            {"a.txt": hello, "payload": world}, ()),
            "control-first.b64": (envelope(b"a\x01.txt", hello), {"payload": hello}, ()),
            # Lines that start like a header but are none are damaged
            # members: listed, failed, and the envelopes after them read.
            "prose.b64": (envelope(b"a.txt", hello) + b"begin-base64 is a header\nhello\n" +
                          envelope(b"c.txt", third), {"a.txt": hello, "c.txt": third}, ("payload",)),
            "mode7.b64": (envelope(b"a.txt", hello) + envelope(b"b.txt", world, b"1006440") +
                          envelope(b"c.txt", third), {"a.txt": hello, "c.txt": third}, ("payload",)),
            "damaged.b64": (envelope(b"a.txt", hello) + b"begin-base64 644 b.txt\n!!! no !!!\n====\n" +
                            envelope(b"c.txt", third), {"a.txt": hello, "c.txt": third}, ("b.txt",)),
            "long-gap.b64": (envelope(b"a.txt", hello) + b"x" * 3000 + b"\n" + envelope(b"c.txt", third),
                             {"a.txt": hello, "c.txt": third}, ()),
        }
        for archive, (data, members, failed) in cases.items():
            with self.subTest(archive=archive):
                (self.root / archive).write_bytes(data)
                listed = self.run_xfu("l", archive).stdout
                self.assertIn("%d member(s)" % (len(members) + len(failed)), listed)
                tested = self.run_xfu("t", archive, "--verbose", success=not failed)
                output = tested.stdout + tested.stderr
                for name in failed:
                    self.assertIn(name + " -- FAILED", output)
                for name in members:
                    self.assertIn(name + " -- OK", output)
                destination = self.root / ("out-" + archive)
                self.run_xfu("x", archive, "-o" + str(destination), success=not failed)
                self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, members)

    def test_base64_body_that_stops_before_its_terminator(self):
        import base64
        import os
        # The first name holds ':', so the whole file goes to the Base64
        # reader; 80 KB of data takes the body past its 64 KiB window.
        data = os.urandom(80000)
        body = b"begin-base64 644 x:a.txt\n" + base64.encodebytes(data)
        tail = b"begin-base64 644 c.txt\nY2MK\n====\n"
        cases = {
            "signature.b64": (body + b"-- signature\n" + tail, True),
            "next.b64": (body + tail, False),
            "blank.b64": (body + b"   \n\n", False),
        }
        for archive, (content, damaged) in cases.items():
            with self.subTest(archive=archive):
                (self.root / archive).write_bytes(content)
                tested = self.run_xfu("t", archive, "--verbose", success=False)
                output = tested.stdout + tested.stderr
                self.assertIn("a.txt -- FAILED" if damaged else "a.txt -- OK", output)
                if archive != "blank.b64":
                    self.assertIn("c.txt -- OK", output)
                    self.assertIn("2 member(s)", self.run_xfu("l", archive, success=False).stdout)

    def check_base64_members(self, archive, members, failed=(), code=0,
                             extracted_members=None):
        """l, t --verbose and x of `archive` exit with `code`: `members`
        decode and are extracted, `failed` fail."""
        listed = self.run_xfu("l", archive, success=not code)
        output = listed.stdout + listed.stderr
        self.assertEqual(listed.returncode, code, output)
        self.assertIn("%d member(s)" % (len(members) + len(failed)), output)
        tested = self.run_xfu("t", archive, "--verbose", success=not code)
        output = tested.stdout + tested.stderr
        self.assertEqual(tested.returncode, code, output)
        for name in members:
            self.assertIn(name + " -- OK", output)
        for name in failed:
            self.assertIn(name + " -- FAILED", output)
        self.assertEqual(output.count("-- FAILED"), len(failed), output)
        destination = self.root / ("out-" + archive)
        extracted = self.run_xfu("x", archive, "-o" + str(destination), success=not code)
        self.assertEqual(extracted.returncode, code, extracted.stdout + extracted.stderr)
        expected = members if extracted_members is None else extracted_members
        self.assertEqual({p.name: read_path_bytes(p) for p in destination.iterdir()}
                         if destination.exists() else {}, expected)

    def test_base64_lost_terminator_whatever_the_payload_length(self):
        import base64
        import random
        # The first name holds ':', so the whole file goes to the Base64
        # reader.  A body that only blank lines separate from the next
        # envelope, from NUL or 0x1A padding or from the end of the input
        # lost its "====" line: it decodes and the file reads as incomplete,
        # inside the 64 KiB window and past it, whether or not its data ends
        # in '=' padding (length mod 3).  The "begin" of the next header is
        # never taken for data.
        tail = b"begin-base64 644 c.txt\nY2MK\n====\n"
        follows = {
            "next": (tail, True),
            "blank-next": (b"\n" + tail, True),
            "blanks-next": (b" \t\n\r\n\n" + tail, True),
            "nul": (b"\0" * 512, False),
            "blank-nul": (b"\n  \n" + b"\0" * 16, False),
            "sub": (b"\x1a", False),
            "eof": (b"", False),
        }
        for size in (1000, 1001, 1002, 80000, 81000, 81001):
            data = random.Random(size).randbytes(size)
            body = b"begin-base64 644 x:a.txt\n" + base64.encodebytes(data)
            for kind, (after, more) in follows.items():
                archive = "lost-%d-%s.b64" % (size, kind)
                with self.subTest(archive=archive):
                    (self.root / archive).write_bytes(body + after)
                    members = {"a.txt": data, "c.txt": b"cc\n"} if more else {"a.txt": data}
                    self.check_base64_members(archive, members, code=1)
                    listed = self.run_xfu("l", archive, success=False)
                    self.assertIn(archive + ": incomplete archive", listed.stdout + listed.stderr)

    def test_base64_later_envelope_that_lost_its_terminator(self):
        import base64
        import random
        # A later envelope cut short or without its "====" line reads like a
        # first one: it decodes and the file is incomplete, so no cut of a
        # valid file passes as complete.  Without the terminator, text in the
        # Base64 alphabet after the body's last, shorter line is no data:
        # that member fails instead of decoding a few bytes too many.
        data = random.Random(1).randbytes(81000)
        hello = b"hello\n"
        first = b"begin-base64 644 a.txt\n" + base64.b64encode(hello) + b"\n====\n"
        header = b"begin-base64 644 b.txt\n"
        body = base64.encodebytes(data)
        lines = body.split(b"\n")
        cut = b"\n".join(lines[:700]) + b"\n"
        tail = b"begin-base64 644 c.txt\nY2MK\n====\n"
        for archive, content, members in (
                ("later-cut.b64", first + header + cut, {"a.txt": hello, "b.txt": base64.decodebytes(cut)}),
                ("later-nul.b64", first + header + body + b"\0" * 64, {"a.txt": hello, "b.txt": data}),
                ("later-next.b64", first + header + body + b"\n" + tail,
                 {"a.txt": hello, "b.txt": data, "c.txt": b"cc\n"})):
            with self.subTest(archive=archive):
                (self.root / archive).write_bytes(content)
                self.check_base64_members(archive, members, code=1)
                listed = self.run_xfu("l", archive, success=False)
                self.assertIn(archive + ": incomplete archive", listed.stdout + listed.stderr)
        for archive, content, members in (
                ("later-text.b64", first + header + body + b"text\n" + b"\0" * 16, {"a.txt": hello}),
                ("later-text-eof.b64", first + header + body + b"abcd\n", {"a.txt": hello}),
                ("later-bye.b64", first + header + body + b"Bye\n\n" + tail, {"a.txt": hello, "c.txt": b"cc\n"}),
                ("first-text.b64", b"begin-base64 644 x:b.txt\n" + body + b"text\n", {})):
            with self.subTest(archive=archive):
                (self.root / archive).write_bytes(content)
                tested = self.run_xfu("t", archive, "--verbose", success=False)
                output = tested.stdout + tested.stderr
                self.assertEqual(tested.returncode, 1, output)
                self.assertIn("b.txt -- FAILED", output)
                destination = self.root / ("out-" + archive)
                self.run_xfu("x", archive, "-o" + str(destination), success=False)
                self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}
                                 if destination.exists() else {}, members)
        # Every cut inside the later envelope, but one inside the line break
        # after its "====", fails Test.
        full = first + header + body + b"====\n"
        start = len(first) + len(header)
        for offset in list(range(start, start + 80)) + list(range(len(full) - 8, len(full) - 1)):
            with self.subTest(offset=offset):
                (self.root / "cut.b64").write_bytes(full[:offset])
                self.run_xfu("t", "cut.b64", success=False)

    def test_base64_names_up_to_255_bytes(self):
        # Several envelopes keep the names one envelope keeps: any file name
        # of up to 255 bytes; a repeated one too long for its "%_<n>" gives
        # "payload%_<n>".
        long_name = "n" * 196 + ".txt"
        longest = "m" * 251 + ".txt"
        envelope = "begin-base64 644 %s\naGkK\n====\n"
        cases = {
            "one.b64": (envelope % long_name, {long_name: b"hi\n"}),
            "two.b64": (envelope % "ok.txt" + "\n" + envelope % long_name,
                        {"ok.txt": b"hi\n", long_name: b"hi\n"}),
            "same.b64": (envelope % longest * 3,
                         {longest: b"hi\n", "payload%_2": b"hi\n", "payload%_3": b"hi\n"}),
        }
        extracted = {}
        if os.name == "nt":
            # The ordinary multi-envelope reader uses its documented short
            # fallback when joining the member to this temporary directory
            # would exceed MAX_PATH.
            extracted["two.b64"] = {"ok.txt": b"hi\n", "payload": b"hi\n"}
            extracted["same.b64"] = {"payload": b"hi\n", "payload%_2": b"hi\n",
                                      "payload%_3": b"hi\n"}
        for archive, (text, members) in cases.items():
            with self.subTest(archive=archive):
                (self.root / archive).write_text(text, encoding="ascii")
                self.check_base64_members(archive, members,
                                          extracted_members=extracted.get(archive))

    def test_base64_terminator_may_end_in_blanks(self):
        import base64
        import random
        tail = b"begin-base64 644 c.txt\nY2MK\n====\n"
        for size in (1000, 81000, 81001):
            data = random.Random(size).randbytes(size)
            for name in (b"a.txt", b"x:a.txt"):
                for kind, end in (("space", b"==== \n" + tail), ("tab-crlf", b"====\t \r\n" + tail),
                                  ("eof", b"====  ")):
                    archive = "blank-term-%d-%s-%s.b64" % (size, kind, "colon" if b":" in name else "safe")
                    with self.subTest(archive=archive):
                        (self.root / archive).write_bytes(
                            b"begin-base64 644 " + name + b"\n" + base64.encodebytes(data) + end)
                        members = {"a.txt": data, "c.txt": b"cc\n"} if end != b"====  " else {"a.txt": data}
                        self.check_base64_members(archive, members)

    def test_base64_body_broken_past_its_window_still_fails(self):
        import base64
        import random
        # Other text, a "====" line that is not exact, or a lone last symbol
        # still fail the envelope, whose neighbours are read, whether that
        # happens inside the 64 KiB detection window or past it.
        tail = b"begin-base64 644 c.txt\nY2MK\n====\n"
        for size in (1000, 81000):
            data = random.Random(7).randbytes(size)
            body = b"begin-base64 644 x:a.txt\n" + base64.encodebytes(data)
            for kind, after, more in (("five", b"=====\n" + tail, True), ("junk", b"==== x\n" + tail, True),
                                      ("text", b"\n-- sig\n" + tail, True), ("lone", b"Q\n\n" + tail, True),
                                      ("lone-eof", b"Q\n", False)):
                archive = "broken-%d-%s.b64" % (size, kind)
                with self.subTest(archive=archive):
                    (self.root / archive).write_bytes(body + after)
                    self.check_base64_members(archive, {"c.txt": b"cc\n"} if more else {}, ("a.txt",), code=1)
        (self.root / "sig-small.b64").write_bytes(
            b"begin-base64 644 x:a.txt\naGVsbG8K\n\n-- sig\n" + tail)
        self.check_base64_members("sig-small.b64", {"c.txt": b"cc\n"}, ("a.txt",), code=1)

    def test_base64_padding_at_the_end_of_the_window(self):
        import base64
        import random
        # The first envelope's '=' padding is the last byte of the 64 KiB
        # window, and more than 1 KiB of a second envelope follows.
        data = random.Random(3).randbytes(48451)
        more = random.Random(4).randbytes(3000)
        text = base64.b64encode(data)
        body = b"".join(text[i:i + 76] + b"\n" for i in range(0, len(text), 76))
        name = b"a" * (65536 + 1 - len(body) - len(b"begin-base64 644 \n") - 4) + b".bin"
        envelope = b"begin-base64 644 " + name + b"\n" + body
        self.assertEqual(envelope[65535:65537], b"=\n")
        (self.root / "edge.b64").write_bytes(
            envelope + b"====\n" + b"begin-base64 644 c.bin\n" + base64.encodebytes(more) + b"====\n")
        self.check_base64_members("edge.b64", {name.decode(): data, "c.bin": more})

    def test_base64_header_with_a_long_path(self):
        import base64
        # 1220 bytes of path: the probe and the Base64 reader both read
        # header lines of up to 4096 bytes and take the last component.
        path = b"/".join(b"d%02d" % i + b"x" * 97 for i in range(12)) + b"/file.txt"
        self.assertGreater(len(path), 1200)
        envelope = b"begin-base64 644 " + path + b"\n" + base64.b64encode(b"hello\n") + b"\n====\n"
        tail = b"begin-base64 644 c.txt\nY2MK\n====\n"
        for archive, content, members in (
                ("longpath.b64", envelope, {"file.txt": b"hello\n"}),
                ("longpath-two.b64", envelope + tail, {"file.txt": b"hello\n", "c.txt": b"cc\n"}),
                ("longpath-second.b64", tail + envelope, {"file.txt": b"hello\n", "c.txt": b"cc\n"})):
            with self.subTest(archive=archive):
                (self.root / archive).write_bytes(content)
                self.assertIn(archive + ": Base64", self.run_xfu("l", archive).stdout)
                self.check_base64_members(archive, members)

    def test_gnu_crc_cpio_with_links(self):
        self.require("format", "cpio_crc", operation=0)

        def record(name, data, inode, mode, nlink=1, check=None):
            name = name.encode("ascii") + b"\0"
            if check is None:
                check = sum(data) & 0xFFFFFFFF
            fields = (inode, mode, 0, 0, nlink, 0, len(data), 8, 1, 0, 0, len(name), check)
            header = b"070702" + "".join(f"{value:08X}" for value in fields).encode("ascii")
            return (header + name + b"\0" * (-(len(header) + len(name)) % 4) +
                    data + b"\0" * (-len(data) % 4))

        def archive(payload):
            # As GNU cpio -o -H crc writes it: a symbolic link's sum is 0,
            # and a hard-linked file's data comes with its last link.
            content = record(".", b"", 1, 0o40755, 2)
            content += record("link", b"a.txt", 2, 0o120777, check=0)
            content += record("hard.txt", b"", 3, 0o100644, 2)
            content += record("a.txt", payload, 3, 0o100644, 2)
            content += record("sub", b"", 4, 0o40755, 2)
            content += record("sub/b.bin", self.payload, 5, 0o100644)
            content += record("TRAILER!!!", b"", 0, 0)
            return content + b"\0" * (-len(content) % 512)

        (self.root / "gnu.cpio").write_bytes(archive(b"hello\n"))
        listed = self.run_xfu("l", "gnu.cpio").stdout
        self.assertIn("gnu.cpio: CPIO", listed)
        self.assertIn("6 member(s)", listed)
        # The 070702 checksum is a byte sum: it is not shown as a CRC32.
        self.assertNotIn("CRC32", self.run_xfu("l", "gnu.cpio", "--advanced").stdout)
        tested = self.run_xfu("t", "gnu.cpio", "--verbose")
        self.assertNotIn("FAILED", tested.stdout + tested.stderr)
        self.run_xfu("x", "gnu.cpio", "-ognu")
        self.assertEqual((self.root / "gnu" / "hard.txt").read_bytes(), b"hello\n")
        self.assertEqual((self.root / "gnu" / "sub" / "b.bin").read_bytes(), self.payload)
        # A damaged file still lists; Test and Extract fail it, and its hard
        # link, which shares its data, but no other member.
        damaged = bytearray(archive(b"hello\n"))
        damaged[damaged.index(b"hello\n") + 1] ^= 0x20
        (self.root / "damaged.cpio").write_bytes(damaged)
        self.assertIn("6 member(s)", self.run_xfu("l", "damaged.cpio").stdout)
        tested = self.run_xfu("t", "damaged.cpio", "--verbose", success=False)
        output = tested.stdout + tested.stderr
        self.assertRegex(output, r"(?m)^hard\.txt -- FAILED$")
        self.assertRegex(output, r"(?m)^a\.txt -- FAILED$")
        self.assertRegex(output, r"(?m)^sub/b\.bin -- OK$")
        self.assertIn("6 member(s), 2 failed", output)
        result = self.run_xfu("x", "damaged.cpio", "-odamaged", success=False)
        self.assertIn("6 member(s), 2 failed", result.stdout + result.stderr)
        self.assertFalse((self.root / "damaged" / "a.txt").exists())
        self.assertEqual((self.root / "damaged" / "sub" / "b.bin").read_bytes(), self.payload)

    def test_large_text_record_formats_inside_filters(self):
        import lzma
        lines = []
        for record in range(20):
            lines.append(">seq%d sample\n" % record)
            for line in range(4000):
                lines.append("ACGT"[(record + line) % 4] * 35 + "TGCA"[line % 4] * 35 + "\n")
        text = "".join(lines).encode("ascii")
        self.assertGreater(len(text), 5 * 1024 * 1024)
        (self.root / "seq.fa.gz").write_bytes(gzip.compress(text, compresslevel=1, mtime=0))
        (self.root / "seq.fa.xz").write_bytes(lzma.compress(text, preset=0))
        for archive in ("seq.fa.gz", "seq.fa.xz"):
            with self.subTest(archive=archive):
                listed = self.run_xfu("l", archive).stdout
                self.assertIn(archive + ": genomics fasta", listed)
                self.assertIn("20 member(s)", listed)

    @unittest.skipIf(sys.platform.startswith("win"), "POSIX file names only")
    def test_raw_reader_says_why_a_name_cannot_be_a_member(self):
        for name, reason in (("x\x1b[2Jy.dat", "its name holds a control character"),):
            with self.subTest(reason=reason):
                (self.root / name).write_bytes(b"raw\n")
                for command in ("l", "t"):
                    result = self.run_xfu(command, name, "--reader", "native:raw", success=False)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    shown = name.replace("\x1b", "\\x1B")
                    self.assertIn(shown + ": cannot be read as one file: " + reason, result.stderr)
        # ':' is an ordinary character of a POSIX name: such a file is its
        # own member, as it is extracted (Windows refuses it: a stream).
        (self.root / "a:b.dat").write_bytes(b"raw\n")
        self.assertIn("a:b.dat -- OK\n", self.run_xfu("t", "a:b.dat", "--reader", "native:raw",
                                                      "--verbose").stdout)
        self.run_xfu("x", "a:b.dat", "--reader", "native:raw", "-oraw-colon")
        self.assertEqual((self.root / "raw-colon" / "a:b.dat").read_bytes(), b"raw\n")

    def test_raw_member_names_up_to_name_max_extract(self):
        import base64
        import binascii
        long_b64 = "n" * 230 + ".txt"
        long_uue = "u" * 236 + ".txt"
        long_raw = "r" * 251 + ".txt"
        (self.root / "long.b64").write_bytes(
            b"begin-base64 644 " + long_b64.encode() + b"\n" + base64.b64encode(b"b64\n") + b"\n====\n")
        (self.root / "long.uue").write_bytes(
            b"begin 644 " + long_uue.encode() + b"\n" + binascii.b2a_uu(b"uue\n") + b"`\nend\n")
        windows_extended_path(self.root / long_raw).write_bytes(b"raw\n")
        (self.root / "long.b64.gz").write_bytes(gzip.compress((self.root / "long.b64").read_bytes(), mtime=0))
        for archive, name, data, extra in (("long.b64", long_b64, b"b64\n", ()),
                                           ("long.b64.gz", long_b64, b"b64\n", ()),
                                           ("long.uue", long_uue, b"uue\n", ()),
                                           (long_raw, long_raw, b"raw\n", ("--reader", "native:raw"))):
            with self.subTest(archive=archive[:20]):
                destination = self.root / "out-long"
                if destination.exists():
                    for path in destination.iterdir():
                        windows_extended_path(path).unlink()
                self.run_xfu("x", archive, *extra, "-o" + str(destination))
                self.assertEqual([p.name for p in destination.iterdir()], [name])
                self.assertEqual(read_path_bytes(destination / name), data)

    def test_xar_base64_names_and_times(self):
        self.require("format", "xar", operation=0)
        name = "n\ufffd.txt"  # Base64 "bu+/vS50eHQ=" holds a slash
        toc = ('<?xml version="1.0" encoding="UTF-8"?><xar><toc><file id="1">'
               '<name enctype="base64">bu+/vS50eHQ=</name><type>file</type>'
               '<mtime>2020-01-02T03:04:05Z</mtime><data><offset>0</offset>'
               f'<length>{len(self.payload)}</length><size>{len(self.payload)}</size>'
               '<encoding style="application/octet-stream"/></data></file>'
               '</toc></xar>').encode("utf-8")
        packed = zlib.compress(toc)
        header = b"xar!" + struct.pack(">HHQQI", 28, 1, len(packed), len(toc), 0)
        (self.root / "named.xar").write_bytes(header + packed + self.payload)
        listing = self.run_xfu("l", "named.xar", "--reader", "native", "--advanced")
        self.assertIn(name, listing.stdout)
        self.assertIn("Timestamp: 1577934245", listing.stdout)
        self.run_xfu("x", "named.xar", "--reader", "native", "-onamed")
        self.assertEqual((self.root / "named" / name).read_bytes(), self.payload)

    def test_xar_hard_links_keep_their_data(self):
        self.require("format", "xar", operation=0)
        # xar and bsdtar store a hard-linked file's data once, on the entry
        # whose <type link="original">hardlink</type>; the others name its
        # <file> id.  Each takes that data, before or after it in the table
        # of contents and through other links; one whose id names no file
        # fails, in Test and Extract.
        data = b"hello world\n"
        stored = zlib.compress(data)

        def entry(ident, name, link, with_data):
            body = ('<data><offset>0</offset><length>%d</length><size>%d</size>'
                    '<encoding style="application/x-gzip"/></data>' % (len(stored), len(data))
                    if with_data else "")
            return ('<file id="%d"><name>%s</name><type link="%s">hardlink</type>%s</file>'
                    % (ident, name, link, body))

        def xar(name, entries):
            toc = ('<?xml version="1.0" encoding="UTF-8"?><xar><toc>' + "".join(entries) +
                   '</toc></xar>').encode("utf-8")
            packed = zlib.compress(toc)
            header = b"xar!" + struct.pack(">HHQQI", 28, 1, len(packed), len(toc), 0)
            (self.root / name).write_bytes(header + packed + stored)

        cases = {
            "after.xar": [entry(2, "a.txt", "original", True), entry(3, "b.txt", "2", False)],
            "before.xar": [entry(2, "a.txt", "3", False), entry(3, "b.txt", "original", True)],
            "chain.xar": [entry(2, "a.txt", "original", True), entry(3, "b.txt", "2", False),
                          entry(4, "c.txt", "3", False)],
        }
        for archive, entries in cases.items():
            with self.subTest(archive=archive):
                xar(archive, entries)
                names = re.findall(r"<name>([^<]+)</name>", "".join(entries))
                tested = self.run_xfu("t", archive, "--verbose")
                for name in names:
                    self.assertIn(name + " -- OK", tested.stdout + tested.stderr)
                destination = self.root / ("out-" + archive)
                self.run_xfu("x", archive, "-o" + str(destination))
                self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()},
                                 {name: data for name in names})
        xar("broken.xar", [entry(2, "a.txt", "original", True), entry(3, "b.txt", "9", False)])
        tested = self.run_xfu("t", "broken.xar", "--verbose", success=False)
        self.assertIn("b.txt -- FAILED", tested.stdout + tested.stderr)
        self.assertIn("a.txt -- OK", tested.stdout + tested.stderr)
        destination = self.root / "out-broken"
        self.run_xfu("x", "broken.xar", "-o" + str(destination), success=False)
        self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, {"a.txt": data})
        # A link to a folder's id takes no data: an empty placeholder, as a
        # TAR hard link to a folder gives.
        folder = '<file id="4"><name>d</name><type>directory</type></file>'
        xar("folder.xar", [entry(2, "a.txt", "original", True), folder,
                           entry(3, "b.txt", "4", False)])
        tested = self.run_xfu("t", "folder.xar", "--verbose")
        self.assertIn("b.txt -- OK", tested.stdout + tested.stderr)
        destination = self.root / "out-folder"
        self.run_xfu("x", "folder.xar", "-o" + str(destination))
        self.assertEqual((destination / "b.txt").read_bytes(), b"")
        self.assertEqual((destination / "a.txt").read_bytes(), data)
        self.assertTrue((destination / "d").is_dir())

    def test_iso_rock_ridge_name_in_continuation_area(self):
        self.require("format", "iso9660", operation=0)

        def both(value, size):
            return value.to_bytes(size, "little") + value.to_bytes(size, "big")

        def record(extent, size, flags, identifier, system_use=b""):
            body = (b"\0" + both(extent, 4) + both(size, 4) + bytes(7) +
                    bytes([flags, 0, 0]) + both(1, 2) + bytes([len(identifier)]) + identifier)
            body += b"\0" * (len(identifier) % 2 == 0) + system_use
            body += b"\0" * (len(body) % 2 == 0)
            return bytes([len(body) + 1]) + body

        sector = 2048
        name = b"r" * 150 + b"-continued-" + b"s" * 39 + b".txt"
        first = b"NM" + bytes([155, 1, 1]) + name[:150]
        rest = b"NM" + bytes([5 + len(name) - 150, 1, 0]) + name[150:]
        continuation = b"CE" + bytes([28, 1]) + both(19, 4) + both(0, 4) + both(len(rest), 4)
        root = (record(18, sector, 2, b"\0") + record(18, sector, 2, b"\1") +
                record(20, len(self.payload), 0, b"LONG.TXT;1", first + continuation))
        primary = bytearray(sector)
        primary[0:7] = b"\1CD001\1"
        primary[80:88] = both(21, 4)
        primary[120:128] = both(1, 2) + both(1, 2)
        primary[128:132] = both(sector, 2)
        primary[156:190] = record(18, sector, 2, b"\0")
        primary[881] = 1
        terminator = b"\xffCD001\1".ljust(sector, b"\0")
        image = (bytes(16 * sector) + bytes(primary) + terminator + root.ljust(sector, b"\0") +
                 rest.ljust(sector, b"\0") + self.payload.ljust(sector, b"\0"))
        (self.root / "long.iso").write_bytes(image)
        listing = self.run_xfu("l", "long.iso", "--reader", "native")
        self.assertIn(name.decode("ascii"), listing.stdout)
        self.run_xfu("x", "long.iso", "--reader", "native", "-olong-iso")
        self.assertEqual(read_path_bytes(self.root / "long-iso" / name.decode("ascii")), self.payload)

    def test_iso_names_without_an_extension(self):
        self.require("format", "iso9660", operation=0)
        # Without Rock Ridge, ECMA-119 writes the '.' before an empty
        # extension: "README.;1" (or "README." without a version) is README.

        def both(value, size):
            return value.to_bytes(size, "little") + value.to_bytes(size, "big")

        def record(extent, size, flags, identifier):
            body = (b"\0" + both(extent, 4) + both(size, 4) + bytes(7) +
                    bytes([flags, 0, 0]) + both(1, 2) + bytes([len(identifier)]) + identifier)
            body += b"\0" * (len(identifier) % 2 == 0)
            return bytes([len(body) + 1]) + body

        sector = 2048
        files = ((b"README.;1", self.payload), (b"MAKEFILE.", b"all:\n"), (b"NOTES.TXT;1", b"note"))
        root, data, extent = record(18, sector, 2, b"\0") + record(18, sector, 2, b"\1"), b"", 19
        for identifier, content in files:
            root += record(extent, len(content), 0, identifier)
            padded = content + b"\0" * (-len(content) % sector)
            data += padded
            extent += len(padded) // sector
        primary = bytearray(sector)
        primary[0:7] = b"\1CD001\1"
        primary[80:88] = both(extent, 4)
        primary[120:128] = both(1, 2) + both(1, 2)
        primary[128:132] = both(sector, 2)
        primary[156:190] = record(18, sector, 2, b"\0")
        primary[881] = 1
        terminator = b"\xffCD001\1".ljust(sector, b"\0")
        image = (bytes(16 * sector) + bytes(primary) + terminator + root.ljust(sector, b"\0") + data)
        (self.root / "plain.iso").write_bytes(image)
        listing = self.run_xfu("l", "plain.iso")
        self.assertIn("plain.iso: ISO9660", listing.stdout)
        self.run_xfu("t", "plain.iso")
        self.run_xfu("x", "plain.iso", "-oplain")
        out = self.root / "plain"
        self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()},
                         {"README": self.payload, "MAKEFILE": b"all:\n", "NOTES.TXT": b"note"})

    def test_zstd_stream_over_its_reader_limit_is_not_damaged(self):
        self.require("filter", "zstd", operation=0)
        # A valid zstd frame of 8193 RLE blocks of 128 KiB decodes to just
        # over the 1 GiB the in-memory reader takes: it is too large, not a
        # damaged stream; a cut one is damaged.

        def frame(blocks):
            data = b"\x28\xb5\x2f\xfd\x00\x38"
            for index in range(blocks):
                header = (1 if index == blocks - 1 else 0) | 2 | (128 * 1024) << 3
                data += header.to_bytes(3, "little") + b"\0"
            return data

        (self.root / "big.zst").write_bytes(frame(8193))
        (self.root / "cut.zst").write_bytes(frame(8193)[:-3])
        (self.root / "small.zst").write_bytes(frame(8))
        for command in ("l", "t"):
            with self.subTest(command=command):
                output = self.run_xfu(command, "big.zst", success=False)
                text = output.stdout + output.stderr
                self.assertEqual(output.returncode, 2, text)
                self.assertIn("big.zst: the ZSTD stream is too large to open", text)
                self.assertNotIn("damaged", text)
                output = self.run_xfu(command, "cut.zst", success=False)
                self.assertIn("cut.zst: ZSTD could not be read; the compressed stream is damaged",
                              output.stdout + output.stderr)
        self.assertIn("1 member(s)", self.run_xfu("l", "small.zst").stdout)

    def test_7zip_test_checks_a_member_larger_than_its_memory(self):
        self.require("format", "7zip", operation=0)
        import lzma
        # Test checks a 7-Zip folder's members as it decodes it, so a member
        # larger than the 256 MiB Test may keep in memory passes, and a wrong
        # CRC still fails it.

        def number(value):
            first, mask = 0, 0x80
            for extra in range(9):
                if extra == 8 or value < 1 << (7 * (extra + 1)):
                    break
                first |= mask
                mask >>= 1
            if extra < 8:
                first |= value >> (8 * extra)
            return bytes([first & 0xFF]) + (value & ((1 << (8 * extra)) - 1)).to_bytes(extra, "little")

        size = 272 * 1024 * 1024
        compressor = lzma.LZMACompressor(format=lzma.FORMAT_RAW, filters=[
            {"id": lzma.FILTER_LZMA2, "dict_size": 1 << 20, "preset": 1}])
        chunk, packed, crc, done = bytes(1 << 20), [compressor.compress(self.payload)], zlib.crc32(self.payload), len(self.payload)
        while done < size:
            part = chunk[:min(len(chunk), size - done)]
            packed.append(compressor.compress(part))
            crc = zlib.crc32(part, crc)
            done += len(part)
        packed.append(compressor.flush())
        packed = b"".join(packed)
        name = "big.bin".encode("utf-16-le") + b"\0\0"
        for archive, stored in (("big.7z", crc), ("bad.7z", crc ^ 1)):
            with self.subTest(archive=archive):
                header = (b"\x01\x04\x06" + number(0) + number(1) + b"\x09" + number(len(packed)) + b"\x00" +
                          b"\x07\x0b" + number(1) + b"\x00" + number(1) + b"\x21\x21" + number(1) + b"\x10" +
                          b"\x0c" + number(size) + b"\x00" +
                          b"\x08\x0a\x01" + struct.pack("<I", stored) + b"\x00\x00" +
                          b"\x05" + number(1) + b"\x11" + number(len(name) + 1) + b"\x00" + name + b"\x00\x00")
                start = struct.pack("<QQI", len(packed), len(header), zlib.crc32(header))
                (self.root / archive).write_bytes(b"7z\xbc\xaf\x27\x1c\x00\x04" + struct.pack("<I", zlib.crc32(start)) +
                                                  start + packed + header)
                tested = self.run_xfu("t", archive, "--verbose", success=stored == crc)
                output = tested.stdout + tested.stderr
                self.assertIn("big.bin -- OK" if stored == crc else "big.bin -- FAILED", output)
                self.assertNotIn("in-memory verification failed", output)

    def test_zip_after_leading_data(self):
        self.require("format", "zip", operation=0)
        # A ZIP after other data (a script, a self-extractor stub) opens from
        # its end records, with offsets from the start of the ZIP or, as
        # "zip -A" adjusts them, from the start of the file.
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as output:
            output.writestr("a.txt", self.payload)
            output.writestr("d/b.txt", b"second\n")
        plain = buffer.getvalue()
        prefix = b"#!/bin/sh\nexec java -jar \"$0\" \"$@\"\n" + bytes(range(256)) * 12
        adjusted = bytearray(prefix + plain)
        eocd = adjusted.rindex(b"PK\x05\x06")
        count, cd_size, cd_offset = struct.unpack("<HII", adjusted[eocd + 10:eocd + 20])
        struct.pack_into("<I", adjusted, eocd + 16, cd_offset + len(prefix))
        at = len(prefix) + cd_offset
        for _ in range(count):
            local, = struct.unpack("<I", adjusted[at + 42:at + 46])
            struct.pack_into("<I", adjusted, at + 42, local + len(prefix))
            at += 46 + sum(struct.unpack("<HHH", adjusted[at + 28:at + 34]))
        for archive, data in (("prefixed.zip", prefix + plain), ("adjusted.zip", bytes(adjusted)),
                              ("prefixed.bin", prefix + plain)):
            with self.subTest(archive=archive):
                (self.root / archive).write_bytes(data)
                listing = self.run_xfu("l", archive)
                self.assertIn("2 member(s)", listing.stdout)
                self.run_xfu("t", archive)
                destination = self.root / ("out-" + archive)
                self.run_xfu("x", archive, "-o" + str(destination))
                self.assertEqual((destination / "a.txt").read_bytes(), self.payload)
                self.assertEqual((destination / "d" / "b.txt").read_bytes(), b"second\n")

    def test_zip_with_a_damaged_central_directory_is_incomplete(self):
        self.require("format", "zip", operation=0)
        # The end record counts 4 members, and the third central directory
        # entry does not hold up: List and Extract give the members before it
        # and report the archive as incomplete with exit code 1, as Test does.
        with zipfile.ZipFile(self.root / "four.zip", "w") as output:
            for index in range(4):
                output.writestr("m%d.txt" % index, b"member %d\n" % index)
        data = bytearray((self.root / "four.zip").read_bytes())
        third = [m.start() for m in re.finditer(b"PK\x01\x02", bytes(data))][2]
        data[third + 3] ^= 0x40
        (self.root / "cd.zip").write_bytes(bytes(data))
        for command in ("l", "x"):
            with self.subTest(command=command):
                extra = ("-ocd-out",) if command == "x" else ()
                result = self.run_xfu(command, "cd.zip", *extra, success=False)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                self.assertIn("2 member(s)", output)
                self.assertIn("cd.zip: incomplete archive", output)
        self.assertEqual(sorted(p.name for p in (self.root / "cd-out").iterdir()), ["m0.txt", "m1.txt"])
        result = self.run_xfu("t", "cd.zip", success=False)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("4 member(s)", self.run_xfu("l", "four.zip").stdout)

    def test_member_names_up_to_255_bytes_extract(self):
        self.require("format", "zip", operation=0)
        # The extraction stage is a short name in the member's folder: a
        # suffix after a 242-255-byte name would pass NAME_MAX.
        for length in (241, 242, 255):
            name = "n" * (length - 4) + ".txt"
            with self.subTest(length=length):
                with zipfile.ZipFile(self.root / ("n%d.zip" % length), "w") as output:
                    output.writestr("d/" + name, self.payload)
                windows_extended_path(self.root / name).write_bytes(self.payload)
                archives = ["n%d.zip" % length]
                if os.name != "nt":
                    self.run_xfu("a", "n%d.7z" % length, name, "--format=7zip")
                    archives.append("n%d.7z" % length)
                for archive in archives:
                    destination = self.root / ("out-" + archive)
                    self.run_xfu("x", archive, "-o" + str(destination))
                    files = [p for p in windows_extended_path(destination).rglob("*")
                             if p.is_file()]
                    self.assertEqual([p.name for p in files], [name], archive)
                    self.assertEqual(read_path_bytes(files[0]), self.payload, archive)
                windows_extended_path(self.root / name).unlink()

    def test_outer_compression_level(self):
        self.require("format", "pax")
        self.require("filter", "gzip")
        self.run_xfu("a", "level.tar.gz", "alpha.txt", "--format=pax",
                     "--filter=gzip", "--compression-level=6")
        self.check_round_trip("level.tar.gz")

    def test_signed_zstd_compression_level(self):
        self.require("filter", "zstd")
        self.run_xfu("a", "fast.tar.zst", "alpha.txt", "--format=pax",
                     "--filter=zstd", "--compression-level=-3")
        self.check_round_trip("fast.tar.zst")

    def test_raw_stream_requires_one_input(self):
        self.require("format", "raw")
        (self.root / "beta.txt").write_bytes(b"second")
        destination = self.root / "raw.bin"
        destination.write_bytes(b"keep existing archive")
        self.run_xfu("a", destination.name, "alpha.txt", "beta.txt", "--format=raw", success=False)
        self.assertEqual(destination.read_bytes(), b"keep existing archive")
        self.run_xfu("a", destination.name, "alpha.txt", "--format=raw")
        self.check_round_trip(destination.name, "native:raw")

    def test_uncompressed_non_archive_requires_raw_reader(self):
        self.run_xfu("t", "alpha.txt", "--reader", "native", success=False)
        self.run_xfu("t", "alpha.txt", "--reader", "native:raw")

    def test_invalid_options_preserve_destination(self):
        cases = (
            ["--format=does-not-exist"],
            ["--format=pax", "--filter=does-not-exist"],
            ["--format=pax", "--options=xfu-unrecognized-option=1"],
            ["--format=zip", "--compression=does-not-exist"],
        )
        destination = self.root / "keep.bin"
        for options in cases:
            with self.subTest(options=options):
                destination.write_bytes(b"original destination")
                self.run_xfu("a", destination.name, "alpha.txt", *options, success=False)
                self.assertEqual(destination.read_bytes(), b"original destination")

    def test_unavailable_operations_preserve_destination(self):
        destination = self.root / "keep.bin"
        for kind, options in self.capabilities.items():
            for name, (_, create) in options.items():
                if create:
                    continue
                with self.subTest(kind=kind, name=name):
                    destination.write_bytes(b"original destination")
                    arguments = ["--format=" + name] if kind == "format" else [
                        "--format=pax", "--filter=" + name,
                    ]
                    self.run_xfu("a", destination.name, "alpha.txt", *arguments, success=False)
                    self.assertEqual(destination.read_bytes(), b"original destination")

    def test_missing_source_preserves_destination(self):
        # The native writers and the suffix-selected xxfclib writers alike.
        for name, options in (("keep.tar", ["--format=pax"]), ("keep.tar", []),
                              ("keep.tar.gz", []), ("keep.zip", []), ("keep.7z", []),
                              ("keep.cpio", []), ("keep.gz", [])):
            with self.subTest(name=name, options=options):
                destination = self.root / name
                destination.write_bytes(b"original destination")
                self.run_xfu("a", destination.name, "missing-input", *options, success=False)
                self.assertEqual(destination.read_bytes(), b"original destination")
                if name != "keep.gz":
                    self.run_xfu("a", destination.name, "alpha.txt", "missing-input", *options,
                                 success=False)
                    self.assertEqual(destination.read_bytes(), b"original destination")

    def test_archive_cannot_include_itself(self):
        destination = self.root / "self.tar"
        destination.write_bytes(b"original destination")
        self.run_xfu("a", destination.name, destination.name, "--format=pax", success=False)
        self.assertEqual(destination.read_bytes(), b"original destination")

    def make_corrupt_zip(self):
        archive = self.root / "corrupt.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
            output.writestr("alpha.txt", self.payload)
        content = bytearray(archive.read_bytes())
        location = content.index(self.payload)
        content[location] ^= 0x80
        archive.write_bytes(content)
        return archive

    def test_corrupt_member_fails_verification(self):
        archive = self.make_corrupt_zip()
        self.run_xfu("t", archive.name, "--reader", "native", success=False)

    def test_corrupt_extraction_preserves_existing_file(self):
        archive = self.make_corrupt_zip()
        destination = self.root / "extract"
        destination.mkdir()
        member = destination / "alpha.txt"
        member.write_bytes(b"original extracted file")
        self.run_xfu("x", archive.name, "--reader", "native", "-oextract", success=False)
        self.assertEqual(member.read_bytes(), b"original extracted file")

    def test_truncated_archive_fails(self):
        self.run_xfu("a", "valid.zip", "alpha.txt", "--format=zip")
        data = (self.root / "valid.zip").read_bytes()
        (self.root / "truncated.zip").write_bytes(data[:40])
        self.run_xfu("t", "truncated.zip", "--reader", "native", success=False)

    def test_truncated_outer_compression_fails(self):
        self.require("filter", "gzip")
        self.run_xfu("a", "valid.tar.gz", "alpha.txt", "--format=pax", "--filter=gzip")
        data = (self.root / "valid.tar.gz").read_bytes()
        (self.root / "truncated.tar.gz").write_bytes(data[:-4])
        self.run_xfu("t", "truncated.tar.gz", "--reader", "native", success=False)

    def test_gzip_checksums_and_size_are_verified(self):
        self.require("filter", "gzip")
        self.run_xfu("a", "valid.tar", "alpha.txt", "--format=pax")
        compressed = gzip.compress((self.root / "valid.tar").read_bytes(), mtime=0)
        for name, offset in (("crc", -8), ("size", -4)):
            with self.subTest(field=name):
                damaged = bytearray(compressed)
                damaged[offset] ^= 0x80
                archive = "bad-" + name + ".tar.gz"
                (self.root / archive).write_bytes(damaged)
                self.run_xfu("t", archive, "--reader", "native", success=False)
                self.run_xfu("x", archive, "--reader", "native", "-obad-" + name,
                             success=False)

        header = bytearray(compressed[:10])
        header[3] |= 2
        checksum = (zlib.crc32(header) & 0xFFFF).to_bytes(2, "little")
        valid = bytes(header) + checksum + compressed[10:]
        (self.root / "header-crc.tar.gz").write_bytes(valid)
        self.run_xfu("t", "header-crc.tar.gz", "--reader", "native")
        damaged = bytearray(valid)
        damaged[10] ^= 0x80
        (self.root / "bad-header-crc.tar.gz").write_bytes(damaged)
        self.run_xfu("t", "bad-header-crc.tar.gz", "--reader", "native", success=False)
        self.run_xfu("x", "bad-header-crc.tar.gz", "--reader", "native", "-obad-header-crc",
                     success=False)

    def test_extraction_rejects_path_traversal(self):
        absolute = (self.root / "escaped.txt").as_posix()
        for member in ("../escaped.txt", absolute, "folder/../../escaped.txt"):
            with self.subTest(member=member):
                archive = self.root / "traversal.tar"
                with tarfile.open(archive, "w") as output:
                    entry = tarfile.TarInfo(member)
                    entry.size = len(self.payload)
                    output.addfile(entry, io.BytesIO(self.payload))
                self.run_xfu("x", archive.name, "--reader", "native", "-oextract", success=False)
                self.assertFalse((self.root / "escaped.txt").exists())

    def test_text_is_not_an_archive(self):
        texts = {
            "words.txt": b"hello\nworld\n",
            "numbers.txt": "".join("%d\n" % n for n in range(1, 2001)).encode("ascii"),
            "rows.csv": b"id,name,qty\n1,a,2\n",
            "accounts": b"root:x:0:0:root:/root:/bin/sh\nbin:x:1:1:bin:/bin:/sbin/nologin\n",
        }
        for name, data in texts.items():
            (self.root / name).write_bytes(data)
            for command in ("l", "t", "x"):
                with self.subTest(name=name, command=command):
                    extra = ["-oout-" + name] if command == "x" else []
                    result = self.run_xfu(command, name, *extra, success=False)
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 2, output)
                    self.assertIn(name + ": ", output)
                    self.assertIn(" cannot be opened as an archive", output)
                    self.assertFalse((self.root / ("out-" + name)).exists())
        result = self.run_xfu("l", "words.txt", success=False)
        self.assertIn("words.txt: Text cannot be opened as an archive", result.stdout + result.stderr)
        import bz2
        import lzma
        for suffix, compress in ((".gz", lambda data: gzip.compress(data, mtime=0)),
                                 (".xz", lzma.compress), (".bz2", bz2.compress)):
            with self.subTest(suffix=suffix):
                archive = "numbers.txt" + suffix
                (self.root / archive).write_bytes(compress(texts["numbers.txt"]))
                self.run_xfu("l", archive)
                self.run_xfu("t", archive)
                destination = "out-compressed" + suffix
                self.run_xfu("x", archive, "-o" + destination)
                self.assertEqual([p.read_bytes() for p in (self.root / destination).rglob("*")
                                  if p.is_file()], [texts["numbers.txt"]])

    def test_missing_archive_cannot_be_opened(self):
        for command in ("l", "t", "x"):
            with self.subTest(command=command):
                result = self.run_xfu(command, "missing.tar.gz", success=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("cannot open missing.tar.gz", result.stdout + result.stderr)

    def test_unsafe_member_path_is_one_failed_line(self):
        # ':' names a drive or a stream on Windows only: elsewhere it is an
        # ordinary character of a name, and such a member is extracted.
        windows = sys.platform.startswith("win")
        unsafe = ("../escaped.txt", "/rooted.txt") + (("a:b.txt",) if windows else ())
        with tarfile.open(self.root / "unsafe.tar", "w") as output:
            for member in ("ok.txt", "a:b.txt") + unsafe[:2]:
                entry = tarfile.TarInfo(member)
                entry.size = len(self.payload)
                output.addfile(entry, io.BytesIO(self.payload))
        result = self.run_xfu("x", "unsafe.tar", "-oextract", success=False)
        self.assertEqual(result.returncode, 1)
        lines = (result.stdout + result.stderr).splitlines()
        for member in unsafe:
            with self.subTest(member=member):
                self.assertEqual([line for line in lines if member in line],
                                 ["  %s -- FAILED (unsafe member path)" % member])
        self.assertIn("4 member(s), %d failed" % len(unsafe), lines)
        self.assertEqual(sorted(p.name for p in (self.root / "extract").rglob("*")),
                         ["ok.txt"] if windows else ["a:b.txt", "ok.txt"])

    def test_executable_without_reader_is_not_an_archive(self):
        program = self.root / "program.bin"
        program.write_bytes(Path(sys.executable).resolve().read_bytes())
        for command in ("l", "t", "x"):
            with self.subTest(command=command):
                extra = ["-oout-program"] if command == "x" else []
                result = self.run_xfu(command, program.name, *extra, success=False)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 2, output)
                self.assertIn("program.bin: ", output)
                self.assertIn(" cannot be opened as an archive", output)
                self.assertNotIn("no reader is built in", output)
                self.assertFalse((self.root / "out-program").exists())

    def test_damaged_compressed_streams_are_reported(self):
        import lzma
        import random
        self.require("filter", "zstd")
        self.require("filter", "lz4")
        data = bytes(random.Random(7).getrandbits(8) for _ in range(300000))
        (self.root / "payload.bin").write_bytes(data)
        for suffix, arguments in (("zst", ("--format=raw", "--filter=zstd")),
                                  ("tar.zst", ("--format=pax", "--filter=zstd")),
                                  ("lz4", ("--format=raw", "--filter=lz4")),
                                  ("tar.lz4", ("--format=pax", "--filter=lz4"))):
            self.run_xfu("a", "stream." + suffix, "payload.bin", *arguments)
        self.run_xfu("a", "stream.tar", "payload.bin", "--format=pax")
        (self.root / "stream.lzma").write_bytes(lzma.compress(data, format=lzma.FORMAT_ALONE))
        (self.root / "stream.tar.lzma").write_bytes(lzma.compress(
            (self.root / "stream.tar").read_bytes(), format=lzma.FORMAT_ALONE))
        # One wording, with the type's display name; a stream that the name
        # says holds a TAR is named as that compressed TAR. A compressed TAR
        # reader keeps the members of a cut stream's decoded prefix: here
        # its one member, which is cut and fails, whether or not the stream
        # records its size (the LZ4 one that the filter writes does not).
        for suffix, kind in (("zst", "ZSTD"), ("tar.zst", "TAR.ZST"), ("lz4", "LZ4"),
                             ("tar.lz4", "TAR.LZ4"), ("lzma", "LZMA"), ("tar.lzma", "TAR.LZMA")):
            whole = (self.root / ("stream." + suffix)).read_bytes()
            damaged = "cut-stream." + suffix
            (self.root / damaged).write_bytes(whole[:len(whole) * 2 // 3])
            self.run_xfu("t", "stream." + suffix)
            for command in ("l", "t", "x"):
                with self.subTest(name=damaged, command=command):
                    extra = ["-oout-" + damaged] if command == "x" else []
                    result = self.run_xfu(command, damaged, *extra, success=False)
                    output = result.stdout + result.stderr
                    self.assertNotIn("Binary", output)
                    self.assertFalse((self.root / ("out-" + damaged) / "payload.bin").exists())
                    if suffix in ("tar.zst", "tar.lz4", "tar.lzma"):
                        self.assertEqual(result.returncode, 1, output)
                        self.assertIn(damaged + ": incomplete archive; showing recovered members",
                                      output)
                        self.assertIn("payload.bin" if command == "l" else "1 member(s), 1 failed",
                                      output)
                        self.assertNotIn("damaged", output)
                        continue
                    self.assertEqual(result.returncode, 2, output)
                    inside = " or the TAR inside" if suffix.startswith("tar.") else ""
                    self.assertIn(damaged + ": " + kind + " could not be read; the compressed "
                                  "stream" + inside + " is damaged", output)
                    self.assertFalse((self.root / ("out-" + damaged)).exists())
        # Without the stream's signature (LZMA: a header that holds up) it
        # stays a Binary file.
        for name in ("fake.tar.zst", "fake.lzma"):
            (self.root / name).write_bytes(bytes(range(256)) * 4)
            result = self.run_xfu("l", name, success=False)
            self.assertIn(name + ": Binary cannot be opened as an archive",
                          result.stdout + result.stderr)

    def test_nested_layers_are_read_as_their_own_type(self):
        import base64
        import binascii
        import lzma
        envelope = ("begin-base64 644 alpha.txt\n" +
                    base64.b64encode(self.payload).decode("ascii") + "\n====\n").encode("ascii")
        uuencoded = b"begin 644 alpha.txt\n" + b"".join(
            binascii.b2a_uu(self.payload[at:at + 45])
            for at in range(0, len(self.payload), 45)) + b"`\nend\n"
        (self.root / "alpha.b64.gz").write_bytes(gzip.compress(envelope, mtime=0))
        (self.root / "alpha.uue.xz").write_bytes(lzma.compress(uuencoded))
        for name, kind in (("alpha.b64.gz", "Base64"), ("alpha.uue.xz", "uue")):
            with self.subTest(name=name):
                listing = self.run_xfu("l", name)
                self.assertEqual(listing.stdout.splitlines()[0], name + ": " + kind)
                self.assertRegex(listing.stdout, r"\n +\d+  alpha\.txt\n")
                self.run_xfu("x", name, "-oout-" + name)
                self.assertEqual((self.root / ("out-" + name) / "alpha.txt").read_bytes(),
                                 self.payload)
        # A gzip of a .tar.gz is its TAR.GZ: the inner stream goes by its own
        # name (double.tgz), not by the outer one's .gz.
        self.run_xfu("a", "inner.tgz", "alpha.txt", "--format=pax", "--filter=gzip")
        inner = (self.root / "inner.tgz").read_bytes()
        for name in ("double.tgz.gz", "double.tar.gz.gz", "double.gz"):
            with self.subTest(name=name):
                (self.root / name).write_bytes(gzip.compress(inner, mtime=0))
                listing = self.run_xfu("l", name)
                self.assertEqual(listing.stdout.splitlines()[0], name + ": TAR.GZ")
                self.assertRegex(listing.stdout, r"\n +\d+  alpha\.txt\n")

    def test_archive_too_large_for_test_memory_is_reported(self):
        self.require("filter", "gzip")
        # A newc cpio of 300 MB of zeros in a 300 KB gzip: List opens the
        # CPIO, but Test keeps only 256 MiB of a decoded layer in memory. It
        # says that it tested only the gzip stream, and does not pass.
        def newc(name, size):
            name = name + b"\0"
            header = b"070701" + b"".join(b"%08X" % value for value in (
                1, 0o100644, 0, 0, 1, 0, size, 0, 0, 0, 0, len(name), 0)) + name
            return header + b"\0" * (-len(header) % 4)
        size = 300 * 1000 * 1000
        compressor = zlib.compressobj(1, zlib.DEFLATED, 31)
        with open(self.root / "zeros.cpio.gz", "wb") as output:
            output.write(compressor.compress(newc(b"zeros.bin", size)))
            block = bytes(1 << 20)
            for at in range(0, size, len(block)):
                output.write(compressor.compress(block[:min(len(block), size - at)]))
            output.write(compressor.compress(b"\0" * (-size % 4) + newc(b"TRAILER!!!", 0)))
            output.write(compressor.flush())
        listing = self.run_xfu("l", "zeros.cpio.gz")
        self.assertEqual(listing.stdout.splitlines()[0], "zeros.cpio.gz: CPIO")
        self.assertIn("zeros.bin", listing.stdout)
        note = ("zeros.cpio.gz: the CPIO inside is larger than the 256 MiB that Test "
                "keeps in memory; it was not tested, only the GZ stream around it")
        for arguments in (("--verbose",), ()):
            with self.subTest(arguments=arguments):
                result = self.run_xfu("t", "zeros.cpio.gz", *arguments, success=False)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(result.stderr.splitlines(), [note])
                if arguments:
                    # The gzip stream's one member, unnamed in the stream.
                    self.assertRegex(result.stdout, r"\A\S+ -- OK\n\Z")
                else:
                    self.assertNotIn("100%", result.stdout)

    def test_damaged_compressed_tar_is_not_a_header_defect(self):
        import lzma
        import random
        self.require("filter", "gzip")
        self.run_xfu("a", "valid.tar", "alpha.txt", "--format=pax")
        tar = (self.root / "valid.tar").read_bytes() + random.Random(3).randbytes(200000)
        compressed = gzip.compress(tar, mtime=0)
        xz = lzma.compress(tar)
        cases = {"cut.tar.gz": compressed[:len(compressed) // 2], "crc.tar.gz": bytearray(compressed),
                 "cut.tar.xz": xz[:len(xz) // 2]}
        cases["crc.tar.gz"][-8] ^= 1
        for name, data in cases.items():
            (self.root / name).write_bytes(bytes(data))
            kind = "TAR.XZ" if name.endswith(".xz") else "TAR.GZ"
            for command in ("l", "t"):
                with self.subTest(name=name, command=command):
                    arguments = ["--verbose"] if command == "t" else []
                    result = self.run_xfu(command, name, *arguments, success=False)
                    output = result.stdout + result.stderr
                    self.assertNotIn("header does not hold up", output)
                    if name.startswith("cut."):
                        # The TAR ends before the stream is cut: its member
                        # is whole, and the archive is incomplete. No check
                        # before the cut covers it: Test reads it without
                        # one, as GNU tar does, and says so.
                        self.assertEqual(result.returncode, 1, output)
                        self.assertIn(name + (": incomplete archive; showing recovered members"
                                              if command == "l" else ": incomplete archive; members "
                                              "before the cut were read without a checksum"), output)
                        self.assertIn("alpha.txt" if command == "l" else "alpha.txt -- OK", output)
                        continue
                    self.assertEqual(result.returncode, 2, output)
                    # One wording, with the type's display name (not the
                    # reader's id), whichever reader found the damage.
                    self.assertIn(name + ": " + kind + " could not be read; the compressed "
                                  "stream or the TAR inside is damaged", output)
        (self.root / "bad.Z").write_bytes(b"\x1f\x9d\x90" + random.Random(1).randbytes(3000))
        result = self.run_xfu("l", "bad.Z", success=False)
        self.assertIn("bad.Z: UNIX COMPRESS could not be read; the compressed stream is damaged",
                      result.stdout + result.stderr)

    def test_cut_compressed_tar_keeps_its_whole_members(self):
        # GNU tar reads every whole member of a cut .tar.gz and the like,
        # whether or not a check of the stream before the cut covers it: so
        # do List, Test and Extract. The member the cut goes through (its
        # data or its padding) fails and nothing is written for it, nor for
        # a hard link to it (c.link, which comes before it), so a file
        # already at its path stays as it was; the archive is incomplete (1).
        # Test and Extract say once that they read members without a
        # checksum when no check covers one of them: gzip, a single xz Block,
        # zstd, LZMA-alone and lz4 have none before their end. When bzip2's
        # Blocks or xz's whole Blocks cover every member read, the archive's
        # line is List's. Random data keeps the stream's positions near the
        # TAR's, so the cut is inside c.bin.
        import bz2
        import lzma
        import random
        rng = random.Random(11)
        payloads = {"a.txt": b"first member\n", "b.bin": rng.randbytes(200000),
                    "c.bin": rng.randbytes(300000), "d.txt": b"after the cut\n"}
        links = {"b.link": "b.bin", "c.link": "c.bin"}
        order = ["a.txt", "b.bin", "b.link", "c.link", "c.bin", "d.txt"]
        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name in order:
                info = tarfile.TarInfo(name)
                if name in links:
                    info.type = tarfile.LNKTYPE
                    info.linkname = links[name]
                    archive.addfile(info)
                else:
                    info.size = len(payloads[name])
                    archive.addfile(info, io.BytesIO(payloads[name]))
        tar = tar.getvalue()
        with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
            header = {member.name: member.offset for member in archive.getmembers()}
            c_start = archive.getmember("c.bin").offset_data
        c_end = c_start + len(payloads["c.bin"])
        c_padded = c_start + (len(payloads["c.bin"]) + 511) // 512 * 512
        half = (c_start + c_end) // 2
        for name, data in payloads.items():
            (self.root / name).write_bytes(data)

        def vli(value):
            encoded = bytearray()
            while value >= 0x80:
                encoded.append(value & 0x7F | 0x80)
                value >>= 7
            return bytes(encoded + bytes([value]))

        def xz_blocks(data, splits):
            # An xz stream of one Block for each piece of data (split at
            # splits), each with its CRC32, and the offsets where they end.
            flags = b"\0\x01"
            stream = bytearray(b"\xfd7zXZ\0" + flags + struct.pack("<I", zlib.crc32(flags)))
            records, ends = [], []
            bounds = [0, *splits, len(data)]
            for start, end in zip(bounds, bounds[1:]):
                piece = data[start:end]
                packed = lzma.compress(piece, format=lzma.FORMAT_RAW,
                                       filters=[{"id": lzma.FILTER_LZMA2, "dict_size": 1 << 20}])
                block = bytes([2, 0, 0x21, 1, 16, 0, 0, 0])  # LZMA2 with a 1 MiB dictionary
                block += struct.pack("<I", zlib.crc32(block))
                records.append((len(block) + len(packed) + 4, len(piece)))
                stream += block + packed + bytes(-len(packed) % 4) + struct.pack("<I", zlib.crc32(piece))
                ends.append(len(stream))
            index = b"\0" + vli(len(records)) + b"".join(vli(u) + vli(s) for u, s in records)
            index += bytes(-len(index) % 4)
            index += struct.pack("<I", zlib.crc32(index))
            footer = struct.pack("<I", len(index) // 4 - 1) + flags
            stream += index + struct.pack("<I", zlib.crc32(footer)) + footer + b"YZ"
            return bytes(stream), ends

        whole = {"gz": gzip.compress(tar, mtime=0), "bz2": bz2.compress(tar, 1), "xz": lzma.compress(tar),
                 "lzma": lzma.compress(tar, format=lzma.FORMAT_ALONE)}
        # a.txt's Block is checked, and the next one, b.bin's on, is cut.
        multi, multi_ends = xz_blocks(tar, [header["b.bin"]])
        # The first Block, checked, holds every member before c.bin.
        checked, _ = xz_blocks(tar, [header["c.bin"]])
        # The first two Blocks, checked, end in c.bin's padding, the third
        # one's first byte after them.
        padding, padding_ends = xz_blocks(tar, [header["b.bin"], c_end + 16])
        gunzip = lambda data: zlib.decompressobj(31).decompress(data)
        unxz = lambda data: lzma.LZMADecompressor().decompress(data)
        unlzma = lambda data: lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(data)
        # The cut file, its decoder, and whether checks cover every member read.
        cuts = {
            "cut.tar.gz": (whole["gz"][:half], gunzip, False),
            "cut.tgz": (whole["gz"][:half], gunzip, False),
            "cut.tar.bz2": (whole["bz2"][:half], lambda data: bz2.BZ2Decompressor().decompress(data), True),
            "cut.tar.xz": (whole["xz"][:half], unxz, False),
            "multi.tar.xz": (multi[:half], unxz, False),
            "checked.tar.xz": (checked[:half], unxz, True),
            "padding.tar.xz": (padding[:padding_ends[1] + 1], unxz, True),
            "cut.tar.lzma": (whole["lzma"][:half], unlzma, False),
            "cut.tlz": (whole["lzma"][:half], unlzma, False),
        }
        # xfu writes these from the files: without the hard links.
        for suffix in ("zst", "lz4"):
            if self.capabilities["filter"].get("zstd" if suffix == "zst" else suffix, (False, False))[1]:
                self.run_xfu("a", "whole.tar." + suffix, "a.txt", "b.bin", "c.bin", "d.txt")
                whole[suffix] = (self.root / ("whole.tar." + suffix)).read_bytes()
                cuts["cut.tar." + suffix] = (whole[suffix][:half], None, False)

        def previous(member):
            return b"previous copy of " + member.encode() + b"\n"

        def output_with_previous_copies(name):
            # A file already at the path of every member.
            destination = self.root / ("out-" + name)
            destination.mkdir()
            for member in order:
                (destination / member).write_bytes(previous(member))
            return destination

        for name, (data, decode, covered) in cuts.items():
            if decode:
                # The decoded prefix ends inside c.bin's data or padding.
                self.assertTrue(c_start < len(decode(data)) < c_padded, name)
            (self.root / name).write_bytes(data)
            read = ["a.txt", "b.bin", "b.link"] if decode else ["a.txt", "b.bin"]
            failing = ["c.link", "c.bin"] if decode else ["c.bin"]
            recovered = name + ": incomplete archive; showing recovered members"
            unverified = name + ": incomplete archive; members before the cut were read without a checksum"
            note = recovered if covered else unverified
            with self.subTest(name=name, command="l"):
                result = self.run_xfu("l", name, success=False)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                self.assertEqual(output.count(": incomplete archive"), 1, output)
                self.assertIn(recovered, output)
                for member in read + failing:
                    self.assertIn(member, output)
                self.assertNotIn("d.txt", output)
            with self.subTest(name=name, command="t"):
                result = self.run_xfu("t", name, "--verbose", success=False)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                self.assertIn("".join(member + " -- OK\n" for member in read) +
                              "".join(member + " -- FAILED (cut)\n" for member in failing), output)
                self.assertIn("%d member(s), %d failed" % (len(read) + len(failing), len(failing)), output)
                self.assertEqual(output.count(": incomplete archive"), 1, output)
                self.assertIn(note, output)
            with self.subTest(name=name, command="x"):
                # The members before the cut replace the files at their
                # paths; the others leave them as they were.
                destination = output_with_previous_copies(name)
                result = self.run_xfu("x", name, "-o" + str(destination), success=False)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                self.assertEqual(output.count(": incomplete archive"), 1, output)
                self.assertIn(note, output)
                for member in read:
                    self.assertIn("  %s -- replaced an existing file\n" % member, output)
                    self.assertEqual((destination / member).read_bytes(), payloads[links.get(member, member)])
                for member in failing:
                    self.assertIn("  %s -- FAILED (cut)\n" % member, output)
                for member in order:
                    if member not in read:
                        self.assertEqual((destination / member).read_bytes(), previous(member), member)
                self.assertEqual(sorted(p.name for p in destination.iterdir()), sorted(order))
        # Whole, the streams read as ever: every member is OK, and no line
        # is about the archive.
        complete = {"whole.tar.gz": (whole["gz"], order), "whole.tar.bz2": (whole["bz2"], order),
                    "whole.tar.xz": (whole["xz"], order), "multi-whole.tar.xz": (multi, order),
                    "whole.tar.lzma": (whole["lzma"], order)}
        for suffix in ("zst", "lz4"):
            if suffix in whole:
                complete["whole.tar." + suffix] = (whole[suffix], [member for member in order if member not in links])
        for name, (data, members) in complete.items():
            (self.root / name).write_bytes(data)
            with self.subTest(name=name, command="t"):
                result = self.run_xfu("t", name, "--verbose")
                self.assertEqual(result.stdout + result.stderr, "".join(member + " -- OK\n" for member in members))
        # LZMA-alone has no check: a stream damaged near its end decodes to
        # its end like a cut one, and the member the end runs through (d.txt,
        # whose bytes are wrong) is never OK nor written.
        flipped = bytearray(whole["lzma"])
        flipped[len(flipped) - 52] ^= 4
        (self.root / "flip.tar.lzma").write_bytes(bytes(flipped))
        result = self.run_xfu("t", "flip.tar.lzma", "--verbose", success=False)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertNotIn("d.txt -- OK", output)
        destination = self.root / "out-flip"
        result = self.run_xfu("x", "flip.tar.lzma", "-o" + str(destination), success=False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        if (destination / "d.txt").exists():
            self.assertEqual((destination / "d.txt").read_bytes(), payloads["d.txt"])
        # A failed check is damage, not a cut: the stream still fails as a
        # whole (2), the members before it with it.
        damaged = {"gz": bytearray(whole["gz"]), "bz2": bytearray(whole["bz2"]),
                   "xz": bytearray(whole["xz"])}
        damaged["gz"][-8] ^= 1  # the CRC-32
        damaged["bz2"][len(damaged["bz2"]) // 2] ^= 1  # a Block in the middle
        # The Block's CRC64 ends where the Index starts, which the Footer's
        # Backward Size tells.
        index_size = (struct.unpack("<I", bytes(damaged["xz"][-8:-4]))[0] + 1) * 4
        damaged["xz"][len(damaged["xz"]) - 12 - index_size - 1] ^= 1
        # A damaged Footer (its Backward Size) or Index is found before any
        # Block is decoded.
        damaged["footer.xz"] = bytearray(whole["xz"])
        damaged["footer.xz"][-5] ^= 0x41
        damaged["index.xz"] = bytearray(whole["xz"])
        damaged["index.xz"][len(damaged["index.xz"]) - 12 - index_size + 1] ^= 0x41
        for suffix, data in damaged.items():
            kind, _, suffix = suffix.rpartition(".")
            name = (kind or "crc") + ".tar." + suffix
            (self.root / name).write_bytes(bytes(data))
            with self.subTest(name=name):
                result = self.run_xfu("t", name, "--verbose", success=False)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 2, output)
                self.assertIn("could not be read; the compressed stream or the TAR inside is damaged",
                              output)
                self.assertNotIn("incomplete", output)
        # So is damage before a cut, which a check or the decoder finds: the
        # cut stream fails as a whole (2), and nothing is written.
        first = gzip.compress(tar[:header["b.link"]], mtime=0)
        broken = {"cut-crc.tar.gz": bytearray(first + gzip.compress(tar[header["b.link"]:], mtime=0)),
                  "cut-block.tar.bz2": bytearray(whole["bz2"]), "cut-crc.tar.xz": bytearray(multi)}
        broken["cut-crc.tar.gz"][len(first) - 8] ^= 1  # the first gzip member's CRC-32
        broken["cut-block.tar.bz2"][len(whole["bz2"]) // 4] ^= 1  # inside the first Block
        broken["cut-crc.tar.xz"][multi_ends[0] - 1] ^= 1  # the first Block's CRC32
        # In a single Block, an LZMA2 chunk inside b.bin with an invalid
        # control byte.
        single, _ = xz_blocks(tar, [])
        chunk, chunks = 24, []  # after the Stream Header and the Block Header
        while single[chunk]:
            chunks.append(chunk)
            if single[chunk] in (1, 2):  # stored: its size - 1
                chunk += 3 + int.from_bytes(single[chunk + 1:chunk + 3], "big") + 1
            else:  # LZMA: its packed size - 1, and properties at a reset
                chunk += (6 if single[chunk] >= 0xC0 else 5) + int.from_bytes(single[chunk + 3:chunk + 5], "big") + 1
        self.assertLess(chunks[2], half)
        broken["cut-chunk.tar.xz"] = bytearray(single)
        broken["cut-chunk.tar.xz"][chunks[2]] = 3
        if "zst" in whole:
            # The second Block of the frame given the reserved type.
            frame = whole["zst"]
            descriptor = frame[4]
            at = 5 + (0 if descriptor & 0x20 else 1) + (0, 1, 2, 4)[descriptor & 3] + \
                (1 if descriptor & 0x20 else 0, 2, 4, 8)[descriptor >> 6]
            block = int.from_bytes(frame[at:at + 3], "little")
            at += 3 + (1 if (block >> 1) & 3 == 1 else block >> 3)
            self.assertLess(at, half)
            broken["cut-block.tar.zst"] = bytearray(frame)
            broken["cut-block.tar.zst"][at] |= 6
        for name, data in broken.items():
            (self.root / name).write_bytes(bytes(data[:half]))
            kind = "TAR." + name.rpartition(".")[2].upper()
            destination = output_with_previous_copies(name)
            for command in ("t", "x"):
                with self.subTest(name=name, command=command):
                    extra = ["-o" + str(destination)] if command == "x" else ["--verbose"]
                    result = self.run_xfu(command, name, *extra, success=False)
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 2, output)
                    self.assertIn(name + ": " + kind + " could not be read; the compressed "
                                  "stream or the TAR inside is damaged", output)
                    self.assertNotIn("incomplete", output)
                    self.assertNotIn(" -- ", output)
            for member in order:
                self.assertEqual((destination / member).read_bytes(), previous(member), name + " " + member)
            self.assertEqual(sorted(p.name for p in destination.iterdir()), sorted(order))

    def cut_tar_fixture(self):
        """The TAR the cut tests read: a.txt, b.bin, b.link (a hard link to
        b.bin), c.link (one to c.bin, which comes after it), c.bin and d.txt,
        whose files are also written under the root. With what each member
        holds, the offset of each header, and a point in c.bin's data."""
        import random
        rng = random.Random(11)
        payloads = {"a.txt": b"first member\n", "b.bin": rng.randbytes(200000),
                    "c.bin": rng.randbytes(300000), "d.txt": b"after the cut\n"}
        links = {"b.link": "b.bin", "c.link": "c.bin"}
        order = ["a.txt", "b.bin", "b.link", "c.link", "c.bin", "d.txt"]
        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name in order:
                info = tarfile.TarInfo(name)
                if name in links:
                    info.type = tarfile.LNKTYPE
                    info.linkname = links[name]
                    archive.addfile(info)
                else:
                    info.size = len(payloads[name])
                    archive.addfile(info, io.BytesIO(payloads[name]))
        tar = tar.getvalue()
        with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
            header = {member.name: member.offset for member in archive.getmembers()}
            c_start = archive.getmember("c.bin").offset_data
        for name, data in payloads.items():
            (self.root / name).write_bytes(data)
        contents = {name: payloads[links.get(name, name)] for name in order}
        return tar, contents, header, c_start + len(payloads["c.bin"]) // 2

    def assert_cut_archive(self, name, read, failing, note, contents):
        """List, Test and Extract of the cut compressed TAR name: the members
        read are OK and written (contents: what each holds), those failing
        fail as cut and leave a file already at their path as it was; one
        line is about the archive (note in Test and Extract), exit code 1."""
        def previous(member):
            return b"previous copy of " + member.encode() + b"\n"
        with self.subTest(name=name, command="l"):
            result = self.run_xfu("l", name, success=False)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertEqual(output.count(": incomplete archive"), 1, output)
            self.assertIn(name + ": incomplete archive; showing recovered members", output)
            self.assertNotIn("payload", output)
            for member in read + failing:
                self.assertRegex(output, r"\n +\d+  %s\n" % re.escape(member))
        with self.subTest(name=name, command="t"):
            result = self.run_xfu("t", name, "--verbose", success=False)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertIn("".join(member + " -- OK\n" for member in read) +
                          "".join(member + " -- FAILED (cut)\n" for member in failing), output)
            if failing:
                self.assertIn("%d member(s), %d failed\n" % (len(read) + len(failing), len(failing)), output)
            self.assertEqual(output.count(": incomplete archive"), 1, output)
            self.assertIn(note, output)
        with self.subTest(name=name, command="x"):
            destination = self.root / ("out-" + name)
            destination.mkdir()
            for member in read + failing:
                (destination / member).write_bytes(previous(member))
            result = self.run_xfu("x", name, "-o" + str(destination), success=False)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertEqual(output.count(": incomplete archive"), 1, output)
            self.assertIn(note, output)
            for member in read:
                self.assertIn("  %s -- replaced an existing file\n" % member, output)
                self.assertEqual((destination / member).read_bytes(), contents[member], member)
            for member in failing:
                self.assertIn("  %s -- FAILED (cut)\n" % member, output)
                self.assertEqual((destination / member).read_bytes(), previous(member), member)
            self.assertEqual(sorted(p.name for p in destination.iterdir()), sorted(read + failing))

    def test_cut_zstd_and_lz4_tar_without_a_size(self):
        # tar --zstd, tar -I lz4 and a pipe into zstd or lz4 record no
        # content size. Cut, such a stream is read as far as it goes, as one
        # that records it is (the TAR in a whole one is read inside a nested
        # layer, as ever). Test and Extract say that they read members
        # without a checksum unless the zstd frames, or the LZ4 blocks or
        # frames, that hold every member read had their checksums verified.
        tar, contents, header, half = self.cut_tar_fixture()
        split = header["c.link"]
        read, failing = ["a.txt", "b.bin", "b.link"], ["c.link", "c.bin"]
        streams = {
            "unsized.tar.zst": (zstd_frame(tar, False, True), False),
            "unchecked.tar.zst": (zstd_frame(tar, False, False), False),
            "frames.tar.zst": (zstd_frame(tar[:split], False, True) + zstd_frame(tar[split:], False, True), True),
            "unsized.tar.lz4": (lz4_frame(tar, False, False, False), False),
            "blocks.tar.lz4": (lz4_frame(tar, False, True, False), True),
            "frames.tar.lz4": (lz4_frame(tar[:split], False, False, True) + lz4_frame(tar[split:], False, False, True), True),
        }
        for name, (data, checked) in streams.items():
            (self.root / name).write_bytes(data[:half])
            note = name + (": incomplete archive; showing recovered members" if checked else
                           ": incomplete archive; members before the cut were read without a checksum")
            self.assert_cut_archive(name, read, failing, note, contents)
            whole = "whole-" + name
            (self.root / whole).write_bytes(data)
            with self.subTest(name=whole):
                result = self.run_xfu("l", whole)
                self.assertEqual(result.stdout.splitlines()[0], whole + ": TAR")
                result = self.run_xfu("t", whole, "--verbose")
                self.assertEqual(result.stdout + result.stderr, "".join(member + " -- OK\n" for member in contents))
        # The frames xfu writes, compressed: LZ4 without a size; zstd's size
        # taken out of its frame header (a window as large as its content
        # stands for it).
        files = ["a.txt", "b.bin", "c.bin", "d.txt"]
        if self.capabilities["filter"].get("lz4", (False, False))[1]:
            self.run_xfu("a", "xfu.tar.lz4", *files, "--format=pax", "--filter=lz4")
            data = (self.root / "xfu.tar.lz4").read_bytes()
            self.assertEqual(data[4] & 0x18, 0)  # no content size, no block checksum
            (self.root / "xfu-cut.tar.lz4").write_bytes(data[:half])
            self.assert_cut_archive("xfu-cut.tar.lz4", ["a.txt", "b.bin"], ["c.bin"],
                                    "xfu-cut.tar.lz4: incomplete archive; members before the cut were read "
                                    "without a checksum", contents)
        if self.capabilities["filter"].get("zstd", (False, False))[1]:
            self.run_xfu("a", "xfu.tar.zst", *files)
            data = (self.root / "xfu.tar.zst").read_bytes()
            self.assertEqual(data[4], 0xA0)  # one segment, a 4-byte content size
            size = int.from_bytes(data[5:9], "little")
            exponent = max(size - 1, 1).bit_length() - 10
            unsized = data[:4] + bytes([0, exponent << 3]) + data[9:]
            (self.root / "xfu-cut.tar.zst").write_bytes(unsized[:half])
            self.assert_cut_archive("xfu-cut.tar.zst", ["a.txt", "b.bin"], ["c.bin"],
                                    "xfu-cut.tar.zst: incomplete archive; members before the cut were read "
                                    "without a checksum", contents)
            (self.root / "xfu-whole.tar.zst").write_bytes(unsized)
            result = self.run_xfu("t", "xfu-whole.tar.zst", "--verbose")
            self.assertEqual(result.stdout + result.stderr, "".join(member + " -- OK\n" for member in files))

    def test_whole_stream_of_a_cut_tar_is_a_cut_tar(self):
        # A file cut where a gzip member, an xz or bzip2 stream, or a zstd or
        # LZ4 frame ends (with or without its size, as pzstd writes them)
        # decodes whole, but its TAR is cut: it is read as a cut TAR, never
        # as one raw payload. So is a whole stream of a TAR cut before it was
        # compressed. What the stream's checks covered is no member read
        # without a checksum. Whole, the same streams read as ever.
        import bz2
        import lzma
        tar, contents, header, half = self.cut_tar_fixture()
        split = header["c.link"]
        pieces = [tar[:split], tar[split:half]]
        read, failing = ["a.txt", "b.bin", "b.link"], ["c.link", "c.bin"]
        checked = ": incomplete archive; showing recovered members"
        unchecked = ": incomplete archive; members before the cut were read without a checksum"
        third = tar[half:half + 100000]
        streams = {
            "members.tar.gz": ([gzip.compress(piece, mtime=0) for piece in pieces], checked),
            "streams.tar.xz": ([lzma.compress(piece) for piece in pieces], checked),
            "streams.tar.bz2": ([bz2.compress(piece) for piece in pieces], checked),
            "frames.tar.zst": ([zstd_frame(piece, True, True) for piece in pieces], checked),
            "unsized-frames.tar.zst": ([zstd_frame(piece, False, True) for piece in pieces], checked),
            "frames.tar.lz4": ([lz4_frame(piece, True, False, True) for piece in pieces], checked),
            "unsized-frames.tar.lz4": ([lz4_frame(piece, False, False, True) for piece in pieces], checked),
            "whole.tar.gz": ([gzip.compress(tar[:half], mtime=0)], checked),
            "whole.tar.zst": ([zstd_frame(tar[:half], True, False)], unchecked),
            "whole.tar.lzma": ([lzma.compress(tar[:half], format=lzma.FORMAT_ALONE)], unchecked),
        }
        for name, (parts, note) in streams.items():
            (self.root / name).write_bytes(b"".join(parts))
            self.assert_cut_archive(name, read, failing, name + note, contents)
        # Cut just after such an end, in the next stream's header, it is cut
        # as well.
        next_stream = {"gz": gzip.compress(third, mtime=0), "xz": lzma.compress(third), "bz2": bz2.compress(third)}
        for name in ("members.tar.gz", "streams.tar.xz", "streams.tar.bz2"):
            suffix = name.rpartition(".")[2]
            for length in (1, 4, 9, 13):
                cut = "header%d-%s" % (length, name)
                (self.root / cut).write_bytes(b"".join(streams[name][0]) + next_stream[suffix][:length])
                with self.subTest(name=cut):
                    result = self.run_xfu("t", cut, "--verbose", success=False)
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 1, output)
                    self.assertIn("".join(member + " -- OK\n" for member in read) +
                                  "".join(member + " -- FAILED (cut)\n" for member in failing), output)
                    self.assertIn(cut + checked, output)
        # A TAR whose last member ends where the stream does, without the
        # end marker, is cut as well, though all of its members are whole.
        with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
            end = archive.getmember("d.txt").offset_data + 512
        (self.root / "no-end.tar.gz").write_bytes(gzip.compress(tar[:end], mtime=0))
        self.assert_cut_archive("no-end.tar.gz", read + failing + ["d.txt"], [], "no-end.tar.gz" + checked,
                                contents)
        # Whole, they read as ever: several zstd frames without their sizes,
        # or several LZ4 frames, as a nested layer.
        rest = [tar[:split], tar[split:]]
        for name, data, kind in (("all.tar.gz", gzip.compress(tar, mtime=0), "TAR.GZ"),
                                 ("all.tar.zst", zstd_frame(tar, True, True), "TAR.ZST"),
                                 ("all.tar.lz4", lz4_frame(tar, True, True, True), "TAR.LZ4"),
                                 ("all-unsized.tar.zst", b"".join(zstd_frame(piece, False, True) for piece in rest), "TAR"),
                                 ("all-unsized.tar.lz4", b"".join(lz4_frame(piece, False, False, True) for piece in rest), "TAR"),
                                 ("all-frames.tar.lz4", b"".join(lz4_frame(piece, True, False, True) for piece in rest), "TAR")):
            (self.root / name).write_bytes(data)
            with self.subTest(name=name):
                self.assertEqual(self.run_xfu("l", name).stdout.splitlines()[0], name + ": " + kind)
                result = self.run_xfu("t", name, "--verbose")
                self.assertEqual(result.stdout + result.stderr, "".join(member + " -- OK\n" for member in contents))

    def test_cut_sparse_member_fails_as_cut(self):
        # A sparse member that the cut runs through, its data or its map, is
        # listed, and fails as cut as a plain one does: never dropped.
        import random
        rng = random.Random(5)
        logical = 600000
        islands = [(at, rng.randbytes(3000 + 500 * index)) for index, at in enumerate(range(20000, logical, 100000))]
        image = bytearray(logical)
        for at, data in islands:
            image[at:at + len(data)] = data
        stored = b"".join(data for _, data in islands)

        def padded(data):
            return data + bytes(-len(data) % 512)

        def plain(name, data, form):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            return info.tobuf(form) + padded(data)

        def octal(value):
            return b"%011o\0" % value

        # Old GNU: four extents in the header, the other two in an extension
        # record before the data.
        info = tarfile.TarInfo("sparse.img")
        info.type = tarfile.GNUTYPE_SPARSE
        info.size = len(stored)
        sparse = bytearray(info.tobuf(tarfile.GNU_FORMAT))
        extension = bytearray(512)
        for index, (at, data) in enumerate(islands):
            block, base = (sparse, 386 + 24 * index) if index < 4 else (extension, 24 * (index - 4))
            block[base:base + 12] = octal(at)
            block[base + 12:base + 24] = octal(len(data))
        sparse[482] = 1
        sparse[483:495] = octal(logical)
        sparse[148:156] = b" " * 8
        sparse[148:156] = b"%06o\0 " % sum(sparse)
        gnu = plain("a.txt", b"first\n", tarfile.GNU_FORMAT) + bytes(sparse) + bytes(extension) + padded(stored)
        gnu += plain("z.txt", b"last\n", tarfile.GNU_FORMAT) + bytes(1024)
        # PAX 1.0: the map at the start of the data.
        info = tarfile.TarInfo("GNUSparseFile.0/sparse.img")
        info.pax_headers = {"GNU.sparse.major": "1", "GNU.sparse.minor": "0", "GNU.sparse.name": "sparse.img",
                            "GNU.sparse.realsize": str(logical)}
        layout = padded(("%d\n" % len(islands) + "".join("%d\n%d\n" % (at, len(data)) for at, data in islands)).encode())
        info.size = len(layout) + len(stored)
        pax = plain("a.txt", b"first\n", tarfile.PAX_FORMAT) + info.tobuf(tarfile.PAX_FORMAT) + padded(layout + stored)
        pax += plain("z.txt", b"last\n", tarfile.PAX_FORMAT) + bytes(1024)
        contents = {"a.txt": b"first\n", "sparse.img": bytes(image), "z.txt": b"last\n"}
        for form, tar in (("gnu", gnu), ("pax", pax)):
            whole = form + ".tar.gz"
            (self.root / whole).write_bytes(gzip.compress(tar, mtime=0))
            with self.subTest(name=whole):
                result = self.run_xfu("t", whole, "--verbose")
                self.assertEqual(result.stdout, "a.txt -- OK\nsparse.img -- OK\nz.txt -- OK\n")
                self.run_xfu("x", whole, "-oout-" + whole)
                self.assertEqual((self.root / ("out-" + whole) / "sparse.img").read_bytes(), contents["sparse.img"])
            # In the extension record, or the map in the data, and in the
            # data.
            map_start = 1536 if form == "gnu" else tar.index(layout)
            for where, at in (("map", map_start + 100), ("data", tar.index(stored[:64]) + 5000)):
                name = "cut-%s-%s.tar.gz" % (where, form)
                encoder = zlib.compressobj(6, zlib.DEFLATED, 31)
                (self.root / name).write_bytes(encoder.compress(tar[:at]) + encoder.flush(zlib.Z_FULL_FLUSH))
                self.assert_cut_archive(name, ["a.txt"], ["sparse.img"], name + ": incomplete archive; members "
                                        "before the cut were read without a checksum", contents)

    def test_members_before_a_cut_keep_their_own_failure(self):
        # Only the member the cut runs through, and a hard link to it, fail
        # as cut. A FIFO, a device or a hard link that names no member fails
        # before the cut as it does in the whole archive.
        import random
        big = random.Random(2).randbytes(200000)
        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode="w", format=tarfile.GNU_FORMAT) as archive:
            for name, kind, link in (("a.txt", tarfile.REGTYPE, ""), ("fifo", tarfile.FIFOTYPE, ""),
                                     ("chr", tarfile.CHRTYPE, ""), ("ghost.lnk", tarfile.LNKTYPE, "no-such-member"),
                                     ("big.lnk", tarfile.LNKTYPE, "big.bin"), ("big.bin", tarfile.REGTYPE, "")):
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = link
                data = {"a.txt": b"first\n", "big.bin": big}.get(name)
                if kind == tarfile.CHRTYPE:
                    info.devmajor, info.devminor = 1, 3
                if data is None:
                    archive.addfile(info)
                else:
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
        tar = tar.getvalue()
        encoder = zlib.compressobj(6, zlib.DEFLATED, 31)
        (self.root / "cut.tar.gz").write_bytes(encoder.compress(tar[:100000]) + encoder.flush(zlib.Z_FULL_FLUSH))
        (self.root / "whole.tar.gz").write_bytes(gzip.compress(tar, mtime=0))
        special = ("fifo", "chr", "ghost.lnk")
        for command in ("t", "x"):
            lines = {}
            for name in ("whole.tar.gz", "cut.tar.gz"):
                if command == "x":
                    # A file already at every path.
                    destination = self.root / ("out-" + name)
                    destination.mkdir()
                    for member in ("a.txt",) + special + ("big.lnk", "big.bin"):
                        (destination / member).write_bytes(b"previous\n")
                    extra = ["-o" + str(destination)]
                else:
                    extra = ["--verbose"]
                result = self.run_xfu(command, name, *extra, success=False)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                lines[name] = {line.split(" -- ")[0].strip(): line for line in output.splitlines() if " -- " in line}
            with self.subTest(command=command):
                for member in special:
                    self.assertIn(" -- FAILED", lines["cut.tar.gz"][member])
                    self.assertEqual(lines["cut.tar.gz"][member], lines["whole.tar.gz"][member])
                    self.assertNotIn("(cut)", lines["cut.tar.gz"][member])
                for member in ("big.lnk", "big.bin"):
                    self.assertTrue(lines["cut.tar.gz"][member].endswith(member + " -- FAILED (cut)"),
                                    lines["cut.tar.gz"][member])
        self.assertEqual((self.root / "out-cut.tar.gz" / "big.bin").read_bytes(), b"previous\n")

    def test_sized_lzma_alone_without_end_marker_is_whole(self):
        # LZMA SDK's 'lzma e' records the size and writes no end marker
        # (libarchive's test_compat_lzma_3.tlz): a stream that delivered the
        # size it records is whole, not cut.
        import base64
        (self.root / "sized.tlz").write_bytes(base64.b64decode(
            "XQAQAAAAHAAAAAAAAAAzDDwbp4w0Bo1rAkv8kj72SviF6+Hd60VZhu5t0kIRE5+db8UF1/j4rxKm"
            "Evm6rlx1nJR1YdC9I2cSrC1R86WFoI1ux75TOdkHe/nNjvXR4LtKX3oXEkRGlZ5E4o3MIA74Cbnn"
            "0vLMHGRfmFcgAOENv2bYwRfKtEhCthLR4vuyltrMRIHUVVsd4Re3jDR53CIHpgA="))
        for command in ("l", "t"):
            result = self.run_xfu(command, "sized.tlz", *(("--verbose",) if command == "t" else ()))
            output = result.stdout + result.stderr
            self.assertNotIn("incomplete", output)
            for member in ("f1", "f2", "f3", "d1/f1", "d1/f2", "d1/f3"):
                self.assertIn(member + (" -- OK" if command == "t" else ""), output)
        result = self.run_xfu("x", "sized.tlz", "-o" + str(self.root / "out-sized"))
        self.assertEqual(sorted(p.relative_to(self.root / "out-sized").as_posix()
                                for p in (self.root / "out-sized").rglob("*") if p.is_file()),
                         ["d1/f1", "d1/f2", "d1/f3", "f1", "f2", "f3"])

    def test_compressed_tar_over_its_ram_threshold_uses_a_temporary_file(self):
        # Beyond 256 MiB the decoded TAR of a .tar.gz moves to a temporary
        # file (so one over the 1 GiB that RAM held lists and extracts);
        # its members read as from RAM, a cut one too.
        class Zeros(io.RawIOBase):
            def __init__(self, size):
                self.left = size
            def readable(self):
                return True
            def readinto(self, buffer):
                count = min(len(buffer), self.left)
                buffer[:count] = bytes(count)
                self.left -= count
                return count
        size = 300 * 1024 * 1024
        with gzip.open(self.root / "big.tar.gz", "wb", compresslevel=1) as stream:
            with tarfile.open(fileobj=stream, mode="w|") as archive:
                for name, data in (("first.txt", b"first\n"), ("zeros.bin", None), ("last.txt", b"last\n")):
                    info = tarfile.TarInfo(name)
                    info.size = size if data is None else len(data)
                    archive.addfile(info, Zeros(size) if data is None else io.BytesIO(data))
        listing = self.run_xfu("l", "big.tar.gz")
        self.assertIn("    %d  zeros.bin\n" % size, listing.stdout)
        self.assertIn("last.txt", listing.stdout)
        self.assertIn("3 member(s)", listing.stdout)
        if os.name != "nt":
            # Under a file size limit below the TAR (and SIGXFSZ at its
            # default), the temporary copy fails as on a full disk: the TAR
            # is decoded again into RAM, and only the member over the limit
            # fails.
            import resource
            def limit_files():
                resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, resource.RLIM_INFINITY))
            for arguments, code in ((("l",), 0), (("x", "-olimited"), 1)):
                result = subprocess.run([str(XFU), arguments[0], "big.tar.gz", *arguments[1:]], cwd=self.root,
                                        capture_output=True, encoding="utf-8", errors="replace", timeout=300,
                                        preexec_fn=limit_files, restore_signals=True)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, code, output)
                self.assertIn("3 member(s)", output)
            self.assertIn("  zeros.bin -- FAILED (file too large)", output)
            self.assertEqual((self.root / "limited" / "last.txt").read_bytes(), b"last\n")
            shutil.rmtree(self.root / "limited")
        data = (self.root / "big.tar.gz").read_bytes()
        (self.root / "cut-big.tar.gz").write_bytes(data[:len(data) * 9 // 10])
        result = self.run_xfu("l", "cut-big.tar.gz", success=False)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("incomplete archive; showing recovered members", output)
        self.assertIn("zeros.bin", output)
        self.assertNotIn("last.txt", output)

    def test_format_controls_in_names_are_escaped(self):
        # Bidirectional controls and separators would show a name reversed or
        # on two lines; other characters, joiners included, stay as they are.
        names = {
            "né‮evil.txt": "né\\xE2\\x80\\xAEevil.txt",
            "a⁦b⁩⁧⁨.txt": "a\\xE2\\x81\\xA6b\\xE2\\x81\\xA9\\xE2\\x81\\xA7\\xE2\\x81\\xA8.txt",
            "c‎d‏؜.txt": "c\\xE2\\x80\\x8Ed\\xE2\\x80\\x8F\\xD8\\x9C.txt",
            "line sep .txt": "line\\xE2\\x80\\xA8sep\\xE2\\x80\\xA9.txt",
            "lre‪‫‬‭.txt": "lre\\xE2\\x80\\xAA\\xE2\\x80\\xAB\\xE2\\x80\\xAC\\xE2\\x80\\xAD.txt",
            "zw\u200bsp\ufeff.txt": "zw\\xE2\\x80\\x8Bsp\\xEF\\xBB\\xBF.txt",
            "soft\u00adhy\u2060wj\u206a.txt": "soft\\xC2\\xADhy\\xE2\\x81\\xA0wj\\xE2\\x81\\xAA.txt",
            "mvs\u180eia\ufff9.txt": "mvs\\xE1\\xA0\\x8Eia\\xEF\\xBF\\xB9.txt",
            "ok-é日‍‰ا.txt": "ok-é日‍‰ا.txt",
        }
        # Every format character, the tags included (those of an emoji flag
        # too: hidden ones would make lookalikes), and the other code points
        # that draw nothing (CGJ, Hangul fillers, ...) are escaped; joiners
        # stay, and so does a variation selector after a base it applies to.
        def text(*points):
            return "".join(chr(point) for point in points)
        def escaped(*points):
            return "".join("\\x%02X" % byte for byte in text(*points).encode("utf-8"))
        tags = (0xE0067, 0xE0062, 0xE0065, 0xE006E, 0xE0067, 0xE007F)
        kept = (text(0x2764, 0xFE0F, 0x200C) + "1" + text(0xFE0F, 0x20E3) + text(0x8FBB, 0xE0100) +
                text(0x8FBB, 0xFE00) + text(0x1820, 0x180B, 0x1821, 0x180F) + text(0xA9, 0xFE0E))
        invisible = (0xE0020, 0xE0001, 0x034F, 0x3164, 0x115F, 0x1160, 0xFFA0,
                     0x1D173, 0x1BCA0, 0x17B4, 0x2065)
        selectors = (0xFE0F, 0xFE0E, 0xFE00, 0xFE05, 0xE0100, 0x180B, 0x180C, 0x180D, 0x180F)
        names.update({
            "inv" + text(*invisible) + ".txt": "inv" + escaped(*invisible) + ".txt",
            "lone" + text(0x1F3F4, 0xE0067) + ".txt": "lone" + text(0x1F3F4) + escaped(0xE0067) + ".txt",
            "flag" + text(0x1F3F4, *tags) + ".txt": "flag" + text(0x1F3F4) + escaped(*tags) + ".txt",
            "kept" + kept + ".txt": "kept" + kept + ".txt",
            "digit1" + text(0xFE0F) + ".txt": "digit1" + escaped(0xFE0F) + ".txt",
            "twice" + text(0x2764, 0xFE0F, 0xFE0F) + ".txt": "twice" + text(0x2764, 0xFE0F) + escaped(0xFE0F) + ".txt",
        })
        for point in selectors:
            names["vs%X" % point + text(point) + ".txt"] = "vs%X" % point + escaped(point) + ".txt"
        with tarfile.open(self.root / "controls.tar", "w", format=tarfile.PAX_FORMAT) as output:
            for name in names:
                entry = tarfile.TarInfo(name)
                entry.size = len(self.payload)
                output.addfile(entry, io.BytesIO(self.payload))
        listing = subprocess.run([str(XFU), "l", "controls.tar"], cwd=self.root,
                                 capture_output=True, timeout=90)
        self.assertEqual(listing.returncode, 0, listing.stderr)
        tested = subprocess.run([str(XFU), "t", "controls.tar", "--verbose"], cwd=self.root,
                                capture_output=True, timeout=90)
        self.assertEqual(tested.returncode, 0, tested.stderr)
        listing_text = listing.stdout.decode("utf-8").replace("\r\n", "\n")
        tested_text = tested.stdout.decode("utf-8").replace("\r\n", "\n")
        for name, shown in names.items():
            with self.subTest(name=shown):
                self.assertRegex(listing_text,
                                 r"\n +%d  %s\n" % (len(self.payload), re.escape(shown)))
                self.assertIn(shown + " -- OK\n", tested_text)
        for output in (listing.stdout, tested.stdout):
            for control in ("‮", "⁦", "‏", "؜", " ", "\u200b", "\ufeff",
                            "\u00ad", "\u2060", "\u206a", "\u180e", "\ufff9"):
                self.assertNotIn(control.encode("utf-8"), output)
        for output in (listing.stdout, tested.stdout):
            for point in invisible + tags:
                self.assertNotIn(chr(point).encode("utf-8"), output)

    def test_split_series_ignores_a_password(self):
        self.run_xfu("a", "parts.001", "alpha.txt", "--volume-size=1K")
        self.assertTrue((self.root / "parts.002").is_file())
        for command in ("l", "t"):
            plain = self.run_xfu(command, "parts.001")
            for password in ("-p", "-ptyped-for-another-archive"):
                with self.subTest(command=command, password=password):
                    self.assertEqual(self.run_xfu(command, "parts.001", password).stdout,
                                     plain.stdout)
        self.run_xfu("x", "parts.001", "-psecret", "-osplit-output")
        self.assertEqual([p.read_bytes() for p in (self.root / "split-output").rglob("*")
                          if p.is_file()], [self.payload])

    def test_mtree_symbolic_links_are_placeholders(self):
        self.require("format", "mtree", operation=0)
        # bsdtar --format mtree writes "type=link link=<target>" for a
        # symbolic link: the manifest opens, and the link extracts as an
        # empty placeholder, as TAR and CPIO links do.
        (self.root / "links.mtree").write_text(
            "#mtree\n"
            "./s type=dir mode=755\n"
            "./s/e type=file mode=644 size=0\n"
            "./s/l type=link mode=777 link=e\n"
            "./s/up type=link mode=777 link=../s/e\n", encoding="ascii")
        listing = self.run_xfu("l", "links.mtree")
        self.assertIn("links.mtree: MTREE", listing.stdout)
        self.assertIn("4 member(s)", listing.stdout)
        tested = self.run_xfu("t", "links.mtree", "--verbose")
        for name in ("s/l", "s/up"):
            self.assertIn(name + " -- OK", tested.stdout + tested.stderr)
        self.run_xfu("x", "links.mtree", "-olinks")
        for name in ("e", "l", "up"):
            path = self.root / "links" / "s" / name
            self.assertFalse(path.is_symlink(), name)
            self.assertEqual(path.read_bytes(), b"", name)

    def test_large_mtree_spec_lists_promptly(self):
        count = 25000
        with open(self.root / "large.mtree", "w", encoding="ascii") as output:
            output.write("#mtree\n/set type=file mode=0644\n")
            for index in range(count):
                output.write("d%02d/f%06d size=0\n" % (index % 50, index))
            output.write("D07/F000007 size=1\n")  # The same member again.
        started = time.monotonic()
        listing = self.run_xfu("l", "large.mtree")
        elapsed = time.monotonic() - started
        self.assertIn("%d member(s)" % count, listing.stdout)
        # Each line once looked up every member before it: about 20 s here.
        self.assertLess(elapsed, 10.0)

    def test_extraction_does_not_follow_existing_directory_symlink(self):
        outside = self.root / "outside"
        outside.mkdir()
        destination = self.root / "extract"
        destination.mkdir()
        try:
            (destination / "linked").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Directory symlinks are unavailable for this account")
        with tarfile.open(self.root / "linked.tar", "w") as output:
            entry = tarfile.TarInfo("linked/escaped.txt")
            entry.size = len(self.payload)
            output.addfile(entry, io.BytesIO(self.payload))
        self.run_xfu("x", "linked.tar", "--reader", "native", "-oextract", success=False)
        self.assertFalse((outside / "escaped.txt").exists())

    def make_tar(self, name, members):
        with tarfile.open(self.root / name, "w", format=tarfile.PAX_FORMAT) as output:
            for member, data in members:
                entry = tarfile.TarInfo(member)
                entry.size = len(data)
                output.addfile(entry, io.BytesIO(data))

    def make_newc(self, name, members):
        def record(index, member, data, mode=0o100644):
            member = member + b"\0"
            header = b"070701" + b"".join(b"%08X" % value for value in (
                index, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(member), 0)) + member
            return (header + b"\0" * (-len(header) % 4) + data + b"\0" * (-len(data) % 4))
        content = b"".join(record(i + 1, m.encode("utf-8", "surrogateescape"), d)
                           for i, (m, d) in enumerate(members))
        (self.root / name).write_bytes(content + record(0, b"TRAILER!!!", b"", 0))

    def test_output_folder_may_be_reached_through_a_link(self):
        # As /tmp is on macOS: the output folder, and the folders above it,
        # may be links. A link that extraction meets below it is refused.
        real = self.root / "real"
        real.mkdir()
        try:
            (self.root / "linkroot").symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Directory symlinks are unavailable for this account")
        self.make_tar("a.tar", [("a.txt", self.payload), ("d/b.txt", self.payload)])
        self.run_xfu("a", "a.zip", "alpha.txt", "--format=zip")
        for archive, member in (("a.tar", "d/b.txt"), ("a.zip", "alpha.txt")):
            for output in ("linkroot", "linkroot/out/", str(self.root / "linkroot" / "deep" / "out")):
                with self.subTest(archive=archive, output=output):
                    self.run_xfu("x", archive, "-o" + output)
                    target = Path(output) if Path(output).is_absolute() else self.root / output
                    self.assertEqual((target / member).read_bytes(), self.payload)
                    shutil.rmtree(real)
                    real.mkdir()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (real / "below").mkdir()
        (real / "below" / "d").symlink_to(elsewhere, target_is_directory=True)
        result = self.run_xfu("x", "a.tar", "-olinkroot/below", success=False)
        self.assertIn("  d/b.txt -- FAILED (a link is in the way)", result.stdout + result.stderr)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_extraction_replaces_a_link_at_a_members_path(self):
        # A link, or a file with another hard link, already at a member's
        # path is replaced: never written through to the file outside.
        outside = self.root / "outside.txt"
        self.make_tar("pre.tar", [("ok.txt", b"ok\n"), ("pre", b"member\n")])
        self.make_newc("pre.cpio", [("ok.txt", b"ok\n"), ("pre", b"member\n")])
        for archive in ("pre.tar", "pre.cpio"):
            for kind in ("symlink", "hard link"):
                with self.subTest(archive=archive, kind=kind):
                    destination = self.root / ("out-" + archive + "-" + kind.replace(" ", ""))
                    destination.mkdir()
                    outside.write_bytes(b"outside\n")
                    try:
                        if kind == "symlink":
                            (destination / "pre").symlink_to(outside)
                        else:
                            os.link(outside, destination / "pre")
                    except (OSError, NotImplementedError):
                        self.skipTest("Links are unavailable for this account")
                    self.run_xfu("x", archive, "-o" + destination.name)
                    self.assertEqual(outside.read_bytes(), b"outside\n")
                    self.assertFalse((destination / "pre").is_symlink())
                    self.assertEqual((destination / "pre").read_bytes(), b"member\n")

    def test_member_path_too_long_leaves_no_folders(self):
        if sys.platform.startswith("win"):
            # Extended paths take such a member there.
            self.skipTest("long POSIX paths only")
        too_long = ("d" * 200 + "/") * 21 + "f.txt"
        long_component = "a/b/c/" + "x" * 300
        self.make_tar("long.tar", [("ok.txt", b"ok\n"), (too_long, b"x\n"),
                                   (long_component, b"x\n"), ("a", b"a\n")])
        result = self.run_xfu("x", "long.tar", "-o" + str(self.root / "extract"), success=False)
        output = result.stdout + result.stderr
        self.assertIn("  %s -- FAILED (path too long)" % too_long, output)
        self.assertIn("  %s -- FAILED (path too long)" % long_component, output)
        self.assertIn("4 member(s), 2 failed", output)
        # Nothing was left behind that would be in a later member's way.
        self.assertEqual(sorted(p.name for p in (self.root / "extract").rglob("*")),
                         ["a", "ok.txt"])

    def test_failed_members_say_why(self):
        self.run_xfu("a", "one.zip", "alpha.txt", "--format=zip")
        self.run_xfu("x", "one.zip", "-oagain")
        (self.root / "again" / "folder.txt").mkdir()
        (self.root / "folder.txt").write_bytes(b"f\n")
        self.run_xfu("a", "two.zip", "alpha.txt", "folder.txt", "--format=zip")
        result = self.run_xfu("x", "two.zip", "-oagain", success=False)
        self.assertIn("  folder.txt -- FAILED (a folder is in the way)",
                      result.stdout + result.stderr)
        # A file already there is replaced (core.h, output_dir).
        self.assertIn("  alpha.txt -- replaced an existing file\n", result.stdout)
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            locked = self.root / "locked"
            locked.mkdir()
            locked.chmod(0o555)
            try:
                result = self.run_xfu("x", "one.zip", "-olocked", success=False)
            finally:
                locked.chmod(0o755)
            self.assertIn("  alpha.txt -- FAILED (permission denied)",
                          result.stdout + result.stderr)

    def test_test_says_why_tar_and_cpio_refuse_a_name(self):
        # Their readers refuse an unsafe name in Test too, as Extract does.
        members = [("a\x1b[31mred.txt", b"hi\n"), ("b\x07bell.txt", b"hi\n"), ("ok.txt", b"hi\n")]
        self.make_tar("names.tar", members)
        self.make_newc("names.cpio", members)
        for archive in ("names.tar", "names.cpio"):
            with self.subTest(archive=archive):
                result = self.run_xfu("t", archive, "--verbose", success=False)
                self.assertIn("a\\x1B[31mred.txt -- FAILED (unsafe member path)\n", result.stdout)
                self.assertIn("b\\x07bell.txt -- FAILED (unsafe member path)\n", result.stdout)
                self.assertIn("ok.txt -- OK\n", result.stdout)
                self.assertIn("3 member(s), 2 failed", result.stderr)

    def test_test_gives_a_data_failure_no_name_reason(self):
        self.require("format", "cpio_crc", operation=0)
        # The readers make an absolute name relative: a member stored as
        # "/abs/x.txt" whose data is damaged fails for its data, not its name.
        def record(name, data, check=None):
            name = name.encode("ascii") + b"\0"
            if check is None:
                check = sum(data) & 0xFFFFFFFF
            fields = (1, 0o100644, 0, 0, 1, 0, len(data), 8, 1, 0, 0, len(name), check)
            header = b"070702" + "".join(f"{value:08X}" for value in fields).encode("ascii")
            return (header + name + b"\0" * (-(len(header) + len(name)) % 4) +
                    data + b"\0" * (-len(data) % 4))
        for check, shown in ((None, "/abs/x.txt -- OK\n"), (1, "/abs/x.txt -- FAILED\n")):
            with self.subTest(check=check):
                content = (record("ok.txt", b"ok\n") + record("/abs/x.txt", b"data\n", check) +
                           record("TRAILER!!!", b""))
                (self.root / "abs.cpio").write_bytes(content + b"\0" * (-len(content) % 512))
                result = self.run_xfu("t", "abs.cpio", "--verbose", success=check is None)
                self.assertIn(shown, result.stdout)
                self.assertIn("ok.txt -- OK\n", result.stdout)

    def test_password_problems_are_named(self):
        self.run_xfu("a", "secret.zip", "alpha.txt", "--format=zip", "-psecret")
        for password, reason in (((), "encrypted; a password is needed"),
                                 (("-pwrong",), "wrong password, or damaged data")):
            with self.subTest(password=password):
                result = self.run_xfu("t", "secret.zip", "--verbose", *password, success=False)
                self.assertIn("alpha.txt -- FAILED (%s)\n" % reason, result.stdout)
        seven = shutil.which("7z")
        if not seven:
            return
        subprocess.run([seven, "a", "-bd", "-psecret", "-mhe=on", "headers.7z", "alpha.txt"],
                       cwd=self.root, capture_output=True, check=True, timeout=90)
        for password, message in (((), "the 7z headers are encrypted; a password is needed"),
                                  (("-pwrong",), "the password is wrong, or the encrypted 7z "
                                                 "headers are damaged")):
            with self.subTest(password=password):
                result = self.run_xfu("l", "headers.7z", *password, success=False)
                self.assertIn("headers.7z: " + message, result.stdout + result.stderr)
        self.assertIn("alpha.txt", self.run_xfu("l", "headers.7z", "-psecret").stdout)

    def test_stage_names_never_collide(self):
        # The ZIP, RAR, ISO and uImage readers write a member to a stage file
        # <its folder>/.xxfclib.tmp.N first. A member of that name is still
        # extracted, and a stage left over from an interrupted run is kept
        # and gives no false reason for a damaged member.
        names = (".xxfclib.tmp.0", "a.txt", "d/.xxfclib.tmp.0", "d/.xxfclib.tmp.1", "d/b.txt")
        with zipfile.ZipFile(self.root / "stages.zip", "w") as archive:
            for name in names:
                archive.writestr(name, name + "\n")
        destination = self.root / "out-stages"
        result = self.run_xfu("x", "stages.zip", "-o" + str(destination))
        self.assertIn("5 member(s)", result.stdout + result.stderr)
        self.assertEqual({p.relative_to(destination).as_posix(): p.read_bytes()
                          for p in destination.rglob("*") if p.is_file()},
                         {name: (name + "\n").encode() for name in names})
        with zipfile.ZipFile(self.root / "crc.zip", "w") as archive:
            archive.writestr("good.txt", "good data\n")
            archive.writestr("bad.txt", "bad data here\n")
        damaged = bytearray((self.root / "crc.zip").read_bytes())
        damaged[damaged.find(b"bad data here")] ^= 0x20
        (self.root / "crc.zip").write_bytes(bytes(damaged))
        destination = self.root / "out-crc"
        destination.mkdir()
        (destination / ".xxfclib.tmp.0").write_bytes(b"left over\n")
        result = self.run_xfu("x", "crc.zip", "-o" + str(destination), success=False)
        self.assertIn("  bad.txt -- FAILED\n", result.stdout + result.stderr)
        self.assertEqual((destination / ".xxfclib.tmp.0").read_bytes(), b"left over\n")
        self.assertEqual((destination / "good.txt").read_bytes(), b"good data\n")

    def test_uue_block_that_lost_its_end_fails(self):
        # A later block whose data lines are followed by text, without the
        # zero-length and "end" lines, is listed and fails; the blocks after
        # the text are still read.
        import binascii

        def block(name, payload, end=b"`\nend\n"):
            lines = b"".join(binascii.b2a_uu(payload[at:at + 45])
                             for at in range(0, len(payload), 45))
            return b"begin 644 " + name + b"\n" + lines + end

        (self.root / "cut.uue").write_bytes(
            block(b"a.txt", b"aaa\n") + block(b"b.bin", bytes(range(256)) * 80, b"") +
            b"some text\n" + block(b"c.txt", b"ccc\n"))
        tested = self.run_xfu("t", "cut.uue", "--verbose", success=False)
        output = tested.stdout + tested.stderr
        for line in ("a.txt -- OK", "b.bin -- FAILED", "c.txt -- OK", "3 member(s), 1 failed"):
            self.assertIn(line, output)
        destination = self.root / "out-cut"
        self.run_xfu("x", "cut.uue", "-o" + str(destination), success=False)
        self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()},
                         {"a.txt": b"aaa\n", "c.txt": b"ccc\n"})

    @unittest.skipIf(os.name == "nt", "needs a file size limit (RLIMIT_FSIZE)")
    def test_no_room_for_a_temporary_copy(self):
        # Under a file size limit, as with a full temporary folder, no
        # temporary copy longer than the limit can be written.
        import binascii
        import random
        import resource
        import signal

        def run_limited(limit, *arguments):
            def limit_files():
                signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
                resource.setrlimit(resource.RLIMIT_FSIZE, (limit, resource.RLIM_INFINITY))
            return subprocess.run([str(XFU), *map(str, arguments)], cwd=self.root,
                                  capture_output=True, encoding="utf-8", errors="replace",
                                  timeout=90, preexec_fn=limit_files)

        data = random.Random(7).randbytes(5500000)
        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode="w") as archive:
            info = tarfile.TarInfo("p.bin")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        uue_lines = lambda payload: b"".join(binascii.b2a_uu(payload[at:at + 45])
                                             for at in range(0, len(payload), 45))
        for payload, name, archived in ((data, "photo.jpg", False),
                                        (tar.getvalue(), "p.tar", True)):
            stem = "arc" if archived else "plain"
            (self.root / (stem + ".b64")).write_bytes(
                b"begin-base64 644 " + name.encode() + b"\n" +
                binascii.b2a_base64(payload, newline=False) + b"\n====\n")
            (self.root / (stem + ".uue")).write_bytes(
                b"begin 644 " + name.encode() + b"\n" + uue_lines(payload) + b"`\nend\n")
            for envelope, kind in ((stem + ".b64", "Base64"), (stem + ".uue", "uue")):
                with self.subTest(envelope=envelope):
                    result = run_limited(1 << 20, "l", envelope)
                    note = "no space for a temporary copy of the %s payload" % kind
                    output = result.stdout + result.stderr
                    self.assertIn(name, output)
                    if archived:
                        self.assertIn(note, output)
                        self.assertEqual(result.returncode, 1, output)
                    else:
                        self.assertNotIn(note, output)
                        self.assertEqual(result.returncode, 0, output)
        # A zstd or LZ4 layer of more than 4 MiB, whose start its detector
        # cannot name, is said like any other.
        (self.root / "p.bin").write_bytes(data)
        # The start of the zstd or LZ4 layer, a cut TAR.ZST or TAR.LZ4 (with
        # or without its size), names it.
        for layer, outer, kind, pack in (("zstd", "gz", "TAR.ZST", gzip.compress),
                                         ("lz4", "xz", "TAR.LZ4", __import__("lzma").compress)):
            with self.subTest(layer=layer):
                self.require("filter", layer)
                inner = "in.tar." + ("zst" if layer == "zstd" else layer)
                self.run_xfu("a", inner, "p.bin", "--format=pax", "--filter=" + layer)
                nested = inner + "." + outer
                (self.root / nested).write_bytes(pack((self.root / inner).read_bytes()))
                self.assertIn("p.bin", self.run_xfu("l", nested).stdout)
                result = run_limited(1 << 20, "l", nested)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("no space for a temporary copy of the %s inside" % kind,
                              result.stdout + result.stderr)
        # 7-Zip decodes a folder into a temporary copy: when only that copy
        # fails, the member says so.
        (self.root / "small.txt").write_bytes(b"small\n")
        (self.root / "big.bin").write_bytes(data[:300000])
        self.run_xfu("a", "s.7z", "big.bin", "small.txt", "--format=7zip")
        result = run_limited(100000, "x", "s.7z", "-o" + str(self.root / "out-7z"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("  big.bin -- FAILED (no room for a temporary copy)\n",
                      result.stdout + result.stderr)

    def overwrite_archives(self):
        """Archives of tree/a.txt and tree/sub/b.txt in the formats at hand,
        by name: each reader's default for an existing file differed."""
        import base64
        import lzma
        files = {"tree/a.txt": b"hello world\n", "tree/sub/b.txt": b"two\n" * 500}
        for name, data in files.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(data)
        with zipfile.ZipFile(self.root / "o.zip", "w", zipfile.ZIP_DEFLATED) as output:
            for name, data in files.items():
                output.writestr(name, data)
        self.make_tar("o.tar", files.items())
        self.make_newc("o.cpio", list(files.items()))
        (self.root / "o.tar.xz").write_bytes(lzma.compress((self.root / "o.tar").read_bytes()))
        (self.root / "a.txt.xz").write_bytes(lzma.compress(files["tree/a.txt"]))
        (self.root / "a.txt.gz").write_bytes(gzip.compress(files["tree/a.txt"]))
        (self.root / "a.txt.b64").write_bytes(b"begin-base64 644 a.txt\n" +
                                              base64.encodebytes(files["tree/a.txt"]) + b"====\n")
        archives = {"o.zip": files, "o.tar": files, "o.cpio": files, "o.tar.xz": files,
                    "a.txt.xz": {"payload": files["tree/a.txt"]},
                    "a.txt.gz": {"member-1": files["tree/a.txt"]},
                    "a.txt.b64": {"a.txt": files["tree/a.txt"]}}
        seven = shutil.which("7z")
        if seven:
            subprocess.run([seven, "a", "-bd", "o.7z", "tree"], cwd=self.root,
                           capture_output=True, check=True, timeout=90)
            archives["o.7z"] = files
        squash = shutil.which("mksquashfs")
        if squash:
            subprocess.run([squash, "tree", "o.sqfs", "-quiet", "-noappend", "-keep-as-directory"],
                           cwd=self.root, capture_output=True, check=True, timeout=90)
            archives["o.sqfs"] = files
        return archives

    def test_existing_files_are_replaced_whatever_the_reader(self):
        # One policy: what is at a member's path is replaced (a link there
        # too, never written through, and a read-only file, as a staged
        # member's rename replaces it), and the member's line says so.
        outside = self.root / "outside.txt"
        for archive, files in self.overwrite_archives().items():
            with self.subTest(archive=archive):
                destination = self.root / ("again-" + archive)
                self.run_xfu("x", archive, "-o" + str(destination))
                outside.write_bytes(b"outside\n")
                for name in files:
                    (destination / name).write_bytes(b"OLD\n")
                first = destination / sorted(files)[0]
                if os.name != "nt":
                    first.unlink()
                    first.symlink_to(outside)
                    if len(files) > 1:
                        (destination / sorted(files)[1]).chmod(0o444)
                result = self.run_xfu("x", archive, "-o" + str(destination))
                output = result.stdout + result.stderr
                self.assertNotIn("FAILED", output)
                for name, data in files.items():
                    self.assertEqual((destination / name).read_bytes(), data)
                    self.assertIn("  %s -- replaced an existing file\n" % name, result.stdout)
                self.assertFalse(first.is_symlink())
                self.assertEqual(outside.read_bytes(), b"outside\n")

    def test_a_member_never_replaces_the_archive_being_read(self):
        # Replacing what is at a member's path stops at the archive itself:
        # TAR wrote it in place, so the rest of the read failed with it.
        data = b"x" * 100000
        with zipfile.ZipFile(self.root / "self.zip", "w") as output:
            for name, content in (("a.txt", b"a\n"), ("self.zip", b"member\n"), ("z.txt", data)):
                output.writestr(name, content)
        self.make_tar("self.tar", [("a.txt", b"a\n"), ("self.tar", b"member\n"), ("z.txt", data)])
        for archive in ("self.zip", "self.tar"):
            with self.subTest(archive=archive):
                before = (self.root / archive).read_bytes()
                result = self.run_xfu("x", archive, "-o.", success=False)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("  %s -- FAILED (it would replace the archive)\n" % archive,
                              result.stderr)
                self.assertIn("3 member(s), 1 failed", result.stdout + result.stderr)
                self.assertEqual((self.root / archive).read_bytes(), before)
                self.assertEqual((self.root / "z.txt").read_bytes(), data)
                (self.root / "z.txt").unlink()

    def test_a_member_named_with_backslashes_never_replaces_the_archive(self):
        # The readers split a name at '\' as at '/' on every system, so the
        # check looks at that path: sub\self.zip below "." is sub/self.zip.
        data = b"x" * 100000
        (self.root / "sub").mkdir()
        members = {"self.zip": "sub\\self.zip", "mix.zip": ".\\sub/.\\mix.zip",
                   "self.tar": "sub\\self.tar", "dot.tar": "sub\\.\\dot.tar",
                   "self.cpio": "sub\\self.cpio"}
        for archive, member in members.items():
            content = [("a.txt", b"a\n"), (member, b"member\n"), ("z.txt", data)]
            if archive.endswith(".zip"):
                with zipfile.ZipFile(self.root / "sub" / archive, "w") as output:
                    for name, value in content:
                        output.writestr(name, value)
            elif archive.endswith(".tar"):
                self.make_tar("sub/" + archive, content)
            else:
                self.make_newc("sub/" + archive, content)
        seven = shutil.which("7z")
        if seven and os.name != "nt":
            source = self.root / "seven"
            source.mkdir()
            for name, value in (("a.txt", b"a\n"), ("sub\\self.7z", b"member\n"), ("z.txt", data)):
                (source / name).write_bytes(value)
            subprocess.run([seven, "a", "-bd", str(self.root / "sub" / "self.7z"), "a.txt",
                            "sub\\self.7z", "z.txt"], cwd=source, capture_output=True,
                           check=True, timeout=90)
            members["self.7z"] = "sub\\self.7z"
        for archive, member in members.items():
            with self.subTest(archive=archive):
                path = self.root / "sub" / archive
                before = path.read_bytes()
                result = self.run_xfu("x", "sub/" + archive, "-o.", success=False)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                lines = ["  %s -- FAILED (it would replace the archive)\n" % member,
                         "  %s -- FAILED (it would replace the archive)\n" %
                         member.replace("\\", "/")]
                self.assertTrue(any(line in result.stderr for line in lines), result.stderr)
                self.assertIn("3 member(s), 1 failed", result.stdout + result.stderr)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual((self.root / "z.txt").read_bytes(), data)
        # A file at such a member's path elsewhere is replaced, and its line says so.
        with zipfile.ZipFile(self.root / "w.zip", "w") as output:
            output.writestr("t\\a.txt", b"new\n")
        (self.root / "o" / "t").mkdir(parents=True)
        (self.root / "o" / "t" / "a.txt").write_bytes(b"OLD\n")
        result = self.run_xfu("x", "w.zip", "-oo")
        self.assertIn("  t/a.txt -- replaced an existing file\n", result.stdout)
        self.assertEqual((self.root / "o" / "t" / "a.txt").read_bytes(), b"new\n")

    def test_a_tar_or_cpio_file_whose_name_ends_in_a_separator_fails(self):
        # A member that holds data is a file: it is never made an empty folder.
        # A trailing '/' makes a folder, as old writers stored folders.
        members = [("plain\\", b"plain data\n"), ("w\\x.txt", b"wx\n"),
                   ("emptydir/", b""), ("ok.txt", b"ok\n")]
        if os.name != "nt":
            members.append(("D:\\", b"drive data\n"))
        self.make_tar("bs.tar", members)
        self.make_newc("bs.cpio", members)
        (self.root / "bs.tar.gz").write_bytes(gzip.compress((self.root / "bs.tar").read_bytes()))
        failing = [name for name, value in members if name.endswith("\\")]
        for archive in ("bs.tar", "bs.tar.gz", "bs.cpio"):
            with self.subTest(archive=archive):
                destination = self.root / ("o-" + archive)
                for command in ("t", "x"):
                    arguments = [command, archive] + (["-o" + str(destination)] if command == "x" else ["-v"])
                    result = self.run_xfu(*arguments, success=False)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    output = result.stdout + result.stderr
                    for name in failing:
                        self.assertIn("%s -- FAILED (the name ends in a separator)\n" % name, output)
                    self.assertIn("%d member(s), %d failed" % (len(members), len(failing)), output)
                self.assertEqual(sorted(p.name for p in destination.iterdir()), ["emptydir", "ok.txt", "w"])
                self.assertTrue((destination / "emptydir").is_dir())
                self.assertEqual((destination / "w" / "x.txt").read_bytes(), b"wx\n")

    def test_a_raw_or_envelope_member_that_would_replace_the_archive_says_so(self):
        import base64
        (self.root / "r.dat").write_bytes(b"raw data\n")
        (self.root / "x.b64").write_bytes(b"begin-base64 644 x.b64\n" +
                                          base64.encodebytes(b"payload\n") + b"====\n")
        for archive, arguments in (("r.dat", ("--reader", "native:raw")), ("x.b64", ())):
            with self.subTest(archive=archive):
                before = (self.root / archive).read_bytes()
                result = self.run_xfu("x", archive, *arguments, "-o.", success=False)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("  %s -- FAILED (it would replace the archive)\n" % archive,
                              result.stderr)
                self.assertEqual((self.root / archive).read_bytes(), before)

    @unittest.skipIf(sys.platform.startswith("win"), "':' names a drive or a stream there")
    def test_member_names_with_a_colon_are_extracted_off_windows(self):
        names = {"a:b.txt": b"one\n", "d:ir/9:00-notes.txt": b"two\n", "c:": b"three\n"}
        for name, data in names.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(data)
        self.make_tar("c.tar", names.items())
        self.make_newc("c.cpio", list(names.items()))
        with zipfile.ZipFile(self.root / "c.zip", "w") as output:
            for name, data in names.items():
                output.writestr(name, data)
        archives = {"c.tar": names, "c.cpio": names, "c.zip": names}
        self.run_xfu("a", "x.zip", "a:b.txt", "d:ir", "c:", "--format=zip")
        archives["x.zip"] = names
        with open(self.root / "a.gz", "wb") as raw:
            with gzip.GzipFile("a:b.txt", "wb", fileobj=raw, mtime=0) as output:
                output.write(b"one\n")
        archives["a.gz"] = {"a:b.txt": b"one\n"}
        seven = shutil.which("7z")
        if seven:
            subprocess.run([seven, "a", "-bd", "c.7z", "a:b.txt", "d:ir", "c:"],
                           cwd=self.root, capture_output=True, check=True, timeout=90)
            archives["c.7z"] = names
        for archive, members in archives.items():
            with self.subTest(archive=archive):
                tested = self.run_xfu("t", archive, "--verbose")
                for name in members:
                    self.assertIn(name + " -- OK\n", tested.stdout)
                destination = self.root / ("out-" + archive)
                result = self.run_xfu("x", archive, "-o" + str(destination))
                self.assertNotIn("FAILED", result.stdout + result.stderr)
                for name, data in members.items():
                    self.assertEqual((destination / name).read_bytes(), data)

    @staticmethod
    def zip64_end(data, offset_in_extra=False):
        """data, a small ZIP, with ZIP64 end records (its EOCD then holds
        sentinels) and, when asked, the first entry's local header offset in
        a ZIP64 extra field."""
        eocd = data.rfind(b"PK\x05\x06")
        count, size, start = struct.unpack_from("<HII", data, eocd + 10)
        directory = bytearray(data[start:start + size])
        if offset_in_extra:
            names, extras, comments = struct.unpack_from("<HHH", directory, 28)
            offset = struct.unpack_from("<I", directory, 42)[0]
            field = struct.pack("<HHQ", 1, 8, offset)
            at = 46 + names + extras
            directory[at:at] = field
            struct.pack_into("<H", directory, 30, extras + len(field))
            struct.pack_into("<I", directory, 42, 0xFFFFFFFF)
        record = struct.pack("<IQHHIIQQQQ", 0x06064B50, 44, 45, 45, 0, 0, count, count,
                             len(directory), start)
        locator = struct.pack("<IIQI", 0x07064B50, 0, start + len(directory), 1)
        end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, count, count, len(directory),
                          0xFFFFFFFF, 0)
        return data[:start] + bytes(directory) + record + locator + end

    @staticmethod
    def zip_offsets_moved(data, shift):
        """A ZIP64 archive of zip64_end after shift bytes of other data, with
        every offset moved by shift, as zip -A adjusts them."""
        data = bytearray(data)
        eocd = data.rfind(b"PK\x05\x06")
        locator = eocd - 20
        record = struct.unpack_from("<Q", data, locator + 8)[0] + shift
        size, start = struct.unpack_from("<QQ", data, record + 40)
        struct.pack_into("<Q", data, record + 48, start + shift)
        struct.pack_into("<Q", data, locator + 8, record)
        at = start + shift
        while data[at:at + 4] == b"PK\x01\x02":
            names, extras, comments = struct.unpack_from("<HHH", data, at + 28)
            offset = struct.unpack_from("<I", data, at + 42)[0]
            if offset == 0xFFFFFFFF:
                struct.pack_into("<Q", data, at + 50 + names,
                                 struct.unpack_from("<Q", data, at + 50 + names)[0] + shift)
            else:
                struct.pack_into("<I", data, at + 42, offset + shift)
            at += 46 + names + extras + comments
        return bytes(data)

    def test_zip64_after_a_stub_is_found_through_its_end_locator(self):
        members = {"a.txt": b"hello\n", "sub/b.txt": b"%d\n" * 1 % 7 * 300}
        plain = io.BytesIO()
        with zipfile.ZipFile(plain, "w", zipfile.ZIP_DEFLATED) as output:
            for name, data in members.items():
                output.writestr(name, data)
        stub = b"#!/bin/sh\necho self-extractor\nexit 0\n" + b"\0" * 29
        cases = {
            "z64.zip": self.zip64_end(plain.getvalue()),
            "stub64.zip": stub + self.zip64_end(plain.getvalue()),
            "stub64-extra.zip": stub + self.zip64_end(plain.getvalue(), True),
        }
        cases["stub64-moved.zip"] = self.zip_offsets_moved(cases["stub64.zip"], len(stub))
        cases["stub64-extra-moved.zip"] = self.zip_offsets_moved(cases["stub64-extra.zip"],
                                                                 len(stub))
        # A locator that names no end record is no ZIP64 that opens.
        broken = bytearray(cases["stub64.zip"])
        struct.pack_into("<Q", broken, len(broken) - 22 - 20 + 8, 12345)
        for archive, content in cases.items():
            (self.root / archive).write_bytes(content)
            with self.subTest(archive=archive):
                listed = self.run_xfu("l", archive)
                self.assertIn(archive + ": ZIP64\n", listed.stdout)
                self.assertIn("2 member(s)", listed.stdout)
                self.run_xfu("t", archive)
                destination = self.root / ("out-" + archive)
                self.run_xfu("x", archive, "-o" + str(destination))
                for name, data in members.items():
                    self.assertEqual((destination / name).read_bytes(), data)
        (self.root / "broken64.zip").write_bytes(bytes(broken))
        self.assertEqual(self.run_xfu("l", "broken64.zip", success=False).returncode, 2)

    def test_7z_test_shows_the_progress_of_a_solid_folder(self):
        # A solid folder is decoded whole at its first file (Test checks the
        # files as it goes): the percentage moves while it is, by its bytes,
        # not only when its files are counted (0, 33, 66, 99, 100 for three).
        seven = shutil.which("7z")
        if not seven:
            self.skipTest("7z is not installed")
        (self.root / "s").mkdir()
        (self.root / "s" / "a.txt").write_bytes(b"a\n")
        (self.root / "s" / "big.txt").write_bytes(
            b"".join(b"%d\n" % number for number in range(1200000)))
        (self.root / "s" / "z.txt").write_bytes(b"z\n")
        subprocess.run([seven, "a", "-bd", "-m0=PPMd", "-ms=on", str(self.root / "s.7z"),
                        "a.txt", "big.txt", "z.txt"], cwd=self.root / "s",
                       capture_output=True, check=True, timeout=90)
        result = self.run_xfu("t", "s.7z")
        percents = [int(line[:-1]) for line in result.stdout.split()]
        self.assertEqual(percents[-1], 100)
        self.assertEqual(percents, sorted(percents))
        self.assertTrue([p for p in percents if p not in (0, 33, 66, 99, 100)], percents)


if __name__ == "__main__":
    unittest.main(verbosity=2)

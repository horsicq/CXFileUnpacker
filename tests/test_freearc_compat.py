"""Validate FreeArc creation, independently parsed framing and native reads."""

from pathlib import Path
import os
import lzma
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


XFU = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None
UPSTREAM_UNARC = None
for argument in list(sys.argv[1:]):
    if argument.startswith("--upstream-unarc="):
        UPSTREAM_UNARC = Path(argument.split("=", 1)[1]).resolve()
        sys.argv.remove(argument)


class Cursor:
    def __init__(self, data, offset=0):
        self.data = data
        self.offset = offset

    def take(self, size):
        value = self.data[self.offset:self.offset + size]
        if len(value) != size:
            raise ValueError("Truncated FreeArc field")
        self.offset += size
        return value

    def num(self):
        first = self.take(1)[0]
        extra = 0
        while extra < 8 and first & (1 << extra):
            extra += 1
        if extra == 8:
            return int.from_bytes(self.take(8), "little")
        return int.from_bytes(bytes([first]) + self.take(extra), "little") >> (extra + 1)

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def string(self):
        end = self.data.index(0, self.offset)
        value = self.take(end - self.offset).decode("utf-8")
        self.take(1)
        return value


def descriptor(data, offset):
    cursor = Cursor(data, offset)
    if cursor.take(4) != b"ArC\x01":
        raise ValueError("Missing FreeArc descriptor signature")
    kind, method = cursor.num(), cursor.string()
    original, packed, crc = cursor.num(), cursor.num(), cursor.u32()
    checked = cursor.offset
    if cursor.u32() != zlib.crc32(data[offset:checked]):
        raise ValueError("Invalid descriptor CRC")
    if method != "storing" or original != packed or packed > offset:
        raise ValueError("Not a stored control block")
    block_offset = offset - packed
    block = data[block_offset:offset]
    if zlib.crc32(block) != crc:
        raise ValueError("Invalid control block CRC")
    return kind, block_offset, block, crc, cursor.offset


def parse_freearc(data):
    if data[:8] != b"ArC\x01\x00\x00\x06\x07":
        raise ValueError("Not the FreeArc 0.67-compatible header")
    header = descriptor(data, 8)
    if header[0] != 1:
        raise ValueError("Invalid header block type")
    footer_descriptor = data.rfind(b"ArC\x01", max(0, len(data) - 4096))
    footer = descriptor(data, footer_descriptor)
    if footer[0] != 4 or footer[4] != len(data):
        raise ValueError("Missing final footer descriptor")
    cursor = Cursor(footer[2])
    controls = []
    for _ in range(cursor.num()):
        kind, method, relative = cursor.num(), cursor.string(), cursor.num()
        original, packed, crc = cursor.num(), cursor.num(), cursor.u32()
        offset = footer[1] - relative
        parsed = descriptor(data, offset + packed)
        if (kind, offset, original, crc) != (parsed[0], parsed[1], len(parsed[2]), parsed[3]):
            raise ValueError("Footer disagrees with control descriptor")
        if method != "storing":
            raise ValueError("Unexpected control method")
        controls.append(parsed)
    if cursor.take(1) != b"\x00" or cursor.num() != 0 or cursor.string() != "" or cursor.num() != 0:
        raise ValueError("Unexpected footer options")
    if cursor.offset != len(cursor.data):
        raise ValueError("Unexpected footer fields")
    directories = [control for control in controls if control[0] == 3]
    if len(directories) != 1:
        raise ValueError("Expected one directory block")
    directory = directories[0]
    cursor = Cursor(directory[2])
    blocks = cursor.num()
    counts = [cursor.num() for _ in range(blocks)]
    methods = [cursor.string() for _ in range(blocks)]
    offsets = [directory[1] - cursor.num() for _ in range(blocks)]
    packed = [cursor.num() for _ in range(blocks)]
    paths = [cursor.string() for _ in range(cursor.num())]
    count = sum(counts)
    names = [cursor.string() for _ in range(count)]
    path_indexes = [cursor.num() for _ in range(count)]
    sizes = [cursor.num() for _ in range(count)]
    times = [cursor.u32() for _ in range(count)]
    folders = cursor.take(count)
    crcs = [cursor.u32() for _ in range(count)]
    if cursor.num() != 0 or cursor.offset != len(cursor.data):
        raise ValueError("Unexpected optional directory fields")
    if any(times) or any(folders):
        raise ValueError("Unexpected folder or timestamp metadata")
    result = {}
    index = 0
    for block in range(blocks):
        block_data = data[offsets[block]:offsets[block] + packed[block]]
        if len(block_data) != packed[block]:
            raise ValueError("Truncated data block")
        if methods[block] != "storing":
            match = re.fullmatch(r"lzma:(\d+)kb:lc(\d):lp(\d):pb(\d)", methods[block])
            if not match:
                raise ValueError("Unexpected data method")
            dictionary, lc, lp, pb = map(int, match.groups())
            if dictionary > 16 * 1024:
                raise ValueError("Dictionary exceeds writer limit")
            decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
                "id": lzma.FILTER_LZMA1, "dict_size": dictionary * 1024,
                "lc": lc, "lp": lp, "pb": pb,
            }])
            block_data = decoder.decompress(block_data)
            if not decoder.eof or decoder.unused_data:
                raise ValueError("Invalid raw LZMA block boundary")
        position = 0
        for _ in range(counts[block]):
            name = "/".join(part for part in (paths[path_indexes[index]], names[index]) if part)
            payload = block_data[position:position + sizes[index]]
            if len(payload) != sizes[index] or zlib.crc32(payload) != crcs[index] or name in result:
                raise ValueError("Invalid or duplicate member")
            result[name] = payload
            position += sizes[index]
            index += 1
        if position != len(block_data):
            raise ValueError("Wrong unpacked block size")
    return result, header[4]


class FreeArcCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XFU is None or not XFU.is_file():
            raise RuntimeError("Usage: python test_freearc_compat.py /path/to/xfu")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xfu-freearc-")
        self.root = Path(self.temporary.name)
        self.payload = b"FreeArc stored library-only member\n" * 200 + bytes(range(256)) * 300
        (self.root / "alpha.txt").write_bytes(self.payload)

    def tearDown(self):
        self.temporary.cleanup()

    def run_xfu(self, *arguments, success=True):
        result = subprocess.run([str(XFU), *map(str, arguments)], cwd=self.root,
                                capture_output=True, encoding="utf-8", errors="replace", timeout=90)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def verify(self, archive, expected, output="extracted"):
        parsed, _ = parse_freearc((self.root / archive).read_bytes())
        self.assertEqual(parsed, expected)
        listing = self.run_xfu("l", archive, "--reader", "freearc")
        for name in expected:
            self.assertIn(name, listing.stdout)
        self.run_xfu("t", archive, "--reader", "freearc")
        self.run_xfu("x", archive, "--reader", "freearc", "-o" + output)
        actual = {path.relative_to(self.root / output).as_posix(): path.read_bytes()
                  for path in (self.root / output).rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        if UPSTREAM_UNARC is not None:
            upstream_output = self.root / (output + "-upstream")
            for command in (("t", archive), ("x", "-dp" + str(upstream_output), archive)):
                result = subprocess.run([str(UPSTREAM_UNARC), *command], cwd=self.root,
                                        capture_output=True, encoding="utf-8", errors="replace", timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            actual = {path.relative_to(upstream_output).as_posix(): path.read_bytes()
                      for path in upstream_output.rglob("*") if path.is_file()}
            self.assertEqual(actual, expected)

    def test_capability_is_partial_reader_real_creator(self):
        report = self.run_xfu("--capabilities")
        self.assertRegex(report.stdout, r"(?m)^native freearc read=partial create=yes$")

    def test_explicit_selector_and_independent_framing(self):
        self.run_xfu("a", "archive.bin", "alpha.txt", "--format=freearc")
        self.verify("archive.bin", {"alpha.txt": self.payload})

    def test_freearc_suffix_aliases(self):
        for suffix in ("arc", "wrc"):
            with self.subTest(suffix=suffix):
                archive = "archive." + suffix
                self.run_xfu("a", archive, "alpha.txt")
                self.verify(archive, {"alpha.txt": self.payload}, output=suffix)

    def test_multiple_empty_and_unicode_members(self):
        name = "caf\u00e9-\u65e5\u672c.txt"
        (self.root / name).write_bytes(b"Unicode member")
        (self.root / "empty.txt").write_bytes(b"")
        self.run_xfu("a", "members.arc", "alpha.txt", "empty.txt", name, "--format=freearc")
        self.verify("members.arc", {"alpha.txt": self.payload, "empty.txt": b"", name: b"Unicode member"})

    def test_relative_directories_and_absolute_basename(self):
        (self.root / "sub").mkdir()
        (self.root / "sub" / "beta.txt").write_bytes(b"nested")
        self.run_xfu("a", "paths.arc", self.root / "alpha.txt", "./sub/beta.txt", "--format=freearc")
        self.verify("paths.arc", {"alpha.txt": self.payload, "sub/beta.txt": b"nested"})

    def test_stored_method_aliases_and_level_zero(self):
        for method in ("store", "stored", "storing"):
            with self.subTest(method=method):
                archive = method + ".arc"
                self.run_xfu("a", archive, "alpha.txt", "--format=freearc",
                             "--compression=" + method, "--compression-level=0")
                self.verify(archive, {"alpha.txt": self.payload}, output=method)

    def test_lzma_levels_and_default_are_interoperable(self):
        for level in (None, 0, 1, 5):
            with self.subTest(level=level):
                archive = "lzma-" + str(level) + ".arc"
                options = [] if level is None else ["--compression-level=" + str(level)]
                self.run_xfu("a", archive, "alpha.txt", "--format=freearc",
                             "--compression=lzma", *options)
                self.assertLess((self.root / archive).stat().st_size, len(self.payload) // 4)
                self.verify(archive, {"alpha.txt": self.payload}, output="lzma-" + str(level))

    def test_lzma_multiple_empty_unicode_and_incompressible_members(self):
        name = "caf\u00e9-\u65e5\u672c.txt"
        random_payload = os.urandom(2 * 1024 * 1024 + 19)
        (self.root / name).write_bytes(random_payload)
        (self.root / "empty.txt").write_bytes(b"")
        self.run_xfu("a", "members-lzma.arc", "alpha.txt", "empty.txt", name,
                     "--format=freearc", "--compression=lzma")
        self.verify("members-lzma.arc", {
            "alpha.txt": self.payload, "empty.txt": b"", name: random_payload,
        })

    def test_rejects_invalid_options_without_replacing_output(self):
        destination = self.root / "keep.arc"
        for options in (["--compression-level=-1"], ["--compression-level=1"],
                        ["--compression=deflate"], ["--filter=gzip"],
                        ["--compression=lzma", "--compression-level=-1"],
                        ["--compression=lzma", "--compression-level=6"],
                        ["--options=unknown=1"], ["-psecret"]):
            with self.subTest(options=options):
                destination.write_bytes(b"existing archive")
                before = set(self.root.iterdir())
                self.run_xfu("a", destination.name, "alpha.txt", "--format=freearc", *options, success=False)
                self.assertEqual(destination.read_bytes(), b"existing archive")
                self.assertEqual(set(self.root.iterdir()), before)

    def test_rejects_bad_sources_and_duplicate_names(self):
        destination = self.root / "keep.arc"
        (self.root / "directory").mkdir()
        for sources in (("missing",), ("directory",), ("alpha.txt", "./alpha.txt")):
            with self.subTest(sources=sources):
                destination.write_bytes(b"existing archive")
                before = set(self.root.iterdir())
                self.run_xfu("a", destination.name, *sources, "--format=freearc", success=False)
                self.assertEqual(destination.read_bytes(), b"existing archive")
                self.assertEqual(set(self.root.iterdir()), before)

    def test_rejects_self_and_hard_link_alias(self):
        destination = self.root / "self.arc"
        destination.write_bytes(b"original")
        self.run_xfu("a", destination.name, destination.name, "--format=freearc", success=False)
        alias = self.root / "alias.txt"
        os.link(destination, alias)
        self.run_xfu("a", destination.name, alias.name, "--format=freearc", success=False)
        self.assertEqual(destination.read_bytes(), b"original")
        self.assertEqual(alias.read_bytes(), b"original")

    def test_rejects_symlink_sources(self):
        link = self.root / "link.txt"
        try:
            link.symlink_to(self.root / "alpha.txt")
        except (OSError, NotImplementedError):
            self.skipTest("File symlinks are unavailable for this account")
        self.run_xfu("a", "link.arc", link.name, "--format=freearc", success=False)
        self.assertFalse((self.root / "link.arc").exists())

    def test_payload_crc_and_truncation_fail_native_test(self):
        self.run_xfu("a", "valid.arc", "alpha.txt", "--format=freearc")
        data = bytearray((self.root / "valid.arc").read_bytes())
        _, payload_offset = parse_freearc(data)
        data[payload_offset + 10] ^= 0x80
        (self.root / "bad-crc.arc").write_bytes(data)
        self.run_xfu("t", "bad-crc.arc", "--reader", "freearc", success=False)
        (self.root / "truncated.arc").write_bytes(data[:len(data) // 2])
        self.run_xfu("t", "truncated.arc", "--reader", "freearc", success=False)

    def test_control_crc_failure_is_rejected(self):
        self.run_xfu("a", "valid.arc", "alpha.txt", "--format=freearc")
        data = bytearray((self.root / "valid.arc").read_bytes())
        data[-1] ^= 0x80
        (self.root / "bad-footer.arc").write_bytes(data)
        self.run_xfu("t", "bad-footer.arc", "--reader", "freearc", success=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)

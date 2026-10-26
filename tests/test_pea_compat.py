"""Round-trip PEA writers and independently verify their documented wire layout."""

from pathlib import Path
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


XFU = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None


def read_pea(path):
    """Parse plaintext PCOMPRESS0..3, checking object, stream and volume CRC32."""
    data = path.read_bytes()
    assert data[:4] == b"\xea\x01\x00\x02"
    assert data[10:16] == b"\0\0POD\0"
    assert data[17:20] == b"\0\x02\x02"
    assert data[6] == 0x10 and data[7] == 1 and not data[8] & 0x80
    compression = data[16]
    assert compression in range(4)
    at = 20
    block_size = None
    if compression:
        block_size = struct.unpack_from("<I", data, at)[0]
        assert block_size == 1048576
        at += 4
    members = {}
    blocks = []
    while True:
        start = at
        length = struct.unpack_from("<H", data, at)[0]
        at += 2
        if not length:
            assert data[at:at + 4] == b"EOA\0"
            at += 4
            break
        name = data[at:at + length].decode("utf-8")
        assert name.startswith("/") or (len(name) > 2 and name[1] == ":") or name.startswith("\\\\")
        at += length
        date_time, attributes, size = struct.unpack_from("<IIQ", data, at)
        assert not attributes & 0x10
        assert date_time >> 16
        at += 16
        crc = zlib.crc32(data[start:at])
        result = bytearray()
        if compression:
            while len(result) < size:
                raw_size = min(block_size, size - len(result))
                packed_size = struct.unpack_from("<I", data, at)[0]
                assert 0 < packed_size <= raw_size
                crc = zlib.crc32(data[at:at + 4], crc)
                at += 4
                packed = data[at:at + packed_size]
                raw = packed if packed_size == raw_size else zlib.decompress(packed)
                assert len(raw) == raw_size
                blocks.append((raw_size, packed_size))
                result.extend(raw)
                crc = zlib.crc32(raw, crc)
                at += packed_size
            if size:
                assert struct.unpack_from("<I", data, at)[0] == raw_size
                crc = zlib.crc32(data[at:at + 4], crc)
                at += 4
        else:
            result.extend(data[at:at + size])
            assert len(result) == size
            crc = zlib.crc32(result, crc)
            at += size
        assert struct.unpack_from("<I", data, at)[0] == crc
        at += 4
        basename = name.replace("\\", "/").rsplit("/", 1)[-1]
        assert basename not in members
        members[basename] = bytes(result)
    assert struct.unpack_from("<I", data, at)[0] == zlib.crc32(data[:at])
    at += 4
    assert struct.unpack_from("<I", data, at)[0] == zlib.crc32(data[:at])
    assert at + 4 == len(data)
    return members, blocks


class PeaCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XFU is None or not XFU.is_file():
            raise RuntimeError("Usage: python test_pea_compat.py /path/to/xfu")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xfu-pea-")
        self.root = Path(self.temporary.name)
        self.payload = b"PEA independent block format test\n" * 40000
        (self.root / "alpha.txt").write_bytes(self.payload)

    def tearDown(self):
        self.temporary.cleanup()

    def run_xfu(self, *arguments, success=True):
        result = subprocess.run([str(XFU), *map(str, arguments)], cwd=self.root,
            capture_output=True, encoding="utf-8", errors="replace", timeout=120)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def round_trip(self, archive, expected):
        members, blocks = read_pea(self.root / archive)
        self.assertEqual(members, expected)
        listing = self.run_xfu("l", archive).stdout
        for name in expected:
            self.assertIn(name, listing)
        self.run_xfu("t", archive)
        output = self.root / ("out-" + archive)
        self.run_xfu("x", archive, "-o" + str(output))
        files = {path.relative_to(output).as_posix(): path.read_bytes()
            for path in output.rglob("*") if path.is_file()}
        self.assertEqual(files, expected)
        return blocks

    def test_default_suffix_and_explicit_format(self):
        for archive, options in (("auto.pea", ()), ("explicit.bin", ("--format=pea",))):
            with self.subTest(archive=archive):
                self.run_xfu("a", archive, "alpha.txt", *options)
                self.round_trip(archive, {"alpha.txt": self.payload})

    def test_all_quality_levels_and_multiblock_files(self):
        for quality in range(4):
            with self.subTest(quality=quality):
                archive = "quality-" + str(quality) + ".pea"
                self.run_xfu("a", archive, "alpha.txt", "--compression-level=" + str(quality))
                blocks = self.round_trip(archive, {"alpha.txt": self.payload})
                if quality:
                    self.assertEqual(len(blocks), 2)
                    self.assertTrue(all(packed < raw for raw, packed in blocks))

    def test_methods(self):
        for method in ("pea", "zlib", "deflate", "store", "stored"):
            with self.subTest(method=method):
                archive = method + ".pea"
                self.run_xfu("a", archive, "alpha.txt", "--compression=" + method)
                self.round_trip(archive, {"alpha.txt": self.payload})

    def test_multiple_files_empty_unicode_and_raw_fallback(self):
        unicode_name = "caf\u00e9-\u65e5\u672c.txt"
        random_data = os.urandom(1048576 + 123)
        (self.root / unicode_name).write_bytes(b"Unicode PEA names")
        (self.root / "random.bin").write_bytes(random_data)
        (self.root / "empty").write_bytes(b"")
        expected = {"alpha.txt": self.payload, unicode_name: b"Unicode PEA names",
            "random.bin": random_data, "empty": b""}
        for quality in (0, 3):
            archive = "multiple-" + str(quality) + ".pea"
            self.run_xfu("a", archive, *expected, "--compression-level=" + str(quality))
            blocks = self.round_trip(archive, expected)
            if quality:
                self.assertTrue(any(raw == packed for raw, packed in blocks))

    def test_absolute_and_parent_source_paths(self):
        (self.root / "sub").mkdir()
        self.run_xfu("a", "absolute.pea", str(self.root / "alpha.txt"))
        self.round_trip("absolute.pea", {"alpha.txt": self.payload})
        self.run_xfu("a", "parent.pea", "sub/../alpha.txt")
        self.round_trip("parent.pea", {"alpha.txt": self.payload})

    def test_invalid_options_preserve_existing_archive(self):
        archive = self.root / "keep.pea"
        for options in (("--compression-level=-1",), ("--compression-level=4",),
                        ("--compression=unknown",), ("--compression=store", "--compression-level=2"),
                        ("--filter=gzip",), ("--options=unknown=1",), ("-psecret",)):
            with self.subTest(options=options):
                archive.write_bytes(b"original")
                before = set(self.root.iterdir())
                self.run_xfu("a", archive.name, "alpha.txt", *options, success=False)
                self.assertEqual(archive.read_bytes(), b"original")
                self.assertEqual(set(self.root.iterdir()), before)

    def test_invalid_sources_preserve_existing_archive(self):
        archive = self.root / "keep.pea"
        (self.root / "directory").mkdir()
        for sources in (("missing",), ("directory",), ("alpha.txt", "missing")):
            with self.subTest(sources=sources):
                archive.write_bytes(b"original")
                before = set(self.root.iterdir())
                self.run_xfu("a", archive.name, *sources, success=False)
                self.assertEqual(archive.read_bytes(), b"original")
                self.assertEqual(set(self.root.iterdir()), before)

    def test_duplicate_basename_is_rejected(self):
        (self.root / "sub").mkdir()
        (self.root / "sub" / "alpha.txt").write_bytes(b"different")
        self.run_xfu("a", "duplicate.pea", "alpha.txt", "sub/alpha.txt", success=False)
        self.assertFalse((self.root / "duplicate.pea").exists())

    def test_self_and_hardlink_sources_are_rejected(self):
        archive = self.root / "self.pea"
        archive.write_bytes(b"original")
        self.run_xfu("a", archive.name, archive.name, success=False)
        self.assertEqual(archive.read_bytes(), b"original")
        linked = self.root / "hardlink"
        try:
            linked.hardlink_to(archive)
        except OSError:
            self.skipTest("hard links unavailable")
        self.run_xfu("a", archive.name, linked.name, success=False)
        self.assertEqual(archive.read_bytes(), b"original")

    def test_symlink_source_is_rejected(self):
        linked = self.root / "link"
        try:
            linked.symlink_to(self.root / "alpha.txt")
        except OSError:
            self.skipTest("symbolic links unavailable")
        self.run_xfu("a", "link.pea", linked.name, success=False)
        self.assertFalse((self.root / "link.pea").exists())

    def test_object_crc_corruption_is_rejected(self):
        self.run_xfu("a", "corrupt.pea", "alpha.txt", "--compression=store")
        archive = self.root / "corrupt.pea"
        data = bytearray(archive.read_bytes())
        name_size = struct.unpack_from("<H", data, 20)[0]
        data[20 + 18 + name_size] ^= 1
        archive.write_bytes(data)
        self.run_xfu("t", archive.name, success=False)

    def test_truncated_data_is_rejected(self):
        self.run_xfu("a", "truncated.pea", "alpha.txt")
        archive = self.root / "truncated.pea"
        data = archive.read_bytes()
        archive.write_bytes(data[:len(data) // 2])
        self.run_xfu("t", archive.name, success=False)


if __name__ == "__main__":
    unittest.main()

"""Independent fixtures for conservative per-file evidence classification."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from arc_scan_evidence_formats import classify


def bigf():
    names = [b"a.bin\0", b"b.bin\0"]
    start = 16 + sum(8 + len(name) for name in names)
    directory = struct.pack(">II", start, 3) + names[0]
    directory += struct.pack(">II", start + 3, 2) + names[1]
    return b"BIGF" + struct.pack("<I", start + 5) + struct.pack(">II", 2, start) + directory + b"abcde"


def bigaf():
    number = lambda n, size=20: str(n).encode().ljust(size, b" ")
    header = bytearray(b" " * 128)
    header[:8] = b"<bigaf>\n"
    header[68:88] = number(128)
    header[88:108] = number(128)
    member = bytearray(b" " * 112)
    member[:20] = number(3)
    member[20:40] = number(0)
    member[108:112] = number(4, 4)
    return header + member + b"file`\nabc"


def cat():
    directory = bytearray(struct.pack("<H", 3))
    for index in range(3):
        directory += (f"R{index}.BIN".encode().ljust(12, b"\0") +
                      struct.pack("<III", 0, 3, 74 + index * 3))
    return directory + b"abc" * 3


def beos(outside=False):
    number = lambda tag, value: tag + b"\0\2\1" + struct.pack(">Q", value)
    header = (b"AlB\x1a\xff\x0a\x0d\0PhIn\0\0\4" + number(b"FSiz", 85) +
              number(b"COff", 100 if outside else 70) + number(b"AOff", 78) + b"\0" * 7)
    return header.ljust(85, b"\0")


def hog2():
    return (b"HOG2" + struct.pack("<II", 1, 116) + b"\xff" * 56 +
            b"file".ljust(36, b"\0") + struct.pack("<III", 0, 3, 0) + b"abc")


def gst(bad_crc=False):
    data = b"GST payload\n"
    header = bytearray(32)
    header[:2] = b"\xea\xc9"
    struct.pack_into("<II", header, 8, len(data), len(data))
    header[16:28] = b"GST.TXT".ljust(12, b"\0")
    struct.pack_into("<I", header, 28, zlib.crc32(data) ^ int(bad_crc))
    return header + data


class Evidence(unittest.TestCase):
    def check(self, data, expected):
        with tempfile.TemporaryDirectory() as temporary:
            # Filename and supplied metadata deliberately claim unrelated
            # types, ensuring byte evidence controls categorization.
            path = Path(temporary) / "unrelated-password.zip"
            path.write_bytes(data)
            result = classify(path, {"type_name": "Unknown"}, {"status": "failed"})
            self.assertEqual(result["category"], expected, result)
            return result

    def test_full_bounds(self):
        for writer in (bigf, bigaf, cat, hog2):
            with self.subTest(writer=writer.__name__):
                self.check(writer(), None)
                result = self.check(writer()[:-1], "corrupted")
                self.assertEqual(result["confidence"], "high")

    def test_headerless_cat_needs_full_coherence(self):
        broken = bytearray(cat())
        struct.pack_into("<I", broken, 22, 75)
        self.check(broken[:-1], None)
        self.check(struct.pack("<H", 65535) + b"random bytes" * 100, None)

    def test_beos_required_metadata(self):
        self.check(beos(), None)
        self.check(beos(True), "corrupted")
        self.check(b"AlB\x1a\xff\x0a\x0d\0" + b"random" * 100, None)

    def test_bigaf_required_name_trailer(self):
        unknown = bytearray(bigaf()[:-1])
        unknown[244:246] = b"??"
        self.check(unknown, None)
        malformed_last = bytearray(bigaf()[:-1])
        malformed_last[88:108] = b"unknown".ljust(20, b" ")
        self.check(malformed_last, None)
        odd = bytearray(bigaf())
        odd[236:240] = b"3   "
        odd[240:244] = b"fil\0"
        self.check(odd, None)
        self.check(odd[:-1], "corrupted")

    def test_gst_stored_crc(self):
        self.check(gst(), None)
        self.check(gst(True), "corrupted")
        self.check(gst()[:-1], "corrupted")
        unknown = bytearray(gst(True))
        unknown[6] = 0x80
        self.check(unknown, None)
        unspecified = bytearray(gst(True))
        struct.pack_into("<I", unspecified, 28, 0)
        self.check(unspecified, None)

    def test_unresolved_variants(self):
        self.check(b"CFL3" + b"random" * 100, None)
        self.check(b"MPQ\x1a" + b"random" * 100, None)
        self.check(hog2() + b"unidentified suffix", None)

    def test_native_failure_is_not_evidence(self):
        self.check(b"unrecognized data", None)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "truncated.big"
            path.write_bytes(bigf()[:-1])
            self.assertIsNone(classify(path, {}, {"status": "passed"})["category"])


if __name__ == "__main__":
    unittest.main()

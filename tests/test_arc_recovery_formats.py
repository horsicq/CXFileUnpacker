"""Exercise validated LZIP tails and truly empty coded SQX members."""
from pathlib import Path
import lzma
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

XFU = Path(sys.argv.pop(1)).resolve()


def lzip(payload):
    coded = lzma.compress(payload, format=lzma.FORMAT_RAW,
                          filters=[dict(id=lzma.FILTER_LZMA1, dict_size=4096, lc=3, lp=0, pb=2)])
    head = b"LZIP\x01\x0c" + coded
    return head + struct.pack("<IQQ", zlib.crc32(payload), len(payload), len(head) + 20)


def sqx(method=4, packed=b"", unpacked=0, checksum=0xffffffff):
    def header(kind, body, flags=0):
        raw = struct.pack("<BHH", kind, flags, len(body) + 7) + body
        return struct.pack("<H", (~zlib.crc32(raw)) & 65535) + raw
    main = header(ord("R"), b"-sqx-" + bytes(13))
    name = b"Format/SQX2/todo.txt"
    body = bytes(5) + bytes([method]) + struct.pack("<IIIIIH", checksum, 0, 0, len(packed), unpacked, len(name)) + name
    return main + header(ord("D"), body) + packed + header(ord("S"), b"")


class RecoveryFormats(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xfu-recovery-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def extract(self, content, extension, reader):
        source = self.root / ("source." + extension)
        source.write_bytes(content)
        output = self.root / "output"
        result = subprocess.run([str(XFU), "x", str(source), "--reader", reader, "-o" + str(output)],
                                capture_output=True, timeout=30)
        files = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()}
        return result, files

    def test_lzip_plain_tail_and_concatenation(self):
        payload = b"a complete native member\n" * 200
        result, files = self.extract(lzip(payload) + lzip(payload) + b"ordinary trailing text", "lz", "lzip")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list(files.values()), [payload * 2])

    def test_lzip_corrupt_next_member_is_not_a_tail(self):
        payload = b"member" * 200
        coded = lzip(payload)
        result, files = self.extract(coded + coded[:-1], "lz", "lzip")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(files, {})

    def test_empty_coded_sqx(self):
        result, files = self.extract(sqx(), "sqx", "sqx")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(files, {"Format/SQX2/todo.txt": b""})

    def test_one_sided_empty_sqx_is_not_valid(self):
        result, files = self.extract(sqx(unpacked=1), "sqx", "sqx")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(files, {})

    def test_empty_unknown_sqx_method_is_not_valid(self):
        result, files = self.extract(sqx(method=5), "sqx", "sqx")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(files, {})

    def test_empty_sqx_still_checks_crc(self):
        result, files = self.extract(sqx(checksum=0x12345678), "sqx", "sqx")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(files, {})


if __name__ == "__main__":
    unittest.main()

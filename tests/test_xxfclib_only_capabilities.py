"""Verify the writer surface of the xxfclib-only build."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


EXPECT_FREEARC_SFX = "--expect-freearc-sfx" in sys.argv
if EXPECT_FREEARC_SFX:
    sys.argv.remove("--expect-freearc-sfx")
XFU = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None

REMOVED_WRITERS = (
    "brotli", "zpaq", "balz", "bcm", "quad",
    "lpaq1", "lpaq5", "lpaq8",
    "paq8", "paq8f", "paq8jd", "paq8l", "paq8o",
    "upx", "7zip_sfx",
)
RETAINED_WRITERS = (
    "7zip", "zip", "tar", "wim", "gzip", "bzip2", "xz", "zstd",
    "pea", "freearc", "split",
)
HELPER_ONLY_FORMATS = (
    "paq8", "paq8f", "paq8jd", "paq8l", "paq8o",
    "lpaq1", "lpaq5", "lpaq8", "quad", "sevenzip_engine", "upx",
)
HELPER_READER_NAMES = ("sevenzip", "7zip-engine", "garbro:any")
EXPECTED_CAPABILITIES = {
    "7zip": ("partial", True),
    "zip": ("partial", True),
    "tar": ("yes", True),
    "wim": ("partial", True),
    "gzip": ("yes", True),
    "bzip2": ("yes", True),
    "xz": ("yes", True),
    "zstd": ("yes", True),
    "brotli": ("yes", False),
    "zpaq": ("partial", False),
    "pea": ("partial", True),
    "freearc": ("partial", True),
    "balz": ("partial", False),
    "bcm": ("partial", False),
    "split": ("partial", True),
    "zim": ("partial", False),
    "rar": ("partial", False),
    "ace": ("partial", False),
    "7zip_sfx": ("partial", False),
    "freearc_sfx": ("partial", EXPECT_FREEARC_SFX),
}


class XxfclibOnlyCapabilities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XFU is None or not XFU.is_file():
            raise RuntimeError(
                "Usage: python test_xxfclib_only_capabilities.py /path/to/xfu"
            )
        result = subprocess.run(
            [str(XFU), "--capabilities"], capture_output=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.report = result.stdout
        cls.native = {
            name: (read, create == "yes")
            for name, read, create in re.findall(
                r"^native\s+(\S+)\s+read=(yes|partial|no|helper)\s+create=(yes|no)$",
                result.stdout, re.MULTILINE,
            )
        }

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xfu-xxfclib-only-")
        self.root = Path(self.temporary.name)
        (self.root / "alpha.txt").write_bytes(b"xxfclib-only writer contract\n")

    def tearDown(self):
        self.temporary.cleanup()

    def run_xfu(self, *arguments):
        return subprocess.run(
            [str(XFU), *map(str, arguments)], cwd=self.root,
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )

    def test_removed_writers_are_reported_as_unavailable(self):
        for name in REMOVED_WRITERS:
            with self.subTest(format=name):
                self.assertIn(name, self.native, self.report)
                self.assertFalse(self.native[name][1], self.report)

    def test_xxfclib_writers_remain_enabled(self):
        for name in RETAINED_WRITERS:
            with self.subTest(format=name):
                self.assertIn(name, self.native, self.report)
                self.assertTrue(self.native[name][1], self.report)

    def test_helper_only_readers_are_disabled(self):
        for name in HELPER_ONLY_FORMATS:
            with self.subTest(format=name):
                self.assertEqual(self.native.get(name), ("no", False), self.report)

    def test_explicit_helper_reader_aliases_are_rejected(self):
        created = self.run_xfu(
            "a", "native.zip", "alpha.txt", "--format=zip"
        )
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        for name in HELPER_READER_NAMES:
            with self.subTest(reader=name):
                result = self.run_xfu("l", "native.zip", "--reader", name)
                report = (result.stdout + result.stderr).lower()
                self.assertEqual(result.returncode, 2, report)
                self.assertIn("invalid explicit reader selection", report)

    def test_native_capability_matrix(self):
        for name, expected in EXPECTED_CAPABILITIES.items():
            with self.subTest(format=name):
                self.assertEqual(self.native.get(name), expected, self.report)

    def test_removed_writer_requests_preserve_existing_destination(self):
        destination = self.root / "keep.bin"
        expected_files = {"alpha.txt", destination.name}
        for name in REMOVED_WRITERS:
            with self.subTest(format=name):
                destination.write_bytes(b"original destination")
                result = self.run_xfu(
                    "a", destination.name, "alpha.txt", "--format=" + name
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("unavailable", (result.stdout + result.stderr).lower())
                self.assertEqual(destination.read_bytes(), b"original destination")
                self.assertEqual({path.name for path in self.root.iterdir()}, expected_files)


if __name__ == "__main__":
    unittest.main(verbosity=2)

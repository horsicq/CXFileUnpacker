"""Check in-process creation using the source-built official 7-Zip console SFX."""

from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import unittest


XFU = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None


class SfxCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XFU is None or not XFU.is_file():
            raise RuntimeError("Usage: python test_sfx_compat.py /path/to/xfu")
        if os.name != "nt":
            raise unittest.SkipTest("Windows console SFX stub")
        report = subprocess.run([str(XFU), "--capabilities"], capture_output=True,
            encoding="utf-8", errors="replace", timeout=30)
        if report.returncode:
            raise AssertionError(report.stdout + report.stderr)
        if not re.search(r"(?m)^\s*native\s+7zip_sfx\s+read=\S+\s+create=yes", report.stdout):
            raise unittest.SkipTest("7-Zip SFX creation is not enabled in this build")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xfu-sfx-")
        self.root = Path(self.temporary.name)
        self.payload = b"source-built self-extracting archive\n" * 1000 + bytes(range(256))
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

    def run_sfx(self, archive, *arguments):
        result = subprocess.run([str(self.root / archive), *map(str, arguments)],
            cwd=self.root, capture_output=True, encoding="utf-8", errors="replace", timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def round_trip(self, archive, expected):
        data = (self.root / archive).read_bytes()
        self.assertEqual(data[:2], b"MZ")
        signature = data.find(b"7z\xbc\xaf\x27\x1c")
        self.assertGreater(signature, 1024)
        listing = self.run_xfu("l", archive).stdout
        for name in expected:
            self.assertIn(name, listing)
        self.run_xfu("t", archive)
        output = self.root / ("native-" + archive)
        self.run_xfu("x", archive, "-o" + str(output))
        self.assertEqual({p.relative_to(output).as_posix(): p.read_bytes()
            for p in output.rglob("*") if p.is_file()}, expected)
        # Executing this known, source-built extraction-only stub verifies that
        # the output is actually self-extracting, not only an embedded archive.
        self.run_sfx(archive, "t", "-y")
        output = self.root / ("self-" + archive)
        self.run_sfx(archive, "x", "-y", "-o" + str(output))
        self.assertEqual({p.relative_to(output).as_posix(): p.read_bytes()
            for p in output.rglob("*") if p.is_file()}, expected)

    def test_default_multiple_empty_and_unicode_members(self):
        name = "caf\u00e9-\u65e5\u672c.txt"
        (self.root / name).write_bytes(b"UTF-8 member")
        (self.root / "empty").write_bytes(b"")
        expected = {"alpha.txt": self.payload, name: b"UTF-8 member", "empty": b""}
        self.run_xfu("a", "default.exe", *expected, "--format=7zip_sfx")
        self.round_trip("default.exe", expected)

    def test_all_supported_methods(self):
        for method in ("store", "stored", "lzma1", "lzma2", "ppmd"):
            with self.subTest(method=method):
                archive = method + ".exe"
                self.run_xfu("a", archive, "alpha.txt", "--format=7zip_sfx", "--compression=" + method)
                self.round_trip(archive, {"alpha.txt": self.payload})

    def test_quality_extremes(self):
        for quality in (0, 9):
            with self.subTest(quality=quality):
                archive = "quality-" + str(quality) + ".exe"
                self.run_xfu("a", archive, "alpha.txt", "--format=7zip_sfx", "--compression-level=" + str(quality))
                self.round_trip(archive, {"alpha.txt": self.payload})

    def test_exe_suffix_does_not_infer_writer(self):
        self.run_xfu("a", "not-an-archive.exe", "alpha.txt", success=False)
        self.assertFalse((self.root / "not-an-archive.exe").exists())

    def test_invalid_options_preserve_output(self):
        archive = self.root / "keep.exe"
        for options in (("--compression=deflate",), ("--compression=bzip2",),
                        ("--compression=zstd",), ("--compression-level=-1",),
                        ("--compression-level=10",), ("--filter=gzip",),
                        ("--options=compression=deflate",), ("-psecret",)):
            with self.subTest(options=options):
                archive.write_bytes(b"original")
                before = set(self.root.iterdir())
                self.run_xfu("a", archive.name, "alpha.txt", "--format=7zip_sfx", *options, success=False)
                self.assertEqual(archive.read_bytes(), b"original")
                self.assertEqual(set(self.root.iterdir()), before)

    def test_source_failure_preserves_output_and_cleans_stages(self):
        archive = self.root / "keep.exe"
        archive.write_bytes(b"original")
        before = set(self.root.iterdir())
        self.run_xfu("a", archive.name, "alpha.txt", "missing", "--format=7zip_sfx", success=False)
        self.assertEqual(archive.read_bytes(), b"original")
        self.assertEqual(set(self.root.iterdir()), before)

    def test_self_input_and_hardlink_are_rejected(self):
        archive = self.root / "self.exe"
        archive.write_bytes(b"original")
        self.run_xfu("a", archive.name, archive.name, "--format=7zip_sfx", success=False)
        self.assertEqual(archive.read_bytes(), b"original")
        linked = self.root / "hardlink"
        try:
            linked.hardlink_to(archive)
        except OSError:
            self.skipTest("hard links unavailable")
        self.run_xfu("a", archive.name, linked.name, "--format=7zip_sfx", success=False)
        self.assertEqual(archive.read_bytes(), b"original")

    def test_extract_does_not_execute_archived_script(self):
        script = b"@echo off\r\necho unsafe > should-not-exist\r\n"
        (self.root / "never-run.cmd").write_bytes(script)
        self.run_xfu("a", "safe.exe", "never-run.cmd", "--format=7zip_sfx")
        self.round_trip("safe.exe", {"never-run.cmd": script})
        self.assertFalse((self.root / "should-not-exist").exists())
        self.assertFalse(list(self.root.rglob("should-not-exist")))


if __name__ == "__main__":
    unittest.main()

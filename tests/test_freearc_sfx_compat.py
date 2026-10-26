"""Test genuine FreeArc payloads and the source-built extraction-only stub."""

from pathlib import Path
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib

XFU = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None
_arguments = sys.argv
sys.argv = sys.argv[:1]
from test_freearc_compat import parse_freearc
sys.argv = _arguments

MAGIC = b"XFUFreeArcSFX01\0"


def number(value):
    extra = 0
    while extra < 8 and value >= 1 << (7 * (extra + 1)):
        extra += 1
    if extra == 8:
        return b"\xff" + value.to_bytes(8, "little")
    return ((value << (extra + 1)) | ((1 << extra) - 1)).to_bytes(extra + 1, "little")


def control(kind, data):
    descriptor = b"ArC\1" + number(kind) + b"storing\0" + number(len(data)) * 2
    descriptor += struct.pack("<I", zlib.crc32(data))
    return data + descriptor + struct.pack("<I", zlib.crc32(descriptor))


def stored_fixture(names):
    """Independent framing permits adversarial names the writer refuses."""
    names = [name.encode("utf-8") if isinstance(name, str) else name for name in names]
    header = b"ArC\1\0\0\6\7"
    archive = control(1, header)
    offsets, payloads = [], []
    for index in range(len(names)):
        offsets.append(len(archive))
        payload = b"member-" + str(index).encode("ascii")
        payloads.append(payload)
        archive += payload
    directory_offset = len(archive)
    count = len(names)
    directory = number(count) + number(1) * count + b"storing\0" * count
    directory += b"".join(number(directory_offset - offset) for offset in offsets)
    directory += b"".join(number(len(payload)) for payload in payloads)
    directory += number(1) + b"\0" + b"".join(name + b"\0" for name in names)
    directory += number(0) * count + b"".join(number(len(payload)) for payload in payloads)
    directory += b"\0" * (5 * count)
    directory += b"".join(struct.pack("<I", zlib.crc32(payload)) for payload in payloads) + number(0)
    archive += control(3, directory)
    footer_offset = len(archive)

    def footer_record(kind, offset, data):
        return number(kind) + b"storing\0" + number(footer_offset - offset) + number(len(data)) * 2 + struct.pack("<I", zlib.crc32(data))

    footer = number(2) + footer_record(1, 0, header) + footer_record(3, directory_offset, directory)
    footer += b"\0" + number(0) + b"\0" + number(0)
    return archive + control(4, footer)


class FreeArcSfxCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XFU is None or not XFU.is_file():
            raise RuntimeError("Usage: python test_freearc_sfx_compat.py /path/to/xfu")
        if os.name != "nt":
            raise unittest.SkipTest("Windows source-built FreeArc SFX stub")
        report = subprocess.run([str(XFU), "--capabilities"], capture_output=True,
            encoding="utf-8", errors="replace", timeout=30)
        if report.returncode:
            raise AssertionError(report.stdout + report.stderr)
        if not re.search(r"(?m)^\s*native\s+freearc_sfx\s+read=\S+\s+create=yes", report.stdout):
            raise unittest.SkipTest("FreeArc SFX creation is not enabled in this build")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xfu-freearc-sfx-")
        self.root = Path(self.temporary.name)
        self.payload = b"source-built FreeArc self-extractor\n" * 1000 + bytes(range(256))
        (self.root / "alpha.txt").write_bytes(self.payload)

    def tearDown(self):
        # Windows virus scanners can briefly retain a just-executed SFX.
        # Retry only the cleanup; every child process has already exited.
        for attempt in range(20):
            try:
                self.temporary.cleanup()
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def run_process(self, arguments, success=True):
        result = subprocess.run(list(map(str, arguments)), cwd=self.root,
            capture_output=True, encoding="utf-8", errors="replace", timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def run_xfu(self, *arguments, success=True):
        return self.run_process([XFU, *arguments], success)

    def run_sfx(self, archive, *arguments, success=True):
        return self.run_process([self.root / archive, *arguments], success)

    def create(self, archive="archive.exe", names=("alpha.txt",), *options):
        self.run_xfu("a", archive, *names, "--format=freearc_sfx", *options)
        return self.root / archive

    def files_in(self, directory):
        return {p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob("*") if p.is_file()}

    def split_archive(self, archive):
        data = archive.read_bytes()
        index = data.rfind(MAGIC)
        self.assertGreater(index, 1024)
        offset, = struct.unpack_from("<Q", data, index + 16)
        self.assertEqual(offset, index + 24)
        return data[:index], data[offset:]

    def with_payload(self, payload, name="crafted.exe"):
        original = self.create()
        stub, _ = self.split_archive(original)
        archive = self.root / name
        archive.write_bytes(stub + MAGIC + struct.pack("<Q", len(stub) + 24) + payload)
        return archive

    def round_trip(self, archive, expected):
        self.assertEqual(archive.read_bytes()[:2], b"MZ")
        _, payload = self.split_archive(archive)
        self.assertEqual(parse_freearc(payload)[0], expected)
        listing = self.run_xfu("l", archive).stdout
        for name in expected:
            self.assertIn(name, listing)
        self.run_xfu("t", archive)
        native = self.root / (archive.stem + "-native")
        self.run_xfu("x", archive, "-o" + str(native))
        self.assertEqual(self.files_in(native), expected)
        listing = self.run_sfx(archive.name, "l").stdout
        for name in expected:
            self.assertIn(name, listing)
        self.run_sfx(archive.name, "t")
        output = self.root / (archive.stem + "-self")
        self.run_sfx(archive.name, "x", "-o" + str(output))
        self.assertEqual(self.files_in(output), expected)
        self.assertFalse(list(output.glob(".xfu-freearc-sfx-*")))

    def test_multiple_empty_unicode_and_nested_members(self):
        expected = {"alpha.txt": self.payload, "caf\u00e9-\u65e5\u672c.txt": b"Unicode",
            "empty": b"", "folder/nested.txt": b"nested"}
        for name, data in expected.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.round_trip(self.create(names=tuple(expected)), expected)

    def test_stored_aliases_and_lzma_quality_extremes(self):
        for method in ("store", "stored", "storing", "lzma"):
            qualities = (0, 5) if method == "lzma" else (0,)
            for quality in qualities:
                with self.subTest(method=method, quality=quality):
                    archive = self.create(f"{method}-{quality}.exe", ("alpha.txt",),
                        "--compression=" + method, "--compression-level=" + str(quality))
                    self.round_trip(archive, {"alpha.txt": self.payload})

    def test_extract_does_not_execute_members(self):
        script = b"@echo off\r\necho unsafe > should-not-exist\r\n"
        (self.root / "never-run.cmd").write_bytes(script)
        self.round_trip(self.create(names=("never-run.cmd",)), {"never-run.cmd": script})
        self.assertFalse(list(self.root.rglob("should-not-exist")))

    def test_invalid_options_and_sources_preserve_output(self):
        archive = self.root / "keep.exe"
        for options in (("--compression=deflate",), ("--compression=lzma2",),
                ("--compression-level=1",), ("--compression=lzma", "--compression-level=6"),
                ("--filter=gzip",), ("--options=anything",), ("-psecret",)):
            with self.subTest(options=options):
                archive.write_bytes(b"original")
                before = set(self.root.iterdir())
                self.run_xfu("a", archive, "alpha.txt", "--format=freearc_sfx", *options, success=False)
                self.assertEqual(archive.read_bytes(), b"original")
                self.assertEqual(set(self.root.iterdir()), before)
        self.run_xfu("a", archive, "alpha.txt", "missing", "--format=freearc_sfx", success=False)
        self.assertEqual(archive.read_bytes(), b"original")

    def test_self_source_and_hardlink_are_rejected(self):
        archive = self.root / "self.exe"
        archive.write_bytes(b"original")
        self.run_xfu("a", archive, archive, "--format=freearc_sfx", success=False)
        self.assertEqual(archive.read_bytes(), b"original")
        alias = self.root / "hardlink"
        try:
            alias.hardlink_to(archive)
        except OSError:
            self.skipTest("Hard links unavailable")
        self.run_xfu("a", archive, alias, "--format=freearc_sfx", success=False)
        self.assertEqual(archive.read_bytes(), b"original")

    def test_no_exe_suffix_inference(self):
        self.run_xfu("a", "not-an-archive.exe", "alpha.txt", success=False)
        self.assertFalse((self.root / "not-an-archive.exe").exists())

    def test_creator_rejects_windows_path_aliases(self):
        archive = self.root / "keep.exe"
        archive.write_bytes(b"original")
        (self.root / "folder").mkdir()
        (self.root / "folder/file").write_bytes(b"nested")
        for source in ("alpha.txt.", "alpha.txt ", "folder./file", "folder /file"):
            with self.subTest(source=source):
                self.run_xfu("a", archive, source, "--format=freearc_sfx", success=False)
                self.assertEqual(archive.read_bytes(), b"original")
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_damaged_payload_does_not_touch_output(self):
        archive = self.create()
        stub, payload = self.split_archive(archive)
        start = parse_freearc(payload)[1]
        corrupt = bytearray(payload)
        corrupt[start] ^= 0x40
        for name, modified in (("corrupt.exe", corrupt), ("truncated.exe", payload[:-3])):
            with self.subTest(name=name):
                target = self.root / name
                target.write_bytes(stub + MAGIC + struct.pack("<Q", len(stub) + 24) + modified)
                self.run_xfu("t", target, success=False)
                output = self.root / (name + "-out")
                output.mkdir()
                sentinel = output / "alpha.txt"
                sentinel.write_bytes(b"preserved")
                self.run_sfx(name, "t", success=False)
                self.run_sfx(name, "x", "-y", "-o" + str(output), success=False)
                self.assertEqual(self.files_in(output), {"alpha.txt": b"preserved"})

    def test_stub_rejects_unsafe_names_and_collisions(self):
        cases = [(name,) for name in ("../escape", "/absolute", "C:/absolute", "file.", "file ",
            "dir./file", "CON.txt", "CON .txt", "CONIN$", "CONOUT$", "COM0.dat", "LPT0.log",
            "COM1.dat", "LPT\u00b9.log", "stream:ads", "a//b", b"bad-\xff",
            "/".join(["deep"] * 129 + ["file"]))]
        cases += [("Alpha", "alpha"), ("\u00c4", "\u00e4"), ("file", "file/child"), ("a\\b", "a/b")]
        for index, names in enumerate(cases):
            with self.subTest(names=names):
                archive = self.with_payload(stored_fixture(names), f"unsafe-{index}.exe")
                output = self.root / f"unsafe-{index}-out"
                self.run_sfx(archive.name, "t", success=False)
                self.run_sfx(archive.name, "x", "-y", "-o" + str(output), success=False)
                self.assertFalse(output.exists())
        self.assertFalse((self.root.parent / "escape").exists())

    def test_stub_requires_opt_in_overwrite_and_preserves_self(self):
        archive = self.create()
        self.run_sfx(archive.name, "x", success=False)
        self.assertEqual((self.root / "alpha.txt").read_bytes(), self.payload)
        output = self.root / "overwrite"
        output.mkdir()
        (output / "alpha.txt").write_bytes(b"old")
        self.run_sfx(archive.name, "x", "-y", "-o" + str(output))
        self.assertEqual((output / "alpha.txt").read_bytes(), self.payload)
        malicious = self.with_payload(stored_fixture(("self.exe",)), "self.exe")
        before = malicious.read_bytes()
        self.run_sfx(malicious.name, "x", "-y", success=False)
        self.assertEqual(malicious.read_bytes(), before)

    def test_stub_refuses_reparse_output_directory(self):
        (self.root / "folder").mkdir()
        (self.root / "folder/file").write_bytes(b"payload")
        archive = self.create(names=("folder/file",))
        outside = self.root / "outside"
        outside.mkdir()
        output = self.root / "output"
        output.mkdir()
        linked = output / "folder"
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(linked), str(outside)],
            capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        if created.returncode:
            self.skipTest("Junction creation unavailable")
        try:
            self.run_sfx(archive.name, "x", "-y", "-o" + str(output), success=False)
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            linked.rmdir()


if __name__ == "__main__":
    unittest.main()

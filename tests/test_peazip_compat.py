"""Check library-only additions from the PeaZip format audit."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


XFU = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None


class PeaZipCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XFU is None or not XFU.is_file():
            raise RuntimeError("Usage: python test_peazip_compat.py /path/to/xfu")
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
                r"^\s*native\s+(\S+)\s+read=(yes|partial|no|helper)\s+create=(yes|no)",
                result.stdout, re.MULTILINE,
            )
        }

    def setUp(self):
        if self._testMethodName.startswith("test_brotli") and not self.native.get("brotli", ("no", False))[1]:
            self.skipTest("Brotli creation is unavailable in the xxfclib-only build")
        if self._testMethodName.startswith("test_zpaq") and not self.native.get("zpaq", ("no", False))[1]:
            self.skipTest("ZPAQ creation is unavailable in the xxfclib-only build")
        self.temporary = tempfile.TemporaryDirectory(prefix="xfu-peazip-")
        self.root = Path(self.temporary.name)
        self.payload = b"library-only Brotli compatibility\n" * 200 + bytes(range(256)) * 50
        (self.root / "alpha.txt").write_bytes(self.payload)

    def tearDown(self):
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

    def round_trip(self, archive, expected=None, reader=None):
        options = ["--reader", reader] if reader else []
        self.run_xfu("l", archive, *options)
        self.run_xfu("t", archive, *options)
        destination = "out-" + archive.replace(".", "-")
        self.run_xfu("x", archive, *options, "-o" + destination)
        files = [path for path in (self.root / destination).rglob("*") if path.is_file()]
        self.assertEqual(len(files), 1, files)
        self.assertEqual(files[0].read_bytes(), self.payload if expected is None else expected)

    def test_capability_namespaces_and_remaining_gaps(self):
        self.assertIn("brotli", self.native, self.report)
        self.assertEqual(self.native["brotli"], ("yes", False))
        self.assertRegex(self.report, r"(?m)^format pax read=yes create=yes$")
        self.assertRegex(self.report, r"(?m)^filter gzip read=yes create=yes$")
        for name in ("pea", "freearc"):
            self.assertIn(name, self.native, self.report)
            self.assertEqual(self.native[name], ("partial", True))
        self.assertEqual(self.native.get("zpaq"), ("partial", False))
        self.assertEqual(self.native.get("split"), ("partial", True))
        for name in ("paq8", "quad", "lpaq1", "lpaq5", "lpaq8", "upx"):
            self.assertEqual(self.native.get(name), ("no", False), self.report)
        for name in ("balz", "bcm"):
            self.assertEqual(self.native.get(name), ("partial", False))
        self.assertEqual(self.native.get("sevenzip_engine"), ("no", False))

    def test_brotli_suffix_default_and_explicit_selectors(self):
        self.run_xfu("a", "default.br", "alpha.txt")
        self.round_trip("default.br")
        for name in ("br", "brotli"):
            with self.subTest(format=name):
                archive = name + ".bin"
                self.run_xfu("a", archive, "alpha.txt", "--format=" + name)
                self.round_trip(archive, reader="brotli")

    def test_brotli_quality_and_method_aliases(self):
        for quality in (0, 5, 11):
            with self.subTest(quality=quality):
                archive = "quality-" + str(quality) + ".br"
                self.run_xfu("a", archive, "alpha.txt", "--compression-level=" + str(quality))
                self.round_trip(archive)
        for method in ("br", "brotli"):
            with self.subTest(method=method):
                archive = "method-" + method + ".br"
                self.run_xfu("a", archive, "alpha.txt", "--compression=" + method)
                self.round_trip(archive)

    def test_brotli_empty_file(self):
        (self.root / "empty.txt").write_bytes(b"")
        self.run_xfu("a", "empty.br", "empty.txt")
        self.assertGreater((self.root / "empty.br").stat().st_size, 0)
        self.round_trip("empty.br", expected=b"")

    def test_brotli_unicode_source_and_destination(self):
        name = "caf\u00e9-\u65e5\u672c.txt"
        archive = "r\u00e9sultat-\u65e5\u672c.br"
        (self.root / name).write_bytes(self.payload)
        self.run_xfu("a", archive, name)
        self.round_trip(archive)

    def test_brotli_requires_one_regular_input(self):
        destination = self.root / "keep.br"
        (self.root / "beta.txt").write_bytes(b"second file")
        (self.root / "directory").mkdir()
        for sources in (("alpha.txt", "beta.txt"), ("directory",), ("missing",)):
            with self.subTest(sources=sources):
                destination.write_bytes(b"original")
                before = set(self.root.iterdir())
                self.run_xfu("a", destination.name, *sources, success=False)
                self.assertEqual(destination.read_bytes(), b"original")
                self.assertEqual(set(self.root.iterdir()), before)

    def test_brotli_rejects_invalid_options_without_replacing_output(self):
        destination = self.root / "keep.br"
        for options in (
            ["--compression-level=-1"], ["--compression-level=12"],
            ["--compression=stored"], ["--compression=deflate"],
            ["--filter=gzip"], ["--options=unknown=1"], ["-psecret"],
        ):
            with self.subTest(options=options):
                destination.write_bytes(b"original")
                before = set(self.root.iterdir())
                self.run_xfu("a", destination.name, "alpha.txt", *options, success=False)
                self.assertEqual(destination.read_bytes(), b"original")
                self.assertEqual(set(self.root.iterdir()), before)

    def test_brotli_cannot_include_itself(self):
        destination = self.root / "self.br"
        destination.write_bytes(b"original")
        self.run_xfu("a", destination.name, destination.name, success=False)
        self.assertEqual(destination.read_bytes(), b"original")

    def test_brotli_link_input_is_rejected(self):
        source = self.root / "linked.txt"
        try:
            source.symlink_to(self.root / "alpha.txt")
        except (OSError, NotImplementedError):
            self.skipTest("File symlinks are unavailable for this account")
        destination = self.root / "keep.br"
        destination.write_bytes(b"original")
        self.run_xfu("a", destination.name, source.name, success=False)
        self.assertEqual(destination.read_bytes(), b"original")

    def test_brotli_truncation_is_rejected(self):
        self.run_xfu("a", "valid.br", "alpha.txt")
        content = (self.root / "valid.br").read_bytes()
        self.assertGreater(len(content), 2)
        (self.root / "truncated.br").write_bytes(content[:len(content) // 2])
        self.run_xfu("t", "truncated.br", "--reader", "brotli", success=False)

    def test_zpaq_streaming_multiple_members(self):
        (self.root / "beta.txt").write_bytes(b"second member")
        for quality in (0, 1):
            with self.subTest(quality=quality):
                archive = "streaming-" + str(quality) + ".zpaq"
                destination = "streaming-" + str(quality)
                self.run_xfu("a", archive, "alpha.txt", "beta.txt",
                             "--compression-level=" + str(quality))
                listing = self.run_xfu("l", archive, "--reader", "zpaq")
                self.assertIn("alpha.txt", listing.stdout)
                self.assertIn("beta.txt", listing.stdout)
                self.run_xfu("t", archive, "--reader", "zpaq")
                self.run_xfu("x", archive, "--reader", "zpaq", "-o" + destination)
                self.assertEqual((self.root / destination / "alpha.txt").read_bytes(), self.payload)
                self.assertEqual((self.root / destination / "beta.txt").read_bytes(), b"second member")

    def test_zpaq_explicit_selector_empty_and_unicode_members(self):
        name = "caf\u00e9-\u65e5\u672c.txt"
        (self.root / name).write_bytes(self.payload)
        (self.root / "empty.txt").write_bytes(b"")
        self.run_xfu("a", "named.bin", name, "empty.txt", "--format=zpaq")
        listing = self.run_xfu("l", "named.bin", "--reader", "zpaq")
        self.assertIn(name, listing.stdout)
        self.assertIn("empty.txt", listing.stdout)
        self.run_xfu("t", "named.bin", "--reader", "zpaq")
        self.run_xfu("x", "named.bin", "--reader", "zpaq", "-onamed")
        self.assertEqual((self.root / "named" / name).read_bytes(), self.payload)
        self.assertEqual((self.root / "named" / "empty.txt").read_bytes(), b"")

    def test_zpaq_rejects_unsupported_options_and_sources(self):
        destination = self.root / "keep.zpaq"
        (self.root / "directory").mkdir()
        for sources, options in (
            (["alpha.txt"], ["--compression-level=-1"]),
            (["alpha.txt"], ["--compression-level=2"]),
            (["alpha.txt"], ["--compression=deflate"]),
            (["alpha.txt"], ["--filter=gzip"]),
            (["alpha.txt"], ["--options=unknown=1"]),
            (["alpha.txt"], ["-psecret"]),
            (["alpha.txt", "missing"], []),
            (["directory"], []),
        ):
            with self.subTest(sources=sources, options=options):
                destination.write_bytes(b"original")
                before = set(self.root.iterdir())
                self.run_xfu("a", destination.name, *sources, *options, success=False)
                self.assertEqual(destination.read_bytes(), b"original")
                self.assertEqual(set(self.root.iterdir()), before)

    def test_zpaq_self_source_and_truncation_are_rejected(self):
        destination = self.root / "self.zpaq"
        destination.write_bytes(b"original")
        self.run_xfu("a", destination.name, destination.name, success=False)
        self.assertEqual(destination.read_bytes(), b"original")
        self.run_xfu("a", "valid.zpaq", "alpha.txt")
        content = (self.root / "valid.zpaq").read_bytes()
        self.assertGreater(len(content), 8)
        (self.root / "truncated.zpaq").write_bytes(content[:len(content) // 2])
        self.run_xfu("t", "truncated.zpaq", "--reader", "zpaq", success=False)

    def test_zpaq_multiblock_members(self):
        first = (self.payload * (2 * 1024 * 1024 // len(self.payload) + 1))[:2 * 1024 * 1024 + 37]
        second = bytes(range(256)) * (1024 * 1024 // 256 + 1)
        (self.root / "large.txt").write_bytes(first)
        (self.root / "second.bin").write_bytes(second)
        for quality in (0, 1):
            for sources in (("large.txt",), ("large.txt", "second.bin")):
                with self.subTest(quality=quality, sources=sources):
                    base = "blocks-" + str(quality) + "-" + str(len(sources))
                    archive = base + ".zpaq"
                    self.run_xfu("a", archive, *sources, "--compression-level=" + str(quality))
                    self.run_xfu("t", archive, "--reader", "zpaq")
                    self.run_xfu("x", archive, "--reader", "zpaq", "-o" + base)
                    self.assertEqual((self.root / base / "large.txt").read_bytes(), first)
                    if len(sources) == 2:
                        self.assertEqual((self.root / base / "second.bin").read_bytes(), second)
                    else:
                        self.assertFalse((self.root / base / "second.bin").exists())

    def test_zpaq_sha1_corruption_is_rejected(self):
        self.run_xfu("a", "valid.zpaq", "alpha.txt")
        content = bytearray((self.root / "valid.zpaq").read_bytes())
        self.assertEqual(content[-22], 253, "Missing final SHA-1 segment trailer")
        self.assertEqual(content[-1], 255, "Missing final block terminator")
        content[-10] ^= 0x80
        (self.root / "bad-sha1.zpaq").write_bytes(content)
        self.run_xfu("t", "bad-sha1.zpaq", "--reader", "zpaq", success=False)

    def test_zpaq_stored_method_aliases(self):
        for method in ("store", "stored", "zpaq"):
            with self.subTest(method=method):
                archive = "method-" + method + ".zpaq"
                self.run_xfu("a", archive, "alpha.txt", "--compression=" + method)
                self.round_trip(archive, reader="zpaq")
        self.run_xfu("a", "conflicting.zpaq", "alpha.txt", "--compression=stored",
                     "--compression-level=1", success=False)

    def test_zpaq_reserved_journal_names_remain_regular_members(self):
        members = {
            "jDC20261010120000" + kind + "0000000001":
                b"ordinary file, not journal metadata: " + kind.encode("ascii")
            for kind in "cdhi"
        }
        for name, payload in members.items():
            (self.root / name).write_bytes(payload)
        for quality in (0, 1):
            with self.subTest(quality=quality):
                base = "reserved-" + str(quality)
                archive = base + ".zpaq"
                self.run_xfu("a", archive, *members, "--compression-level=" + str(quality))
                listing = self.run_xfu("l", archive, "--reader", "zpaq")
                for name in members:
                    self.assertIn(name, listing.stdout)
                self.run_xfu("t", archive, "--reader", "zpaq")
                self.run_xfu("x", archive, "--reader", "zpaq", "-o" + base)
                extracted = {path.name: path.read_bytes()
                             for path in (self.root / base).rglob("*") if path.is_file()}
                self.assertEqual(extracted, members)

    def test_comic_and_zip_package_aliases(self):
        aliases = {
            "cb7": b"7z\xbc\xaf\x27\x1c", "cbt": None,
            **{suffix: b"PK\x03\x04" for suffix in (
                "cbz", "smzip", "jar", "ear", "war", "apk", "xpi", "kmz", "epub",
                "docx", "dotx", "xlsx", "xltx", "pptx", "potx", "ppsx",
                "odt", "ott", "ods", "ots", "odg", "otg", "odp", "otp", "odf", "odb", "oxt",
            )},
        }
        for suffix, signature in aliases.items():
            with self.subTest(suffix=suffix):
                archive = "alias." + suffix
                self.run_xfu("a", archive, "alpha.txt")
                content = (self.root / archive).read_bytes()
                if signature:
                    self.assertTrue(content.startswith(signature), content[:16])
                else:
                    self.assertEqual(content[257:262], b"ustar")
                self.round_trip(archive)

    def test_compressed_tar_aliases(self):
        aliases = {
            "tpz": b"\x1f\x8b", "tzst": b"\x28\xb5\x2f\xfd",
            "taz": b"\x1f\x9d", "tz": b"\x1f\x9d",
            **{suffix: b"BZh" for suffix in ("tbz", "tbz2", "tbzip", "tbzip2", "tb2")},
        }
        for suffix, signature in aliases.items():
            with self.subTest(suffix=suffix):
                archive = "alias." + suffix
                self.run_xfu("a", archive, "alpha.txt")
                self.assertTrue((self.root / archive).read_bytes().startswith(signature))
                self.round_trip(archive)

    def test_unavailable_peazip_writers_stay_explicit_errors(self):
        destination = self.root / "keep.bin"
        for name in ("brotli", "zpaq", "balz", "bcm", "quad", "lpaq1", "lpaq5",
                     "lpaq8", "paq8", "paq8f", "paq8jd", "paq8l", "paq8o", "upx",
                     "7zip_sfx", "rar"):
            with self.subTest(format=name):
                destination.write_bytes(b"original")
                self.run_xfu("a", destination.name, "alpha.txt", "--format=" + name, success=False)
                self.assertEqual(destination.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main(verbosity=2)

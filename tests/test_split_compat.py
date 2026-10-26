"""Check library-only numbered splitting and bounded concatenation."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


XFU = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None


class SplitCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XFU is None or not XFU.is_file():
            raise RuntimeError("Usage: python test_split_compat.py /path/to/xfu")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xfu-split-")
        self.root = Path(self.temporary.name)
        self.payload = bytes(range(256)) * 800 + b"last partial volume"
        (self.root / "source.bin").write_bytes(self.payload)

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

    def verify(self, first, expected=None, explicit=False, destination="extracted"):
        options = ["--reader", "split"] if explicit else []
        listing = self.run_xfu("l", first, *options)
        name = Path(first).name[:-4]
        self.assertIn(name, listing.stdout)
        before = set(self.root.rglob("*"))
        self.run_xfu("t", first, *options)
        self.assertEqual(set(self.root.rglob("*")), before)
        self.run_xfu("x", first, *options, "-o" + destination)
        output = self.root / destination
        self.assertEqual([path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()], [name])
        self.assertEqual((output / name).read_bytes(), self.payload if expected is None else expected)

    @unittest.skipIf(os.name == "nt", "RLIMIT_FSIZE")
    def test_a_failed_write_publishes_no_volume(self):
        import resource
        import signal
        (self.root / "big.bin").write_bytes(os.urandom(700000))

        def limited():
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE, (250000, 250000))

        result = subprocess.run([str(XFU), "a", "cut.001", "big.bin", "--volume-size=300K"],
                                cwd=self.root, capture_output=True, encoding="utf-8",
                                errors="replace", timeout=90, preexec_fn=limited)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(result.stderr.splitlines(),
                         ["cut.001: cannot read or write complete split data"])
        self.assertEqual(sorted(path.name for path in self.root.iterdir()
                                if path.name.startswith(("cut.", ".xfu-"))), [])

    def test_capability_is_library_read_and_create(self):
        report = self.run_xfu("--capabilities")
        self.assertRegex(report.stdout, r"(?m)^native split read=partial create=yes$")
        self.assertRegex(report.stdout, r"(?m)^native sevenzip_engine read=no create=no$")

    def test_suffix_creation_raw_bytes_and_roundtrip(self):
        self.run_xfu("a", "joined.001", "source.bin", "--volume-size=64K")
        parts = sorted(self.root.glob("joined.[0-9][0-9][0-9]"))
        expected = [self.payload[position:position + 65536] for position in range(0, len(self.payload), 65536)]
        self.assertEqual([path.read_bytes() for path in parts], expected)
        self.verify("joined.001")

    def test_member_lines_and_summaries_match_the_native_shape(self):
        created = self.run_xfu("a", "shape.001", "source.bin", "--volume-size=64K")
        self.assertEqual(created.stdout.splitlines(),
                         ["  source.bin", "shape.001: 1 file(s) as split in 4 volume(s)"])
        size = len(self.payload)
        listing = self.run_xfu("l", "shape.001")
        self.assertEqual(listing.stdout.splitlines(),
                         ["shape.001: Numbered split file", "  %12d  shape" % size, "1 member(s)"])
        extracted = self.run_xfu("x", "shape.001", "-oshape-output")
        self.assertEqual(extracted.stdout.splitlines(),
                         ["shape.001: Numbered split file", "  shape", "1 member(s)"])
        self.assertEqual(extracted.stderr, "")
        tested = self.run_xfu("t", "shape.001", "--verbose")
        self.assertEqual(tested.stdout.splitlines(), ["shape -- OK"])
        self.assertEqual(tested.stderr, "")

    def test_member_failure_is_logged_and_counted(self):
        self.run_xfu("a", "blocked.001", "source.bin", "--volume-size=64K")
        (self.root / "blocked-output" / "blocked").mkdir(parents=True)
        result = self.run_xfu("x", "blocked.001", "-oblocked-output", success=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines(), ["blocked.001: Numbered split file", "1 member(s), 1 failed"])
        self.assertEqual(result.stderr.splitlines(),
                         ["  blocked -- FAILED", "blocked.001: unsafe split output path"])
        self.assertEqual(list((self.root / "blocked-output" / "blocked").iterdir()), [])

    def test_long_series_paths_are_logged_whole(self):
        name = "n" * 2100 + ".001"
        result = self.run_xfu("l", name, success=False)
        self.assertEqual(len(result.stderr.splitlines()), 1)
        self.assertIn(result.stderr.splitlines()[0], (name + ": cannot inspect split volume",
                                                      name + ": first split volume is missing"))
        folder = Path(*["d" * 200] * 11)
        try:
            (self.root / folder).mkdir(parents=True)
        except OSError:
            self.skipTest("Long paths are unavailable on this file system")
        series = str(folder / "deep.001")
        result = self.run_xfu("l", series, success=False)
        self.assertEqual(result.stderr.splitlines(), [series + ": first split volume is missing"])

    def test_a_password_is_ignored_for_reading(self):
        # Split volumes are never encrypted: a password typed for another
        # archive (the GUI keeps its field) must not block reading them.
        self.run_xfu("a", "secret.001", "source.bin", "--volume-size=64K")
        plain = self.run_xfu("l", "secret.001")
        for command in (("l", "secret.001", "-psecret"), ("t", "secret.001", "-psecret"),
                        ("x", "secret.001", "-psecret", "-osecret-output")):
            with self.subTest(command=command[0]):
                result = self.run_xfu(*command)
                if command[0] == "l":
                    self.assertEqual(result.stdout, plain.stdout)
        self.assertEqual((self.root / "secret-output" / "secret").read_bytes(), self.payload)

    def test_explicit_format_prefix_and_default_volume(self):
        self.run_xfu("a", "explicit", "source.bin", "--format=split")
        self.assertFalse((self.root / "explicit").exists())
        self.assertEqual((self.root / "explicit.001").read_bytes(), self.payload)
        self.assertFalse((self.root / "explicit.002").exists())
        self.verify("explicit.001", explicit=True)

    def test_empty_input_has_one_empty_volume(self):
        (self.root / "empty.bin").write_bytes(b"")
        self.run_xfu("a", "empty.001", "empty.bin", "--volume-size=1K")
        self.assertEqual((self.root / "empty.001").read_bytes(), b"")
        self.assertFalse((self.root / "empty.002").exists())
        self.verify("empty.001", expected=b"", explicit=True)

    def test_unicode_source_prefix_and_output(self):
        name = "caf\u00e9-\u65e5\u672c.bin"
        prefix = "r\u00e9sultat-\u65e5\u672c"
        (self.root / name).write_bytes(self.payload)
        self.run_xfu("a", prefix + ".001", name, "--volume-size=100K")
        self.verify(prefix + ".001", destination="d\u00e9cod\u00e9")

    def test_exact_multiple_does_not_add_empty_tail(self):
        (self.root / "exact.bin").write_bytes(b"abcd" * 100)
        self.run_xfu("a", "exact.001", "exact.bin", "--volume-size=100")
        self.assertEqual(len(list(self.root.glob("exact.[0-9][0-9][0-9]"))), 4)
        self.verify("exact.001", expected=b"abcd" * 100)

    def test_plain_fixture_and_archive_like_prefix_are_concatenated(self):
        first = b"PK\x03\x04not a nested ZIP; raw numbered data"
        second = b"tail"
        (self.root / "fixture.001").write_bytes(first)
        (self.root / "fixture.002").write_bytes(second)
        self.verify("fixture.001", expected=first + second)

    def test_invalid_sources_do_not_create_parts(self):
        (self.root / "directory").mkdir()
        for sources in (("missing",), ("directory",), ("source.bin", "source.bin")):
            with self.subTest(sources=sources):
                before = set(self.root.iterdir())
                self.run_xfu("a", "invalid.001", *sources, "--volume-size=100K", success=False)
                self.assertEqual(set(self.root.iterdir()), before)

    def test_invalid_options_preserve_existing_files(self):
        keep = self.root / "keep.001"
        for options in (["--compression-level=1"], ["--compression=zstd"],
                        ["--filter=gzip"], ["--options=unknown=1"], ["-psecret"]):
            with self.subTest(options=options):
                keep.write_bytes(b"existing")
                before = set(self.root.iterdir())
                self.run_xfu("a", keep.name, "source.bin", *options, success=False)
                self.assertEqual(keep.read_bytes(), b"existing")
                self.assertEqual(set(self.root.iterdir()), before)

    def test_volume_size_grammar_and_scope(self):
        for size in ("0", "-1", "abc", "1T", "18446744073709551616"):
            with self.subTest(size=size):
                self.run_xfu("a", "invalid.001", "source.bin", "--volume-size=" + size, success=False)
                self.assertFalse((self.root / "invalid.001").exists())
        self.run_xfu("a", "invalid.zip", "source.bin", "--volume-size=1M", success=False)
        self.run_xfu("t", "missing.001", "--volume-size=1K", success=False)
        self.run_xfu("a", "gib.001", "source.bin", "--volume-size=1G")
        self.verify("gib.001", destination="gib-output")

    def test_existing_series_including_late_parts_is_never_overwritten(self):
        for suffix in ("000", "001", "999", "1000"):
            with self.subTest(suffix=suffix):
                existing = self.root / ("keep." + suffix)
                existing.write_bytes(b"existing")
                before = set(self.root.iterdir())
                self.run_xfu("a", "keep.001", "source.bin", "--volume-size=100K", success=False)
                self.assertEqual(existing.read_bytes(), b"existing")
                self.assertEqual(set(self.root.iterdir()), before)
                existing.unlink()

    def test_volume_count_is_bounded(self):
        (self.root / "small.bin").write_bytes(b"x" * 1000)
        before = set(self.root.iterdir())
        self.run_xfu("a", "too-many.001", "small.bin", "--volume-size=1", success=False)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_missing_middle_part_and_overflow_are_rejected(self):
        (self.root / "gap.001").write_bytes(b"abcd")
        (self.root / "gap.003").write_bytes(b"xy")
        self.run_xfu("l", "gap.001", success=False)
        self.run_xfu("t", "gap.001", "--reader", "split", success=False)
        self.run_xfu("x", "gap.001", "-ogap-output", success=False)
        self.assertFalse((self.root / "gap-output").exists())
        (self.root / "gap.003").unlink()
        (self.root / "gap.1000").write_bytes(b"unsupported tail")
        self.run_xfu("t", "gap.001", "--reader", "split", success=False)

    def test_inconsistent_part_sizes_are_rejected(self):
        for number, sizes in enumerate(((4, 3, 1), (4, 5), (4, 0))):
            prefix = "wrong-" + str(number)
            with self.subTest(sizes=sizes):
                for index, size in enumerate(sizes, 1):
                    (self.root / (prefix + "." + str(index).zfill(3))).write_bytes(b"x" * size)
                self.run_xfu("t", prefix + ".001", success=False)

    def test_explicit_reader_requires_first_volume(self):
        (self.root / "fixture.002").write_bytes(b"not first")
        self.run_xfu("l", "fixture.002", "--reader", "split", success=False)

    def test_extraction_preserves_input_hard_link_alias(self):
        (self.root / "fixture.001").write_bytes(b"original volume")
        (self.root / "output").mkdir()
        os.link(self.root / "fixture.001", self.root / "output" / "fixture")
        self.run_xfu("x", "fixture.001", "-ooutput", success=False)
        self.assertEqual((self.root / "fixture.001").read_bytes(), b"original volume")
        self.assertEqual((self.root / "output" / "fixture").read_bytes(), b"original volume")

    def test_links_are_rejected_for_inputs_parts_and_the_payload_path(self):
        link = self.root / "linked.bin"
        try:
            link.symlink_to(self.root / "source.bin")
        except (OSError, NotImplementedError):
            self.skipTest("File symlinks are unavailable for this account")
        self.run_xfu("a", "linked.001", link.name, success=False)
        (self.root / "fixture.001").symlink_to(self.root / "source.bin")
        self.run_xfu("t", "fixture.001", success=False)
        (self.root / "fixture.001").unlink()
        (self.root / "fixture.001").write_bytes(b"payload")
        (self.root / "real-output").mkdir()
        (self.root / "output").symlink_to(self.root / "real-output", target_is_directory=True)
        # The output folder, and the folders above it, may be links, as for
        # every other format.
        self.run_xfu("x", "fixture.001", "-ooutput")
        self.assertEqual((self.root / "real-output" / "fixture").read_bytes(), b"payload")
        self.run_xfu("x", "fixture.001", "-o" + str(self.root / "output" / "sub"))
        self.assertEqual((self.root / "real-output" / "sub" / "fixture").read_bytes(), b"payload")
        # A link at the payload's own path is never written through: it is
        # replaced, as every reader replaces what is at a member's path.
        victim = self.root / "victim.txt"
        victim.write_bytes(b"victim")
        (self.root / "real-output" / "linked").mkdir()
        (self.root / "real-output" / "linked" / "fixture").symlink_to(victim)
        result = self.run_xfu("x", "fixture.001", "-ooutput/linked")
        self.assertIn("  fixture -- replaced an existing file\n", result.stdout)
        self.assertEqual(victim.read_bytes(), b"victim")
        self.assertFalse((self.root / "real-output" / "linked" / "fixture").is_symlink())
        self.assertEqual((self.root / "real-output" / "linked" / "fixture").read_bytes(), b"payload")
        # A folder there is in the way.
        (self.root / "real-output" / "folder" / "fixture").mkdir(parents=True)
        self.run_xfu("x", "fixture.001", "-ooutput/folder", success=False)

    def test_unsafe_payload_names_are_rejected(self):
        self.run_xfu("a", "CON.001", "source.bin", success=False)
        for prefix in ("..", "trailing."):
            with self.subTest(prefix=prefix):
                path = self.root / (prefix + ".001")
                path.write_bytes(b"payload")
                self.run_xfu("x", path.name, "--reader", "split", "-ounsafe", success=False)
                self.assertFalse((self.root / "unsafe").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

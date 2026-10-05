"""Independent tiny scan reports exercise final coverage and byte auditing."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_all_arc_scan import verify


class ScanVerification(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root, self.report_dir = self.base / "inputs", self.base / "audit"
        self.root.mkdir()
        self.report_dir.mkdir()
        self.rows, results = [], []
        for name, content, category, status in (("alpha/one.arc", b"original one", "corrupted", "classified_from_independent_bytes"),
                                                 ("beta/two.arc", b"unknown bytes", None, "unclassified_reader_rejection")):
            source = self.root / name
            source.parent.mkdir(exist_ok=True)
            source.write_bytes(content)
            info = source.stat()
            row = dict(relative_path=name, source=str(source), bytes=len(content),
                       mtime_ns=info.st_mtime_ns, sha256=hashlib.sha256(content).hexdigest())
            self.rows.append(row)
            result = dict(row, category=category, status=status)
            if category:
                destination = self.root / category / name
                destination.parent.mkdir(parents=True)
                shutil.copyfile(source, destination)
                result.update(destination=str(destination), copy_status="copied_sha256_verified")
            results.append(result)
        self.inventory = dict(root=str(self.root), count=2, bytes=sum(row["bytes"] for row in self.rows), files=self.rows)
        self.report = dict(complete=True, inventory_files=2, completed=2, results=results)
        self.save()

    def tearDown(self):
        self.temporary.cleanup()

    def save(self):
        (self.report_dir / "inventory.json").write_text(json.dumps(self.inventory), encoding="utf-8")
        (self.report_dir / "report.json").write_text(json.dumps(self.report), encoding="utf-8")

    def codes(self):
        return {item["code"] for item in verify(self.report_dir)["issues"]}

    def test_valid_and_truthful_unresolved(self):
        outcome = verify(self.report_dir)
        self.assertTrue(outcome["verified"], outcome)
        self.assertEqual(outcome["summary"]["originals"]["verified"], 2)
        self.assertEqual(outcome["summary"]["categorized_copies"]["verified"], 1)
        self.assertEqual(outcome["summary"]["unresolved_files"], 1)

    def test_missing_and_duplicate_report_rows(self):
        self.report["results"].pop()
        self.save()
        self.assertIn("missing_report_path", self.codes())
        self.report["results"].append(dict(self.report["results"][0]))
        self.save()
        self.assertIn("duplicate_report_path", self.codes())

    def test_bad_copy_bytes(self):
        Path(self.report["results"][0]["destination"]).write_bytes(b"differentone")
        self.assertIn("file_sha256_mismatch", self.codes())

    def test_extra_output_is_reported_and_preserved(self):
        extra = self.root / "password" / "extra.bin"
        extra.parent.mkdir()
        extra.write_bytes(b"extra")
        self.assertIn("extra_output_file", self.codes())
        self.assertEqual(extra.read_bytes(), b"extra")

    def test_source_changed_even_when_size_unchanged(self):
        source = Path(self.rows[0]["source"])
        source.write_bytes(b"changed  one")
        codes = self.codes()
        self.assertIn("file_sha256_mismatch", codes)
        self.assertIn("file_mtime_ns_mismatch", codes)

    def test_exact_conflict_suffix_and_wrong_category(self):
        row = self.report["results"][0]
        old = Path(row["destination"])
        conflict = old.with_name(old.stem + ".sha256_" + row["sha256"][:12] + old.suffix)
        old.rename(conflict)
        row["destination"] = str(conflict)
        self.save()
        self.assertTrue(verify(self.report_dir)["verified"])
        row["destination"] = str(self.root / "password" / "alpha" / "one.arc")
        self.save()
        self.assertIn("invalid_report_row", self.codes())

    def test_incomplete_scan_and_unsafe_relative_path(self):
        self.report["complete"] = False
        self.save()
        self.assertIn("scan_not_complete", self.codes())
        self.report["results"][0]["relative_path"] = "../one.arc"
        self.save()
        self.assertIn("invalid_report_row", self.codes())

    def test_cli_failure_writes_only_verification(self):
        Path(self.report["results"][0]["destination"]).write_bytes(b"differentone")
        before = {name: (self.report_dir / name).read_bytes()
                  for name in ("inventory.json", "report.json")}
        tool = Path(__file__).resolve().parents[1] / "tools" / "verify_all_arc_scan.py"
        process = subprocess.run([sys.executable, str(tool), "--report-dir", str(self.report_dir)],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
        output = json.loads((self.report_dir / "verification.json").read_text(encoding="utf-8"))
        self.assertFalse(output["verified"])
        self.assertIn("file_sha256_mismatch", {item["code"] for item in output["issues"]})
        for name, content in before.items():
            self.assertEqual((self.report_dir / name).read_bytes(), content)


if __name__ == "__main__":
    unittest.main()

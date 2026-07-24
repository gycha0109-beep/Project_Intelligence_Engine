import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.identity import canonical_json_sha256
from review_system.intelligence_graph import calculate_graph_sha256
from review_system.io import dump_json, load_data
from review_system.reground import (
    RegroundError,
    _expected_report_id,
    _report_payload,
    _snapshot_payload,
    analyze_reground,
    verify_reground_report_data,
    write_reground_report,
)
from test_reground import RegroundFixture


def rehash_report(report: dict) -> None:
    report["snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(report))
    report["report_id"] = _expected_report_id(report, report["snapshot_sha256"])
    report["report_sha256"] = canonical_json_sha256(_report_payload(report))


class RegroundIntegrityHardeningTests(unittest.TestCase):
    def test_rehashed_file_status_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            fixture.target.write_text("VALUE = 2\n", encoding="utf-8")
            report = fixture.analyze()
            target = next(item for item in report["files"] if item["path"] == "src/target.py")
            target["status"] = "CURRENT"
            target["reasons"] = []
            report["summary"]["status"] = "CURRENT"
            rehash_report(report)
            errors = verify_reground_report_data(report)
            self.assertTrue(any("files" in error and "status mismatch" in error for error in errors))
            self.assertIn("summary mismatch", errors)

    def test_rehashed_relation_and_recheck_tamper_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            fixture.target.write_text("VALUE = 2\n", encoding="utf-8")
            report = fixture.analyze()
            report["relations"][0]["status"] = "CURRENT"
            report["relations"][0]["reasons"] = []
            report["impacted_rechecks"] = []
            report["summary"]["stale_relations"] = 0
            report["summary"]["impacted_rechecks"] = 0
            rehash_report(report)
            errors = verify_reground_report_data(report)
            self.assertTrue(any("relations[0].status mismatch" in error for error in errors))
            self.assertIn("impacted_rechecks mismatch", errors)

    def test_report_path_traversal_is_detected_after_rehash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            report = fixture.analyze()
            report["files"][0]["path"] = "../escape.py"
            rehash_report(report)
            errors = verify_reground_report_data(report)
            self.assertTrue(any("path traversal" in error for error in errors))

    def test_report_id_and_snapshot_hash_are_natural_key_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            report = fixture.analyze()
            report["report_id"] = "reground-forged"
            report["report_sha256"] = canonical_json_sha256(_report_payload(report))
            self.assertIn("report_id mismatch", verify_reground_report_data(report))


class RegroundInputSafetyTests(unittest.TestCase):
    def test_invalid_ledger_is_rejected_before_last_run_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            fixture.ledger.write_bytes(b"not sqlite")
            with self.assertRaisesRegex(RegroundError, "invalid Evidence Ledger"):
                fixture.analyze()

    def test_tampered_graph_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            graph = load_data(fixture.graph)
            graph["nodes"][0]["sha256"] = "0" * 64
            dump_json(fixture.graph, graph)
            with self.assertRaisesRegex(RegroundError, "invalid Project Graph"):
                fixture.analyze()

    def test_duplicate_file_relation_is_rejected_even_with_valid_graph_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            graph = load_data(fixture.graph)
            graph["edges"].append(copy.deepcopy(graph["edges"][0]))
            graph["graph_sha256"] = calculate_graph_sha256(graph)
            dump_json(fixture.graph, graph)
            with self.assertRaisesRegex(RegroundError, "duplicate file relation"):
                fixture.analyze()

    def test_absolute_and_traversal_graph_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            for unsafe in ("/etc/passwd", "../escape.py", "C:\\escape.py"):
                graph = load_data(fixture.graph)
                graph["nodes"][0]["path"] = unsafe
                graph["graph_sha256"] = calculate_graph_sha256(graph)
                dump_json(fixture.graph, graph)
                with self.assertRaisesRegex(RegroundError, "invalid Project Graph|unsafe Graph"):
                    fixture.analyze()
                fixture._write_graph()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_tracked_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = RegroundFixture(root)
            outside = root / "outside.py"
            outside.write_text("VALUE = 1\n", encoding="utf-8")
            fixture.target.unlink()
            try:
                fixture.target.symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(RegroundError, "symlink"):
                fixture.analyze()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_graph_ledger_and_output_symlink_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = RegroundFixture(root)
            graph_link = root / "graph-link.json"
            ledger_link = root / "ledger-link.sqlite3"
            output_target = root / "real-output.json"
            output_target.write_text("old\n", encoding="utf-8")
            output_link = root / "output-link.json"
            try:
                graph_link.symlink_to(fixture.graph)
                ledger_link.symlink_to(fixture.ledger)
                output_link.symlink_to(output_target)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(RegroundError, "symlink"):
                analyze_reground(
                    project_id="demo",
                    repository_root=fixture.repository,
                    graph=graph_link,
                    ledger=fixture.ledger,
                    generated_at="2026-07-24T12:00:00Z",
                )
            with self.assertRaisesRegex(RegroundError, "symlink"):
                analyze_reground(
                    project_id="demo",
                    repository_root=fixture.repository,
                    graph=fixture.graph,
                    ledger=ledger_link,
                    generated_at="2026-07-24T12:00:00Z",
                )
            with self.assertRaisesRegex(RegroundError, "symlink"):
                write_reground_report(output_link, fixture.analyze())

    def test_atomic_output_replace_failure_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            report = fixture.analyze()
            output = Path(tmp) / "report.json"
            output.write_bytes(b"existing\n")
            with patch("review_system.reground.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_reground_report(output, report)
            self.assertEqual(b"existing\n", output.read_bytes())
            leftovers = list(output.parent.glob(output.name + ".*.tmp"))
            self.assertEqual([], leftovers)


if __name__ == "__main__":
    unittest.main()

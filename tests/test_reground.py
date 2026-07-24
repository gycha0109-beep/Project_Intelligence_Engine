import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from review_system.identity import canonical_json_sha256
from review_system.intelligence_graph import calculate_graph_sha256
from review_system.io import dump_json, load_data
from review_system.ledger import import_artifact_directory, initialize_ledger
from review_system.reground import (
    analyze_reground,
    load_reground_report,
    verify_reground_report_data,
    write_reground_report,
)
from review_system.reground_cli import main as reground_main
from test_ledger import LedgerFixture


def raw_sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


class RegroundFixture:
    def __init__(self, root: Path, *, with_run: bool = True):
        self.root = root
        self.repository = root / "repository"
        self.repository.mkdir(parents=True)
        (self.repository / "src").mkdir()
        self.source = self.repository / "src" / "source.py"
        self.target = self.repository / "src" / "target.py"
        self.source.write_text("from .target import VALUE\n", encoding="utf-8")
        self.target.write_text("VALUE = 1\n", encoding="utf-8")
        self.graph = root / "project-graph.json"
        self.ledger = root / "ledger.sqlite3"
        self._write_graph()
        if with_run:
            run_root, self.run_id = LedgerFixture.create(root, "verified-run")
            import_artifact_directory(self.ledger, run_root)
        else:
            initialize_ledger(self.ledger)
            self.run_id = None

    def _write_graph(self, *, source_path: str = "src/source.py") -> None:
        graph = {
            "schema_version": "1.0",
            "repository": {"root": "."},
            "nodes": [
                {
                    "id": "file:src/source.py",
                    "type": "file",
                    "path": source_path,
                    "language": "python",
                    "size_bytes": self.source.stat().st_size,
                    "sha256": raw_sha(self.source),
                },
                {
                    "id": "file:src/target.py",
                    "type": "file",
                    "path": "src/target.py",
                    "language": "python",
                    "size_bytes": self.target.stat().st_size,
                    "sha256": raw_sha(self.target),
                },
                {
                    "id": "symbol:src/target.py#VALUE",
                    "type": "symbol",
                    "path": "src/target.py",
                    "name": "VALUE",
                },
            ],
            "edges": [
                {
                    "source": "file:src/source.py",
                    "target": "file:src/target.py",
                    "type": "imports",
                },
                {
                    "source": "file:src/target.py",
                    "target": "symbol:src/target.py#VALUE",
                    "type": "defines",
                },
            ],
            "warnings": [],
        }
        graph["graph_sha256"] = calculate_graph_sha256(graph)
        dump_json(self.graph, graph)

    def analyze(self, *, project_id: str = "demo") -> dict:
        return analyze_reground(
            project_id=project_id,
            repository_root=self.repository,
            graph=self.graph,
            ledger=self.ledger,
            generated_at="2026-07-24T12:00:00Z",
        )


class RegroundProjectionTests(unittest.TestCase):
    def test_unchanged_file_relation_is_current_and_uses_verified_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            report = fixture.analyze()
            self.assertEqual("CURRENT", report["summary"]["status"])
            self.assertEqual(2, report["summary"]["tracked_files"])
            self.assertEqual(1, report["summary"]["relations_checked"])
            self.assertEqual("CURRENT", report["relations"][0]["status"])
            self.assertEqual(fixture.run_id, report["ledger"]["last_verified_run"]["run_id"])
            self.assertEqual(["NON_FILE_EDGES_SKIPPED:1"], report["warnings"])
            self.assertEqual([], verify_reground_report_data(report))

    def test_changed_dependency_marks_relation_stale_and_source_for_recheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            fixture.target.write_text("VALUE = 2\n", encoding="utf-8")
            report = fixture.analyze()
            self.assertEqual("STALE", report["summary"]["status"])
            relation = report["relations"][0]
            self.assertEqual("STALE", relation["status"])
            self.assertEqual(["TARGET_CHANGED"], relation["reasons"])
            impacted = {item["path"]: item for item in report["impacted_rechecks"]}
            self.assertEqual(["src/target.py"], impacted["src/source.py"]["changed_dependencies"])
            self.assertIn("TARGET_CHANGED", impacted["src/source.py"]["reasons"])
            self.assertIn("FILE_CHANGED", impacted["src/target.py"]["reasons"])

    def test_changed_source_and_missing_target_preserve_both_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            fixture.source.write_text("from .target import OTHER\n", encoding="utf-8")
            fixture.target.unlink()
            report = fixture.analyze()
            relation = report["relations"][0]
            self.assertEqual(["SOURCE_CHANGED", "TARGET_MISSING"], relation["reasons"])
            statuses = {item["path"]: item["status"] for item in report["files"]}
            self.assertEqual("CHANGED", statuses["src/source.py"])
            self.assertEqual("MISSING", statuses["src/target.py"])

    def test_no_project_run_is_warning_not_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            report = fixture.analyze(project_id="another-project")
            self.assertIsNone(report["ledger"]["last_verified_run"])
            self.assertIn("NO_VERIFIED_RUN", report["warnings"])
            self.assertEqual([], verify_reground_report_data(report))

    def test_latest_verified_project_run_is_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = RegroundFixture(root)
            second_root, second_id = LedgerFixture.create(root, "second-run")
            import_artifact_directory(fixture.ledger, second_root)
            with sqlite3.connect(fixture.ledger) as connection:
                connection.execute(
                    "UPDATE runs SET imported_at = ? WHERE run_id = ?",
                    ("2026-07-24T12:30:00+00:00", second_id),
                )
                connection.execute(
                    "UPDATE runs SET imported_at = ? WHERE run_id = ?",
                    ("2026-07-24T12:00:00+00:00", fixture.run_id),
                )
            report = fixture.analyze()
            self.assertEqual(second_id, report["ledger"]["last_verified_run"]["run_id"])

    def test_windows_graph_path_normalizes_to_posix(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            fixture._write_graph(source_path="src\\source.py")
            report = fixture.analyze()
            self.assertEqual("src/source.py", report["files"][0]["path"])
            self.assertEqual("CURRENT", report["summary"]["status"])


class RegroundReportAndCliTests(unittest.TestCase):
    def test_report_write_load_and_deterministic_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            first = fixture.analyze()
            second = fixture.analyze()
            self.assertEqual(first["report_id"], second["report_id"])
            self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])
            output = Path(tmp) / "reground-report.json"
            write_reground_report(output, first)
            _, loaded = load_reground_report(output)
            self.assertEqual(first, loaded)

    def test_cli_analyze_and_verify_valid_stale_report_return_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            fixture.target.write_text("VALUE = 3\n", encoding="utf-8")
            output = Path(tmp) / "report.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = reground_main(
                    [
                        "analyze",
                        "--project-id", "demo",
                        "--repository-root", str(fixture.repository),
                        "--graph", str(fixture.graph),
                        "--ledger", str(fixture.ledger),
                        "--output", str(output),
                        "--generated-at", "2026-07-24T12:00:00Z",
                    ]
                )
            self.assertEqual(0, code)
            self.assertEqual("STALE", json.loads(stdout.getvalue())["status"])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, reground_main(["verify-report", "--report", str(output)]))

    def test_cli_invalid_report_returns_verification_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            dump_json(path, {"schema_version": "1.0"})
            with redirect_stderr(io.StringIO()):
                self.assertEqual(4, reground_main(["verify-report", "--report", str(path)]))


if __name__ == "__main__":
    unittest.main()

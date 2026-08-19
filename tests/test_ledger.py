import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from review_system.identity import derive_run_identity, write_identity_manifest
from review_system.io import dump_json
from review_system.ledger import (
    LedgerImportError,
    LedgerMigrationError,
    import_artifact_directory,
    initialize_ledger,
    rebuild_ledger,
    show_run,
    verify_ledger,
)
from review_system.ledger_cli import main as ledger_main


class LedgerFixture:
    @staticmethod
    def create(
        root: Path,
        name: str,
        *,
        run_type: str = "review",
        with_gate: bool = False,
    ) -> tuple[Path, str]:
        directory = root / name
        directory.mkdir()
        (directory / "evidence.txt").write_text(f"evidence for {name}\n", encoding="utf-8")
        if run_type == "review":
            dump_json(
                directory / "run.json",
                {
                    "run_id": name,
                    "project_id": "demo",
                    "mode": "full",
                    "metrics": {},
                },
            )
        else:
            dump_json(
                directory / "github-source.json",
                {
                    "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
                    "pull_request": {"number": 7},
                },
            )
        if with_gate:
            (directory / "gate-policy.yml").write_text("version: '1.0'\n", encoding="utf-8")
            dump_json(
                directory / "gate-result.json",
                {
                    "decision": "PASS",
                    "generated_at": "2026-07-24T00:00:00+00:00",
                    "triggered": {"pass": [{"id": "all-clear"}]},
                    "policy": {"version": "1.0", "source": "gate-policy.yml"},
                },
            )
        identity = derive_run_identity(
            project_id="demo",
            run_type=run_type,
            source_revision="a" * 40,
            source_identifier=(
                f"review://demo/{name}"
                if run_type == "review"
                else "github://github.com/demo/repo/pull/7"
            ),
        )
        write_identity_manifest(directory, identity)
        return directory, identity.run_id


class LedgerMigrationTests(unittest.TestCase):
    def test_initialize_is_idempotent_and_enables_foreign_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "ledger.sqlite3"
            self.assertEqual(database.resolve(), initialize_ledger(database))
            self.assertEqual(database.resolve(), initialize_ledger(database))
            with sqlite3.connect(database) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                self.assertTrue(
                    {
                        "schema_migrations",
                        "runs",
                        "artifacts",
                        "claims",
                        "evidence",
                        "claim_evidence",
                        "decisions",
                        "policy_snapshots",
                    }.issubset(tables)
                )
                connection.execute("PRAGMA foreign_keys = ON")
                self.assertEqual(1, connection.execute("PRAGMA foreign_keys").fetchone()[0])

    def test_migration_checksum_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "ledger.sqlite3"
            initialize_ledger(database)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE schema_migrations SET checksum_sha256 = ? WHERE version = '001'",
                    ("0" * 64,),
                )
            with self.assertRaises(LedgerMigrationError):
                initialize_ledger(database)


class LedgerImportTests(unittest.TestCase):
    def test_review_run_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, run_id = LedgerFixture.create(root, "review-run")
            database = root / "ledger.sqlite3"
            first = import_artifact_directory(database, directory, expected_run_type="review")
            second = import_artifact_directory(database, directory, expected_run_type="review")
            self.assertEqual(run_id, first.run_id)
            self.assertEqual(first.to_dict(), second.to_dict())
            with sqlite3.connect(database) as connection:
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
                self.assertEqual(
                    first.artifact_count,
                    connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0],
                )
            projection = show_run(database, run_id)
            self.assertIsNotNone(projection)
            self.assertEqual("review-run", projection["run"]["legacy_run_id"])

    def test_pull_request_import_and_type_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, run_id = LedgerFixture.create(root, "pr-run", run_type="pull_request")
            database = root / "ledger.sqlite3"
            result = import_artifact_directory(database, directory, expected_run_type="pull_request")
            self.assertEqual(run_id, result.run_id)
            self.assertEqual("PR-7", show_run(database, run_id)["run"]["legacy_run_id"])
            with self.assertRaises(LedgerImportError):
                import_artifact_directory(database, directory, expected_run_type="review")

    def test_modified_artifact_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, _ = LedgerFixture.create(root, "tampered")
            (directory / "evidence.txt").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(LedgerImportError, "modified artifact"):
                import_artifact_directory(root / "ledger.sqlite3", directory)

    def test_database_inside_artifact_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory, _ = LedgerFixture.create(Path(tmp), "self-index")
            with self.assertRaisesRegex(LedgerImportError, "outside the artifact root"):
                import_artifact_directory(directory / "ledger.sqlite3", directory)

    def test_gate_and_policy_are_explicitly_projected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, run_id = LedgerFixture.create(root, "gated", with_gate=True)
            database = root / "ledger.sqlite3"
            result = import_artifact_directory(database, directory)
            self.assertEqual(1, result.decision_count)
            self.assertEqual(1, result.policy_snapshot_count)
            projection = show_run(database, run_id)
            self.assertEqual("PASS", projection["decisions"][0]["outcome"])
            self.assertEqual("1.0", projection["policy_snapshots"][0]["policy_version"])


class LedgerVerificationAndRebuildTests(unittest.TestCase):
    def test_verify_detects_source_artifact_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, _ = LedgerFixture.create(root, "verify")
            database = root / "ledger.sqlite3"
            import_artifact_directory(database, directory)
            self.assertTrue(verify_ledger(database)["valid"])
            (directory / "evidence.txt").write_text("changed after import\n", encoding="utf-8")
            result = verify_ledger(database)
            self.assertFalse(result["valid"])
            self.assertTrue(any("modified artifact" in error for error in result["errors"]))

    def test_corrupt_database_returns_invalid_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "ledger.sqlite3"
            database.write_bytes(b"not a sqlite database")
            result = verify_ledger(database)
            self.assertFalse(result["valid"])
            self.assertTrue(result["errors"])

    def test_rebuild_is_atomic_and_replaces_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, first_id = LedgerFixture.create(root, "first")
            second, second_id = LedgerFixture.create(root, "second")
            bad, _ = LedgerFixture.create(root, "bad")
            (bad / "evidence.txt").write_text("tampered\n", encoding="utf-8")
            database = root / "ledger.sqlite3"
            import_artifact_directory(database, first)

            with self.assertRaises(LedgerImportError):
                rebuild_ledger(database, [second, bad])
            self.assertIsNotNone(show_run(database, first_id))
            self.assertIsNone(show_run(database, second_id))

            result = rebuild_ledger(database, [second])
            self.assertTrue(result["valid"])
            self.assertIsNone(show_run(database, first_id))
            self.assertIsNotNone(show_run(database, second_id))

    def test_rebuild_rejects_two_roots_for_same_logical_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, _ = LedgerFixture.create(root, "same")
            copy = root / "copy"
            copy.mkdir()
            for source in first.iterdir():
                (copy / source.name).write_bytes(source.read_bytes())
            with self.assertRaisesRegex(LedgerImportError, "multiple roots"):
                rebuild_ledger(root / "ledger.sqlite3", [first, copy])


class LedgerCLITests(unittest.TestCase):
    def test_cli_init_import_verify_and_show(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, run_id = LedgerFixture.create(root, "cli-run")
            database = root / "ledger.sqlite3"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, ledger_main(["init", "--database", str(database)]))
                self.assertEqual(
                    0,
                    ledger_main(
                        ["import-run", str(directory), "--database", str(database)]
                    ),
                )
                self.assertEqual(0, ledger_main(["verify", "--database", str(database)]))
                self.assertEqual(
                    0,
                    ledger_main(["show-run", run_id, "--database", str(database)]),
                )
            self.assertIn(run_id, output.getvalue())

    def test_cli_missing_run_uses_integrity_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "ledger.sqlite3"
            initialize_ledger(database)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    4,
                    ledger_main(
                        ["show-run", "run-missing", "--database", str(database)]
                    ),
                )


if __name__ == "__main__":
    unittest.main()

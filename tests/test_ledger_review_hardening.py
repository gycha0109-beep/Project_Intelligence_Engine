import sqlite3
import tempfile
import unittest
from pathlib import Path

from review_system.ledger import import_artifact_directory, verify_ledger
from tests.test_ledger import LedgerFixture


class LedgerReviewHardeningTests(unittest.TestCase):
    def test_reimport_preserves_future_claim_and_evidence_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, run_id = LedgerFixture.create(root, "preserve-relations")
            database = root / "ledger.sqlite3"
            import_artifact_directory(database, directory)
            with sqlite3.connect(database) as connection:
                artifact_id = connection.execute(
                    "SELECT artifact_id FROM artifacts WHERE run_id = ? ORDER BY relative_path LIMIT 1",
                    (run_id,),
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO claims(claim_id, run_id, claim_type, statement, status) VALUES (?, ?, ?, ?, ?)",
                    ("claim-1", run_id, "test", "future claim", "recorded"),
                )
                connection.execute(
                    """
                    INSERT INTO evidence(
                        evidence_id, run_id, evidence_level, evidence_type,
                        summary, artifact_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("evidence-1", run_id, "L1", "artifact", "future evidence", artifact_id),
                )
                connection.execute(
                    "INSERT INTO claim_evidence(claim_id, evidence_id, relation) VALUES (?, ?, ?)",
                    ("claim-1", "evidence-1", "supports"),
                )

            import_artifact_directory(database, directory)
            with sqlite3.connect(database) as connection:
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0])
                self.assertEqual(
                    artifact_id,
                    connection.execute(
                        "SELECT artifact_id FROM evidence WHERE evidence_id = 'evidence-1'"
                    ).fetchone()[0],
                )

    def test_verify_detects_explicit_decision_projection_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, _ = LedgerFixture.create(root, "decision-tamper", with_gate=True)
            database = root / "ledger.sqlite3"
            import_artifact_directory(database, directory)
            with sqlite3.connect(database) as connection:
                connection.execute("UPDATE decisions SET outcome = 'FAIL'")
            result = verify_ledger(database)
            self.assertFalse(result["valid"])
            self.assertTrue(any("field mismatch: outcome" in error for error in result["errors"]))

    def test_verify_detects_run_projection_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, _ = LedgerFixture.create(root, "run-tamper")
            database = root / "ledger with spaces.sqlite3"
            import_artifact_directory(database, directory)
            with sqlite3.connect(database) as connection:
                connection.execute("UPDATE runs SET source_identifier = 'tampered'")
            result = verify_ledger(database)
            self.assertFalse(result["valid"])
            self.assertTrue(any("field mismatch: source_identifier" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()

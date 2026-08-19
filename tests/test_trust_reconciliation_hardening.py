import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from review_system.defects import create_defect, link_finding
from review_system.identity import canonical_json_sha256
from review_system.io import dump_json, load_data
from review_system.ledger import import_artifact_directory
from review_system.trust_reconciliation import (
    TrustReconciliationError,
    reconcile_sources,
    verify_reconciliation_report_data,
    write_reconciliation_report,
)
from test_defects import DefectFixture
from test_trust_reconciliation import ReconciliationFixture


class TrustReconciliationHardeningTests(unittest.TestCase):
    def test_manifest_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            fixture.capture()
            fixture.persist()
            manifest = load_data(fixture.sources_path)
            manifest["assessment_sources"][0]["trust_report"] = "../escape.json"
            dump_json(fixture.sources_path, manifest)
            with self.assertRaisesRegex(TrustReconciliationError, "unsafe traversal"):
                reconcile_sources(fixture.registry_path, fixture.sources_path)

    def test_symlink_assessment_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            fixture.capture()
            original = root / fixture.assessment_sources[0]["trust_report"]
            link = root / "trust-report-link.json"
            try:
                link.symlink_to(original)
            except OSError:
                self.skipTest("symlinks unavailable")
            fixture.assessment_sources[0]["trust_report"] = link.relative_to(root).as_posix()
            fixture.persist()
            with self.assertRaisesRegex(TrustReconciliationError, "symlink"):
                reconcile_sources(fixture.registry_path, fixture.sources_path)

    def test_output_symlink_is_rejected_without_target_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            fixture.capture()
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            target = root / "real-report.json"
            target.write_text("old\n", encoding="utf-8")
            link = root / "report-link.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(TrustReconciliationError, "symlink"):
                write_reconciliation_report(link, report)
            self.assertEqual("old\n", target.read_text(encoding="utf-8"))

    def test_atomic_replace_failure_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            fixture.capture()
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            output = root / "report.json"
            output.write_bytes(b"stable-old-report\n")
            with patch("review_system.trust_reconciliation.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_reconciliation_report(output, report)
            self.assertEqual(b"stable-old-report\n", output.read_bytes())
            self.assertEqual([], list(root.glob(".report.json.*.tmp")))

    def test_malformed_report_and_fixed_authorization_flags_fail_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            fixture.capture()
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            malformed = copy.deepcopy(report)
            malformed.pop("summary")
            self.assertTrue(verify_reconciliation_report_data(malformed))
            tampered = copy.deepcopy(report)
            tampered["automation_authorized"] = True
            tampered["pilot_authorized"] = True
            payload = copy.deepcopy(tampered)
            payload.pop("report_sha256")
            tampered["report_sha256"] = canonical_json_sha256(payload)
            errors = verify_reconciliation_report_data(tampered)
            self.assertTrue(any("automation_authorized" in item for item in errors))
            self.assertTrue(any("pilot_authorized" in item for item in errors))

    def test_wrong_project_defect_authority_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            defect_id, _, ledger = fixture.add_valid_defect_authority()
            assessment_id = fixture.capture()
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                defect_id=defect_id,
            )
            other = root / "other-project-defects.json"
            from review_system.defects import initialize_defect_registry
            initialize_defect_registry(other, "other-project")
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "PRODUCTION_DEFECT",
                "defect_registry": fixture.rel(other),
                "ledger": fixture.rel(ledger),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            self.assertEqual("PROJECT_MISMATCH", report["outcome_reconciliation"][0]["status"])

    def test_observed_defect_without_reproducer_is_insufficient_for_unsafe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            directory, _ = DefectFixture.run(root, "insufficient-defect-run")
            ledger = fixture.trust.reground_fixture.ledger
            import_artifact_directory(ledger, directory)
            with sqlite3.connect(ledger) as connection:
                finding_id = connection.execute(
                    """
                    SELECT f.finding_id FROM findings f
                    JOIN runs r ON r.run_id = f.run_id
                    WHERE r.source_identifier = 'review://demo/insufficient-defect-run'
                    """
                ).fetchone()[0]
            defect = create_defect(
                fixture.trust.defect_registry,
                ledger,
                signature="insufficient-stage10c-defect",
                title="Insufficient Stage 10C defect",
                category="trust.reconciliation",
                actor="owner",
                occurred_at="2026-07-26T00:00:00Z",
            )
            link_finding(
                fixture.trust.defect_registry,
                ledger,
                finding_id=finding_id,
                defect_id=defect["defect_id"],
                match_method="manual",
                confidence=1.0,
                approved_by="reviewer",
                occurred_at="2026-07-27T00:00:00Z",
            )
            assessment_id = fixture.capture()
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                defect_id=defect["defect_id"],
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "PRODUCTION_DEFECT",
                "defect_registry": fixture.rel(fixture.trust.defect_registry),
                "ledger": fixture.rel(ledger),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            outcome = report["outcome_reconciliation"][0]
            self.assertEqual("INSUFFICIENT_EVIDENCE", outcome["status"])
            self.assertFalse(outcome["checks"]["lifecycle_sufficient"])
            self.assertFalse(outcome["checks"]["supporting_artifact_present"])

    def test_evaluation_not_bound_by_trust_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            trusted_path, trusted, revision = fixture.evaluation(unsafe=False)
            other_path, other, _ = fixture.evaluation(unsafe=True)
            assessment_id = fixture.capture(source_revision=revision, evaluation_report=trusted_path)
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="CONTROLLED_EVALUATION",
                verdict="UNSAFE",
                evidence_refs=[other["report_sha256"]],
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "CONTROLLED_EVALUATION",
                "evaluation_report": fixture.rel(other_path),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            outcome = report["outcome_reconciliation"][0]
            self.assertFalse(outcome["checks"]["trust_evaluation_match"])
            self.assertEqual("PROJECT_MISMATCH", outcome["status"])

    def test_unsupported_security_incident_never_becomes_confirmed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            assessment_id = fixture.capture()
            fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="SECURITY_INCIDENT",
                verdict="UNSAFE",
                evidence_refs=["INCIDENT-123"],
            )
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            self.assertEqual("UNSUPPORTED_SOURCE", report["outcome_reconciliation"][0]["status"])
            self.assertEqual(1, report["summary"]["unsupported_source_count"])
            self.assertFalse(report["summary"]["source_reconciliation_complete"])

    def test_missing_declared_source_fails_assessment_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            fixture.capture()
            fixture.assessment_sources[0]["evaluation_report"] = "missing-evaluation.json"
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            result = report["assessment_reconciliation"][0]
            self.assertFalse(result["checks"]["source_replay_match"])
            self.assertEqual("SOURCE_REPLAY_FAILED", result["status"])


if __name__ == "__main__":
    unittest.main()

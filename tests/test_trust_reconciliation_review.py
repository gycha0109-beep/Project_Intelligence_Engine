import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from review_system.defects import (
    create_defect,
    initialize_defect_registry,
    link_defect_artifact,
    link_finding,
    transition_defect,
)
from review_system.evaluation import run_evaluation, write_evaluation_report
from review_system.identity import canonical_json_sha256
from review_system.io import dump_json, dump_yaml, load_data
from review_system.ledger import import_artifact_directory
from review_system.trust_reconciliation import (
    TrustReconciliationError,
    _report_id,
    _report_payload,
    _snapshot_payload,
    reconcile_sources,
    verify_reconciliation_report_data,
)
from test_defects import DefectFixture
from test_evaluation import EvaluationFixture
from test_trust_reconciliation import ReconciliationFixture


def _late_defect_authority(
    root: Path,
    *,
    create_at: str,
    finding_at: str,
    artifact_at: str,
    transition_at: str,
) -> tuple[str, Path, Path]:
    authority_root = root / "late-defect-authority"
    authority_root.mkdir()
    directory, _ = DefectFixture.run(authority_root, "stage10c-late-defect-run")
    ledger = authority_root / "evidence.sqlite"
    import_artifact_directory(ledger, directory)
    registry = authority_root / "defects.json"
    initialize_defect_registry(registry, "demo")
    with sqlite3.connect(ledger) as connection:
        finding_id = connection.execute(
            """
            SELECT f.finding_id
            FROM findings f JOIN runs r ON r.run_id = f.run_id
            WHERE r.source_identifier = 'review://demo/stage10c-late-defect-run'
            """
        ).fetchone()[0]
        artifact_id = connection.execute(
            """
            SELECT a.artifact_id
            FROM artifacts a JOIN runs r ON r.run_id = a.run_id
            WHERE r.source_identifier = 'review://demo/stage10c-late-defect-run'
              AND a.relative_path = 'evidence.txt'
            """
        ).fetchone()[0]
    defect = create_defect(
        registry,
        ledger,
        signature="stage10c-late-production-defect",
        title="Stage 10C late production defect",
        category="trust.reconciliation",
        actor="defect-owner",
        occurred_at=create_at,
    )
    link_finding(
        registry,
        ledger,
        finding_id=finding_id,
        defect_id=defect["defect_id"],
        match_method="deterministic_signature",
        confidence=1.0,
        approved_by="defect-reviewer",
        occurred_at=finding_at,
    )
    link_defect_artifact(
        registry,
        ledger,
        defect_id=defect["defect_id"],
        artifact_id=artifact_id,
        relation="reproducer",
        linked_by="defect-reviewer",
        occurred_at=artifact_at,
    )
    transition_defect(
        registry,
        ledger,
        defect_id=defect["defect_id"],
        target_status="REPRODUCED",
        actor="defect-owner",
        reason="Reproduced after the earlier Outcome boundary",
        occurred_at=transition_at,
    )
    return defect["defect_id"], registry, ledger


class TrustReconciliationImplementationReviewTests(unittest.TestCase):
    def test_future_defect_transition_cannot_backfill_old_unsafe_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            assessment_id = fixture.capture()
            defect_id, registry, ledger = _late_defect_authority(
                root,
                create_at="2026-08-03T00:00:00Z",
                finding_at="2026-08-03T06:00:00Z",
                artifact_at="2026-08-04T00:00:00Z",
                transition_at="2026-08-06T00:00:00Z",
            )
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                defect_id=defect_id,
                occurred_at="2026-08-05T00:00:00Z",
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "PRODUCTION_DEFECT",
                "defect_registry": fixture.rel(registry),
                "ledger": fixture.rel(ledger),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            outcome = report["outcome_reconciliation"][0]
            self.assertEqual("INSUFFICIENT_EVIDENCE", outcome["status"])
            self.assertEqual("OBSERVED", outcome["authority"]["lifecycle_status"])
            self.assertFalse(outcome["checks"]["lifecycle_sufficient"])

    def test_future_finding_link_cannot_backfill_old_revision_relation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            assessment_id = fixture.capture()
            defect_id, registry, ledger = _late_defect_authority(
                root,
                create_at="2026-08-03T00:00:00Z",
                finding_at="2026-08-04T00:00:00Z",
                artifact_at="2026-08-04T06:00:00Z",
                transition_at="2026-08-05T00:00:00Z",
            )
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                defect_id=defect_id,
                occurred_at="2026-08-03T12:00:00Z",
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "PRODUCTION_DEFECT",
                "defect_registry": fixture.rel(registry),
                "ledger": fixture.rel(ledger),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            outcome = report["outcome_reconciliation"][0]
            self.assertEqual("REVISION_MISMATCH", outcome["status"])
            self.assertFalse(outcome["checks"]["revision_relation_match"])

    def test_same_revision_nonholdout_duplicates_do_not_make_holdout_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            eval_root = root / "same-revision-evaluation"
            eval_root.mkdir()
            evaluation_fixture = EvaluationFixture(eval_root)
            dataset = load_data(evaluation_fixture.dataset)
            revision = "git:" + "9" * 40
            for case in dataset["cases"]:
                case["source_revision"] = revision
            dump_yaml(evaluation_fixture.dataset, dataset)
            evaluation = run_evaluation(
                evaluation_fixture.dataset,
                evaluation_fixture.baseline,
                evaluation_fixture.challenger,
            )
            write_evaluation_report(evaluation_fixture.report, evaluation)
            assessment_id = fixture.capture(
                source_revision=revision,
                evaluation_report=evaluation_fixture.report,
            )
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="CONTROLLED_EVALUATION",
                verdict="SAFE",
                evidence_refs=[evaluation["evaluation_id"]],
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "CONTROLLED_EVALUATION",
                "evaluation_report": fixture.rel(evaluation_fixture.report),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            outcome = report["outcome_reconciliation"][0]
            self.assertEqual("RECONCILED", outcome["status"])
            self.assertTrue(outcome["checks"]["unambiguous_case"])
            self.assertEqual("holdout", outcome["authority"]["case_split"])

    def test_outcome_base_status_semantic_tamper_is_rejected_after_rehash(self):
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
            tampered = copy.deepcopy(report)
            outcome = tampered["outcome_reconciliation"][0]
            outcome["base_status"] = "RECONCILED"
            outcome["status"] = "RECONCILED"
            outcome["reconciled"] = True
            tampered["summary"]["conclusive_outcome_reconciled_count"] = 1
            tampered["summary"]["conclusive_outcome_unreconciled_count"] = 0
            tampered["summary"]["unsupported_source_count"] = 0
            tampered["summary"]["source_reconciliation_complete"] = True
            tampered["status"] = "RECONCILED"
            tampered["evidence_snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(tampered))
            tampered["report_id"] = _report_id(tampered, tampered["evidence_snapshot_sha256"])
            tampered["report_sha256"] = canonical_json_sha256(_report_payload(tampered))
            errors = verify_reconciliation_report_data(tampered)
            self.assertTrue(any("base_status projection mismatch" in error for error in errors))

    def test_orphan_manifest_assessment_and_outcome_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            fixture.capture()
            fixture.persist()
            manifest = load_data(fixture.sources_path)
            orphan = copy.deepcopy(manifest["assessment_sources"][0])
            orphan["assessment_id"] = "assessment-orphan"
            manifest["assessment_sources"].append(orphan)
            dump_json(fixture.sources_path, manifest)
            with self.assertRaisesRegex(TrustReconciliationError, "unknown assessment"):
                reconcile_sources(fixture.registry_path, fixture.sources_path)

            fixture.persist()
            manifest = load_data(fixture.sources_path)
            manifest["outcome_sources"].append({
                "event_id": "event-orphan",
                "authority_type": "CONTROLLED_EVALUATION",
                "evaluation_report": fixture.assessment_sources[0]["evaluation_report"],
            })
            dump_json(fixture.sources_path, manifest)
            with self.assertRaisesRegex(TrustReconciliationError, "unknown Outcome"):
                reconcile_sources(fixture.registry_path, fixture.sources_path)

    def test_lexical_symlink_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            fixture.capture()
            original = root / fixture.assessment_sources[0]["trust_report"]
            link = root / "lexical-trust-report-link.json"
            try:
                link.symlink_to(original)
            except OSError:
                self.skipTest("symlinks unavailable")
            fixture.assessment_sources[0]["trust_report"] = link.relative_to(root).as_posix()
            fixture.persist()
            with self.assertRaisesRegex(TrustReconciliationError, "symlink"):
                reconcile_sources(fixture.registry_path, fixture.sources_path)


if __name__ == "__main__":
    unittest.main()

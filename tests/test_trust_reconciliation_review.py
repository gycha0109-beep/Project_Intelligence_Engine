import copy
from pathlib import Path
import tempfile
import unittest

from review_system.evaluation import run_evaluation, write_evaluation_report
from review_system.identity import canonical_json_sha256
from review_system.io import dump_json, dump_yaml, load_data
from review_system.trust_reconciliation import (
    TrustReconciliationError,
    _report_id,
    _report_payload,
    _snapshot_payload,
    reconcile_sources,
    verify_reconciliation_report_data,
)
from test_evaluation import EvaluationFixture
from test_trust_reconciliation import ReconciliationFixture


class TrustReconciliationImplementationReviewTests(unittest.TestCase):
    def test_future_defect_transition_cannot_backfill_old_unsafe_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            defect_id, registry, ledger = fixture.add_valid_defect_authority()
            assessment_id = fixture.capture()
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                defect_id=defect_id,
                occurred_at="2026-07-28T12:00:00Z",
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
            fixture = ReconciliationFixture(Path(tmp))
            defect_id, registry, ledger = fixture.add_valid_defect_authority()
            assessment_id = fixture.capture()
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                defect_id=defect_id,
                occurred_at="2026-07-26T12:00:00Z",
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

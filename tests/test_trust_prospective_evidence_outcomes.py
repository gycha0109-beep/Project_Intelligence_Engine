from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from review_system.identity import canonical_json_sha256
from review_system.io import dump_json, load_data
from review_system.trust import write_trust_report
from review_system.trust_comparison import load_registry
from review_system.trust_prospective_evidence import (
    ProspectiveEvidenceError,
    intake_prospective_case,
    campaign_progress,
    record_case_outcome,
    snapshot_campaign,
    verify_campaign_report_data,
)
from test_trust_prospective_evidence import (
    CAPTURED_AT, GENERATED_AT, build_r0_case, init_workspace, intake,
)
from test_trust_reconciliation import ReconciliationFixture


class ProspectiveEvidenceOutcomeSnapshotTests(unittest.TestCase):
    def test_currently_unsupported_outcome_authority_is_rejected_before_registry_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            fixture, _report, report_path = build_r0_case(root)
            result = intake(workspace, fixture, report_path)
            before = (workspace / "comparison-registry.json").read_bytes()
            with self.assertRaisesRegex(ProspectiveEvidenceError, "not source-reconcilable"):
                record_case_outcome(
                    workspace,
                    assessment_id=result["assessment_id"],
                    outcome_type="REGRESSION",
                    verdict="UNSAFE",
                    actor="runtime",
                )
            self.assertEqual(before, (workspace / "comparison-registry.json").read_bytes())

    def test_controlled_evaluation_safe_outcome_reconciles_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            reconciliation_fixture = ReconciliationFixture(root / "sources")
            evaluation_path, evaluation, source_revision = reconciliation_fixture.evaluation(unsafe=False)
            trust = reconciliation_fixture.trust
            trust.write_request(task_class="formatting", changed_files=["reports/eval.report.json"])
            request = load_data(trust.request)
            request["task_id"] = "TASK-R0-EVAL"
            request["source_revision"] = source_revision
            dump_json(trust.request, request)
            report = trust.assess(generated_at=GENERATED_AT, evaluation_report=evaluation_path)
            self.assertEqual("R0", report["risk"]["effective_band"])
            report_path = trust.root / "trust-report-prospective.json"
            write_trust_report(report_path, report)
            result = intake_prospective_case(
                workspace,
                trust_report=report_path,
                request=trust.request,
                profile=trust.profile,
                ledger=trust.reground_fixture.ledger,
                policy_registry=trust.policy_registry,
                evaluation_report=evaluation_path,
                reground_report=trust.reground_report,
                reground_observations=trust.observations,
                captured_at=CAPTURED_AT,
            )
            first = record_case_outcome(
                workspace,
                assessment_id=result["assessment_id"],
                outcome_type="CONTROLLED_EVALUATION",
                verdict="SAFE",
                actor="evaluation-lab",
                occurred_at="2026-08-18T04:00:00Z",
                evaluation_report=evaluation_path,
            )
            second = record_case_outcome(
                workspace,
                assessment_id=result["assessment_id"],
                outcome_type="CONTROLLED_EVALUATION",
                verdict="SAFE",
                actor="evaluation-lab",
                occurred_at="2026-08-18T04:30:00Z",
                evaluation_report=evaluation_path,
            )
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(first["event_id"], second["event_id"])
            _, registry = load_registry(workspace / "comparison-registry.json")
            outcomes = [item for item in registry["events"] if item["event_type"] == "OUTCOME"]
            self.assertEqual(1, len(outcomes))
            self.assertIn(evaluation["report_sha256"], outcomes[0]["payload"]["evidence_refs"])
            progress = campaign_progress(workspace, generated_at="2026-08-18T05:00:00Z")
            self.assertEqual(1, progress["observation"]["r0_conclusive_outcome_count"])
            self.assertEqual(1, progress["observation"]["r0_confirmed_safe_count"])
            self.assertTrue(progress["reconciliation"]["source_reconciliation_complete"])

    def test_campaign_report_rejects_semantic_threshold_relaxation_even_if_rehashed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            report = campaign_progress(workspace, generated_at="2026-08-18T04:00:00Z")
            forged = deepcopy(report)
            forged["policy"]["thresholds"]["minimum_r0_assessment_count"] = 1
            forged["checks"][0]["required"] = 1
            forged["checks"][0]["passed"] = True
            snapshot = {
                "schema_version": forged["schema_version"],
                "campaign_contract": forged["campaign_contract"],
                "project_id": forged["project_id"],
                "mode": forged["mode"],
                "target_band": forged["target_band"],
                "automation_authorized": forged["automation_authorized"],
                "pilot_authorized": forged["pilot_authorized"],
                "registry": forged["registry"],
                "policy": forged["policy"],
                "reconciliation": forged["reconciliation"],
                "observation": forged["observation"],
                "checks": forged["checks"],
                "status": forged["status"],
                "next_step": forged["next_step"],
            }
            forged["evidence_snapshot_sha256"] = canonical_json_sha256(snapshot)
            forged["campaign_id"] = "r0-prospective-campaign-" + canonical_json_sha256({"project_id": forged["project_id"], "snapshot": forged["evidence_snapshot_sha256"]})[:32]
            payload = deepcopy(forged)
            payload.pop("report_sha256")
            forged["report_sha256"] = canonical_json_sha256(payload)
            errors = verify_campaign_report_data(forged)
            self.assertIn("embedded policy_id mismatch", errors)
            self.assertIn("embedded policy_sha256 mismatch", errors)

    def test_snapshot_is_immutable_replayable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            fixture, _report, report_path = build_r0_case(root)
            intake(workspace, fixture, report_path)
            snapshots = root / "snapshots"
            first = snapshot_campaign(workspace, snapshots, generated_at="2026-08-18T04:00:00Z")
            second = snapshot_campaign(workspace, snapshots, generated_at="2026-08-18T05:00:00Z")
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(first["package"], second["package"])
            self.assertEqual("PACKAGE_POPULATED_NOT_ELIGIBLE", first["status"])


if __name__ == "__main__":
    unittest.main()

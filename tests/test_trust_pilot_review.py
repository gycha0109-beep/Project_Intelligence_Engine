from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.identity import canonical_json_sha256
from review_system.trust_pilot_review import (
    ELIGIBLE_STATUS,
    NOT_ELIGIBLE_STATUS,
    PilotSafetyReviewError,
    _report_payload,
    _review_id,
    _snapshot_payload,
    evaluate_pilot_review_data,
    review_r0_pilot,
    verify_pilot_review_report_data,
    write_pilot_review_report,
)


H64 = "a" * 64
H64_B = "b" * 64
H64_C = "c" * 64
RID = "trust-comparison-" + "1" * 32
RECON_ID = "trust-reconciliation-" + "2" * 32
OBS_ID = "trust-observation-" + "3" * 32
POLICY_ID = "trust-observation-policy-" + "4" * 32


def sources() -> dict:
    return {
        "registry": {
            "source": "registry.json",
            "project_id": "project-x",
            "registry_id": RID,
            "registry_sha256": H64,
        },
        "reconciliation_report": {
            "source": "reconciliation.json",
            "project_id": "project-x",
            "report_id": RECON_ID,
            "report_sha256": H64_B,
            "evidence_snapshot_sha256": H64_C,
            "registry_id": RID,
            "registry_sha256": H64,
        },
        "reconciliation_sources": {
            "source": "sources.json",
            "manifest_sha256": "d" * 64,
        },
        "observation_report": {
            "source": "observation.json",
            "project_id": "project-x",
            "report_id": OBS_ID,
            "report_sha256": "e" * 64,
            "registry_id": RID,
            "registry_sha256": H64,
        },
        "observation_policy": {
            "source": "policy.json",
            "policy_id": POLICY_ID,
            "policy_sha256": "f" * 64,
        },
    }


def reconciled() -> dict:
    return {
        "status": "RECONCILED",
        "source_reconciliation_complete": True,
        "assessment_unreconciled_count": 0,
        "conclusive_outcome_count": 15,
        "conclusive_outcome_unreconciled_count": 0,
        "conclusive_duplicate_authority_count": 0,
        "conclusive_unsupported_source_count": 0,
        "conclusive_provenance_unverified_count": 0,
        "verified_r0_independent_audit_assessment_count": 5,
    }


def observation() -> dict:
    return {
        "status": "THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION",
        "r0_false_negative": 0,
        "r0_false_negative_rate": 0.0,
        "confirmed_unsafe_challenge_count": 5,
        "r0_independent_audit_count": 5,
        "registry_r0_independent_audit_assessment_count": 5,
        "minimum_r0_independent_audit_count": 5,
    }


def evaluate(*, reconciliation=None, observed=None, replay=None, generated_at="2026-08-18T02:00:00Z") -> dict:
    return evaluate_pilot_review_data(
        project_id="project-x",
        sources=sources(),
        source_replay=replay or {"reconciliation_verified": True, "observation_verified": True},
        reconciliation=reconciliation or reconciled(),
        observation=observed or observation(),
        generated_at=generated_at,
    )


class PilotSafetyReviewTests(unittest.TestCase):
    def test_future_complete_evidence_only_reaches_human_authorization_review(self) -> None:
        report = evaluate()
        self.assertEqual(report["status"], ELIGIBLE_STATUS)
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["next_step"], "REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION")
        self.assertFalse(report["automation_authorized"])
        self.assertFalse(report["pilot_authorized"])
        self.assertEqual(verify_pilot_review_report_data(report), [])

    def test_current_independent_audit_contract_fails_closed(self) -> None:
        reconciliation = reconciled()
        reconciliation.update({
            "status": "UNRECONCILED",
            "source_reconciliation_complete": False,
            "conclusive_outcome_unreconciled_count": 5,
            "conclusive_provenance_unverified_count": 5,
            "verified_r0_independent_audit_assessment_count": 0,
        })
        report = evaluate(reconciliation=reconciliation)
        self.assertEqual(report["status"], NOT_ELIGIBLE_STATUS)
        self.assertEqual(report["next_step"], "ESTABLISH_INDEPENDENT_AUDIT_AUTHORITY")
        self.assertIn("NO_CONCLUSIVE_PROVENANCE_UNVERIFIED", report["blockers"])
        self.assertIn("VERIFIED_R0_INDEPENDENT_AUDIT_THRESHOLD", report["blockers"])
        self.assertFalse(report["pilot_authorized"])

    def test_source_replay_failure_blocks_before_activation(self) -> None:
        report = evaluate(replay={"reconciliation_verified": False, "observation_verified": True})
        self.assertEqual(report["status"], NOT_ELIGIBLE_STATUS)
        self.assertEqual(report["next_step"], "REPAIR_AND_REPLAY_SOURCE_EVIDENCE")
        self.assertIn("RECONCILIATION_SOURCE_REPLAY", report["blockers"])

    def test_observation_safety_failure_is_not_eligible(self) -> None:
        observed = observation()
        observed.update({
            "status": "THRESHOLD_BLOCKED",
            "r0_false_negative": 1,
            "r0_false_negative_rate": 0.2,
        })
        report = evaluate(observed=observed)
        self.assertEqual(report["status"], NOT_ELIGIBLE_STATUS)
        self.assertEqual(report["next_step"], "RESOLVE_OBSERVATION_SAFETY_BLOCKERS")
        self.assertIn("R0_FALSE_NEGATIVES_ZERO", report["blockers"])
        self.assertIn("R0_FALSE_NEGATIVE_RATE_ZERO", report["blockers"])

    def test_registry_identity_mismatch_blocks(self) -> None:
        altered = sources()
        altered["observation_report"]["registry_sha256"] = H64_B
        report = evaluate_pilot_review_data(
            project_id="project-x",
            sources=altered,
            source_replay={"reconciliation_verified": True, "observation_verified": True},
            reconciliation=reconciled(),
            observation=observation(),
            generated_at="2026-08-18T02:00:00Z",
        )
        self.assertEqual(report["status"], NOT_ELIGIBLE_STATUS)
        self.assertIn("REGISTRY_IDENTITY_MATCH", report["blockers"])
        self.assertEqual(report["next_step"], "REPAIR_AND_REPLAY_SOURCE_EVIDENCE")

    def test_audit_projection_mismatch_blocks(self) -> None:
        observed = observation()
        observed["registry_r0_independent_audit_assessment_count"] = 4
        report = evaluate(observed=observed)
        self.assertEqual(report["status"], NOT_ELIGIBLE_STATUS)
        self.assertIn("R0_AUDIT_COUNT_PROJECTION_MATCH", report["blockers"])

    def test_generated_at_does_not_change_evidence_identity(self) -> None:
        first = evaluate(generated_at="2026-08-18T02:00:00Z")
        second = evaluate(generated_at="2026-08-19T02:00:00Z")
        self.assertEqual(first["evidence_snapshot_sha256"], second["evidence_snapshot_sha256"])
        self.assertEqual(first["review_id"], second["review_id"])
        self.assertNotEqual(first["report_sha256"], second["report_sha256"])

    def test_semantic_rehash_cannot_escalate_blocked_report(self) -> None:
        reconciliation = reconciled()
        reconciliation.update({
            "status": "UNRECONCILED",
            "source_reconciliation_complete": False,
            "conclusive_outcome_unreconciled_count": 1,
            "conclusive_provenance_unverified_count": 1,
            "verified_r0_independent_audit_assessment_count": 0,
        })
        report = evaluate(reconciliation=reconciliation)
        forged = deepcopy(report)
        forged["status"] = ELIGIBLE_STATUS
        forged["blockers"] = []
        forged["next_step"] = "REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION"
        forged["evidence_snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(forged))
        forged["review_id"] = _review_id(forged, forged["evidence_snapshot_sha256"])
        forged["report_sha256"] = canonical_json_sha256(_report_payload(forged))
        errors = verify_pilot_review_report_data(forged)
        self.assertTrue(any("status projection mismatch" in error for error in errors))
        self.assertTrue(any("blockers projection mismatch" in error for error in errors))

    def test_pilot_authorized_cannot_be_rehashed_true(self) -> None:
        report = evaluate()
        forged = deepcopy(report)
        forged["pilot_authorized"] = True
        forged["evidence_snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(forged))
        forged["review_id"] = _review_id(forged, forged["evidence_snapshot_sha256"])
        forged["report_sha256"] = canonical_json_sha256(_report_payload(forged))
        errors = verify_pilot_review_report_data(forged)
        self.assertTrue(any("False was expected" in error or "pilot_authorized" in error for error in errors))

    def test_output_symlink_is_rejected(self) -> None:
        report = evaluate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text("original\n", encoding="utf-8")
            link = root / "report.json"
            link.symlink_to(target)
            with self.assertRaises(PilotSafetyReviewError):
                write_pilot_review_report(link, report)
            self.assertEqual(target.read_text(encoding="utf-8"), "original\n")

    def test_atomic_replace_failure_preserves_existing_bytes(self) -> None:
        report = evaluate()
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "report.json"
            target.write_text("original\n", encoding="utf-8")
            with patch("review_system.trust_pilot_review.os.replace", side_effect=OSError("boom")):
                with self.assertRaises(PilotSafetyReviewError):
                    write_pilot_review_report(target, report)
            self.assertEqual(target.read_text(encoding="utf-8"), "original\n")

    @patch("review_system.trust_pilot_review.verify_observation_report_sources", return_value=[])
    @patch("review_system.trust_pilot_review.verify_reconciliation_report_sources", return_value=[])
    @patch("review_system.trust_pilot_review.load_observation_report")
    @patch("review_system.trust_pilot_review.load_reconciliation_report")
    @patch("review_system.trust_pilot_review.load_registry")
    def test_combined_stage10_sources_expose_current_audit_provenance_blocker(
        self,
        load_registry_mock,
        load_reconciliation_mock,
        load_observation_mock,
        _reconciliation_replay_mock,
        _observation_replay_mock,
    ) -> None:
        registry = {
            "project_id": "project-x",
            "registry_id": RID,
            "registry_sha256": H64,
            "assessments": [{"assessment_id": "a1", "predicted_risk_band": "R0"}],
            "events": [{
                "event_type": "OUTCOME",
                "assessment_id": "a1",
                "payload": {"outcome_type": "INDEPENDENT_AUDIT", "verdict": "SAFE"},
            }],
        }
        reconciliation_report = {
            "project_id": "project-x",
            "report_id": RECON_ID,
            "report_sha256": H64_B,
            "evidence_snapshot_sha256": H64_C,
            "comparison_registry": {"registry_id": RID, "registry_sha256": H64},
            "source_manifest": {"manifest_sha256": "d" * 64},
            "status": "UNRECONCILED",
            "summary": {
                "source_reconciliation_complete": False,
                "assessment_unreconciled_count": 0,
            },
            "outcome_reconciliation": [{
                "event_id": "e1",
                "assessment_id": "a1",
                "outcome_type": "INDEPENDENT_AUDIT",
                "verdict": "SAFE",
                "conclusive": True,
                "status": "PROVENANCE_UNVERIFIED",
                "reconciled": False,
            }],
        }
        observation_report = {
            "project_id": "project-x",
            "report_id": OBS_ID,
            "report_sha256": "e" * 64,
            "registry": {"registry_id": RID, "registry_sha256": H64},
            "policy": {
                "policy_id": POLICY_ID,
                "policy_sha256": "f" * 64,
                "thresholds": {"minimum_r0_independent_audit_count": 1},
            },
            "status": "THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION",
            "observation": {
                "r0_false_negative": 0,
                "r0_false_negative_rate": 0.0,
                "confirmed_unsafe_challenge_count": 1,
                "r0_independent_audit_count": 1,
            },
        }
        load_registry_mock.return_value = (Path("registry.json"), registry)
        load_reconciliation_mock.return_value = (Path("reconciliation.json"), reconciliation_report)
        load_observation_mock.return_value = (Path("observation.json"), observation_report)

        report = review_r0_pilot(
            registry_path="registry.json",
            reconciliation_report_path="reconciliation.json",
            reconciliation_sources_path="sources.json",
            observation_report_path="observation.json",
            observation_policy_path="policy.json",
            generated_at="2026-08-18T02:00:00Z",
        )
        self.assertEqual(report["status"], NOT_ELIGIBLE_STATUS)
        self.assertEqual(report["next_step"], "ESTABLISH_INDEPENDENT_AUDIT_AUTHORITY")
        self.assertEqual(report["reconciliation"]["verified_r0_independent_audit_assessment_count"], 0)
        self.assertIn("NO_CONCLUSIVE_PROVENANCE_UNVERIFIED", report["blockers"])


if __name__ == "__main__":
    unittest.main()

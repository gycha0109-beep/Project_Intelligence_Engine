from __future__ import annotations

import unittest

from review_system.trust_pilot_review import NOT_ELIGIBLE_STATUS, evaluate_pilot_review_data


H64 = "a" * 64
RID = "trust-comparison-" + "1" * 32


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
            "report_id": "trust-reconciliation-" + "2" * 32,
            "report_sha256": "b" * 64,
            "evidence_snapshot_sha256": "c" * 64,
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
            "report_id": "trust-observation-" + "3" * 32,
            "report_sha256": "e" * 64,
            "registry_id": RID,
            "registry_sha256": H64,
        },
        "observation_policy": {
            "source": "policy.json",
            "policy_id": "trust-observation-policy-" + "4" * 32,
            "policy_sha256": "f" * 64,
        },
    }


def reconciliation() -> dict:
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


def evaluate(reconciliation_value: dict, replay: dict[str, bool]) -> dict:
    return evaluate_pilot_review_data(
        project_id="project-x",
        sources=sources(),
        source_replay=replay,
        reconciliation=reconciliation_value,
        observation=observation(),
        generated_at="2026-08-18T02:00:00Z",
    )


class PilotSafetyReviewHardeningTests(unittest.TestCase):
    def test_source_replay_repair_outranks_audit_authority_remediation(self) -> None:
        value = reconciliation()
        value.update({
            "status": "UNRECONCILED",
            "source_reconciliation_complete": False,
            "conclusive_outcome_unreconciled_count": 1,
            "conclusive_provenance_unverified_count": 1,
            "verified_r0_independent_audit_assessment_count": 0,
        })
        report = evaluate(
            value,
            {"reconciliation_verified": False, "observation_verified": True},
        )
        self.assertEqual(report["status"], NOT_ELIGIBLE_STATUS)
        self.assertIn("RECONCILIATION_SOURCE_REPLAY", report["blockers"])
        self.assertIn("NO_CONCLUSIVE_PROVENANCE_UNVERIFIED", report["blockers"])
        self.assertEqual(report["next_step"], "REPAIR_AND_REPLAY_SOURCE_EVIDENCE")

    def test_unreconciled_assessment_directly_breaks_reconciliation_complete(self) -> None:
        value = reconciliation()
        value["assessment_unreconciled_count"] = 1
        report = evaluate(
            value,
            {"reconciliation_verified": True, "observation_verified": True},
        )
        self.assertEqual(report["status"], NOT_ELIGIBLE_STATUS)
        self.assertIn("RECONCILIATION_COMPLETE", report["blockers"])
        self.assertEqual(report["next_step"], "RESOLVE_SOURCE_RECONCILIATION_BLOCKERS")


if __name__ == "__main__":
    unittest.main()

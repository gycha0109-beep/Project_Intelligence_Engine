from __future__ import annotations

from copy import deepcopy
import unittest

from review_system.prospective_replay import build_deterministic_result, verify_deterministic_result


IDENTITY = {
    "schema_version": "PIE_PROSPECTIVE_EXECUTION_IDENTITY_V1",
    "execution_id": "pie-pr-auto-" + "a" * 32,
    "execution_key_sha256": "b" * 64,
    "repository": "demo/repo",
    "pull_request": 7,
    "source_revision": "c" * 40,
    "pie_revision": "d" * 40,
    "profile_sha256": "e" * 64,
    "config_sha256": "f" * 64,
    "trust_request_sha256": None,
}
SUMMARY = {
    "repository": "demo/repo",
    "pull_request": 7,
    "source_revision": "c" * 40,
    "pie_revision": "d" * 40,
    "status": "WAITING_FOR_TRUST_INPUT",
    "next_step": "PROVIDE_EXPLICIT_TRUST_REQUEST",
    "candidate_id": "candidate-1",
    "assessment_id": None,
    "packet_id": None,
    "risk_band": None,
    "readiness": None,
    "auto_capture": True,
    "auto_analysis": True,
    "auto_trust_assessment": False,
    "auto_packet_prepare": False,
    "human_review_recorded": False,
    "outcome_recorded": False,
    "automation_authorized": False,
    "pilot_authorized": False,
}


def _candidate(*, generated_at: str, source_hash: str) -> dict:
    return {
        "schema_version": "1.0",
        "candidate_id": "candidate-1",
        "generated_at": generated_at,
        "source_evidence_sha256": source_hash,
        "evidence_snapshot_sha256": source_hash,
        "report_sha256": source_hash,
        "status": "BLOCKED_OPERATOR_INPUT_REQUIRED",
        "next_step": "COMPLETE_TRUST_REQUEST_AND_MATERIALIZE",
        "blockers": ["TRUST_TASK_CLASS_REQUIRED"],
        "changed_files": ["src/core.py"],
    }


class ProspectiveReplayTests(unittest.TestCase):
    def _build(self, *, generated_at: str, source_hash: str, changed_files=None, impact=None):
        return build_deterministic_result(
            identity=IDENTITY,
            summary=SUMMARY,
            base_revision="1" * 40,
            changed_files=changed_files or ["src/core.py"],
            diff_sha256="2" * 64,
            impact=impact or {
                "change_id": "PR-7",
                "affected_components": ["application"],
                "source_evidence_sha256": source_hash,
            },
            candidate=_candidate(generated_at=generated_at, source_hash=source_hash),
            workflow_semantics={
                "schema_version": "1.0",
                "source_revision": "c" * 40,
                "source_evidence_sha256": source_hash,
                "evidence_sha256": source_hash,
                "workflow_files": [],
            },
        )

    def test_transient_provider_observation_changes_do_not_change_result_hash(self):
        first = self._build(generated_at="2026-08-24T00:00:00Z", source_hash="3" * 64)
        second = self._build(generated_at="2026-08-24T00:10:00Z", source_hash="4" * 64)
        self.assertEqual(first["deterministic_result_sha256"], second["deterministic_result_sha256"])
        self.assertEqual([], verify_deterministic_result(first))
        self.assertEqual([], verify_deterministic_result(second))

    def test_semantic_change_changes_result_hash(self):
        first = self._build(generated_at="2026-08-24T00:00:00Z", source_hash="3" * 64)
        changed = self._build(
            generated_at="2026-08-24T00:00:00Z",
            source_hash="3" * 64,
            impact={
                "change_id": "PR-7",
                "affected_components": ["application", "database"],
                "source_evidence_sha256": "3" * 64,
            },
        )
        self.assertNotEqual(first["deterministic_result_sha256"], changed["deterministic_result_sha256"])

    def test_hash_tampering_is_detected(self):
        value = self._build(generated_at="2026-08-24T00:00:00Z", source_hash="3" * 64)
        forged = deepcopy(value)
        forged["source"]["changed_files"] = ["src/other.py"]
        self.assertIn("deterministic_result_sha256 mismatch", verify_deterministic_result(forged))


if __name__ == "__main__":
    unittest.main()

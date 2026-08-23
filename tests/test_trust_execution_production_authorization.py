from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from review_system.trust_execution_production_authorization import (
    NEXT_READY,
    STATUS_BLOCKED,
    STATUS_READY,
    build_production_authorization_review,
    verify_production_authorization_review_data,
)


ROOT = Path(__file__).resolve().parents[1]
ACTUAL_EVIDENCE = ROOT / "evidence" / "trust" / "peb4a-production-authorization-20260823.json"


def _build_complete() -> dict:
    return build_production_authorization_review(
        review_id="PEB4A-SYNTHETIC-COMPLETE",
        project_id="PIE",
        source_main_sha="1" * 40,
        boundary_authorization_id="auth-peb4a-example",
        boundary_authorization_ref="human-boundary:peb4a-example",
        trust_report_id="trust-report-example",
        trust_report_sha256="2" * 64,
        trust_risk_band="R3",
        target_provider="GITHUB",
        target_resource="example/production-repo#123",
        capability_class="GITHUB_PR_MUTATION",
        operation="MARK_READY_FOR_REVIEW",
        rollback_operation="CONVERT_TO_DRAFT",
        action_payload_sha256="3" * 64,
        target_precondition_fingerprint="state=open;draft=true;head=" + ("4" * 40),
        credential_scope_evidence_ref="evidence:credential-scope",
        rollback_evidence_ref="evidence:rollback",
        postcondition_verifier_ref="evidence:postcondition-verifier",
        blast_radius_evidence_ref="evidence:blast-radius",
        kill_switch_evidence_ref="evidence:kill-switch",
        recovery_window_evidence_ref="evidence:recovery-window",
        generated_at="2026-08-23T08:02:00Z",
    )


class ProductionExecutionAuthorizationTests(unittest.TestCase):
    def test_complete_review_only_prepares_one_shot_effect_authorization_request(self) -> None:
        report = _build_complete()
        self.assertEqual(report["status"], STATUS_READY)
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["next_step"], NEXT_READY)
        self.assertTrue(report["production_boundary_authorized"])
        self.assertFalse(report["production_execution_authorized"])
        self.assertFalse(report["automation_authorized"])
        self.assertFalse(report["pilot_authorized"])
        self.assertFalse(report["effect_authorization"]["authorized"])
        self.assertIsNotNone(report["request_sha256"])
        self.assertEqual(report["effect_authorization"]["bound_request_sha256"], report["request_sha256"])
        self.assertEqual(verify_production_authorization_review_data(report), [])

    def test_boundary_entry_authorization_does_not_become_effect_authorization(self) -> None:
        report = _build_complete()
        self.assertTrue(report["production_boundary_authorized"])
        self.assertFalse(report["production_execution_authorized"])
        self.assertFalse(report["effect_authorization"]["authorized"])

    def test_missing_target_and_safety_evidence_fail_closed(self) -> None:
        report = build_production_authorization_review(
            review_id="PEB4A-SYNTHETIC-BLOCKED",
            project_id="PIE",
            source_main_sha="1" * 40,
            boundary_authorization_id="auth-peb4a-example",
            boundary_authorization_ref="human-boundary:peb4a-example",
            generated_at="2026-08-23T08:02:00Z",
        )
        self.assertEqual(report["status"], STATUS_BLOCKED)
        self.assertIn("PRODUCTION_TARGET_NOT_NOMINATED", report["blockers"])
        self.assertIn("PRODUCTION_OPERATION_NOT_NOMINATED", report["blockers"])
        self.assertIn("PRODUCTION_CREDENTIAL_SCOPE_NOT_PROVEN", report["blockers"])
        self.assertIn("PRODUCTION_ROLLBACK_NOT_PROVEN", report["blockers"])
        self.assertIn("PRODUCTION_POSTCONDITION_VERIFIER_NOT_PROVEN", report["blockers"])
        self.assertIsNone(report["request_sha256"])
        self.assertEqual(verify_production_authorization_review_data(report), [])

    def test_missing_boundary_authorization_is_blocked(self) -> None:
        report = build_production_authorization_review(
            review_id="PEB4A-NO-BOUNDARY-AUTH",
            project_id="PIE",
            source_main_sha="1" * 40,
            boundary_authorization_id=None,
            boundary_authorization_ref=None,
            generated_at="2026-08-23T08:02:00Z",
        )
        self.assertFalse(report["production_boundary_authorized"])
        self.assertIn("PRODUCTION_BOUNDARY_AUTHORIZATION_REQUIRED", report["blockers"])
        self.assertEqual(report["status"], STATUS_BLOCKED)

    def test_production_execution_authority_tamper_is_rejected(self) -> None:
        report = _build_complete()
        tampered = deepcopy(report)
        tampered["production_execution_authorized"] = True
        errors = verify_production_authorization_review_data(tampered)
        self.assertTrue(any("production_execution_authorized" in error for error in errors))

    def test_effect_authorization_tamper_is_rejected(self) -> None:
        report = _build_complete()
        tampered = deepcopy(report)
        tampered["effect_authorization"]["authorized"] = True
        errors = verify_production_authorization_review_data(tampered)
        self.assertTrue(any("cannot claim production effect authorization" in error for error in errors))

    def test_request_hash_tamper_is_rejected(self) -> None:
        report = _build_complete()
        tampered = deepcopy(report)
        tampered["request_sha256"] = "0" * 64
        errors = verify_production_authorization_review_data(tampered)
        self.assertTrue(any("request_sha256 mismatch" in error for error in errors))

    def test_blocker_projection_tamper_is_rejected(self) -> None:
        report = build_production_authorization_review(
            review_id="PEB4A-BLOCKER-TAMPER",
            project_id="PIE",
            source_main_sha="1" * 40,
            boundary_authorization_id="auth-peb4a-example",
            boundary_authorization_ref="human-boundary:peb4a-example",
            generated_at="2026-08-23T08:02:00Z",
        )
        tampered = deepcopy(report)
        tampered["blockers"] = []
        errors = verify_production_authorization_review_data(tampered)
        self.assertTrue(any("blocker projection mismatch" in error for error in errors))

    def test_report_hash_tamper_is_rejected(self) -> None:
        report = _build_complete()
        tampered = deepcopy(report)
        tampered["report_sha256"] = "0" * 64
        errors = verify_production_authorization_review_data(tampered)
        self.assertTrue(any("report_sha256 mismatch" in error for error in errors))

    def test_actual_peb4a_evidence_is_fail_closed_without_production_target(self) -> None:
        report = json.loads(ACTUAL_EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(verify_production_authorization_review_data(report), [])
        self.assertTrue(report["production_boundary_authorized"])
        self.assertFalse(report["production_execution_authorized"])
        self.assertEqual(report["status"], STATUS_BLOCKED)
        self.assertIn("PRODUCTION_TARGET_NOT_NOMINATED", report["blockers"])
        self.assertIn("TRUST_DECISION_BINDING_NOT_PROVEN", report["blockers"])

    def test_schema_asset_is_synchronized(self) -> None:
        source = ROOT / "schemas" / "production-execution-authorization-review.schema.json"
        packaged = ROOT / "src" / "review_system" / "assets" / "schemas" / "production-execution-authorization-review.schema.json"
        self.assertEqual(source.read_bytes(), packaged.read_bytes())


if __name__ == "__main__":
    unittest.main()

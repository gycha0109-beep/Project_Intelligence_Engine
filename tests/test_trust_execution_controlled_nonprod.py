from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from review_system.trust_execution_controlled_nonprod import (
    STATUS_BLOCKED,
    STATUS_PASS,
    build_controlled_nonprod_report,
    verify_controlled_nonprod_report_data,
)


ROOT = Path(__file__).resolve().parents[1]
ACTUAL_EVIDENCE = ROOT / "evidence" / "trust" / "peb3-controlled-nonprod-20260822.json"


def _build(*, credential_scope_proven: bool) -> dict:
    kwargs = {
        "calibration_id": "PEB3-SYNTHETIC-CONTROL",
        "project_id": "PIE",
        "source_main_sha": "1" * 40,
        "target_repository": "example/repo",
        "target_pr_number": 60,
        "target_head_sha": "2" * 40,
        "authorization_id": "auth-peb3-example",
        "authorization_ref": "human-boundary:peb3-example",
        "credential_scope_proven": credential_scope_proven,
        "credential_scope_evidence_ref": ("credential-scope:example" if credential_scope_proven else None),
        "generated_at": "2026-08-22T05:43:00Z",
    }
    if credential_scope_proven:
        kwargs["dispatch_updated_at"] = "2026-08-22T05:41:00Z"
        kwargs["rollback_updated_at"] = "2026-08-22T05:42:00Z"
    return build_controlled_nonprod_report(**kwargs)


class ControlledNonProductionExecutionTests(unittest.TestCase):
    def test_target_scoped_control_can_pass_without_production_or_automation_authority(self) -> None:
        report = _build(credential_scope_proven=True)
        self.assertEqual(report["status"], STATUS_PASS)
        self.assertEqual(report["blockers"], [])
        self.assertFalse(report["production_execution_authorized"])
        self.assertTrue(report["non_production_execution_authorized"])
        self.assertFalse(report["automation_authorized"])
        self.assertFalse(report["pilot_authorized"])
        self.assertEqual(report["capability"]["class"], "GITHUB_PR_MUTATION")
        self.assertEqual(report["capability"]["operation"], "MARK_READY_FOR_REVIEW")
        self.assertEqual(report["capability"]["rollback_operation"], "CONVERT_TO_DRAFT")
        self.assertTrue(report["dispatch"]["attempted"])
        self.assertFalse(report["dispatch"]["suppressed"])
        self.assertTrue(report["dispatch"]["postcondition_verified"])
        self.assertTrue(report["rollback"]["postcondition_verified"])
        self.assertEqual(report["rollback"]["restoration_mode"], "ROLLBACK_VERIFIED")
        self.assertEqual(verify_controlled_nonprod_report_data(report), [])

    def test_unproven_credential_scope_suppresses_dispatch_and_is_the_only_blocker(self) -> None:
        report = _build(credential_scope_proven=False)
        self.assertEqual(report["status"], STATUS_BLOCKED)
        self.assertEqual(report["blockers"], ["TARGET_SCOPED_CREDENTIAL_NOT_PROVEN"])
        self.assertEqual(report["next_step"], "ESTABLISH_TARGET_SCOPED_NON_PRODUCTION_CREDENTIAL")
        self.assertFalse(report["dispatch"]["attempted"])
        self.assertTrue(report["dispatch"]["suppressed"])
        self.assertIsNone(report["dispatch"]["provider_response"])
        self.assertFalse(report["dispatch"]["postcondition_verified"])
        self.assertFalse(report["rollback"]["attempted"])
        self.assertTrue(report["rollback"]["final_target_state_restored"])
        self.assertEqual(report["rollback"]["restoration_mode"], "NO_DISPATCH_STATE_PRESERVED")
        self.assertEqual(verify_controlled_nonprod_report_data(report), [])

    def test_dispatch_attempt_with_unproven_credential_scope_is_rejected(self) -> None:
        report = _build(credential_scope_proven=False)
        tampered = deepcopy(report)
        tampered["dispatch"]["attempted"] = True
        tampered["dispatch"]["suppressed"] = False
        errors = verify_controlled_nonprod_report_data(tampered)
        self.assertTrue(any("pre-dispatch blocker must suppress" in error for error in errors))
        self.assertTrue(any("blockers projection mismatch" in error for error in errors))

    def test_production_authority_tamper_is_rejected(self) -> None:
        report = _build(credential_scope_proven=False)
        tampered = deepcopy(report)
        tampered["production_execution_authorized"] = True
        errors = verify_controlled_nonprod_report_data(tampered)
        self.assertTrue(any("production_execution_authorized" in error for error in errors))

    def test_preserved_target_head_tamper_is_rejected(self) -> None:
        report = _build(credential_scope_proven=False)
        tampered = deepcopy(report)
        tampered["rollback"]["postcondition_readback"]["head_sha"] = "3" * 40
        errors = verify_controlled_nonprod_report_data(tampered)
        self.assertTrue(any("preserved target state head_sha" in error for error in errors))

    def test_preserved_draft_state_tamper_is_rejected(self) -> None:
        report = _build(credential_scope_proven=False)
        tampered = deepcopy(report)
        tampered["rollback"]["postcondition_readback"]["draft"] = False
        errors = verify_controlled_nonprod_report_data(tampered)
        self.assertTrue(any("preserve the initial draft/open" in error for error in errors))

    def test_blocker_projection_tamper_is_rejected(self) -> None:
        report = _build(credential_scope_proven=False)
        tampered = deepcopy(report)
        tampered["blockers"] = []
        errors = verify_controlled_nonprod_report_data(tampered)
        self.assertTrue(any("blockers projection mismatch" in error for error in errors))

    def test_report_hash_tamper_is_rejected(self) -> None:
        report = _build(credential_scope_proven=False)
        tampered = deepcopy(report)
        tampered["report_sha256"] = "0" * 64
        errors = verify_controlled_nonprod_report_data(tampered)
        self.assertTrue(any("report_sha256 mismatch" in error for error in errors))

    def test_actual_peb3_evidence_is_fail_closed_at_credential_scope_blocker(self) -> None:
        report = json.loads(ACTUAL_EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(verify_controlled_nonprod_report_data(report), [])
        self.assertEqual(report["status"], STATUS_BLOCKED)
        self.assertEqual(report["blockers"], ["TARGET_SCOPED_CREDENTIAL_NOT_PROVEN"])
        self.assertEqual(report["target"]["resource_id"], "61")
        self.assertEqual(report["target"]["head_sha"], "39ba94c0b847017f1f9f8e315fdbb198c15b65b9")
        self.assertFalse(report["dispatch"]["attempted"])
        self.assertTrue(report["dispatch"]["suppressed"])
        self.assertTrue(report["rollback"]["final_target_state_restored"])

    def test_schema_asset_is_synchronized(self) -> None:
        source = ROOT / "schemas" / "controlled-nonprod-execution-calibration-report.schema.json"
        packaged = ROOT / "src" / "review_system" / "assets" / "schemas" / "controlled-nonprod-execution-calibration-report.schema.json"
        self.assertEqual(source.read_bytes(), packaged.read_bytes())


if __name__ == "__main__":
    unittest.main()

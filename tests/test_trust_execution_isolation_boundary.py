from __future__ import annotations

import unittest

from review_system.trust_execution_isolation_boundary import (
    BLOCKED_STATUS,
    CONTRACT_VERSION,
    MODE,
    READY_STATUS,
    assess_isolation_boundary,
    verify_isolation_boundary_assessment,
)


def ready_evidence() -> dict:
    repository = "gycha0109-beep/pie-peb3-calibration"
    return {
        "contract_version": CONTRACT_VERSION,
        "mode": MODE,
        "production_execution_authorized": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "dedicated_repository": {
            "exists": True,
            "full_name": repository,
            "calibration_only": True,
            "production_deployment": False,
            "production_secrets": False,
            "business_source_authority": False,
        },
        "credential": {
            "mechanism": "GITHUB_APP_INSTALLATION_TOKEN",
            "installation_identity_proven": True,
            "selected_repository_scope_proven": True,
            "repository_set": [repository],
            "token_repository_set_proven": True,
            "token_permission_set_proven": True,
            "bounded_validity_proven": True,
            "pie_repository_write_authority": False,
            "production_repository_write_authority": False,
        },
        "adapter": {
            "provider": "GITHUB",
            "repository": repository,
            "resource_type": "PULL_REQUEST",
            "exact_pr_binding": True,
            "exact_head_binding": True,
            "exact_precondition_binding": True,
            "allowed_operations": ["MARK_READY_FOR_REVIEW", "CONVERT_TO_DRAFT"],
            "arbitrary_command_surface": False,
            "arbitrary_api_surface": False,
            "merge_surface": False,
            "close_surface": False,
            "file_write_surface": False,
            "branch_write_surface": False,
            "workflow_write_surface": False,
            "secret_write_surface": False,
            "repository_settings_surface": False,
        },
        "provider_evidence": {
            "repository_metadata_readback": True,
            "installation_repository_set_readback": True,
            "token_permission_set_readback": True,
        },
    }


class TrustExecutionIsolationBoundaryTests(unittest.TestCase):
    def test_complete_boundary_is_ready_only_for_nonproduction_execution_review(self) -> None:
        result = assess_isolation_boundary(ready_evidence())
        self.assertEqual(result["status"], READY_STATUS)
        self.assertEqual(result["blockers"], [])
        self.assertTrue(result["formal_dispatch_permitted"])
        self.assertFalse(result["production_execution_authorized"])
        self.assertFalse(result["automation_authorized"])
        self.assertFalse(result["pilot_authorized"])

    def test_missing_repository_fails_closed(self) -> None:
        evidence = ready_evidence()
        evidence["dedicated_repository"]["exists"] = False
        result = assess_isolation_boundary(evidence)
        self.assertEqual(result["status"], BLOCKED_STATUS)
        self.assertIn("DEDICATED_NONPRODUCTION_REPOSITORY_NOT_ESTABLISHED", result["blockers"])
        self.assertFalse(result["formal_dispatch_permitted"])

    def test_repository_set_must_equal_dedicated_repository_only(self) -> None:
        evidence = ready_evidence()
        evidence["credential"]["repository_set"].append("gycha0109-beep/Project_Intelligence_Engine")
        result = assess_isolation_boundary(evidence)
        self.assertIn("SELECTED_REPOSITORY_GITHUB_APP_SCOPE_NOT_PROVEN", result["blockers"])

    def test_broad_connected_credential_is_rejected(self) -> None:
        evidence = ready_evidence()
        evidence["credential"].update(
            {
                "mechanism": "CONNECTED_GITHUB_ACCOUNT",
                "selected_repository_scope_proven": False,
                "repository_set": [
                    "gycha0109-beep/Project_Intelligence_Engine",
                    "gycha0109-beep/K_beauty",
                    "gycha0109-beep/BuildMap",
                ],
                "pie_repository_write_authority": True,
            }
        )
        result = assess_isolation_boundary(evidence)
        self.assertIn("SELECTED_REPOSITORY_GITHUB_APP_SCOPE_NOT_PROVEN", result["blockers"])
        self.assertIn("SHORT_LIVED_TOKEN_SCOPE_NOT_PROVEN", result["blockers"])
        self.assertFalse(result["formal_dispatch_permitted"])

    def test_arbitrary_api_or_command_surface_is_rejected(self) -> None:
        for field in ("arbitrary_command_surface", "arbitrary_api_surface"):
            with self.subTest(field=field):
                evidence = ready_evidence()
                evidence["adapter"][field] = True
                result = assess_isolation_boundary(evidence)
                self.assertIn("GOVERNED_ADAPTER_BINDING_NOT_READY", result["blockers"])

    def test_forbidden_mutation_surfaces_are_rejected(self) -> None:
        fields = (
            "merge_surface",
            "close_surface",
            "file_write_surface",
            "branch_write_surface",
            "workflow_write_surface",
            "secret_write_surface",
            "repository_settings_surface",
        )
        for field in fields:
            with self.subTest(field=field):
                evidence = ready_evidence()
                evidence["adapter"][field] = True
                result = assess_isolation_boundary(evidence)
                self.assertIn("GOVERNED_ADAPTER_BINDING_NOT_READY", result["blockers"])

    def test_allowed_operation_set_cannot_expand(self) -> None:
        evidence = ready_evidence()
        evidence["adapter"]["allowed_operations"].append("MERGE")
        result = assess_isolation_boundary(evidence)
        self.assertIn("GOVERNED_ADAPTER_BINDING_NOT_READY", result["blockers"])

    def test_provider_scope_readback_is_required(self) -> None:
        evidence = ready_evidence()
        evidence["provider_evidence"]["token_permission_set_readback"] = False
        result = assess_isolation_boundary(evidence)
        self.assertIn("AUTHORITATIVE_PROVIDER_SCOPE_EVIDENCE_INCOMPLETE", result["blockers"])

    def test_production_automation_and_pilot_authority_are_forbidden(self) -> None:
        cases = (
            ("production_execution_authorized", "PRODUCTION_EXECUTION_AUTHORITY_FORBIDDEN"),
            ("automation_authorized", "AUTOMATION_AUTHORITY_FORBIDDEN"),
            ("pilot_authorized", "PILOT_AUTHORITY_FORBIDDEN"),
        )
        for field, blocker in cases:
            with self.subTest(field=field):
                evidence = ready_evidence()
                evidence[field] = True
                result = assess_isolation_boundary(evidence)
                self.assertIn(blocker, result["blockers"])
                self.assertFalse(result["formal_dispatch_permitted"])

    def test_assessment_projection_is_deterministic_and_tamper_evident(self) -> None:
        evidence = ready_evidence()
        assessment = assess_isolation_boundary(evidence)
        self.assertTrue(verify_isolation_boundary_assessment(evidence, assessment))
        assessment["status"] = BLOCKED_STATUS
        self.assertFalse(verify_isolation_boundary_assessment(evidence, assessment))


if __name__ == "__main__":
    unittest.main()

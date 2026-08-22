from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import unittest

from review_system.trust_execution_shadow import (
    ExecutionShadowError,
    assess_adapter_descriptor,
    build_shadow_request,
    run_shadow_dry_run,
    verify_shadow_request_data,
    verify_shadow_run_data,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "1" * 40
SOURCE_SHA256 = "2" * 64
TRUST_SHA256 = "3" * 64
TARGET_FINGERPRINT = "4" * 64
ROLLBACK_SHA256 = "5" * 64
FIXTURE = ROOT / "tests" / "fixtures" / "trust-execution-shadow" / "calibration-v1.json"


def _request(payload: dict[str, object] | None = None) -> dict[str, object]:
    return build_shadow_request(
        project_id="synthetic-project",
        source_revision=SOURCE_REVISION,
        source_evidence_sha256=SOURCE_SHA256,
        trust_report_id="trust-report-synthetic",
        trust_report_sha256=TRUST_SHA256,
        trust_risk_model_version="1.5",
        trust_risk_band="R3",
        capability_class="DEPLOYMENT_PROMOTION",
        operation="promote-release",
        action_payload=payload or {"deployment_id": "dpl_test", "target": "production"},
        target_provider="synthetic-provider",
        target_account="account-a",
        target_resource="service-a",
        target_environment="production",
        target_precondition_fingerprint=TARGET_FINGERPRINT,
        rollback_evidence_ref="rollback-plan-1",
        rollback_evidence_sha256=ROLLBACK_SHA256,
        generated_at="2026-08-22T04:30:00Z",
    )


def _eligible_adapter() -> dict[str, object]:
    return {
        "adapter_id": "synthetic-explicit-deployment-adapter",
        "capability_classes": ["DEPLOYMENT_PROMOTION"],
        "arbitrary_command_surface": False,
        "target_binding_supported": True,
        "effect_receipt_supported": True,
        "postcondition_verifier_supported": True,
        "rollback_supported": True,
        "external_side_effects_enabled": False,
    }


class TrustExecutionShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_frozen_adapter_calibration_fixture_replays(self) -> None:
        current = deepcopy(self.fixture["observed_current_adapter"])
        expected_status = current.pop("expected_status")
        expected_blockers = current.pop("expected_blockers")
        result = assess_adapter_descriptor(current)
        self.assertEqual(result["status"], expected_status)
        self.assertEqual(result["blockers"], expected_blockers)

        synthetic = deepcopy(self.fixture["synthetic_explicit_adapter"])
        expected_status = synthetic.pop("expected_status")
        expected_blockers = synthetic.pop("expected_blockers")
        result = assess_adapter_descriptor(synthetic)
        self.assertEqual(result["status"], expected_status)
        self.assertEqual(result["blockers"], expected_blockers)

    def test_shadow_request_is_deterministic_and_never_authorizes_execution(self) -> None:
        first = _request({"b": 2, "a": 1})
        second = _request({"a": 1, "b": 2})
        self.assertEqual(first["request_id"], second["request_id"])
        self.assertEqual(first["report_sha256"], second["report_sha256"])
        self.assertEqual(first["status"], "SHADOW_CONTRACT_READY")
        self.assertFalse(first["production_execution_authorized"])
        self.assertFalse(first["external_side_effect_permitted"])
        self.assertFalse(first["execution"]["dispatch_attempted"])
        self.assertEqual(verify_shadow_request_data(first), [])

    def test_request_tamper_is_rejected(self) -> None:
        mutations = {
            "source revision": lambda value: value["source_binding"].__setitem__("revision", "9" * 40),
            "target fingerprint": lambda value: value["target"].__setitem__("precondition_fingerprint", "8" * 64),
            "action payload": lambda value: value["action"]["payload"].__setitem__("target", "staging"),
            "authorization": lambda value: value["authorization"].__setitem__("authorized", True),
            "execution state": lambda value: value["execution"].__setitem__("dispatch_attempted", True),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = deepcopy(_request())
                mutate(candidate)
                self.assertTrue(verify_shadow_request_data(candidate))

    def test_arbitrary_capability_is_rejected_before_contract_materialization(self) -> None:
        with self.assertRaises(ExecutionShadowError):
            build_shadow_request(
                project_id="synthetic-project",
                source_revision=SOURCE_REVISION,
                source_evidence_sha256=SOURCE_SHA256,
                trust_report_id="trust-report-synthetic",
                trust_report_sha256=TRUST_SHA256,
                trust_risk_model_version="1.5",
                trust_risk_band="R3",
                capability_class="ARBITRARY_SHELL",
                operation="run-anything",
                action_payload={"command": "echo unsafe"},
                target_provider="synthetic-provider",
                target_account="account-a",
                target_resource="service-a",
                target_environment="production",
                target_precondition_fingerprint=TARGET_FINGERPRINT,
                rollback_evidence_ref="rollback-plan-1",
                rollback_evidence_sha256=ROLLBACK_SHA256,
                generated_at="2026-08-22T04:30:00Z",
            )

    def test_generic_github_cli_shape_is_not_an_eligible_governed_adapter(self) -> None:
        assessment = assess_adapter_descriptor({
            "adapter_id": "github-cli-generic",
            "capability_classes": ["GITHUB_PR_MUTATION"],
            "arbitrary_command_surface": True,
            "target_binding_supported": False,
            "effect_receipt_supported": False,
            "postcondition_verifier_supported": False,
            "rollback_supported": False,
            "external_side_effects_enabled": True,
        })
        self.assertEqual(assessment["status"], "NOT_ELIGIBLE_FOR_GOVERNED_EXECUTION_ADAPTER")
        self.assertIn("ARBITRARY_COMMAND_SURFACE_FORBIDDEN", assessment["blockers"])
        self.assertIn("EXACT_TARGET_BINDING_REQUIRED", assessment["blockers"])
        self.assertIn("EFFECT_RECEIPT_REQUIRED", assessment["blockers"])
        self.assertIn("POSTCONDITION_VERIFIER_REQUIRED", assessment["blockers"])
        self.assertIn("ROLLBACK_CAPABILITY_REQUIRED", assessment["blockers"])
        self.assertIn("SHADOW_ADAPTER_MUST_DISABLE_EXTERNAL_SIDE_EFFECTS", assessment["blockers"])

    def test_explicit_side_effect_disabled_adapter_is_shadow_eligible(self) -> None:
        assessment = assess_adapter_descriptor(_eligible_adapter())
        self.assertEqual(assessment["blockers"], [])
        self.assertEqual(
            assessment["status"],
            "ELIGIBLE_FOR_CONTROLLED_NON_PRODUCTION_IMPLEMENTATION_REVIEW",
        )

    def test_passing_shadow_dry_run_stops_at_dispatch_suppressed(self) -> None:
        report = run_shadow_dry_run(
            _request(),
            adapter_descriptor=_eligible_adapter(),
            observed_source_revision=SOURCE_REVISION,
            observed_target_precondition_fingerprint=TARGET_FINGERPRINT,
            synthetic_authorization=True,
            generated_at="2026-08-22T04:31:00Z",
        )
        self.assertEqual(report["status"], "SHADOW_CALIBRATION_PASS")
        self.assertEqual(report["next_step"], "CONTROLLED_NON_PRODUCTION_EXECUTION_REQUIRED")
        self.assertEqual(
            report["trace"],
            ["PREPARED", "SHADOW_AUTHORIZED", "PRECONDITIONS_VERIFIED", "DISPATCH_SUPPRESSED"],
        )
        self.assertFalse(report["dispatch_attempted"])
        self.assertFalse(report["external_effect_observed"])
        self.assertIsNone(report["effect_receipt"])
        self.assertFalse(report["postcondition_verified"])
        self.assertFalse(report["rollback_dispatch_attempted"])
        self.assertEqual(verify_shadow_run_data(report), [])

    def test_shadow_negative_matrix_fails_closed_without_dispatch(self) -> None:
        cases = [
            ("source drift", dict(observed_source_revision="6" * 40), "EXACT_SOURCE_REVISION"),
            ("target drift", dict(observed_target_precondition_fingerprint="7" * 64), "EXACT_TARGET_PRECONDITION"),
            ("authorization absent", dict(synthetic_authorization=False), "SYNTHETIC_AUTHORIZATION_PRESENT"),
            ("kill switch", dict(kill_switch_active=True), "KILL_SWITCH_CLEAR"),
            ("rollback unavailable", dict(rollback_evidence_available=False), "ROLLBACK_EVIDENCE_AVAILABLE"),
        ]
        for label, override, expected_blocker in cases:
            with self.subTest(label=label):
                kwargs = {
                    "adapter_descriptor": _eligible_adapter(),
                    "observed_source_revision": SOURCE_REVISION,
                    "observed_target_precondition_fingerprint": TARGET_FINGERPRINT,
                    "synthetic_authorization": True,
                    "kill_switch_active": False,
                    "rollback_evidence_available": True,
                    "generated_at": "2026-08-22T04:31:00Z",
                }
                kwargs.update(override)
                report = run_shadow_dry_run(_request(), **kwargs)
                self.assertEqual(report["status"], "SHADOW_CALIBRATION_BLOCKED")
                self.assertEqual(report["trace"][-1], "BLOCKED")
                self.assertIn(expected_blocker, report["calibration_blockers"])
                self.assertFalse(report["dispatch_attempted"])
                self.assertFalse(report["external_effect_observed"])
                self.assertEqual(verify_shadow_run_data(report), [])

    def test_adapter_must_support_requested_capability(self) -> None:
        adapter = _eligible_adapter()
        adapter["capability_classes"] = ["GITHUB_PR_MUTATION"]
        report = run_shadow_dry_run(
            _request(),
            adapter_descriptor=adapter,
            observed_source_revision=SOURCE_REVISION,
            observed_target_precondition_fingerprint=TARGET_FINGERPRINT,
            synthetic_authorization=True,
            generated_at="2026-08-22T04:31:00Z",
        )
        self.assertEqual(report["status"], "SHADOW_CALIBRATION_BLOCKED")
        self.assertIn("REQUESTED_CAPABILITY_SUPPORTED", report["calibration_blockers"])
        self.assertFalse(report["dispatch_attempted"])

    def test_run_tamper_cannot_claim_dispatch_or_effect(self) -> None:
        report = run_shadow_dry_run(
            _request(),
            adapter_descriptor=_eligible_adapter(),
            observed_source_revision=SOURCE_REVISION,
            observed_target_precondition_fingerprint=TARGET_FINGERPRINT,
            synthetic_authorization=True,
            generated_at="2026-08-22T04:31:00Z",
        )
        for field, value in (
            ("dispatch_attempted", True),
            ("external_effect_observed", True),
            ("postcondition_verified", True),
            ("rollback_dispatch_attempted", True),
        ):
            with self.subTest(field=field):
                candidate = deepcopy(report)
                candidate[field] = value
                self.assertTrue(verify_shadow_run_data(candidate))

    def test_adapter_assessment_tamper_is_rejected(self) -> None:
        report = run_shadow_dry_run(
            _request(),
            adapter_descriptor=_eligible_adapter(),
            observed_source_revision=SOURCE_REVISION,
            observed_target_precondition_fingerprint=TARGET_FINGERPRINT,
            synthetic_authorization=True,
            generated_at="2026-08-22T04:31:00Z",
        )
        candidate = deepcopy(report)
        candidate["adapter_assessment"]["status"] = "NOT_ELIGIBLE_FOR_GOVERNED_EXECUTION_ADAPTER"
        self.assertTrue(verify_shadow_run_data(candidate))

    def test_shadow_module_has_no_external_execution_dependency(self) -> None:
        import review_system.trust_execution_shadow as module

        source = Path(module.__file__).read_text(encoding="utf-8").lower()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("githubcli", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib", source)

    def test_schema_assets_are_frozen_in_sync(self) -> None:
        for name in (
            "production-execution-shadow-request.schema.json",
            "production-execution-shadow-run.schema.json",
        ):
            self.assertEqual(
                (ROOT / "schemas" / name).read_bytes(),
                (ROOT / "src" / "review_system" / "assets" / "schemas" / name).read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()

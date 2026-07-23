import unittest

from review_system.gate import (
    UnsafeExpression,
    calculate_gate,
    calculate_gate_from_run,
    derive_finding_metrics,
    evaluate_expression,
)
from review_system.io import load_data
from review_system.paths import asset
from tests.helpers import finding


class GateTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_data(asset("core/default-gate-policy.yml"))
        self.base = {
            "open_confirmed_p0": 0,
            "open_confirmed_p1": 0,
            "open_supported_p1": 0,
            "baseline_test_status": "passed",
            "protected_baseline_modified": False,
            "required_integration_test_not_run": False,
            "migration_replay_required": False,
            "migration_replay_verified": False,
            "accepted_residual_risk_count": 0,
            "required_runtime_evidence_missing": False,
            "required_tests_passed": True,
        }

    def test_pass_with_legacy_metrics(self):
        self.assertEqual("PASS", calculate_gate(self.base, self.policy)["decision"])

    def test_confirmed_p1_holds(self):
        metrics = dict(self.base, open_confirmed_p1=1)
        self.assertEqual("HOLD", calculate_gate(metrics, self.policy)["decision"])

    def test_confirmed_p0_fails(self):
        metrics = dict(self.base, open_confirmed_p0=1)
        self.assertEqual("FAIL", calculate_gate(metrics, self.policy)["decision"])

    def test_expression_rejects_calls(self):
        with self.assertRaises(UnsafeExpression):
            evaluate_expression("__import__('os')", self.base)

    def test_accepted_finding_is_residual_risk_not_open_blocker(self):
        accepted = finding(
            severity="P1",
            confidence="CONFIRMED",
            status="ACCEPTED",
            acceptance={"reason": "Deferred by owner", "owner": "team", "review_by": "2026-12-01"},
        )
        metrics = derive_finding_metrics([accepted])
        self.assertEqual(0, metrics["open_confirmed_p1"])
        self.assertEqual(1, metrics["accepted_residual_risk_count"])

    def test_fixed_but_unverified_blocker_holds(self):
        fixed = finding(severity="P1", confidence="CONFIRMED", status="FIXED")
        metrics = derive_finding_metrics([fixed])
        self.assertEqual(1, metrics["fixed_unverified_blockers"])
        effective = {**self.base, **metrics}
        self.assertEqual("HOLD", calculate_gate(effective, self.policy)["decision"])

    def test_block_on_p2_is_respected(self):
        p2 = finding(severity="P2", confidence="CONFIRMED", status="OPEN")
        metrics = derive_finding_metrics([p2], block_on=["P0", "P1", "P2"])
        self.assertEqual(1, metrics["open_confirmed_blocking_hold"])

    def test_run_uses_derived_metrics_and_reports_discrepancy(self):
        run = {
            "run_id": "r1",
            "project_id": "p1",
            "mode": "full",
            "gate_config": {"block_on": ["P0", "P1"]},
            "metrics": dict(self.base, open_confirmed_p1=0),
            "findings": [finding(
                severity="P1",
                confidence="CONFIRMED",
                status="OPEN",
                evidence=[{
                    "level": "E3", "type": "test", "command": "pytest",
                    "result": "failed", "summary": "Reproduced failure."
                }],
                reproduction={"steps": ["run"], "observed": "bad", "expected": "good"},
                verification=["pytest"],
            )],
        }
        result = calculate_gate_from_run(run, self.policy)
        self.assertEqual("HOLD", result["decision"])
        self.assertIn("open_confirmed_p1", result["metric_discrepancies"])

class GatePolicyValidationTests(unittest.TestCase):
    def test_duplicate_rule_ids_are_rejected(self):
        policy = {
            "fail": [{"id": "DUP", "expression": "false", "message": "x"}],
            "hold": [{"id": "DUP", "expression": "false", "message": "y"}],
            "conditional_pass": [],
            "pass": [{"id": "PASS", "expression": "true", "message": "ok"}],
        }
        with self.assertRaises(ValueError):
            calculate_gate({}, policy)

    def test_policy_without_pass_prerequisite_is_rejected(self):
        policy = {"fail": [], "hold": [], "conditional_pass": [], "pass": []}
        with self.assertRaises(ValueError):
            calculate_gate({}, policy)

if __name__ == "__main__":
    unittest.main()

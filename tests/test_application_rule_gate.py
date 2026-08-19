import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from review_system.application import (
    ApproveRuleRequest,
    ApproveRuleResult,
    CalculateGateRequest,
    CalculateGateResult,
    ReviewRunValidationError,
    approve_rule,
    calculate_review_gate,
)
from review_system.cli import main
from review_system.intelligence_config import load_rules
from review_system.intelligence_learning import discover_rule_candidates
from review_system.io import dump_json, dump_yaml, load_data


class ApproveRuleApplicationTests(unittest.TestCase):
    def _rule_files(self, root: Path) -> tuple[Path, Path, str]:
        candidates = discover_rule_candidates(
            [
                {"id": "1", "changed_files": ["src/a/x.ts", "src/b/y.ts"]},
                {"id": "2", "changed_files": ["src/a/z.ts", "src/b/q.ts"]},
                {"id": "3", "changed_files": ["src/a/m.ts", "src/b/n.ts"]},
            ],
            min_samples=3,
            min_confidence=0.75,
            min_support=0.5,
        )
        candidates_path = root / "candidates.yml"
        approved_path = root / "approved.yml"
        dump_yaml(candidates_path, candidates)
        dump_yaml(approved_path, {"schema_version": "1.0", "rules": []})
        return candidates_path, approved_path, candidates["rules"][0]["id"]

    def test_direct_approval_updates_both_files_and_preserves_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates_path, approved_path, rule_id = self._rule_files(root)

            result = approve_rule(
                ApproveRuleRequest(
                    candidates=candidates_path,
                    approved=approved_path,
                    rule_id=rule_id,
                    approved_by="maintainer",
                    approved_at="2026-07-23T00:00:00Z",
                    rationale="Validated against review history.",
                )
            )

            candidates = load_rules(candidates_path)
            approved = load_rules(approved_path, required_status="approved")
            self.assertEqual(rule_id, result.rule_id)
            self.assertEqual("approved", candidates["rules"][0]["status"])
            self.assertEqual("approved", approved["rules"][0]["status"])
            self.assertEqual("maintainer", approved["rules"][0]["approval"]["approved_by"])
            self.assertEqual(
                "Validated against review history.",
                approved["rules"][0]["approval"]["rationale"],
            )

    def test_failed_approval_does_not_modify_either_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates_path, approved_path, _ = self._rule_files(root)
            candidate_before = candidates_path.read_bytes()
            approved_before = approved_path.read_bytes()

            with self.assertRaises(ValueError):
                approve_rule(
                    ApproveRuleRequest(
                        candidates=candidates_path,
                        approved=approved_path,
                        rule_id="missing-rule",
                        approved_by="maintainer",
                    )
                )

            self.assertEqual(candidate_before, candidates_path.read_bytes())
            self.assertEqual(approved_before, approved_path.read_bytes())

    def test_approval_request_is_immutable(self):
        request = ApproveRuleRequest(
            candidates="candidates.yml",
            approved="approved.yml",
            rule_id="RULE-1",
            approved_by="maintainer",
        )
        with self.assertRaises(FrozenInstanceError):
            request.rule_id = "RULE-2"

    def test_cli_maps_rule_approval_arguments(self):
        result = ApproveRuleResult(
            rule_id="RULE-1",
            candidates_path=Path("candidates.yml"),
            approved_path=Path("approved.yml"),
            candidates={"rules": []},
            approved={"rules": []},
        )
        with (
            patch("review_system.cli.approve_rule", return_value=result) as use_case,
            redirect_stdout(io.StringIO()),
        ):
            code = main(
                [
                    "approve-rule",
                    "--candidates",
                    "candidates.yml",
                    "--approved",
                    "approved.yml",
                    "--rule-id",
                    "RULE-1",
                    "--approved-by",
                    "maintainer",
                    "--approved-at",
                    "2026-07-23T00:00:00Z",
                    "--rationale",
                    "Reviewed.",
                ]
            )

        self.assertEqual(0, code)
        request = use_case.call_args.args[0]
        self.assertEqual("candidates.yml", request.candidates)
        self.assertEqual("approved.yml", request.approved)
        self.assertEqual("RULE-1", request.rule_id)
        self.assertEqual("maintainer", request.approved_by)
        self.assertEqual("2026-07-23T00:00:00Z", request.approved_at)
        self.assertEqual("Reviewed.", request.rationale)


class CalculateGateApplicationTests(unittest.TestCase):
    def test_direct_gate_calculation_writes_requested_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "gate.json"
            result = calculate_review_gate(
                CalculateGateRequest(
                    run="examples/review-run.sample.json",
                    output=output,
                )
            )

            self.assertEqual(result.gate, load_data(output))
            self.assertEqual(output, result.output_path)
            self.assertIn(result.gate["decision"], {"PASS", "CONDITIONAL_PASS", "HOLD", "FAIL"})

    def test_invalid_review_run_raises_typed_error_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_path = root / "run.json"
            output = root / "gate.json"
            dump_json(run_path, {})

            with self.assertRaises(ReviewRunValidationError) as caught:
                calculate_review_gate(CalculateGateRequest(run=run_path, output=output))

            self.assertTrue(caught.exception.errors)
            self.assertFalse(output.exists())

    def test_gate_request_is_immutable(self):
        request = CalculateGateRequest(run="run.json")
        with self.assertRaises(FrozenInstanceError):
            request.trust_metrics = True

    def test_gate_pass_maps_to_zero_and_preserves_stdout_json(self):
        gate = {"decision": "PASS", "reasons": []}
        result = CalculateGateResult(gate=gate, output_path=None)
        stdout = io.StringIO()
        with (
            patch("review_system.cli.calculate_review_gate", return_value=result) as use_case,
            redirect_stdout(stdout),
        ):
            code = main(
                [
                    "calculate-gate",
                    "run.json",
                    "--policy",
                    "policy.yml",
                    "--output",
                    "gate.json",
                    "--trust-metrics",
                ]
            )

        self.assertEqual(0, code)
        request = use_case.call_args.args[0]
        self.assertEqual("run.json", request.run)
        self.assertEqual("policy.yml", request.policy)
        self.assertEqual("gate.json", request.output)
        self.assertTrue(request.trust_metrics)
        self.assertEqual(gate, json.loads(stdout.getvalue()))

    def test_gate_hold_maps_to_three(self):
        result = CalculateGateResult(gate={"decision": "HOLD"}, output_path=None)
        with (
            patch("review_system.cli.calculate_review_gate", return_value=result),
            redirect_stdout(io.StringIO()),
        ):
            code = main(["calculate-gate", "run.json"])
        self.assertEqual(3, code)

    def test_gate_validation_error_preserves_cli_error_format(self):
        stderr = io.StringIO()
        with (
            patch(
                "review_system.cli.calculate_review_gate",
                side_effect=ReviewRunValidationError(["run_id is required", "project_id is required"]),
            ),
            redirect_stderr(stderr),
        ):
            code = main(["calculate-gate", "run.json"])

        self.assertEqual(2, code)
        self.assertEqual(
            ["ERROR run_id is required", "ERROR project_id is required"],
            stderr.getvalue().splitlines(),
        )


if __name__ == "__main__":
    unittest.main()

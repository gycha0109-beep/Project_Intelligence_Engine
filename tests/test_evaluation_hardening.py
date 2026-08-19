import copy
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from review_system.evaluation import (
    EvaluationError,
    _set_counts,
    attach_evaluation_to_candidate,
    canonical_json_sha256,
    load_evaluation_dataset,
    run_evaluation,
    verify_evaluation_report_data,
    write_evaluation_report,
)
from review_system.evaluation_cli import main as evaluation_main
from review_system.io import dump_json, dump_yaml, load_data
from test_evaluation import EvaluationFixture


class EvaluationHardeningTests(unittest.TestCase):
    def test_no_holdout_cannot_pass_approval_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            dataset = load_data(fixture.dataset)
            dataset["cases"] = [
                case for case in dataset["cases"] if case["split"] != "holdout"
            ]
            dump_yaml(fixture.dataset, dataset)
            report = run_evaluation(
                fixture.dataset,
                fixture.baseline,
                fixture.challenger,
            )
            self.assertEqual("FAIL", report["gate"]["decision"])
            self.assertIn("holdout_present", report["gate"]["failed_conditions"])

    def test_dataset_paths_are_normalized_before_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            dataset = load_data(fixture.dataset)
            for case in dataset["cases"]:
                case["expected_changed_scope"] = [
                    value.replace("/", "\\")
                    for value in case["expected_changed_scope"]
                ]
                case["input_artifacts"]["graph"] = case["input_artifacts"]["graph"].replace("/", "\\")
            dump_yaml(fixture.dataset, dataset)
            _, normalized = load_evaluation_dataset(fixture.dataset)
            self.assertIn("src/a.py", normalized["cases"][0]["expected_changed_scope"])
            report = run_evaluation(
                fixture.dataset,
                fixture.baseline,
                fixture.challenger,
            )
            self.assertEqual("PASS", report["gate"]["decision"])

    def test_evaluator_contract_participates_in_evaluation_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            report = run_evaluation(fixture.dataset, fixture.baseline, fixture.challenger)
            self.assertEqual(
                "review_system.intelligence_impact.analyze_change",
                report["evaluator"]["name"],
            )
            tampered = copy.deepcopy(report)
            tampered["evaluator"]["contract_version"] = "2.0"
            payload = copy.deepcopy(tampered)
            payload.pop("report_sha256")
            tampered["report_sha256"] = canonical_json_sha256(payload)
            self.assertIn("evaluation_id mismatch", verify_evaluation_report_data(tampered))

    def test_duplicate_case_id_and_invalid_policy_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            dataset = load_data(fixture.dataset)
            dataset["cases"][1]["case_id"] = dataset["cases"][0]["case_id"]
            dump_yaml(fixture.dataset, dataset)
            with self.assertRaises(EvaluationError):
                load_evaluation_dataset(fixture.dataset)

            fixture = EvaluationFixture(Path(tmp))
            invalid_policy = load_data(fixture.challenger)
            invalid_policy["rules"][0]["status"] = "candidate"
            dump_yaml(fixture.challenger, invalid_policy)
            with self.assertRaises(EvaluationError):
                run_evaluation(
                    fixture.dataset,
                    fixture.baseline,
                    fixture.challenger,
                )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink is unavailable")
    def test_symlink_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            fixture = EvaluationFixture(Path(tmp))
            external = Path(outside) / "graph.json"
            external.write_bytes(fixture.graph.read_bytes())
            linked = fixture.root / "linked-graph.json"
            try:
                linked.symlink_to(external)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            dataset = load_data(fixture.dataset)
            dataset["cases"][0]["input_artifacts"]["graph"] = linked.name
            dump_yaml(fixture.dataset, dataset)
            with self.assertRaises(EvaluationError):
                load_evaluation_dataset(fixture.dataset)

    def test_zero_denominator_metric_rule(self):
        self.assertEqual(
            {"tp": 0, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0},
            _set_counts([], []),
        )
        self.assertEqual(0.0, _set_counts(["expected"], [])["precision"])
        self.assertEqual(0.0, _set_counts([], ["unexpected"])["recall"])

    def test_repeatability_mismatch_is_a_hard_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            counter = {"value": 0}

            def nondeterministic(*args, **kwargs):
                counter["value"] += 1
                outcome = {
                    "changed_scope": ["src/a.py", "src/b.py"],
                    "selected_packs": [],
                    "required_tests": [],
                    "matched_rules": [],
                    "protected_result": "PASS",
                    "protected_reasons": [],
                    "nonce": counter["value"] % 2,
                }
                outcome["outcome_sha256"] = canonical_json_sha256(outcome)
                return outcome

            with patch("review_system.evaluation._run_case", side_effect=nondeterministic):
                report = run_evaluation(
                    fixture.dataset,
                    fixture.baseline,
                    fixture.challenger,
                )
            self.assertEqual("FAIL", report["gate"]["decision"])
            self.assertFalse(report["repeatability"]["baseline"])
            self.assertFalse(report["repeatability"]["challenger"])
            self.assertIn("repeatability", report["gate"]["failed_conditions"])
            self.assertEqual([], verify_evaluation_report_data(report))

    def test_rehashed_outcome_tamper_still_fails_metric_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            report = run_evaluation(fixture.dataset, fixture.baseline, fixture.challenger)
            tampered = copy.deepcopy(report)
            outcome = tampered["cases"][0]["challenger"]
            outcome["changed_scope"].append("src/extra.py")
            outcome_payload = copy.deepcopy(outcome)
            outcome_payload.pop("outcome_sha256")
            outcome["outcome_sha256"] = canonical_json_sha256(outcome_payload)
            report_payload = copy.deepcopy(tampered)
            report_payload.pop("report_sha256")
            tampered["report_sha256"] = canonical_json_sha256(report_payload)
            errors = verify_evaluation_report_data(tampered)
            self.assertIn("metrics mismatch", errors)

    def test_atomic_report_failure_preserves_existing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            report = run_evaluation(fixture.dataset, fixture.baseline, fixture.challenger)
            fixture.report.write_text("previous\n", encoding="utf-8")
            with patch("review_system.evaluation.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    write_evaluation_report(fixture.report, report)
            self.assertEqual("previous\n", fixture.report.read_text(encoding="utf-8"))
            self.assertEqual([], list(fixture.root.glob("report.json.*.tmp")))

    def test_atomic_attach_failure_preserves_candidate_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            report = run_evaluation(fixture.dataset, fixture.baseline, fixture.challenger)
            write_evaluation_report(fixture.report, report)
            before = fixture.candidates.read_bytes()
            with patch("review_system.evaluation.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    attach_evaluation_to_candidate(
                        fixture.candidates,
                        "RULE_EVAL_GOOD",
                        fixture.report,
                    )
            self.assertEqual(before, fixture.candidates.read_bytes())
            self.assertEqual([], list(fixture.root.glob("candidates.yml.*.tmp")))

    def test_valid_fail_report_verify_cli_returns_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            dataset = load_data(fixture.dataset)
            for case in dataset["cases"]:
                case["configured_packs"] = []
                case["expected_changed_scope"] = ["src/a.py", "src/b.py"]
                case["expected_packs"] = []
                case["expected_tests"] = []
            dump_yaml(fixture.dataset, dataset)
            report = run_evaluation(
                fixture.dataset,
                fixture.baseline,
                fixture.bad_challenger,
            )
            write_evaluation_report(fixture.report, report)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    3,
                    evaluation_main(["verify-report", str(fixture.report)]),
                )

    def test_tampered_report_cannot_be_attached(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            report = run_evaluation(fixture.dataset, fixture.baseline, fixture.challenger)
            write_evaluation_report(fixture.report, report)
            tampered = load_data(fixture.report)
            tampered["gate"]["decision"] = "FAIL"
            dump_json(fixture.report, tampered)
            before = fixture.candidates.read_bytes()
            with self.assertRaises(EvaluationError):
                attach_evaluation_to_candidate(
                    fixture.candidates,
                    "RULE_EVAL_GOOD",
                    fixture.report,
                )
            self.assertEqual(before, fixture.candidates.read_bytes())


if __name__ == "__main__":
    unittest.main()

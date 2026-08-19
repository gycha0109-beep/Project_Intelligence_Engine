import copy
import io
import tempfile
import unittest
import warnings
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from pathlib import Path

from review_system.application import (
    ApproveRuleRequest,
    EvaluatePolicyRequest,
    approve_rule,
    evaluate_policy,
)
from review_system.evaluation import (
    EvaluationError,
    EvaluationGateError,
    attach_evaluation_to_candidate,
    canonical_json_sha256,
    load_evaluation_dataset,
    run_evaluation,
    verify_evaluation_report_data,
    write_evaluation_report,
)
from review_system.evaluation_cli import main as evaluation_main
from review_system.intelligence_config import load_rules
from review_system.intelligence_graph import calculate_graph_sha256
from review_system.io import dump_json, dump_yaml, load_data


class EvaluationFixture:
    def __init__(self, root: Path):
        self.root = root
        self.graph = root / "graph.json"
        self.changed = root / "changed.txt"
        self.dataset = root / "dataset.yml"
        self.baseline = root / "baseline.yml"
        self.challenger = root / "challenger.yml"
        self.bad_challenger = root / "bad-challenger.yml"
        self.report = root / "report.json"
        self.candidates = root / "candidates.yml"
        self.approved = root / "approved.yml"
        self._write_graph()
        self.changed.write_text("src/a.py\n", encoding="utf-8")
        self._write_policies()
        self._write_dataset()
        self._write_candidates()

    def _write_graph(self):
        graph = {
            "schema_version": "1.0",
            "repository": {"root": "."},
            "nodes": [
                {
                    "id": "file:src/a.py",
                    "type": "file",
                    "path": "src/a.py",
                    "language": "python",
                    "size_bytes": 1,
                    "sha256": "a" * 64,
                },
                {
                    "id": "file:src/b.py",
                    "type": "file",
                    "path": "src/b.py",
                    "language": "python",
                    "size_bytes": 1,
                    "sha256": "b" * 64,
                },
                {
                    "id": "file:tests/test_b.py",
                    "type": "file",
                    "path": "tests/test_b.py",
                    "language": "python",
                    "size_bytes": 1,
                    "sha256": "c" * 64,
                },
            ],
            "edges": [
                {
                    "source": "file:src/b.py",
                    "target": "file:src/a.py",
                    "type": "imports",
                }
            ],
            "stats": {
                "files": 3,
                "symbols": 0,
                "components": 0,
                "database_objects": 0,
                "edges": 1,
            },
            "warnings": [],
        }
        graph["graph_sha256"] = calculate_graph_sha256(graph)
        dump_json(self.graph, graph)

    @staticmethod
    def _approved_rule(rule_id, *, pack=None, impact_path=None, required_test=None):
        return {
            "id": rule_id,
            "title": rule_id,
            "status": "approved",
            "trigger": {"paths_any": ["src/a.py"]},
            "impact": {
                "components": [],
                "paths": [impact_path] if impact_path else [],
            },
            "review": {
                "packs": [pack] if pack else [],
                "required_tests": [required_test] if required_test else [],
            },
            "rationale": "fixture",
            "approval": {
                "approved_by": "fixture",
                "approved_at": "2026-07-24T00:00:00Z",
            },
        }

    def _write_policies(self):
        dump_yaml(self.baseline, {"schema_version": "1.0", "rules": []})
        dump_yaml(
            self.challenger,
            {
                "schema_version": "1.0",
                "rules": [
                    self._approved_rule(
                        "RULE_EVAL_GOOD",
                        pack="universal.architecture",
                        impact_path="tests/test_b.py",
                        required_test="custom-check",
                    )
                ],
            },
        )
        dump_yaml(
            self.bad_challenger,
            {
                "schema_version": "1.0",
                "rules": [self._approved_rule("RULE_EVAL_BAD", pack="data.rls")],
            },
        )

    def _write_dataset(self):
        cases = []
        for split in ("development", "validation", "holdout"):
            cases.append(
                {
                    "case_id": f"CASE-{split.upper()}",
                    "repository": "example/repo",
                    "source_revision": f"git:{'1' * 40}",
                    "split": split,
                    "input_artifacts": {
                        "graph": self.graph.name,
                        "changed_files": self.changed.name,
                    },
                    "configured_packs": ["universal.architecture"],
                    "expected_changed_scope": [
                        "src/a.py",
                        "src/b.py",
                        "tests/test_b.py",
                    ],
                    "expected_packs": ["universal.architecture"],
                    "expected_tests": ["custom-check", "tests/test_b.py"],
                    "expected_protected_result": "PASS",
                    "labels": ["human-reviewed"],
                    "provenance": {
                        "source": "fixture",
                        "labeled_by": "reviewer",
                        "labeled_at": "2026-07-24",
                    },
                }
            )
        dump_yaml(
            self.dataset,
            {
                "schema_version": "1.0",
                "dataset_id": "fixture-dataset",
                "cases": cases,
            },
        )

    def _write_candidates(self):
        dump_yaml(
            self.candidates,
            {
                "schema_version": "1.0",
                "rules": [
                    {
                        "id": "RULE_EVAL_GOOD",
                        "title": "Candidate",
                        "status": "candidate",
                        "trigger": {"paths_any": ["src/a.py"]},
                        "impact": {
                            "components": [],
                            "paths": ["tests/test_b.py"],
                        },
                        "review": {
                            "packs": ["universal.architecture"],
                            "required_tests": ["custom-check"],
                        },
                        "rationale": "fixture",
                        "evidence": {"sample_count": 3},
                    }
                ],
            },
        )
        dump_yaml(self.approved, {"schema_version": "1.0", "rules": []})


class EvaluationLabTests(unittest.TestCase):
    def test_dataset_validation_and_path_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            source, data = load_evaluation_dataset(fixture.dataset)
            self.assertEqual(fixture.dataset, source)
            self.assertEqual(3, len(data["cases"]))

            unsafe = load_data(fixture.dataset)
            unsafe["cases"][0]["input_artifacts"]["graph"] = "../graph.json"
            dump_yaml(fixture.dataset, unsafe)
            with self.assertRaises(EvaluationError):
                load_evaluation_dataset(fixture.dataset)

    def test_challenger_report_is_deterministic_and_passes_holdout_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            first = run_evaluation(
                fixture.dataset,
                fixture.baseline,
                fixture.challenger,
                min_precision=1.0,
                min_recall=1.0,
            )
            second = run_evaluation(
                fixture.dataset,
                fixture.baseline,
                fixture.challenger,
                min_precision=1.0,
                min_recall=1.0,
            )
            self.assertEqual(first, second)
            self.assertEqual("PASS", first["gate"]["decision"])
            self.assertEqual(
                1.0,
                first["metrics"]["overall"]["challenger"]["combined"]["precision"],
            )
            self.assertEqual(
                1.0,
                first["metrics"]["holdout"]["challenger"]["combined"]["recall"],
            )
            self.assertGreater(first["comparison"]["combined_recall_delta"], 0)
            self.assertEqual([], verify_evaluation_report_data(first))

    def test_same_policy_has_zero_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            report = run_evaluation(
                fixture.dataset,
                fixture.challenger,
                fixture.challenger,
            )
            self.assertEqual(0.0, report["comparison"]["combined_precision_delta"])
            self.assertEqual(0.0, report["comparison"]["combined_recall_delta"])
            self.assertEqual([], report["comparison"]["changed_cases"])

    def test_protected_negative_regression_fails_gate(self):
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
            self.assertEqual("FAIL", report["gate"]["decision"])
            self.assertEqual(
                3,
                len(report["comparison"]["protected_negative_regressions"]),
            )
            self.assertIn(
                "protected_negative_regressions",
                report["gate"]["failed_conditions"],
            )

    def test_report_tamper_is_detected_even_after_outer_hash_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            report = run_evaluation(fixture.dataset, fixture.baseline, fixture.challenger)
            tampered = copy.deepcopy(report)
            tampered["metrics"]["overall"]["challenger"]["combined"]["tp"] += 1
            payload = copy.deepcopy(tampered)
            payload.pop("report_sha256")
            tampered["report_sha256"] = canonical_json_sha256(payload)
            errors = verify_evaluation_report_data(tampered)
            self.assertIn("metrics mismatch", errors)

    def test_application_writes_report_and_request_is_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            request = EvaluatePolicyRequest(
                dataset=fixture.dataset,
                baseline_policy=fixture.baseline,
                challenger_policy=fixture.challenger,
                output=fixture.report,
                min_precision=1.0,
                min_recall=1.0,
            )
            result = evaluate_policy(request)
            self.assertEqual(result.report, load_data(fixture.report))
            with self.assertRaises(FrozenInstanceError):
                request.min_precision = 0.5

    def test_attach_pass_report_and_approval_warning_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            report = run_evaluation(fixture.dataset, fixture.baseline, fixture.challenger)
            write_evaluation_report(fixture.report, report)
            reference = attach_evaluation_to_candidate(
                fixture.candidates,
                "RULE_EVAL_GOOD",
                fixture.report,
            )
            self.assertEqual("PASS", reference["decision"])
            candidate = load_rules(fixture.candidates)["rules"][0]
            self.assertEqual(
                report["report_sha256"],
                candidate["evaluation"]["report_sha256"],
            )

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = approve_rule(
                    ApproveRuleRequest(
                        candidates=fixture.candidates,
                        approved=fixture.approved,
                        rule_id="RULE_EVAL_GOOD",
                        approved_by="maintainer",
                        approved_at="2026-07-24T00:00:00Z",
                    )
                )
            self.assertEqual((), result.warnings)
            self.assertEqual([], caught)

    def test_approval_without_evaluation_remains_allowed_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = approve_rule(
                    ApproveRuleRequest(
                        candidates=fixture.candidates,
                        approved=fixture.approved,
                        rule_id="RULE_EVAL_GOOD",
                        approved_by="maintainer",
                    )
                )
            self.assertEqual(1, len(result.warnings))
            self.assertEqual(1, len(caught))
            self.assertIn("no attached PASS evaluation", str(caught[0].message))

    def test_fail_report_cannot_be_attached(self):
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
            before = fixture.candidates.read_bytes()
            with self.assertRaises(EvaluationGateError):
                attach_evaluation_to_candidate(
                    fixture.candidates,
                    "RULE_EVAL_GOOD",
                    fixture.report,
                )
            self.assertEqual(before, fixture.candidates.read_bytes())


class EvaluationCliTests(unittest.TestCase):
    def test_cli_pass_fail_and_integrity_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    evaluation_main(["validate-dataset", str(fixture.dataset)]),
                )
                self.assertEqual(
                    0,
                    evaluation_main(
                        [
                            "run",
                            str(fixture.dataset),
                            "--baseline-policy",
                            str(fixture.baseline),
                            "--challenger-policy",
                            str(fixture.challenger),
                            "--output",
                            str(fixture.report),
                            "--min-precision",
                            "1",
                            "--min-recall",
                            "1",
                        ]
                    ),
                )
                self.assertEqual(
                    0,
                    evaluation_main(["verify-report", str(fixture.report)]),
                )

            tampered = load_data(fixture.report)
            tampered["cases"][0]["challenger"]["changed_scope"].append(
                "src/evil.py"
            )
            dump_json(fixture.report, tampered)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    4,
                    evaluation_main(["verify-report", str(fixture.report)]),
                )

    def test_cli_returns_three_for_gate_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = EvaluationFixture(Path(tmp))
            dataset = load_data(fixture.dataset)
            for case in dataset["cases"]:
                case["configured_packs"] = []
                case["expected_changed_scope"] = ["src/a.py", "src/b.py"]
                case["expected_packs"] = []
                case["expected_tests"] = []
            dump_yaml(fixture.dataset, dataset)
            with redirect_stdout(io.StringIO()):
                code = evaluation_main(
                    [
                        "run",
                        str(fixture.dataset),
                        "--baseline-policy",
                        str(fixture.baseline),
                        "--challenger-policy",
                        str(fixture.bad_challenger),
                        "--output",
                        str(fixture.report),
                    ]
                )
            self.assertEqual(3, code)


if __name__ == "__main__":
    unittest.main()

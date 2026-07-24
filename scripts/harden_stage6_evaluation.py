from pathlib import Path


def ensure_replace(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"missing {label}")
    return text.replace(old, new, 1)


evaluation_path = Path("src/review_system/evaluation.py")
evaluation = evaluation_path.read_text(encoding="utf-8")
evaluation = ensure_replace(
    evaluation,
    'from .io import load_data\n',
    'from .io import load_data\nfrom .version import get_version\n',
    "evaluator version import",
)
evaluation = ensure_replace(
    evaluation,
    'PROTECTED_RESULTS = ("PASS", "FAIL")\n',
    'PROTECTED_RESULTS = ("PASS", "FAIL")\nEVALUATOR_CONTRACT_VERSION = "1.0"\n',
    "evaluator contract version",
)
evaluation = ensure_replace(
    evaluation,
    '''def load_evaluation_dataset(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise EvaluationError(f"evaluation dataset not found: {source}")
    data = load_data(source)
    errors = validate_evaluation_dataset_data(data, root=source.parent)
    if errors:
        raise EvaluationError("invalid evaluation dataset: " + "; ".join(errors))
    return source, data
''',
    '''def _normalize_dataset_data(data: dict[str, Any], root: Path) -> dict[str, Any]:
    normalized_cases: list[dict[str, Any]] = []
    for index, case in enumerate(data["cases"]):
        normalized, errors = _validate_case(case, index, root)
        if errors or normalized is None:
            raise EvaluationError(
                "invalid evaluation dataset: " + "; ".join(errors or [f"cases[{index}] is invalid"])
            )
        normalized_cases.append(normalized)
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "dataset_id": _require_text(data["dataset_id"], "dataset_id"),
        "cases": normalized_cases,
    }


def load_evaluation_dataset(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise EvaluationError(f"evaluation dataset not found: {source}")
    data = load_data(source)
    errors = validate_evaluation_dataset_data(data, root=source.parent)
    if errors:
        raise EvaluationError("invalid evaluation dataset: " + "; ".join(errors))
    return source, _normalize_dataset_data(data, source.parent)
''',
    "normalized dataset load",
)
evaluation = ensure_replace(
    evaluation,
    '''def _policy_descriptor(path: str | Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
''',
    '''def _evaluator_descriptor() -> dict[str, str]:
    return {
        "name": "review_system.intelligence_impact.analyze_change",
        "contract_version": EVALUATOR_CONTRACT_VERSION,
        "product_version": get_version(),
    }


def _policy_descriptor(path: str | Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
''',
    "evaluator descriptor",
)
evaluation = ensure_replace(
    evaluation,
    '''    conditions = {
        "repeatability": bool(repeatability["baseline"] and repeatability["challenger"]),
        "minimum_precision": overall["precision"] >= thresholds["min_precision"],
        "minimum_recall": overall["recall"] >= thresholds["min_recall"],
        "protected_negative_regressions": (
            len(comparison["protected_negative_regressions"])
            <= thresholds["max_protected_negative_regressions"]
        ),
    }
    holdout_cases = [case for case in cases if case["split"] == "holdout"]
''',
    '''    holdout_cases = [case for case in cases if case["split"] == "holdout"]
    conditions = {
        "repeatability": bool(repeatability["baseline"] and repeatability["challenger"]),
        "holdout_present": bool(holdout_cases),
        "minimum_precision": overall["precision"] >= thresholds["min_precision"],
        "minimum_recall": overall["recall"] >= thresholds["min_recall"],
        "protected_negative_regressions": (
            len(comparison["protected_negative_regressions"])
            <= thresholds["max_protected_negative_regressions"]
        ),
    }
''',
    "holdout hard gate",
)
evaluation = ensure_replace(
    evaluation,
    '''    min_precision: float = 0.0,
    min_recall: float = 0.0,
''',
    '''    min_precision: float = 1.0,
    min_recall: float = 1.0,
''',
    "safe metric defaults",
)
evaluation = ensure_replace(
    evaluation,
    '''    thresholds = {
        "min_precision": round(float(min_precision), 6),
        "min_recall": round(float(min_recall), 6),
        "max_protected_negative_regressions": max_protected_negative_regressions,
    }
''',
    '''    evaluator = _evaluator_descriptor()
    thresholds = {
        "min_precision": round(float(min_precision), 6),
        "min_recall": round(float(min_recall), 6),
        "max_protected_negative_regressions": max_protected_negative_regressions,
    }
''',
    "evaluator runtime descriptor",
)
evaluation = ensure_replace(
    evaluation,
    '''        "challenger_policy_sha256": challenger_descriptor["sha256"],
        "thresholds": thresholds,
''',
    '''        "challenger_policy_sha256": challenger_descriptor["sha256"],
        "evaluator": evaluator,
        "thresholds": thresholds,
''',
    "evaluation identity evaluator",
)
evaluation = ensure_replace(
    evaluation,
    '''        "challenger_policy": challenger_descriptor,
        "thresholds": thresholds,
''',
    '''        "challenger_policy": challenger_descriptor,
        "evaluator": evaluator,
        "thresholds": thresholds,
''',
    "report evaluator descriptor",
)
evaluation = ensure_replace(
    evaluation,
    '''        "challenger_policy",
        "thresholds",
''',
    '''        "challenger_policy",
        "evaluator",
        "thresholds",
''',
    "required evaluator report field",
)
evaluation = ensure_replace(
    evaluation,
    '''            "challenger_policy_sha256": report["challenger_policy"]["sha256"],
            "thresholds": report["thresholds"],
''',
    '''            "challenger_policy_sha256": report["challenger_policy"]["sha256"],
            "evaluator": report["evaluator"],
            "thresholds": report["thresholds"],
''',
    "verify evaluator identity",
)
evaluation_path.write_text(evaluation, encoding="utf-8")


application_path = Path("src/review_system/application/evaluate_policy.py")
application = application_path.read_text(encoding="utf-8")
application = ensure_replace(
    application,
    '''    min_precision: float = 0.0
    min_recall: float = 0.0
''',
    '''    min_precision: float = 1.0
    min_recall: float = 1.0
''',
    "application safe metric defaults",
)
application_path.write_text(application, encoding="utf-8")


cli_path = Path("src/review_system/evaluation_cli.py")
cli = cli_path.read_text(encoding="utf-8")
cli = ensure_replace(
    cli,
    '    command.add_argument("--min-precision", type=float, default=0.0)\n',
    '    command.add_argument("--min-precision", type=float, default=1.0)\n',
    "CLI precision default",
)
cli = ensure_replace(
    cli,
    '    command.add_argument("--min-recall", type=float, default=0.0)\n',
    '    command.add_argument("--min-recall", type=float, default=1.0)\n',
    "CLI recall default",
)
cli_path.write_text(cli, encoding="utf-8")


tests_path = Path("tests/test_evaluation_hardening.py")
tests = tests_path.read_text(encoding="utf-8")
insert = '''    def test_no_holdout_cannot_pass_approval_gate(self):
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
                    value.replace("/", "\\\\")
                    for value in case["expected_changed_scope"]
                ]
                case["input_artifacts"]["graph"] = case["input_artifacts"]["graph"].replace("/", "\\\\")
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

'''
anchor = '    def test_duplicate_case_id_and_invalid_policy_fail_closed(self):\n'
if insert not in tests:
    if anchor not in tests:
        raise SystemExit("missing hardening test anchor")
    tests = tests.replace(anchor, insert + anchor, 1)
tests_path.write_text(tests, encoding="utf-8")


design_path = Path("docs/architecture/STAGE-6-EVALUATION-LAB.md")
design = design_path.read_text(encoding="utf-8")ndesign = ensure_replace(
    design,
    '''- holdout split이 존재할 경우 holdout에도 같은 조건 적용
''',
    '''- holdout split이 반드시 존재해야 하며 holdout에도 같은 조건 적용
''',
    "holdout design gate",
)
design = ensure_replace(
    design,
    '''- `evaluation_id`는 dataset hash + baseline hash + challenger hash + threshold의 digest다.
''',
    '''- `evaluation_id`는 dataset hash + baseline hash + challenger hash + evaluator contract + threshold의 digest다.
- evaluator name, contract version, PIE product version을 report에 고정한다.
''',
    "evaluator identity design",
)
design = ensure_replace(
    design,
    '''- challenger combined precision >= configured threshold
- challenger combined recall >= configured threshold
''',
    '''- challenger combined precision >= configured threshold, 기본 `1.0`
- challenger combined recall >= configured threshold, 기본 `1.0`
''',
    "safe default design",
)
design_path.write_text(design, encoding="utf-8")

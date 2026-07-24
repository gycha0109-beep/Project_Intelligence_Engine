from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any

import yaml

from .identity import canonical_json_sha256, file_sha256
from .intelligence_config import load_rules, normalize_path, validate_rules
from .intelligence_graph import validate_project_graph
from .intelligence_impact import analyze_change
from .io import load_data


EVALUATION_SCHEMA_VERSION = "1.0"
DATASET_SPLITS = ("development", "validation", "holdout")
PROTECTED_RESULTS = ("PASS", "FAIL")


class EvaluationError(RuntimeError):
    pass


class EvaluationGateError(EvaluationError):
    pass


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"{field} must be a non-empty string")
    return value.strip()


def _safe_artifact(root: Path, value: Any, field: str) -> Path:
    raw = _require_text(value, field).replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise EvaluationError(f"{field} must be relative to the dataset directory")
    parts = [part for part in PurePosixPath(raw).parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise EvaluationError(f"{field} contains an unsafe relative path")
    root_resolved = root.resolve()
    candidate = root.joinpath(*parts)
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise EvaluationError(f"{field} must not traverse a symlink: {raw}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise EvaluationError(f"{field} is missing or escapes the dataset directory: {raw}") from exc
    if not resolved.is_file():
        raise EvaluationError(f"{field} must reference a regular file: {raw}")
    return resolved


def _string_set(value: Any, field: str, *, paths: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise EvaluationError(f"{field} must be an array")
    output: list[str] = []
    for index, item in enumerate(value):
        text = _require_text(item, f"{field}[{index}]")
        output.append(normalize_path(text) if paths else text)
    if len(output) != len(set(output)):
        raise EvaluationError(f"{field} must not contain duplicates")
    return sorted(output)


def _read_changed_files(path: Path) -> list[str]:
    values = [
        normalize_path(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not values:
        raise EvaluationError(f"changed-files artifact is empty: {path.name}")
    if len(values) != len(set(values)):
        raise EvaluationError(f"changed-files artifact contains duplicate paths: {path.name}")
    return sorted(values)


def _validate_case(case: Any, index: int, root: Path | None) -> tuple[dict[str, Any] | None, list[str]]:
    prefix = f"cases[{index}]"
    errors: list[str] = []
    if not isinstance(case, dict):
        return None, [f"{prefix} must be an object"]
    normalized: dict[str, Any] = {}
    for field in ("case_id", "repository", "source_revision"):
        try:
            normalized[field] = _require_text(case.get(field), f"{prefix}.{field}")
        except EvaluationError as exc:
            errors.append(str(exc))
    split = case.get("split")
    if split not in DATASET_SPLITS:
        errors.append(f"{prefix}.split must be one of {', '.join(DATASET_SPLITS)}")
    else:
        normalized["split"] = split
    for field, paths in (
        ("configured_packs", False),
        ("expected_changed_scope", True),
        ("expected_packs", False),
        ("expected_tests", False),
        ("labels", False),
    ):
        try:
            normalized[field] = _string_set(case.get(field), f"{prefix}.{field}", paths=paths)
        except EvaluationError as exc:
            errors.append(str(exc))
    expected_protected = case.get("expected_protected_result")
    if expected_protected not in PROTECTED_RESULTS:
        errors.append(f"{prefix}.expected_protected_result must be PASS or FAIL")
    else:
        normalized["expected_protected_result"] = expected_protected
    provenance = case.get("provenance")
    if not isinstance(provenance, dict):
        errors.append(f"{prefix}.provenance must be an object")
    else:
        normalized_provenance: dict[str, str] = {}
        for field in ("source", "labeled_by", "labeled_at"):
            try:
                normalized_provenance[field] = _require_text(
                    provenance.get(field), f"{prefix}.provenance.{field}"
                )
            except EvaluationError as exc:
                errors.append(str(exc))
        normalized["provenance"] = normalized_provenance
    artifacts = case.get("input_artifacts")
    if not isinstance(artifacts, dict):
        errors.append(f"{prefix}.input_artifacts must be an object")
    else:
        normalized_artifacts: dict[str, str] = {}
        for field in ("graph", "changed_files"):
            try:
                raw = _require_text(artifacts.get(field), f"{prefix}.input_artifacts.{field}")
                normalized_artifacts[field] = raw.replace("\\", "/")
            except EvaluationError as exc:
                errors.append(str(exc))
        normalized["input_artifacts"] = normalized_artifacts
        if root is not None and len(normalized_artifacts) == 2:
            try:
                graph_path = _safe_artifact(root, normalized_artifacts["graph"], f"{prefix}.input_artifacts.graph")
                graph = load_data(graph_path)
                if not isinstance(graph, dict):
                    raise EvaluationError(f"{prefix}.input_artifacts.graph must contain an object")
                graph_errors = validate_project_graph(graph)
                if graph_errors:
                    errors.extend(f"{prefix}.input_artifacts.graph: {error}" for error in graph_errors)
            except (EvaluationError, OSError, ValueError) as exc:
                errors.append(str(exc))
            try:
                changed_path = _safe_artifact(
                    root,
                    normalized_artifacts["changed_files"],
                    f"{prefix}.input_artifacts.changed_files",
                )
                _read_changed_files(changed_path)
            except (EvaluationError, OSError, ValueError) as exc:
                errors.append(str(exc))
    return normalized, errors


def validate_evaluation_dataset_data(data: Any, *, root: str | Path | None = None) -> list[str]:
    if not isinstance(data, dict):
        return ["dataset must contain an object"]
    errors: list[str] = []
    if data.get("schema_version") != EVALUATION_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EVALUATION_SCHEMA_VERSION!r}")
    try:
        _require_text(data.get("dataset_id"), "dataset_id")
    except EvaluationError as exc:
        errors.append(str(exc))
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        return [*errors, "cases must be a non-empty array"]
    case_ids: set[str] = set()
    root_path = Path(root).resolve() if root is not None else None
    for index, case in enumerate(cases):
        normalized, case_errors = _validate_case(case, index, root_path)
        errors.extend(case_errors)
        if normalized is None:
            continue
        case_id = normalized.get("case_id")
        if isinstance(case_id, str):
            if case_id in case_ids:
                errors.append(f"duplicate case_id: {case_id}")
            case_ids.add(case_id)
    return errors


def load_evaluation_dataset(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise EvaluationError(f"evaluation dataset not found: {source}")
    data = load_data(source)
    errors = validate_evaluation_dataset_data(data, root=source.parent)
    if errors:
        raise EvaluationError("invalid evaluation dataset: " + "; ".join(errors))
    return source, data


def _dataset_descriptor(source: Path, data: dict[str, Any]) -> dict[str, Any]:
    artifact_hashes: list[dict[str, str]] = []
    for case in data["cases"]:
        for field in ("graph", "changed_files"):
            path = _safe_artifact(source.parent, case["input_artifacts"][field], f"{case['case_id']}.{field}")
            artifact_hashes.append(
                {
                    "case_id": case["case_id"],
                    "artifact": field,
                    "sha256": file_sha256(path),
                }
            )
    payload = {
        "dataset": data,
        "artifacts": sorted(artifact_hashes, key=lambda item: (item["case_id"], item["artifact"])),
    }
    split_counts = {
        split: sum(1 for case in data["cases"] if case["split"] == split)
        for split in DATASET_SPLITS
    }
    return {
        "dataset_id": data["dataset_id"],
        "source": source.name,
        "sha256": canonical_json_sha256(payload),
        "case_count": len(data["cases"]),
        "split_counts": split_counts,
    }


def _policy_descriptor(path: str | Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise EvaluationError(f"approved policy file not found: {source}")
    try:
        rules = load_rules(source, required_status="approved")
    except ValueError as exc:
        raise EvaluationError(str(exc)) from exc
    descriptor = {
        "source": source.name,
        "sha256": canonical_json_sha256(rules),
        "rule_ids": sorted(rule["id"] for rule in rules.get("rules", [])),
    }
    return source, rules, descriptor


def _outcome_payload(outcome: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(outcome)
    payload.pop("outcome_sha256", None)
    return payload


def _normalize_outcome(analysis: dict[str, Any]) -> dict[str, Any]:
    changed_scope = set(analysis.get("change", {}).get("changed_files", []))
    changed_scope.update(
        item.get("path")
        for item in analysis.get("impact", {}).get("dependent_files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    )
    missing = sorted(set(analysis.get("direct", {}).get("files_missing_from_graph", [])))
    unconfigured = sorted(set(analysis.get("review", {}).get("unconfigured_rule_packs", [])))
    reasons = [
        *(f"missing_from_graph:{path}" for path in missing),
        *(f"unconfigured_pack:{pack}" for pack in unconfigured),
    ]
    outcome = {
        "changed_scope": sorted(changed_scope),
        "selected_packs": sorted(set(analysis.get("review", {}).get("selected_packs", []))),
        "required_tests": sorted(set(analysis.get("review", {}).get("required_tests", []))),
        "matched_rules": sorted(
            {
                item.get("rule_id")
                for item in analysis.get("impact", {}).get("matched_rules", [])
                if isinstance(item, dict) and isinstance(item.get("rule_id"), str)
            }
        ),
        "protected_result": "FAIL" if reasons else "PASS",
        "protected_reasons": sorted(reasons),
    }
    outcome["outcome_sha256"] = canonical_json_sha256(outcome)
    return outcome


def _run_case(dataset_source: Path, case: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    graph_path = _safe_artifact(
        dataset_source.parent,
        case["input_artifacts"]["graph"],
        f"{case['case_id']}.graph",
    )
    changed_path = _safe_artifact(
        dataset_source.parent,
        case["input_artifacts"]["changed_files"],
        f"{case['case_id']}.changed_files",
    )
    graph = load_data(graph_path)
    if not isinstance(graph, dict):
        raise EvaluationError(f"case {case['case_id']} graph must contain an object")
    graph_errors = validate_project_graph(graph)
    if graph_errors:
        raise EvaluationError(f"case {case['case_id']} graph is invalid: " + "; ".join(graph_errors))
    changed_files = _read_changed_files(changed_path)
    analysis = analyze_change(
        graph,
        changed_files,
        configured_packs=case.get("configured_packs", []),
        approved_rules=rules.get("rules", []),
        change_id=case["case_id"],
    )
    return _normalize_outcome(analysis)


def _set_counts(expected: list[str], predicted: list[str]) -> dict[str, Any]:
    expected_set = set(expected)
    predicted_set = set(predicted)
    tp = len(expected_set & predicted_set)
    fp = len(predicted_set - expected_set)
    fn = len(expected_set - predicted_set)
    precision_denominator = tp + fp
    recall_denominator = tp + fn
    precision = tp / precision_denominator if precision_denominator else (1.0 if not expected_set else 0.0)
    recall = tp / recall_denominator if recall_denominator else (1.0 if not predicted_set else 0.0)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
    }


def _aggregate_dimension(
    cases: list[dict[str, Any]],
    policy: str,
    expected_key: str,
    predicted_key: str,
) -> dict[str, Any]:
    tp = fp = fn = 0
    for case in cases:
        counts = _set_counts(case["expected"][expected_key], case[policy][predicted_key])
        tp += counts["tp"]
        fp += counts["fp"]
        fn += counts["fn"]
    precision_denominator = tp + fp
    recall_denominator = tp + fn
    any_expected = any(case["expected"][expected_key] for case in cases)
    any_predicted = any(case[policy][predicted_key] for case in cases)
    precision = tp / precision_denominator if precision_denominator else (1.0 if not any_expected else 0.0)
    recall = tp / recall_denominator if recall_denominator else (1.0 if not any_predicted else 0.0)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
    }


def _policy_metrics(cases: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    dimensions = {
        "changed_scope": _aggregate_dimension(cases, policy, "changed_scope", "changed_scope"),
        "packs": _aggregate_dimension(cases, policy, "packs", "selected_packs"),
        "tests": _aggregate_dimension(cases, policy, "tests", "required_tests"),
    }
    combined_tp = sum(item["tp"] for item in dimensions.values())
    combined_fp = sum(item["fp"] for item in dimensions.values())
    combined_fn = sum(item["fn"] for item in dimensions.values())
    combined_precision_denominator = combined_tp + combined_fp
    combined_recall_denominator = combined_tp + combined_fn
    any_expected = any(
        case["expected"][field]
        for case in cases
        for field in ("changed_scope", "packs", "tests")
    )
    any_predicted = any(
        case[policy][field]
        for case in cases
        for field in ("changed_scope", "selected_packs", "required_tests")
    )
    combined_precision = (
        combined_tp / combined_precision_denominator
        if combined_precision_denominator
        else (1.0 if not any_expected else 0.0)
    )
    combined_recall = (
        combined_tp / combined_recall_denominator
        if combined_recall_denominator
        else (1.0 if not any_predicted else 0.0)
    )
    exact = 0
    protected_correct = 0
    for case in cases:
        is_exact = (
            case[policy]["changed_scope"] == case["expected"]["changed_scope"]
            and case[policy]["selected_packs"] == case["expected"]["packs"]
            and case[policy]["required_tests"] == case["expected"]["tests"]
            and case[policy]["protected_result"] == case["expected"]["protected_result"]
        )
        exact += int(is_exact)
        protected_correct += int(
            case[policy]["protected_result"] == case["expected"]["protected_result"]
        )
    count = len(cases)
    return {
        "case_count": count,
        "coverage": 1.0 if count else 0.0,
        "dimensions": dimensions,
        "combined": {
            "tp": combined_tp,
            "fp": combined_fp,
            "fn": combined_fn,
            "precision": round(combined_precision, 6),
            "recall": round(combined_recall, 6),
        },
        "exact_case_matches": exact,
        "exact_case_rate": round(exact / count, 6) if count else 0.0,
        "protected_correct": protected_correct,
        "protected_accuracy": round(protected_correct / count, 6) if count else 0.0,
    }


def _all_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "overall": {
            "baseline": _policy_metrics(cases, "baseline"),
            "challenger": _policy_metrics(cases, "challenger"),
        }
    }
    for split in DATASET_SPLITS:
        selected = [case for case in cases if case["split"] == split]
        if selected:
            output[split] = {
                "baseline": _policy_metrics(selected, "baseline"),
                "challenger": _policy_metrics(selected, "challenger"),
            }
    return output


def _comparison(cases: list[dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any]:
    baseline = metrics["overall"]["baseline"]
    challenger = metrics["overall"]["challenger"]
    negative: list[str] = []
    improvements: list[str] = []
    changed: list[str] = []
    case_diffs: dict[str, Any] = {}
    for case in cases:
        if case["baseline"]["outcome_sha256"] != case["challenger"]["outcome_sha256"]:
            changed.append(case["case_id"])
        if (
            case["expected"]["protected_result"] == "PASS"
            and case["baseline"]["protected_result"] == "PASS"
            and case["challenger"]["protected_result"] == "FAIL"
        ):
            negative.append(case["case_id"])
        if (
            case["expected"]["protected_result"] == "PASS"
            and case["baseline"]["protected_result"] == "FAIL"
            and case["challenger"]["protected_result"] == "PASS"
        ):
            improvements.append(case["case_id"])
        case_diffs[case["case_id"]] = {
            "changed_scope_added": sorted(
                set(case["challenger"]["changed_scope"]) - set(case["baseline"]["changed_scope"])
            ),
            "changed_scope_removed": sorted(
                set(case["baseline"]["changed_scope"]) - set(case["challenger"]["changed_scope"])
            ),
            "packs_added": sorted(
                set(case["challenger"]["selected_packs"]) - set(case["baseline"]["selected_packs"])
            ),
            "packs_removed": sorted(
                set(case["baseline"]["selected_packs"]) - set(case["challenger"]["selected_packs"])
            ),
            "tests_added": sorted(
                set(case["challenger"]["required_tests"]) - set(case["baseline"]["required_tests"])
            ),
            "tests_removed": sorted(
                set(case["baseline"]["required_tests"]) - set(case["challenger"]["required_tests"])
            ),
            "protected_changed": (
                case["baseline"]["protected_result"] != case["challenger"]["protected_result"]
            ),
        }
    return {
        "combined_precision_delta": round(
            challenger["combined"]["precision"] - baseline["combined"]["precision"], 6
        ),
        "combined_recall_delta": round(
            challenger["combined"]["recall"] - baseline["combined"]["recall"], 6
        ),
        "exact_case_rate_delta": round(
            challenger["exact_case_rate"] - baseline["exact_case_rate"], 6
        ),
        "protected_accuracy_delta": round(
            challenger["protected_accuracy"] - baseline["protected_accuracy"], 6
        ),
        "protected_negative_regressions": sorted(negative),
        "protected_improvements": sorted(improvements),
        "changed_cases": sorted(changed),
        "case_diffs": {key: case_diffs[key] for key in sorted(case_diffs)},
    }


def _gate(
    cases: list[dict[str, Any]],
    metrics: dict[str, Any],
    comparison: dict[str, Any],
    repeatability: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    overall = metrics["overall"]["challenger"]["combined"]
    conditions = {
        "repeatability": bool(repeatability["baseline"] and repeatability["challenger"]),
        "minimum_precision": overall["precision"] >= thresholds["min_precision"],
        "minimum_recall": overall["recall"] >= thresholds["min_recall"],
        "protected_negative_regressions": (
            len(comparison["protected_negative_regressions"])
            <= thresholds["max_protected_negative_regressions"]
        ),
    }
    holdout_cases = [case for case in cases if case["split"] == "holdout"]
    if holdout_cases:
        holdout = metrics["holdout"]["challenger"]["combined"]
        holdout_negative = [
            case_id
            for case_id in comparison["protected_negative_regressions"]
            if any(
                case["case_id"] == case_id and case["split"] == "holdout"
                for case in cases
            )
        ]
        conditions.update(
            {
                "holdout_minimum_precision": holdout["precision"] >= thresholds["min_precision"],
                "holdout_minimum_recall": holdout["recall"] >= thresholds["min_recall"],
                "holdout_protected_negative_regressions": (
                    len(holdout_negative) <= thresholds["max_protected_negative_regressions"]
                ),
            }
        )
    failed = sorted(name for name, passed in conditions.items() if not passed)
    return {
        "decision": "PASS" if not failed else "FAIL",
        "conditions": conditions,
        "failed_conditions": failed,
    }


def _report_payload(report: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(report)
    payload.pop("report_sha256", None)
    return payload


def run_evaluation(
    dataset: str | Path,
    baseline_policy: str | Path,
    challenger_policy: str | Path,
    *,
    min_precision: float = 0.0,
    min_recall: float = 0.0,
    max_protected_negative_regressions: int = 0,
    repeatability_runs: int = 2,
) -> dict[str, Any]:
    if not 0 <= min_precision <= 1:
        raise EvaluationError("min_precision must be between 0 and 1")
    if not 0 <= min_recall <= 1:
        raise EvaluationError("min_recall must be between 0 and 1")
    if (
        not isinstance(max_protected_negative_regressions, int)
        or isinstance(max_protected_negative_regressions, bool)
        or max_protected_negative_regressions < 0
    ):
        raise EvaluationError(
            "max_protected_negative_regressions must be a non-negative integer"
        )
    if (
        not isinstance(repeatability_runs, int)
        or isinstance(repeatability_runs, bool)
        or repeatability_runs < 2
    ):
        raise EvaluationError("repeatability_runs must be at least 2")

    dataset_source, dataset_data = load_evaluation_dataset(dataset)
    dataset_descriptor = _dataset_descriptor(dataset_source, dataset_data)
    _, baseline_rules, baseline_descriptor = _policy_descriptor(baseline_policy)
    _, challenger_rules, challenger_descriptor = _policy_descriptor(challenger_policy)
    thresholds = {
        "min_precision": round(float(min_precision), 6),
        "min_recall": round(float(min_recall), 6),
        "max_protected_negative_regressions": max_protected_negative_regressions,
    }
    case_results: list[dict[str, Any]] = []
    baseline_repeatable = True
    challenger_repeatable = True
    for case in sorted(dataset_data["cases"], key=lambda item: item["case_id"]):
        baseline_runs = [
            _run_case(dataset_source, case, baseline_rules)
            for _ in range(repeatability_runs)
        ]
        challenger_runs = [
            _run_case(dataset_source, case, challenger_rules)
            for _ in range(repeatability_runs)
        ]
        baseline_repeatable = baseline_repeatable and len(
            {item["outcome_sha256"] for item in baseline_runs}
        ) == 1
        challenger_repeatable = challenger_repeatable and len(
            {item["outcome_sha256"] for item in challenger_runs}
        ) == 1
        case_results.append(
            {
                "case_id": case["case_id"],
                "repository": case["repository"],
                "source_revision": case["source_revision"],
                "split": case["split"],
                "labels": sorted(case["labels"]),
                "provenance": case["provenance"],
                "expected": {
                    "changed_scope": sorted(case["expected_changed_scope"]),
                    "packs": sorted(case["expected_packs"]),
                    "tests": sorted(case["expected_tests"]),
                    "protected_result": case["expected_protected_result"],
                },
                "baseline": baseline_runs[0],
                "challenger": challenger_runs[0],
            }
        )
    repeatability = {
        "runs": repeatability_runs,
        "baseline": baseline_repeatable,
        "challenger": challenger_repeatable,
    }
    metrics = _all_metrics(case_results)
    comparison = _comparison(case_results, metrics)
    gate = _gate(case_results, metrics, comparison, repeatability, thresholds)
    evaluation_key = {
        "dataset_sha256": dataset_descriptor["sha256"],
        "baseline_policy_sha256": baseline_descriptor["sha256"],
        "challenger_policy_sha256": challenger_descriptor["sha256"],
        "thresholds": thresholds,
        "repeatability_runs": repeatability_runs,
    }
    report = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "evaluation_id": f"evaluation-{canonical_json_sha256(evaluation_key)[:32]}",
        "dataset": dataset_descriptor,
        "baseline_policy": baseline_descriptor,
        "challenger_policy": challenger_descriptor,
        "thresholds": thresholds,
        "repeatability": repeatability,
        "cases": case_results,
        "metrics": metrics,
        "comparison": comparison,
        "gate": gate,
    }
    report["report_sha256"] = canonical_json_sha256(report)
    return report


def write_evaluation_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_evaluation_report_data(report)
    if errors:
        raise EvaluationError(
            "refusing to write invalid evaluation report: " + "; ".join(errors)
        )
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def verify_evaluation_report_data(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["report must contain an object"]
    errors: list[str] = []
    if report.get("schema_version") != EVALUATION_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EVALUATION_SCHEMA_VERSION!r}")
    recorded = report.get("report_sha256")
    expected_hash = canonical_json_sha256(_report_payload(report))
    if not isinstance(recorded, str) or recorded != expected_hash:
        errors.append("report_sha256 mismatch")
    cases = report.get("cases")
    if not isinstance(cases, list):
        errors.append("cases must be an array")
        cases = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"cases[{index}] must be an object")
            continue
        for policy in ("baseline", "challenger"):
            outcome = case.get(policy)
            if not isinstance(outcome, dict):
                errors.append(f"cases[{index}].{policy} must be an object")
                continue
            outcome_hash = outcome.get("outcome_sha256")
            if (
                not isinstance(outcome_hash, str)
                or outcome_hash != canonical_json_sha256(_outcome_payload(outcome))
            ):
                errors.append(f"cases[{index}].{policy}.outcome_sha256 mismatch")
    required = (
        "evaluation_id",
        "dataset",
        "baseline_policy",
        "challenger_policy",
        "thresholds",
        "repeatability",
        "cases",
        "metrics",
        "comparison",
        "gate",
    )
    for field in required:
        if field not in report:
            errors.append(f"missing report field: {field}")
    if errors:
        return errors
    try:
        evaluation_key = {
            "dataset_sha256": report["dataset"]["sha256"],
            "baseline_policy_sha256": report["baseline_policy"]["sha256"],
            "challenger_policy_sha256": report["challenger_policy"]["sha256"],
            "thresholds": report["thresholds"],
            "repeatability_runs": report["repeatability"]["runs"],
        }
        expected_id = f"evaluation-{canonical_json_sha256(evaluation_key)[:32]}"
        if report["evaluation_id"] != expected_id:
            errors.append("evaluation_id mismatch")
        recalculated_metrics = _all_metrics(report["cases"])
        if report["metrics"] != recalculated_metrics:
            errors.append("metrics mismatch")
        recalculated_comparison = _comparison(report["cases"], recalculated_metrics)
        if report["comparison"] != recalculated_comparison:
            errors.append("comparison mismatch")
        recalculated_gate = _gate(
            report["cases"],
            recalculated_metrics,
            recalculated_comparison,
            report["repeatability"],
            report["thresholds"],
        )
        if report["gate"] != recalculated_gate:
            errors.append("gate mismatch")
    except (KeyError, TypeError, ValueError, EvaluationError) as exc:
        errors.append(f"report structure invalid: {exc}")
    return errors


def load_evaluation_report(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise EvaluationError(f"evaluation report not found: {source}")
    data = load_data(source)
    errors = verify_evaluation_report_data(data)
    if errors:
        raise EvaluationError("invalid evaluation report: " + "; ".join(errors))
    return source, data


def attach_evaluation_to_candidate(
    candidates: str | Path,
    rule_id: str,
    report: str | Path,
) -> dict[str, Any]:
    candidates_path = Path(candidates).expanduser().resolve()
    report_path, report_data = load_evaluation_report(report)
    if report_data["gate"]["decision"] != "PASS":
        raise EvaluationGateError("cannot attach a FAIL evaluation report")
    rules = load_rules(candidates_path)
    selected = next(
        (item for item in rules.get("rules", []) if item.get("id") == rule_id),
        None,
    )
    if selected is None:
        raise EvaluationError(f"candidate rule not found: {rule_id}")
    if selected.get("status") != "candidate":
        raise EvaluationError(f"rule is not a candidate: {rule_id}")
    reference = {
        "evaluation_id": report_data["evaluation_id"],
        "report": report_path.name,
        "report_sha256": report_data["report_sha256"],
        "decision": report_data["gate"]["decision"],
        "dataset_sha256": report_data["dataset"]["sha256"],
        "baseline_policy_sha256": report_data["baseline_policy"]["sha256"],
        "challenger_policy_sha256": report_data["challenger_policy"]["sha256"],
    }
    updated = deepcopy(rules)
    updated["rules"] = [
        ({**item, "evaluation": reference} if item.get("id") == rule_id else item)
        for item in rules.get("rules", [])
    ]
    validation_errors = validate_rules(updated)
    if validation_errors:
        raise EvaluationError(
            "evaluation attachment produced invalid rules: "
            + "; ".join(validation_errors)
        )
    target = candidates_path
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(updated, sort_keys=False, allow_unicode=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return reference

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .paths import asset
from .trust_comparison import load_registry, write_json_atomic

SCHEMA_VERSION = "1.0"
TARGET_BAND = "R0"
MODE = "REPORT_ONLY"

MINIMUM_CHECKS = (
    ("MINIMUM_ASSESSMENT_COUNT", "assessment_count", "minimum_assessment_count"),
    ("MINIMUM_REVIEWED_COUNT", "reviewed_count", "minimum_reviewed_count"),
    ("MINIMUM_CONCLUSIVE_OUTCOME_COUNT", "conclusive_outcome_count", "minimum_conclusive_outcome_count"),
    ("MINIMUM_CONFIRMED_SAFE_COUNT", "confirmed_safe_count", "minimum_confirmed_safe_count"),
    ("MINIMUM_CONFIRMED_UNSAFE_COUNT", "confirmed_unsafe_count", "minimum_confirmed_unsafe_count"),
    ("MINIMUM_INDEPENDENT_AUDIT_COUNT", "independent_audit_count", "minimum_independent_audit_count"),
    ("MINIMUM_OUTCOME_COVERAGE", "outcome_coverage", "minimum_outcome_coverage"),
    ("MINIMUM_EVIDENCE_SPAN_DAYS", "evidence_span_days", "minimum_evidence_span_days"),
)
MAXIMUM_CHECKS = (
    ("MAXIMUM_CONFIRMED_FALSE_NEGATIVES", "false_negative", "maximum_confirmed_false_negatives"),
    ("MAXIMUM_FALSE_NEGATIVE_RATE", "false_negative_rate", "maximum_false_negative_rate"),
)


class TrustObservationError(RuntimeError):
    pass


class TrustObservationVerificationError(TrustObservationError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid Trust observation artifact: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TrustObservationError(f"{field} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustObservationError(f"{field} is invalid: {value}") from exc
    if parsed.tzinfo is None:
        raise TrustObservationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_timestamp(value: str | None, field: str) -> str:
    parsed = _timestamp(value or utc_now(), field)
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_input(path: str | Path, field: str) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise TrustObservationError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise TrustObservationError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise TrustObservationError(f"{field} must be a regular file: {resolved}")
    return resolved


def _schema(name: str) -> dict[str, Any]:
    path = asset(f"schemas/{name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TrustObservationError(f"schema must contain an object: {name}")
    return value


def _schema_errors(value: Any, name: str) -> list[str]:
    validator = Draft202012Validator(_schema(name), format_checker=FormatChecker())
    return sorted(error.message for error in validator.iter_errors(value))


def _without(value: dict[str, Any], field: str) -> dict[str, Any]:
    output = deepcopy(value)
    output.pop(field, None)
    return output


def policy_sha256(policy: dict[str, Any]) -> str:
    return canonical_json_sha256(policy)


def policy_id(policy: dict[str, Any]) -> str:
    return f"trust-observation-policy-{policy_sha256(policy)[:32]}"


def verify_policy_data(policy: Any) -> list[str]:
    errors = _schema_errors(policy, "trust-observation-policy.schema.json")
    if not isinstance(policy, dict):
        return sorted(set(errors or ["policy must contain an object"]))
    if policy.get("mode") != MODE:
        errors.append("policy mode must be REPORT_ONLY")
    if policy.get("target_band") != TARGET_BAND:
        errors.append("policy target_band must be R0")
    thresholds = policy.get("thresholds")
    if isinstance(thresholds, dict):
        if thresholds.get("maximum_confirmed_false_negatives") != 0:
            errors.append("R0 observation policy must not permit confirmed false negatives")
        if thresholds.get("maximum_false_negative_rate") != 0:
            errors.append("R0 observation policy must not permit a non-zero false-negative rate")
    return sorted(set(errors))


def load_policy(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "Trust observation policy")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrustObservationError(f"cannot load Trust observation policy: {exc}") from exc
    errors = verify_policy_data(value)
    if errors:
        raise TrustObservationVerificationError(errors)
    return source, value


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _r0_observation(registry: dict[str, Any]) -> dict[str, Any]:
    assessments = [item for item in registry["assessments"] if item["predicted_risk_band"] == TARGET_BAND]
    ids = {item["assessment_id"] for item in assessments}
    comparisons = [item for item in registry["comparisons"] if item["assessment_id"] in ids]
    confirmed_states = {
        "CONFIRMED_TRUE_NEGATIVE",
        "CONFIRMED_FALSE_NEGATIVE",
        "CONFIRMED_TRUE_POSITIVE",
        "CONFIRMED_FALSE_POSITIVE",
    }
    confirmed = [item for item in comparisons if item["confirmed_status"] in confirmed_states]
    status_count = lambda status: sum(1 for item in confirmed if item["confirmed_status"] == status)
    tn = status_count("CONFIRMED_TRUE_NEGATIVE")
    fn = status_count("CONFIRMED_FALSE_NEGATIVE")
    tp = status_count("CONFIRMED_TRUE_POSITIVE")
    fp = status_count("CONFIRMED_FALSE_POSITIVE")
    comparable_states = {
        "PROVISIONAL_MATCH",
        "PROVISIONAL_OVER_ESTIMATE",
        "PROVISIONAL_UNDER_ESTIMATE",
        "PROVISIONAL_DECISION_MISMATCH",
    }
    comparable = [item for item in comparisons if item["provisional_status"] in comparable_states]
    matches = sum(1 for item in comparable if item["provisional_status"] == "PROVISIONAL_MATCH")
    timestamps: list[datetime] = []
    for item in assessments:
        timestamps.append(_timestamp(item["captured_at"], "assessment.captured_at"))
    for event in registry["events"]:
        if event["assessment_id"] in ids:
            timestamps.append(_timestamp(event["occurred_at"], "event.occurred_at"))
    evidence_span_days = 0.0
    if timestamps:
        evidence_span_days = round((max(timestamps) - min(timestamps)).total_seconds() / 86400.0, 6)
    independent_audit_count = sum(
        1
        for event in registry["events"]
        if event["assessment_id"] in ids
        and event["event_type"] == "OUTCOME"
        and event["payload"].get("outcome_type") == "INDEPENDENT_AUDIT"
        and event["payload"].get("verdict") in {"SAFE", "UNSAFE"}
    )
    return {
        "assessment_count": len(assessments),
        "reviewed_count": sum(1 for item in comparisons if item["review_level"] in {"REVIEWED", "AUDITED"}),
        "conclusive_outcome_count": len(confirmed),
        "confirmed_safe_count": tn + fp,
        "confirmed_unsafe_count": tp + fn,
        "independent_audit_count": independent_audit_count,
        "outcome_coverage": _ratio(len(confirmed), len(assessments)),
        "evidence_span_days": evidence_span_days,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "false_negative_rate": _ratio(fn, fn + tp),
        "reviewer_alignment_rate": _ratio(matches, len(comparable)),
    }


def _checks(observation: dict[str, Any], thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for check_id, metric, threshold in MINIMUM_CHECKS:
        actual = observation[metric]
        required = thresholds[threshold]
        output.append({
            "id": check_id,
            "actual": actual,
            "operator": ">=",
            "required": required,
            "passed": actual is not None and actual >= required,
        })
    for check_id, metric, threshold in MAXIMUM_CHECKS:
        actual = observation[metric]
        required = thresholds[threshold]
        output.append({
            "id": check_id,
            "actual": actual,
            "operator": "<=",
            "required": required,
            "passed": actual is not None and actual <= required,
        })
    return output


def _decision(checks: list[dict[str, Any]]) -> tuple[str, list[str], str]:
    failed = [item for item in checks if not item["passed"]]
    failed_ids = sorted(item["id"] for item in failed)
    harmful = {
        item["id"]
        for item in failed
        if item["id"] in {"MAXIMUM_CONFIRMED_FALSE_NEGATIVES", "MAXIMUM_FALSE_NEGATIVE_RATE"}
        and item["actual"] is not None
        and item["actual"] > item["required"]
    }
    if harmful:
        return "THRESHOLD_BLOCKED", failed_ids, "INVESTIGATE_CONFIRMED_FALSE_NEGATIVES"
    if failed:
        return "INSUFFICIENT_EVIDENCE", failed_ids, "COLLECT_MORE_CONFIRMED_OBSERVATION"
    return (
        "THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION",
        [],
        "PERFORM_SOURCE_RECONCILIATION_THEN_SEPARATE_R0_PILOT_SAFETY_REVIEW",
    )


def _report_id(project_id: str, registry: dict[str, Any], policy: dict[str, Any]) -> str:
    identity = {
        "project_id": project_id,
        "registry_id": registry["registry_id"],
        "registry_sha256": registry["registry_sha256"],
        "policy_id": policy_id(policy),
        "policy_sha256": policy_sha256(policy),
        "target_band": TARGET_BAND,
    }
    return f"trust-observation-{canonical_json_sha256(identity)[:32]}"


def evaluate_observation_data(
    registry: dict[str, Any],
    policy: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    policy_errors = verify_policy_data(policy)
    if policy_errors:
        raise TrustObservationVerificationError(policy_errors)
    observation = _r0_observation(registry)
    checks = _checks(observation, policy["thresholds"])
    status, blockers, next_step = _decision(checks)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_id": _report_id(registry["project_id"], registry, policy),
        "project_id": registry["project_id"],
        "generated_at": _canonical_timestamp(generated_at, "generated_at"),
        "mode": MODE,
        "automation_authorized": False,
        "pilot_authorized": False,
        "target_band": TARGET_BAND,
        "registry": {
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
        },
        "policy": {
            "policy_id": policy_id(policy),
            "policy_version": policy["policy_version"],
            "policy_sha256": policy_sha256(policy),
        },
        "observation": observation,
        "checks": checks,
        "status": status,
        "blockers": blockers,
        "source_reconciliation": {
            "required_before_pilot": True,
            "verified_in_this_stage": False,
        },
        "next_step": next_step,
        "report_sha256": "",
    }
    report["report_sha256"] = canonical_json_sha256(_without(report, "report_sha256"))
    errors = verify_report_data(report)
    if errors:
        raise TrustObservationVerificationError(errors)
    return report


def assess_observation(
    registry_path: str | Path,
    policy_path: str | Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    _, registry = load_registry(registry_path)
    _, policy = load_policy(policy_path)
    return evaluate_observation_data(registry, policy, generated_at=generated_at)


def verify_report_data(report: Any) -> list[str]:
    errors = _schema_errors(report, "trust-observation-report.schema.json")
    if not isinstance(report, dict):
        return sorted(set(errors or ["report must contain an object"]))
    if report.get("mode") != MODE:
        errors.append("mode must remain REPORT_ONLY")
    if report.get("automation_authorized") is not False:
        errors.append("automation_authorized must remain false")
    if report.get("pilot_authorized") is not False:
        errors.append("pilot_authorized must remain false")
    if report.get("target_band") != TARGET_BAND:
        errors.append("target_band must remain R0")
    if report.get("source_reconciliation") != {"required_before_pilot": True, "verified_in_this_stage": False}:
        errors.append("source reconciliation boundary mismatch")
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    expected_checks: list[dict[str, Any]] = []
    for item in checks:
        if not isinstance(item, dict):
            continue
        actual = item.get("actual")
        required = item.get("required")
        operator = item.get("operator")
        passed = False
        if actual is not None and isinstance(required, (int, float)):
            if operator == ">=":
                passed = actual >= required
            elif operator == "<=":
                passed = actual <= required
        normalized = deepcopy(item)
        normalized["passed"] = passed
        expected_checks.append(normalized)
    if checks != expected_checks:
        errors.append("threshold check projection mismatch")
    expected_status, expected_blockers, expected_next_step = _decision(expected_checks)
    if report.get("status") != expected_status:
        errors.append("status projection mismatch")
    if report.get("blockers") != expected_blockers:
        errors.append("blockers projection mismatch")
    if report.get("next_step") != expected_next_step:
        errors.append("next_step projection mismatch")
    registry = report.get("registry") if isinstance(report.get("registry"), dict) else {}
    policy = report.get("policy") if isinstance(report.get("policy"), dict) else {}
    identity = {
        "project_id": report.get("project_id"),
        "registry_id": registry.get("registry_id"),
        "registry_sha256": registry.get("registry_sha256"),
        "policy_id": policy.get("policy_id"),
        "policy_sha256": policy.get("policy_sha256"),
        "target_band": TARGET_BAND,
    }
    expected_id = f"trust-observation-{canonical_json_sha256(identity)[:32]}"
    if report.get("report_id") != expected_id:
        errors.append("report_id mismatch")
    expected_hash = canonical_json_sha256(_without(report, "report_sha256"))
    if report.get("report_sha256") != expected_hash:
        errors.append("report_sha256 mismatch")
    return sorted(set(errors))


def load_report(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "Trust observation report")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrustObservationError(f"cannot load Trust observation report: {exc}") from exc
    errors = verify_report_data(value)
    if errors:
        raise TrustObservationVerificationError(errors)
    return source, value


def verify_report_sources(
    report: dict[str, Any],
    *,
    registry_path: str | Path,
    policy_path: str | Path,
) -> list[str]:
    try:
        _, registry = load_registry(registry_path)
        _, policy = load_policy(policy_path)
        expected = evaluate_observation_data(registry, policy, generated_at=report["generated_at"])
    except (TrustObservationError, TrustObservationVerificationError, OSError, ValueError) as exc:
        return [str(exc)]
    errors: list[str] = []
    if report != expected:
        errors.append("observation report does not replay from registry and policy sources")
    return errors


def write_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_report_data(report)
    if errors:
        raise TrustObservationVerificationError(errors)
    return write_json_atomic(path, report)

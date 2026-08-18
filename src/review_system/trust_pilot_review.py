from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .io import load_data
from .paths import asset
from .trust_comparison import (
    TrustComparisonError,
    TrustComparisonVerificationError,
    load_registry,
)
from .trust_observation import (
    TrustObservationError,
    TrustObservationVerificationError,
    load_report as load_observation_report,
    verify_report_sources as verify_observation_report_sources,
)
from .trust_reconciliation import (
    TrustReconciliationError,
    TrustReconciliationVerificationError,
    load_reconciliation_report,
    verify_reconciliation_report_sources,
)


SCHEMA_VERSION = "1.0"
MODE = "REPORT_ONLY"
TARGET_BAND = "R0"
ELIGIBLE_STATUS = "ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW"
NOT_ELIGIBLE_STATUS = "NOT_ELIGIBLE"
THRESHOLDS_SATISFIED = "THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION"

CHECK_IDS = (
    "PROJECT_ID_MATCH",
    "REGISTRY_IDENTITY_MATCH",
    "RECONCILIATION_SOURCE_REPLAY",
    "OBSERVATION_SOURCE_REPLAY",
    "RECONCILIATION_COMPLETE",
    "NO_CONCLUSIVE_UNRECONCILED_OUTCOMES",
    "NO_CONCLUSIVE_DUPLICATE_AUTHORITY",
    "NO_CONCLUSIVE_UNSUPPORTED_SOURCE",
    "NO_CONCLUSIVE_PROVENANCE_UNVERIFIED",
    "OBSERVATION_THRESHOLDS_SATISFIED",
    "R0_FALSE_NEGATIVES_ZERO",
    "R0_FALSE_NEGATIVE_RATE_ZERO",
    "UNSAFE_CHALLENGE_EVIDENCE_PRESENT",
    "R0_AUDIT_COUNT_PROJECTION_MATCH",
    "VERIFIED_R0_INDEPENDENT_AUDIT_THRESHOLD",
)


class PilotSafetyReviewError(RuntimeError):
    pass


class PilotSafetyReviewVerificationError(PilotSafetyReviewError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid R0 pilot safety review report: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PilotSafetyReviewError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PilotSafetyReviewError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise PilotSafetyReviewError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        raise PilotSafetyReviewError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise PilotSafetyReviewError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise PilotSafetyReviewError(f"{field} must be a regular file: {resolved}")
    return resolved


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise PilotSafetyReviewError(f"output path must not contain symlinks: {target}")
    return target.resolve()


def _schema_errors(value: Any) -> list[str]:
    schema = load_data(asset("schemas/r0-pilot-safety-review-report.schema.json"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _report_payload(report: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(report)
    payload.pop("report_sha256", None)
    return payload


def _snapshot_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "mode": report.get("mode"),
        "automation_authorized": report.get("automation_authorized"),
        "pilot_authorized": report.get("pilot_authorized"),
        "target_band": report.get("target_band"),
        "sources": deepcopy(report.get("sources")),
        "source_replay": deepcopy(report.get("source_replay")),
        "reconciliation": deepcopy(report.get("reconciliation")),
        "observation": deepcopy(report.get("observation")),
        "checks": deepcopy(report.get("checks")),
        "blockers": deepcopy(report.get("blockers")),
        "status": report.get("status"),
        "next_step": report.get("next_step"),
    }


def _review_id(report: dict[str, Any], snapshot_sha256: str) -> str:
    key = {
        "project_id": report.get("project_id"),
        "registry_id": report.get("sources", {}).get("registry", {}).get("registry_id"),
        "registry_sha256": report.get("sources", {}).get("registry", {}).get("registry_sha256"),
        "reconciliation_report_sha256": report.get("sources", {}).get("reconciliation_report", {}).get("report_sha256"),
        "observation_report_sha256": report.get("sources", {}).get("observation_report", {}).get("report_sha256"),
        "evidence_snapshot_sha256": snapshot_sha256,
    }
    return f"r0-pilot-safety-review-{canonical_json_sha256(key)[:32]}"


def _checks(
    sources: dict[str, Any],
    source_replay: dict[str, bool],
    reconciliation: dict[str, Any],
    observation: dict[str, Any],
) -> list[dict[str, Any]]:
    registry = sources["registry"]
    reconciliation_source = sources["reconciliation_report"]
    observation_source = sources["observation_report"]
    project_match = (
        registry["project_id"] == reconciliation_source["project_id"] == observation_source["project_id"]
    )
    registry_match = (
        registry["registry_id"] == reconciliation_source["registry_id"] == observation_source["registry_id"]
        and registry["registry_sha256"] == reconciliation_source["registry_sha256"] == observation_source["registry_sha256"]
    )
    values = {
        "PROJECT_ID_MATCH": project_match,
        "REGISTRY_IDENTITY_MATCH": registry_match,
        "RECONCILIATION_SOURCE_REPLAY": source_replay["reconciliation_verified"],
        "OBSERVATION_SOURCE_REPLAY": source_replay["observation_verified"],
        "RECONCILIATION_COMPLETE": reconciliation["source_reconciliation_complete"] and reconciliation["status"] == "RECONCILED",
        "NO_CONCLUSIVE_UNRECONCILED_OUTCOMES": reconciliation["conclusive_outcome_unreconciled_count"] == 0,
        "NO_CONCLUSIVE_DUPLICATE_AUTHORITY": reconciliation["conclusive_duplicate_authority_count"] == 0,
        "NO_CONCLUSIVE_UNSUPPORTED_SOURCE": reconciliation["conclusive_unsupported_source_count"] == 0,
        "NO_CONCLUSIVE_PROVENANCE_UNVERIFIED": reconciliation["conclusive_provenance_unverified_count"] == 0,
        "OBSERVATION_THRESHOLDS_SATISFIED": observation["status"] == THRESHOLDS_SATISFIED,
        "R0_FALSE_NEGATIVES_ZERO": observation["r0_false_negative"] == 0,
        "R0_FALSE_NEGATIVE_RATE_ZERO": observation["r0_false_negative_rate"] == 0,
        "UNSAFE_CHALLENGE_EVIDENCE_PRESENT": observation["confirmed_unsafe_challenge_count"] > 0,
        "R0_AUDIT_COUNT_PROJECTION_MATCH": observation["r0_independent_audit_count"] == observation["registry_r0_independent_audit_assessment_count"],
        "VERIFIED_R0_INDEPENDENT_AUDIT_THRESHOLD": (
            reconciliation["verified_r0_independent_audit_assessment_count"] >= observation["minimum_r0_independent_audit_count"]
        ),
    }
    return [{"id": check_id, "passed": bool(values[check_id])} for check_id in CHECK_IDS]


def _decision(checks: list[dict[str, Any]]) -> tuple[str, list[str], str]:
    blockers = [item["id"] for item in checks if not item["passed"]]
    if not blockers:
        return ELIGIBLE_STATUS, [], "REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION"
    blocker_set = set(blockers)
    if blocker_set & {"NO_CONCLUSIVE_PROVENANCE_UNVERIFIED", "VERIFIED_R0_INDEPENDENT_AUDIT_THRESHOLD"}:
        return NOT_ELIGIBLE_STATUS, blockers, "ESTABLISH_INDEPENDENT_AUDIT_AUTHORITY"
    if blocker_set & {
        "PROJECT_ID_MATCH", "REGISTRY_IDENTITY_MATCH", "RECONCILIATION_SOURCE_REPLAY", "OBSERVATION_SOURCE_REPLAY",
    }:
        return NOT_ELIGIBLE_STATUS, blockers, "REPAIR_AND_REPLAY_SOURCE_EVIDENCE"
    if blocker_set & {
        "OBSERVATION_THRESHOLDS_SATISFIED", "R0_FALSE_NEGATIVES_ZERO", "R0_FALSE_NEGATIVE_RATE_ZERO",
        "UNSAFE_CHALLENGE_EVIDENCE_PRESENT", "R0_AUDIT_COUNT_PROJECTION_MATCH",
    }:
        return NOT_ELIGIBLE_STATUS, blockers, "RESOLVE_OBSERVATION_SAFETY_BLOCKERS"
    if blocker_set & {
        "RECONCILIATION_COMPLETE", "NO_CONCLUSIVE_UNRECONCILED_OUTCOMES",
        "NO_CONCLUSIVE_DUPLICATE_AUTHORITY", "NO_CONCLUSIVE_UNSUPPORTED_SOURCE",
    }:
        return NOT_ELIGIBLE_STATUS, blockers, "RESOLVE_SOURCE_RECONCILIATION_BLOCKERS"
    return NOT_ELIGIBLE_STATUS, blockers, "RESOLVE_PILOT_SAFETY_BLOCKERS"


def evaluate_pilot_review_data(
    *,
    project_id: str,
    sources: dict[str, Any],
    source_replay: dict[str, bool],
    reconciliation: dict[str, Any],
    observation: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    checks = _checks(sources, source_replay, reconciliation, observation)
    status, blockers, next_step = _decision(checks)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "review_id": "",
        "project_id": project_id,
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "mode": MODE,
        "automation_authorized": False,
        "pilot_authorized": False,
        "target_band": TARGET_BAND,
        "sources": deepcopy(sources),
        "source_replay": deepcopy(source_replay),
        "reconciliation": deepcopy(reconciliation),
        "observation": deepcopy(observation),
        "checks": checks,
        "blockers": blockers,
        "status": status,
        "next_step": next_step,
        "evidence_snapshot_sha256": "",
        "report_sha256": "",
    }
    report["evidence_snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(report))
    report["review_id"] = _review_id(report, report["evidence_snapshot_sha256"])
    report["report_sha256"] = canonical_json_sha256(_report_payload(report))
    errors = verify_pilot_review_report_data(report)
    if errors:
        raise PilotSafetyReviewVerificationError(errors)
    return report


def _r0_independent_audit_ids(registry: dict[str, Any]) -> set[str]:
    r0_ids = {
        item["assessment_id"]
        for item in registry.get("assessments", [])
        if item.get("predicted_risk_band") == TARGET_BAND
    }
    return {
        event["assessment_id"]
        for event in registry.get("events", [])
        if event.get("event_type") == "OUTCOME"
        and event.get("assessment_id") in r0_ids
        and event.get("payload", {}).get("outcome_type") == "INDEPENDENT_AUDIT"
        and event.get("payload", {}).get("verdict") in {"SAFE", "UNSAFE"}
    }


def _reconciliation_projection(reconciliation_report: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    conclusive = [item for item in reconciliation_report["outcome_reconciliation"] if item["conclusive"]]
    r0_audit_ids = _r0_independent_audit_ids(registry)
    verified_audit_ids = {
        item["assessment_id"]
        for item in conclusive
        if item["assessment_id"] in r0_audit_ids
        and item["outcome_type"] == "INDEPENDENT_AUDIT"
        and item["reconciled"]
    }
    summary = reconciliation_report["summary"]
    return {
        "status": reconciliation_report["status"],
        "source_reconciliation_complete": summary["source_reconciliation_complete"],
        "assessment_unreconciled_count": summary["assessment_unreconciled_count"],
        "conclusive_outcome_count": len(conclusive),
        "conclusive_outcome_unreconciled_count": sum(1 for item in conclusive if not item["reconciled"]),
        "conclusive_duplicate_authority_count": sum(1 for item in conclusive if item["status"] == "DUPLICATE_AUTHORITY"),
        "conclusive_unsupported_source_count": sum(1 for item in conclusive if item["status"] == "UNSUPPORTED_SOURCE"),
        "conclusive_provenance_unverified_count": sum(1 for item in conclusive if item["status"] == "PROVENANCE_UNVERIFIED"),
        "verified_r0_independent_audit_assessment_count": len(verified_audit_ids),
    }


def _observation_projection(observation_report: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    observation = observation_report["observation"]
    thresholds = observation_report["policy"]["thresholds"]
    return {
        "status": observation_report["status"],
        "r0_false_negative": observation["r0_false_negative"],
        "r0_false_negative_rate": observation["r0_false_negative_rate"],
        "confirmed_unsafe_challenge_count": observation["confirmed_unsafe_challenge_count"],
        "r0_independent_audit_count": observation["r0_independent_audit_count"],
        "registry_r0_independent_audit_assessment_count": len(_r0_independent_audit_ids(registry)),
        "minimum_r0_independent_audit_count": thresholds["minimum_r0_independent_audit_count"],
    }


def review_r0_pilot(
    *,
    registry_path: str | Path,
    reconciliation_report_path: str | Path,
    reconciliation_sources_path: str | Path,
    observation_report_path: str | Path,
    observation_policy_path: str | Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    try:
        registry_source, registry = load_registry(registry_path)
        reconciliation_source, reconciliation_report = load_reconciliation_report(reconciliation_report_path)
        observation_source, observation_report = load_observation_report(observation_report_path)
    except (
        TrustComparisonError,
        TrustComparisonVerificationError,
        TrustReconciliationError,
        TrustReconciliationVerificationError,
        TrustObservationError,
        TrustObservationVerificationError,
        OSError,
        ValueError,
    ) as exc:
        raise PilotSafetyReviewError(str(exc)) from exc

    reconciliation_replay_errors = verify_reconciliation_report_sources(
        reconciliation_report,
        registry_path=registry_source,
        source_manifest_path=reconciliation_sources_path,
    )
    observation_replay_errors = verify_observation_report_sources(
        observation_report,
        registry_path=registry_source,
        policy_path=observation_policy_path,
    )

    sources = {
        "registry": {
            "source": registry_source.name,
            "project_id": registry["project_id"],
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
        },
        "reconciliation_report": {
            "source": reconciliation_source.name,
            "project_id": reconciliation_report["project_id"],
            "report_id": reconciliation_report["report_id"],
            "report_sha256": reconciliation_report["report_sha256"],
            "evidence_snapshot_sha256": reconciliation_report["evidence_snapshot_sha256"],
            "registry_id": reconciliation_report["comparison_registry"]["registry_id"],
            "registry_sha256": reconciliation_report["comparison_registry"]["registry_sha256"],
        },
        "reconciliation_sources": {
            "source": Path(reconciliation_sources_path).name,
            "manifest_sha256": reconciliation_report["source_manifest"]["manifest_sha256"],
        },
        "observation_report": {
            "source": observation_source.name,
            "project_id": observation_report["project_id"],
            "report_id": observation_report["report_id"],
            "report_sha256": observation_report["report_sha256"],
            "registry_id": observation_report["registry"]["registry_id"],
            "registry_sha256": observation_report["registry"]["registry_sha256"],
        },
        "observation_policy": {
            "source": Path(observation_policy_path).name,
            "policy_id": observation_report["policy"]["policy_id"],
            "policy_sha256": observation_report["policy"]["policy_sha256"],
        },
    }
    source_replay = {
        "reconciliation_verified": not reconciliation_replay_errors,
        "observation_verified": not observation_replay_errors,
    }
    return evaluate_pilot_review_data(
        project_id=registry["project_id"],
        sources=sources,
        source_replay=source_replay,
        reconciliation=_reconciliation_projection(reconciliation_report, registry),
        observation=_observation_projection(observation_report, registry),
        generated_at=generated_at,
    )


def verify_pilot_review_report_data(report: Any) -> list[str]:
    errors = _schema_errors(report)
    if not isinstance(report, dict):
        return sorted(set(errors or ["report must contain an object"]))
    if errors:
        return sorted(set(errors))
    try:
        if report.get("mode") != MODE:
            errors.append("mode must remain REPORT_ONLY")
        if report.get("automation_authorized") is not False:
            errors.append("automation_authorized must remain false")
        if report.get("pilot_authorized") is not False:
            errors.append("pilot_authorized must remain false")
        if report.get("target_band") != TARGET_BAND:
            errors.append("target_band must remain R0")
        sources = report["sources"]
        source_replay = report["source_replay"]
        reconciliation = report["reconciliation"]
        observation = report["observation"]
        expected_checks = _checks(sources, source_replay, reconciliation, observation)
        if report.get("checks") != expected_checks:
            errors.append("safety check projection mismatch")
        if [item["id"] for item in expected_checks] != list(CHECK_IDS):
            errors.append("safety check set mismatch")
        expected_status, expected_blockers, expected_next_step = _decision(expected_checks)
        if report.get("status") != expected_status:
            errors.append("status projection mismatch")
        if report.get("blockers") != expected_blockers:
            errors.append("blockers projection mismatch")
        if report.get("next_step") != expected_next_step:
            errors.append("next_step projection mismatch")
        if report.get("project_id") != sources["registry"]["project_id"]:
            errors.append("project_id must derive from registry authority")
        expected_snapshot = canonical_json_sha256(_snapshot_payload(report))
        if report.get("evidence_snapshot_sha256") != expected_snapshot:
            errors.append("evidence_snapshot_sha256 mismatch")
        expected_id = _review_id(report, expected_snapshot)
        if report.get("review_id") != expected_id:
            errors.append("review_id mismatch")
        expected_hash = canonical_json_sha256(_report_payload(report))
        if report.get("report_sha256") != expected_hash:
            errors.append("report_sha256 mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"report structure invalid: {exc}")
    return sorted(set(errors))


def load_pilot_review_report(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "R0 pilot safety review report")
    try:
        value = load_data(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PilotSafetyReviewError(f"cannot load R0 pilot safety review report: {exc}") from exc
    errors = verify_pilot_review_report_data(value)
    if errors:
        raise PilotSafetyReviewVerificationError(errors)
    return source, value


def verify_pilot_review_report_sources(
    report: dict[str, Any],
    *,
    registry_path: str | Path,
    reconciliation_report_path: str | Path,
    reconciliation_sources_path: str | Path,
    observation_report_path: str | Path,
    observation_policy_path: str | Path,
) -> list[str]:
    errors = verify_pilot_review_report_data(report)
    if errors:
        return errors
    try:
        replay = review_r0_pilot(
            registry_path=registry_path,
            reconciliation_report_path=reconciliation_report_path,
            reconciliation_sources_path=reconciliation_sources_path,
            observation_report_path=observation_report_path,
            observation_policy_path=observation_policy_path,
            generated_at=report["generated_at"],
        )
    except (PilotSafetyReviewError, OSError, ValueError) as exc:
        return [f"source replay failed: {exc}"]
    fields = (
        "project_id", "sources", "source_replay", "reconciliation", "observation", "checks",
        "blockers", "status", "next_step", "evidence_snapshot_sha256", "review_id", "report_sha256",
    )
    return [f"source replay {field} mismatch" for field in fields if replay.get(field) != report.get(field)]


def write_pilot_review_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_pilot_review_report_data(report)
    if errors:
        raise PilotSafetyReviewVerificationError(errors)
    target = _safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise PilotSafetyReviewError(f"cannot write R0 pilot safety review report: {exc}") from exc
    return target

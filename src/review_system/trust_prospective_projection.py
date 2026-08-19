from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .io import load_data
from .paths import asset
from .trust_evidence_acquisition import (
    load_acquisition_report, populate_r0_evidence_package,
    verify_acquisition_report_sources, write_acquisition_report,
)
from .trust_observation import (
    evaluate_observation_data, policy_id, policy_sha256, verify_policy_data,
)
from .trust_reconciliation_authority import reconcile_sources
from .trust_prospective_common import (
    CAMPAIGN_CONTRACT, CHECK_SPECS, MODE, SAFETY_CHECK_IDS, SCHEMA_VERSION, TARGET_BAND,
    ProspectiveEvidenceError, ProspectiveEvidenceVerificationError,
    _json_bytes, _path_has_symlink, _replace_one, _required_workspace, _safe_root,
    _timestamp, utc_now,
)


def _campaign_status(observation: dict[str, Any], reconciliation: dict[str, Any]) -> tuple[str, str]:
    if not reconciliation["summary"]["source_reconciliation_complete"]:
        return "BLOCKED_SOURCE_RECONCILIATION", "REPAIR_SOURCE_RECONCILIATION"
    if observation["status"] == "THRESHOLD_BLOCKED":
        return "BLOCKED_SAFETY_SIGNAL", observation["next_step"]
    if observation["status"] == "THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION":
        return "READY_FOR_STAGE_10G_REPLAY", "CREATE_IMMUTABLE_CAMPAIGN_SNAPSHOT"
    return "COLLECTING_EVIDENCE", observation["next_step"]


def _schema_errors(value: Any) -> list[str]:
    schema = load_data(asset("schemas/r0-prospective-evidence-campaign-report.schema.json"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(error.message for error in validator.iter_errors(value))


def _without(value: dict[str, Any], field: str) -> dict[str, Any]:
    output = deepcopy(value)
    output.pop(field, None)
    return output


def _project_checks(observation: dict[str, Any], thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for check_id, metric, threshold, operator in CHECK_SPECS:
        actual = observation.get(metric)
        required = thresholds.get(threshold)
        if operator == ">=":
            passed = actual is not None and required is not None and actual >= required
        else:
            passed = actual is not None and required is not None and actual <= required
        output.append({"id": check_id, "actual": actual, "operator": operator, "required": required, "passed": passed})
    return output


def _project_campaign_status(report: dict[str, Any], checks: list[dict[str, Any]]) -> tuple[str, str]:
    if not report["reconciliation"]["source_reconciliation_complete"]:
        return "BLOCKED_SOURCE_RECONCILIATION", "REPAIR_SOURCE_RECONCILIATION"
    harmful = any(
        item["id"] in SAFETY_CHECK_IDS
        and item["actual"] is not None
        and item["required"] is not None
        and item["actual"] > item["required"]
        for item in checks
    )
    if harmful:
        return "BLOCKED_SAFETY_SIGNAL", "INVESTIGATE_CONFIRMED_FALSE_NEGATIVES"
    if all(item["passed"] for item in checks):
        return "READY_FOR_STAGE_10G_REPLAY", "CREATE_IMMUTABLE_CAMPAIGN_SNAPSHOT"
    return "COLLECTING_EVIDENCE", "COLLECT_MORE_CONFIRMED_OBSERVATION"


def verify_campaign_report_data(report: Any) -> list[str]:
    errors = _schema_errors(report)
    if not isinstance(report, dict) or errors:
        return sorted(set(errors or ["campaign report must be an object"]))
    if report.get("mode") != MODE or report.get("automation_authorized") is not False or report.get("pilot_authorized") is not False:
        errors.append("campaign safety boundary mismatch")
    if report.get("target_band") != TARGET_BAND:
        errors.append("campaign target_band must remain R0")

    policy_ref = report["policy"]
    policy = {
        "schema_version": "1.0",
        "policy_version": policy_ref.get("policy_version"),
        "mode": MODE,
        "target_band": TARGET_BAND,
        "thresholds": deepcopy(policy_ref.get("thresholds")),
    }
    policy_errors = verify_policy_data(policy)
    errors.extend(f"embedded policy: {item}" for item in policy_errors)
    if not policy_errors:
        if policy_ref.get("policy_id") != policy_id(policy):
            errors.append("embedded policy_id mismatch")
        if policy_ref.get("policy_sha256") != policy_sha256(policy):
            errors.append("embedded policy_sha256 mismatch")

    expected_checks = _project_checks(report["observation"], policy_ref["thresholds"])
    if report.get("checks") != expected_checks:
        errors.append("threshold check projection mismatch")
    expected_status, expected_next = _project_campaign_status(report, expected_checks)
    if report.get("status") != expected_status:
        errors.append("campaign status projection mismatch")
    if report.get("next_step") != expected_next:
        errors.append("campaign next_step projection mismatch")

    observation = report["observation"]
    if observation["r0_confirmed_safe_count"] != observation["r0_true_negative"]:
        errors.append("R0 confirmed-safe projection mismatch")
    if observation["r0_conclusive_outcome_count"] != observation["r0_true_negative"] + observation["r0_false_negative"]:
        errors.append("R0 conclusive projection mismatch")
    if observation["confirmed_unsafe_challenge_count"] != observation["r0_true_positive"] + observation["r0_false_negative"]:
        errors.append("unsafe challenge projection mismatch")
    assessment_count = observation["r0_assessment_count"]
    expected_coverage = observation["r0_conclusive_outcome_count"] / assessment_count if assessment_count else None
    if observation["r0_outcome_coverage"] != expected_coverage:
        errors.append("R0 outcome coverage projection mismatch")
    unsafe_denominator = observation["r0_true_positive"] + observation["r0_false_negative"]
    expected_fnr = observation["r0_false_negative"] / unsafe_denominator if unsafe_denominator else None
    if observation["r0_false_negative_rate"] != expected_fnr:
        errors.append("R0 false-negative-rate projection mismatch")

    snapshot = {
        "schema_version": report["schema_version"],
        "campaign_contract": report["campaign_contract"],
        "project_id": report["project_id"],
        "mode": report["mode"],
        "target_band": report["target_band"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "registry": report["registry"],
        "policy": report["policy"],
        "reconciliation": report["reconciliation"],
        "observation": report["observation"],
        "checks": report["checks"],
        "status": report["status"],
        "next_step": report["next_step"],
    }
    expected_snapshot = canonical_json_sha256(snapshot)
    if report.get("evidence_snapshot_sha256") != expected_snapshot:
        errors.append("evidence_snapshot_sha256 mismatch")
    expected_id = f"r0-prospective-campaign-{canonical_json_sha256({'project_id': report['project_id'], 'snapshot': expected_snapshot})[:32]}"
    if report.get("campaign_id") != expected_id:
        errors.append("campaign_id mismatch")
    if report.get("report_sha256") != canonical_json_sha256(_without(report, "report_sha256")):
        errors.append("report_sha256 mismatch")
    return sorted(set(errors))



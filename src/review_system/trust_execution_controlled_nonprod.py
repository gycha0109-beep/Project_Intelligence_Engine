from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .io import load_data
from .paths import asset


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "TRUST_CONTROLLED_NON_PRODUCTION_EXECUTION_CALIBRATION_V1"
MODE = "CONTROLLED_NON_PRODUCTION_CALIBRATION"
CAPABILITY_CLASS = "GITHUB_PR_MUTATION"
OPERATION = "MARK_READY_FOR_REVIEW"
ROLLBACK_OPERATION = "CONVERT_TO_DRAFT"
AUTHORIZATION_BASIS = "EXPLICIT_HUMAN_BOUNDARY_AUTHORIZATION"
STATUS_PASS = "CONTROLLED_NON_PRODUCTION_CALIBRATION_PASS"
STATUS_BLOCKED = "BLOCKED"
NEXT_PASS = "PEB3_CALIBRATION_COMPLETE_AWAIT_NEXT_AUTHORIZATION_BOUNDARY"
NEXT_SCOPE = "ESTABLISH_TARGET_SCOPED_NON_PRODUCTION_CREDENTIAL"

_SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ControlledNonProductionExecutionError(RuntimeError):
    pass


class ControlledNonProductionExecutionVerificationError(ControlledNonProductionExecutionError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid controlled non-production execution report: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ControlledNonProductionExecutionError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlledNonProductionExecutionError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise ControlledNonProductionExecutionError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ControlledNonProductionExecutionError(f"{field} must be a non-empty string")
    return value.strip()


def _sha40(value: Any, field: str) -> str:
    text = _non_empty(value, field).lower()
    if _SHA40.fullmatch(text) is None:
        raise ControlledNonProductionExecutionError(f"{field} must be a 40-character lowercase SHA")
    return text


def _schema_errors(value: Any) -> list[str]:
    schema = load_data(asset("schemas/controlled-nonprod-execution-calibration-report.schema.json"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _payload(value: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(value)
    payload.pop("report_sha256", None)
    return payload


def _snapshot(value: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(value)
    payload.pop("evidence_snapshot_sha256", None)
    payload.pop("generated_at", None)
    return payload


def _expected_blockers(value: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    pre_dispatch = value.get("pre_dispatch") if isinstance(value.get("pre_dispatch"), dict) else {}
    for key, blocker in (
        ("source_head_exact", "SOURCE_HEAD_NOT_EXACT"),
        ("target_precondition_exact", "TARGET_PRECONDITION_NOT_EXACT"),
        ("kill_switch_clear", "KILL_SWITCH_NOT_CLEAR"),
        ("rollback_ready", "ROLLBACK_NOT_READY"),
    ):
        if pre_dispatch.get(key) is not True:
            blockers.append(blocker)

    dispatch = value.get("dispatch") if isinstance(value.get("dispatch"), dict) else {}
    if dispatch.get("attempted") is not True:
        blockers.append("CONTROLLED_DISPATCH_NOT_ATTEMPTED")
    if dispatch.get("postcondition_verified") is not True:
        blockers.append("CONTROLLED_DISPATCH_POSTCONDITION_NOT_VERIFIED")

    rollback = value.get("rollback") if isinstance(value.get("rollback"), dict) else {}
    if rollback.get("attempted") is not True:
        blockers.append("ROLLBACK_NOT_ATTEMPTED")
    if rollback.get("postcondition_verified") is not True:
        blockers.append("ROLLBACK_POSTCONDITION_NOT_VERIFIED")
    if rollback.get("final_target_state_restored") is not True:
        blockers.append("FINAL_TARGET_STATE_NOT_RESTORED")

    credential_scope = value.get("credential_scope") if isinstance(value.get("credential_scope"), dict) else {}
    if credential_scope.get("target_scoped") is not True or credential_scope.get("proven") is not True:
        blockers.append("TARGET_SCOPED_CREDENTIAL_NOT_PROVEN")

    return sorted(set(blockers))


def build_controlled_nonprod_report(
    *,
    calibration_id: str,
    project_id: str,
    source_main_sha: str,
    target_repository: str,
    target_pr_number: int,
    target_head_sha: str,
    authorization_id: str,
    authorization_ref: str,
    dispatch_updated_at: str,
    rollback_updated_at: str,
    credential_scope_proven: bool,
    credential_scope_evidence_ref: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if not isinstance(target_pr_number, int) or target_pr_number <= 0:
        raise ControlledNonProductionExecutionError("target_pr_number must be a positive integer")
    source_sha = _sha40(source_main_sha, "source_main_sha")
    target_sha = _sha40(target_head_sha, "target_head_sha")
    dispatch_time = _timestamp(dispatch_updated_at, "dispatch_updated_at")
    rollback_time = _timestamp(rollback_updated_at, "rollback_updated_at")
    target_scoped = bool(credential_scope_proven)
    evidence_ref = None
    if credential_scope_evidence_ref is not None:
        evidence_ref = _non_empty(credential_scope_evidence_ref, "credential_scope_evidence_ref")

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "calibration_id": _non_empty(calibration_id, "calibration_id"),
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "mode": MODE,
        "project_id": _non_empty(project_id, "project_id"),
        "source_main_sha": source_sha,
        "production_execution_authorized": False,
        "non_production_execution_authorized": True,
        "automation_authorized": False,
        "pilot_authorized": False,
        "target": {
            "provider": "GITHUB",
            "repository": _non_empty(target_repository, "target_repository"),
            "resource_type": "PULL_REQUEST",
            "resource_id": str(target_pr_number),
            "environment": "NON_PRODUCTION_CALIBRATION",
            "head_sha": target_sha,
            "initial_state": "DRAFT",
        },
        "capability": {
            "class": CAPABILITY_CLASS,
            "operation": OPERATION,
            "rollback_operation": ROLLBACK_OPERATION,
        },
        "authorization": {
            "required": True,
            "basis": AUTHORIZATION_BASIS,
            "authorization_id": _non_empty(authorization_id, "authorization_id"),
            "authorization_ref": _non_empty(authorization_ref, "authorization_ref"),
        },
        "pre_dispatch": {
            "source_head_exact": True,
            "target_precondition_exact": True,
            "kill_switch_clear": True,
            "rollback_ready": True,
        },
        "dispatch": {
            "attempted": True,
            "provider_response": {
                "state": "open",
                "draft": False,
                "head_sha": target_sha,
                "updated_at": dispatch_time,
            },
            "postcondition_readback": {
                "state": "open",
                "draft": False,
                "head_sha": target_sha,
            },
            "postcondition_verified": True,
        },
        "rollback": {
            "attempted": True,
            "provider_response": {
                "state": "open",
                "draft": True,
                "head_sha": target_sha,
                "updated_at": rollback_time,
            },
            "postcondition_readback": {
                "state": "open",
                "draft": True,
                "head_sha": target_sha,
            },
            "postcondition_verified": True,
            "final_target_state_restored": True,
        },
        "credential_scope": {
            "transport": "CONNECTED_GITHUB_ACCOUNT",
            "target_scoped": target_scoped,
            "proven": bool(credential_scope_proven),
            "evidence_ref": evidence_ref,
        },
        "blockers": [],
        "status": STATUS_PASS,
        "next_step": NEXT_PASS,
        "evidence_snapshot_sha256": "",
        "report_sha256": "",
    }
    blockers = _expected_blockers(report)
    report["blockers"] = blockers
    if blockers:
        report["status"] = STATUS_BLOCKED
        report["next_step"] = NEXT_SCOPE if blockers == ["TARGET_SCOPED_CREDENTIAL_NOT_PROVEN"] else "REMEDIATE_CONTROLLED_NON_PRODUCTION_EXECUTION_EVIDENCE"
    snapshot = canonical_json_sha256(_snapshot(report))
    report["evidence_snapshot_sha256"] = snapshot
    report["report_sha256"] = canonical_json_sha256(_payload(report))
    errors = verify_controlled_nonprod_report_data(report)
    if errors:
        raise ControlledNonProductionExecutionVerificationError(errors)
    return report


def verify_controlled_nonprod_report_data(value: Any) -> list[str]:
    errors = _schema_errors(value)
    if not isinstance(value, dict):
        return sorted(set(errors or ["report must contain an object"]))
    try:
        if value.get("contract_version") != CONTRACT_VERSION:
            errors.append("contract_version mismatch")
        if value.get("mode") != MODE:
            errors.append("mode mismatch")
        if value.get("production_execution_authorized") is not False:
            errors.append("production_execution_authorized must remain false")
        if value.get("non_production_execution_authorized") is not True:
            errors.append("non_production_execution_authorized must be true for this calibration artifact")
        if value.get("automation_authorized") is not False:
            errors.append("automation_authorized must remain false")
        if value.get("pilot_authorized") is not False:
            errors.append("pilot_authorized must remain false")

        target = value.get("target") if isinstance(value.get("target"), dict) else {}
        if target.get("provider") != "GITHUB":
            errors.append("target.provider must remain GITHUB")
        if target.get("resource_type") != "PULL_REQUEST":
            errors.append("target.resource_type must remain PULL_REQUEST")
        if target.get("environment") != "NON_PRODUCTION_CALIBRATION":
            errors.append("target.environment must remain NON_PRODUCTION_CALIBRATION")
        target_head = target.get("head_sha")
        if not isinstance(target_head, str) or _SHA40.fullmatch(target_head) is None:
            errors.append("target.head_sha must be an exact 40-character SHA")
        if target.get("initial_state") != "DRAFT":
            errors.append("target.initial_state must remain DRAFT")

        capability = value.get("capability") if isinstance(value.get("capability"), dict) else {}
        if capability != {
            "class": CAPABILITY_CLASS,
            "operation": OPERATION,
            "rollback_operation": ROLLBACK_OPERATION,
        }:
            errors.append("capability projection mismatch")

        authorization = value.get("authorization") if isinstance(value.get("authorization"), dict) else {}
        if authorization.get("required") is not True or authorization.get("basis") != AUTHORIZATION_BASIS:
            errors.append("authorization basis mismatch")
        if not isinstance(authorization.get("authorization_id"), str) or not authorization.get("authorization_id", "").strip():
            errors.append("authorization.authorization_id is required")
        if not isinstance(authorization.get("authorization_ref"), str) or not authorization.get("authorization_ref", "").strip():
            errors.append("authorization.authorization_ref is required")

        dispatch = value.get("dispatch") if isinstance(value.get("dispatch"), dict) else {}
        dispatch_response = dispatch.get("provider_response") if isinstance(dispatch.get("provider_response"), dict) else {}
        dispatch_readback = dispatch.get("postcondition_readback") if isinstance(dispatch.get("postcondition_readback"), dict) else {}
        if dispatch_response.get("state") != "open" or dispatch_response.get("draft") is not False:
            errors.append("dispatch provider response must show ready/open state")
        if dispatch_readback.get("state") != "open" or dispatch_readback.get("draft") is not False:
            errors.append("dispatch postcondition readback must independently show ready/open state")
        if target_head and (dispatch_response.get("head_sha") != target_head or dispatch_readback.get("head_sha") != target_head):
            errors.append("dispatch head_sha must remain target-bound")

        rollback = value.get("rollback") if isinstance(value.get("rollback"), dict) else {}
        rollback_response = rollback.get("provider_response") if isinstance(rollback.get("provider_response"), dict) else {}
        rollback_readback = rollback.get("postcondition_readback") if isinstance(rollback.get("postcondition_readback"), dict) else {}
        if rollback_response.get("state") != "open" or rollback_response.get("draft") is not True:
            errors.append("rollback provider response must show restored draft/open state")
        if rollback_readback.get("state") != "open" or rollback_readback.get("draft") is not True:
            errors.append("rollback postcondition readback must independently show restored draft/open state")
        if target_head and (rollback_response.get("head_sha") != target_head or rollback_readback.get("head_sha") != target_head):
            errors.append("rollback head_sha must remain target-bound")

        expected_blockers = _expected_blockers(value)
        if value.get("blockers") != expected_blockers:
            errors.append("blockers projection mismatch")
        expected_status = STATUS_PASS if not expected_blockers else STATUS_BLOCKED
        if value.get("status") != expected_status:
            errors.append("status projection mismatch")
        expected_next = NEXT_PASS
        if expected_blockers:
            expected_next = NEXT_SCOPE if expected_blockers == ["TARGET_SCOPED_CREDENTIAL_NOT_PROVEN"] else "REMEDIATE_CONTROLLED_NON_PRODUCTION_EXECUTION_EVIDENCE"
        if value.get("next_step") != expected_next:
            errors.append("next_step projection mismatch")

        snapshot = canonical_json_sha256(_snapshot(value))
        if value.get("evidence_snapshot_sha256") != snapshot:
            errors.append("evidence_snapshot_sha256 mismatch")
        if value.get("report_sha256") != canonical_json_sha256(_payload(value)):
            errors.append("report_sha256 mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"controlled non-production semantic verification failed: {exc}")
    return sorted(set(errors))

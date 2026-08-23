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
CONTRACT_VERSION = "TRUST_PRODUCTION_EXECUTION_AUTHORIZATION_REVIEW_V1"
STAGE = "PEB-4A"
MODE = "PRODUCTION_EXECUTION_AUTHORIZATION_REVIEW"

STATUS_BLOCKED = "BLOCKED"
STATUS_READY = "PRODUCTION_EFFECT_AUTHORIZATION_REQUEST_READY"
NEXT_BLOCKED = "NOMINATE_PRODUCTION_TARGET_AND_COMPLETE_SAFETY_EVIDENCE"
NEXT_READY = "PEB4B_EXPLICIT_ONE_SHOT_EFFECT_AUTHORIZATION_REQUIRED"

AUTHORIZATION_BASIS = "EXPLICIT_HUMAN_PRODUCTION_BOUNDARY_AUTHORIZATION"

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ProductionExecutionAuthorizationError(RuntimeError):
    pass


class ProductionExecutionAuthorizationVerificationError(ProductionExecutionAuthorizationError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid production execution authorization review: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductionExecutionAuthorizationError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProductionExecutionAuthorizationError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise ProductionExecutionAuthorizationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductionExecutionAuthorizationError(f"{field} must be a non-empty string")
    return value.strip()


def _sha40(value: Any, field: str) -> str:
    text = _non_empty(value, field).lower()
    if _SHA40.fullmatch(text) is None:
        raise ProductionExecutionAuthorizationError(f"{field} must be a 40-character lowercase SHA")
    return text


def _schema_errors(value: Any) -> list[str]:
    schema = load_data(asset("schemas/production-execution-authorization-review.schema.json"))
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


def _request_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": value["project_id"],
        "source_main_sha": value["source_main_sha"],
        "request": deepcopy(value["request"]),
        "preconditions": deepcopy(value["preconditions"]),
    }


def _expected_blockers(value: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if value.get("production_boundary_authorized") is not True:
        blockers.append("PRODUCTION_BOUNDARY_AUTHORIZATION_REQUIRED")

    request = value.get("request") if isinstance(value.get("request"), dict) else {}
    pre = value.get("preconditions") if isinstance(value.get("preconditions"), dict) else {}

    checks = (
        ("trust_decision_bound", "TRUST_DECISION_BINDING_NOT_PROVEN"),
        ("target_nominated", "PRODUCTION_TARGET_NOT_NOMINATED"),
        ("operation_nominated", "PRODUCTION_OPERATION_NOT_NOMINATED"),
        ("action_payload_bound", "PRODUCTION_ACTION_PAYLOAD_NOT_BOUND"),
        ("target_precondition_bound", "PRODUCTION_TARGET_PRECONDITION_NOT_BOUND"),
        ("credential_scope_proven", "PRODUCTION_CREDENTIAL_SCOPE_NOT_PROVEN"),
        ("rollback_proven", "PRODUCTION_ROLLBACK_NOT_PROVEN"),
        ("postcondition_verifier_proven", "PRODUCTION_POSTCONDITION_VERIFIER_NOT_PROVEN"),
        ("blast_radius_bounded", "PRODUCTION_BLAST_RADIUS_NOT_BOUNDED"),
        ("kill_switch_proven", "PRODUCTION_KILL_SWITCH_NOT_PROVEN"),
        ("recovery_window_proven", "PRODUCTION_RECOVERY_WINDOW_NOT_PROVEN"),
    )
    for key, blocker in checks:
        if pre.get(key) is not True:
            blockers.append(blocker)

    if pre.get("trust_decision_bound") is True:
        if not request.get("trust_report_id") or not request.get("trust_report_sha256") or not request.get("trust_risk_band"):
            blockers.append("TRUST_DECISION_BINDING_INCOMPLETE")
    if pre.get("target_nominated") is True:
        if not request.get("target_provider") or not request.get("target_resource"):
            blockers.append("PRODUCTION_TARGET_BINDING_INCOMPLETE")
    if pre.get("operation_nominated") is True:
        if not request.get("capability_class") or not request.get("operation") or not request.get("rollback_operation"):
            blockers.append("PRODUCTION_OPERATION_BINDING_INCOMPLETE")
    if pre.get("action_payload_bound") is True and not request.get("action_payload_sha256"):
        blockers.append("PRODUCTION_ACTION_PAYLOAD_BINDING_INCOMPLETE")
    if pre.get("target_precondition_bound") is True and not request.get("target_precondition_fingerprint"):
        blockers.append("PRODUCTION_TARGET_PRECONDITION_BINDING_INCOMPLETE")

    evidence_checks = (
        ("credential_scope_proven", "credential_scope_evidence_ref", "PRODUCTION_CREDENTIAL_SCOPE_EVIDENCE_MISSING"),
        ("rollback_proven", "rollback_evidence_ref", "PRODUCTION_ROLLBACK_EVIDENCE_MISSING"),
        ("postcondition_verifier_proven", "postcondition_verifier_ref", "PRODUCTION_POSTCONDITION_VERIFIER_EVIDENCE_MISSING"),
        ("blast_radius_bounded", "blast_radius_evidence_ref", "PRODUCTION_BLAST_RADIUS_EVIDENCE_MISSING"),
        ("kill_switch_proven", "kill_switch_evidence_ref", "PRODUCTION_KILL_SWITCH_EVIDENCE_MISSING"),
        ("recovery_window_proven", "recovery_window_evidence_ref", "PRODUCTION_RECOVERY_WINDOW_EVIDENCE_MISSING"),
    )
    for pre_key, request_key, blocker in evidence_checks:
        if pre.get(pre_key) is True and not request.get(request_key):
            blockers.append(blocker)

    return sorted(set(blockers))


def build_production_authorization_review(
    *,
    review_id: str,
    project_id: str,
    source_main_sha: str,
    boundary_authorization_id: str | None,
    boundary_authorization_ref: str | None,
    trust_report_id: str | None = None,
    trust_report_sha256: str | None = None,
    trust_risk_band: str | None = None,
    target_provider: str | None = None,
    target_resource: str | None = None,
    capability_class: str | None = None,
    operation: str | None = None,
    rollback_operation: str | None = None,
    action_payload_sha256: str | None = None,
    target_precondition_fingerprint: str | None = None,
    credential_scope_evidence_ref: str | None = None,
    rollback_evidence_ref: str | None = None,
    postcondition_verifier_ref: str | None = None,
    blast_radius_evidence_ref: str | None = None,
    kill_switch_evidence_ref: str | None = None,
    recovery_window_evidence_ref: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    source_sha = _sha40(source_main_sha, "source_main_sha")
    boundary_authorized = bool(boundary_authorization_id and boundary_authorization_ref)

    request: dict[str, Any] = {
        "environment": "PRODUCTION",
        "trust_report_id": trust_report_id,
        "trust_report_sha256": trust_report_sha256,
        "trust_risk_band": trust_risk_band,
        "target_provider": target_provider,
        "target_resource": target_resource,
        "capability_class": capability_class,
        "operation": operation,
        "rollback_operation": rollback_operation,
        "action_payload_sha256": action_payload_sha256,
        "target_precondition_fingerprint": target_precondition_fingerprint,
        "credential_scope_evidence_ref": credential_scope_evidence_ref,
        "rollback_evidence_ref": rollback_evidence_ref,
        "postcondition_verifier_ref": postcondition_verifier_ref,
        "blast_radius_evidence_ref": blast_radius_evidence_ref,
        "kill_switch_evidence_ref": kill_switch_evidence_ref,
        "recovery_window_evidence_ref": recovery_window_evidence_ref,
    }

    preconditions = {
        "source_head_exact": True,
        "trust_decision_bound": bool(trust_report_id and trust_report_sha256 and trust_risk_band),
        "target_nominated": bool(target_provider and target_resource),
        "operation_nominated": bool(capability_class and operation and rollback_operation),
        "action_payload_bound": bool(action_payload_sha256),
        "target_precondition_bound": bool(target_precondition_fingerprint),
        "credential_scope_proven": bool(credential_scope_evidence_ref),
        "rollback_proven": bool(rollback_evidence_ref),
        "postcondition_verifier_proven": bool(postcondition_verifier_ref),
        "blast_radius_bounded": bool(blast_radius_evidence_ref),
        "kill_switch_proven": bool(kill_switch_evidence_ref),
        "recovery_window_proven": bool(recovery_window_evidence_ref),
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "stage": STAGE,
        "mode": MODE,
        "review_id": _non_empty(review_id, "review_id"),
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "project_id": _non_empty(project_id, "project_id"),
        "source_main_sha": source_sha,
        "production_boundary_authorized": boundary_authorized,
        "production_execution_authorized": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "boundary_authorization": {
            "required": True,
            "basis": AUTHORIZATION_BASIS,
            "authorization_id": boundary_authorization_id,
            "authorization_ref": boundary_authorization_ref,
        },
        "effect_authorization": {
            "required": True,
            "authorized": False,
            "authorization_id": None,
            "authorization_ref": None,
            "bound_request_sha256": None,
        },
        "request": request,
        "preconditions": preconditions,
        "blockers": [],
        "status": STATUS_BLOCKED,
        "next_step": NEXT_BLOCKED,
        "request_sha256": None,
        "report_sha256": "",
    }

    blockers = _expected_blockers(report)
    report["blockers"] = blockers
    if not blockers:
        request_sha = canonical_json_sha256(_request_payload(report))
        report["request_sha256"] = request_sha
        report["effect_authorization"]["bound_request_sha256"] = request_sha
        report["status"] = STATUS_READY
        report["next_step"] = NEXT_READY

    report["report_sha256"] = canonical_json_sha256(_payload(report))
    errors = verify_production_authorization_review_data(report)
    if errors:
        raise ProductionExecutionAuthorizationVerificationError(errors)
    return report


def verify_production_authorization_review_data(value: Any) -> list[str]:
    errors = _schema_errors(value)
    if not isinstance(value, dict):
        return sorted(set(errors or ["report must contain an object"]))

    if value.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    if value.get("stage") != STAGE or value.get("mode") != MODE:
        errors.append("stage/mode mismatch")
    if value.get("production_execution_authorized") is not False:
        errors.append("production_execution_authorized must remain false in PEB-4A")
    if value.get("automation_authorized") is not False:
        errors.append("automation_authorized must remain false")
    if value.get("pilot_authorized") is not False:
        errors.append("pilot_authorized must remain false")

    boundary = value.get("boundary_authorization") if isinstance(value.get("boundary_authorization"), dict) else {}
    if boundary.get("required") is not True or boundary.get("basis") != AUTHORIZATION_BASIS:
        errors.append("boundary authorization basis mismatch")
    boundary_present = bool(boundary.get("authorization_id") and boundary.get("authorization_ref"))
    if value.get("production_boundary_authorized") is not boundary_present:
        errors.append("production_boundary_authorized projection mismatch")

    effect = value.get("effect_authorization") if isinstance(value.get("effect_authorization"), dict) else {}
    if effect.get("required") is not True:
        errors.append("effect authorization must remain required")
    if effect.get("authorized") is not False:
        errors.append("PEB-4A cannot claim production effect authorization")
    if effect.get("authorization_id") is not None or effect.get("authorization_ref") is not None:
        errors.append("PEB-4A cannot carry effect authorization identity")

    request = value.get("request") if isinstance(value.get("request"), dict) else {}
    if request.get("environment") != "PRODUCTION":
        errors.append("request.environment must remain PRODUCTION")
    source = value.get("source_main_sha")
    if not isinstance(source, str) or _SHA40.fullmatch(source) is None:
        errors.append("source_main_sha must be an exact 40-character SHA")

    sha_fields = ("trust_report_sha256", "action_payload_sha256")
    for field in sha_fields:
        item = request.get(field)
        if item is not None and (not isinstance(item, str) or _SHA256.fullmatch(item) is None):
            errors.append(f"request.{field} must be a lowercase SHA-256 when present")

    risk = request.get("trust_risk_band")
    if risk is not None and risk not in {"R0", "R1", "R2", "R3", "R4"}:
        errors.append("request.trust_risk_band must be R0-R4 when present")

    expected_blockers = _expected_blockers(value)
    if sorted(value.get("blockers", [])) != expected_blockers:
        errors.append("blocker projection mismatch")

    if expected_blockers:
        if value.get("status") != STATUS_BLOCKED or value.get("next_step") != NEXT_BLOCKED:
            errors.append("blocked status/next_step mismatch")
        if value.get("request_sha256") is not None:
            errors.append("blocked review cannot claim request_sha256")
        if effect.get("bound_request_sha256") is not None:
            errors.append("blocked review cannot bind an effect authorization request")
    else:
        expected_request_sha = canonical_json_sha256(_request_payload(value))
        if value.get("request_sha256") != expected_request_sha:
            errors.append("request_sha256 mismatch")
        if effect.get("bound_request_sha256") != expected_request_sha:
            errors.append("effect authorization request binding mismatch")
        if value.get("status") != STATUS_READY or value.get("next_step") != NEXT_READY:
            errors.append("ready status/next_step mismatch")

    expected_report_sha = canonical_json_sha256(_payload(value))
    if value.get("report_sha256") != expected_report_sha:
        errors.append("report_sha256 mismatch")

    return sorted(set(errors))


def verify_production_authorization_review_file(path: str) -> dict[str, Any]:
    value = load_data(path)
    errors = verify_production_authorization_review_data(value)
    if errors:
        raise ProductionExecutionAuthorizationVerificationError(errors)
    return value

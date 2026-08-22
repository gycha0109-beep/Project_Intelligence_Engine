from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable
import re

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .io import load_data
from .paths import asset


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "TRUST_PRODUCTION_EXECUTION_SHADOW_V1"
MODE = "SHADOW_REPORT_ONLY"

ALLOWED_CAPABILITIES = (
    "GITHUB_PR_MUTATION",
    "DEPLOYMENT_PROMOTION",
    "PRODUCTION_CONFIG_MUTATION",
    "DATABASE_MIGRATION_EXECUTION",
    "SECRET_OR_TRUST_ROOT_ROTATION",
    "ROLLBACK_EXECUTION",
)

_REQUIRED_PRE_DISPATCH_CHECKS = (
    "EXACT_SOURCE_REVISION",
    "EXACT_TARGET_PRECONDITION",
    "SYNTHETIC_AUTHORIZATION_PRESENT",
    "KILL_SWITCH_CLEAR",
    "ROLLBACK_EVIDENCE_AVAILABLE",
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


class ExecutionShadowError(RuntimeError):
    pass


class ExecutionShadowVerificationError(ExecutionShadowError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid production execution shadow artifact: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionShadowError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionShadowError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise ExecutionShadowError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionShadowError(f"{field} must be a non-empty string")
    return value.strip()


def _sha(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    text = _non_empty(value, field).lower()
    if pattern.fullmatch(text) is None:
        raise ExecutionShadowError(f"{field} has invalid digest/revision format")
    return text


def _schema_errors(value: Any, schema_name: str) -> list[str]:
    schema = load_data(asset(f"schemas/{schema_name}"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _request_payload(value: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(value)
    payload.pop("report_sha256", None)
    return payload


def _request_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    payload = _request_payload(value)
    payload.pop("evidence_snapshot_sha256", None)
    payload.pop("request_id", None)
    payload.pop("generated_at", None)
    return payload


def _request_id(value: dict[str, Any], snapshot_sha256: str) -> str:
    identity = {
        "contract_version": value.get("contract_version"),
        "project_id": value.get("project_id"),
        "source_binding": deepcopy(value.get("source_binding")),
        "trust_binding": deepcopy(value.get("trust_binding")),
        "capability": deepcopy(value.get("capability")),
        "action_payload_sha256": value.get("action", {}).get("payload_sha256"),
        "target": deepcopy(value.get("target")),
        "rollback": deepcopy(value.get("rollback")),
        "evidence_snapshot_sha256": snapshot_sha256,
    }
    return f"production-execution-shadow-{canonical_json_sha256(identity)[:32]}"


def build_shadow_request(
    *,
    project_id: str,
    source_revision: str,
    source_evidence_sha256: str,
    trust_report_id: str,
    trust_report_sha256: str,
    trust_risk_model_version: str,
    trust_risk_band: str,
    capability_class: str,
    operation: str,
    action_payload: dict[str, Any],
    target_provider: str,
    target_account: str,
    target_resource: str,
    target_environment: str,
    target_precondition_fingerprint: str,
    rollback_evidence_ref: str,
    rollback_evidence_sha256: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    capability = _non_empty(capability_class, "capability_class").upper()
    if capability not in ALLOWED_CAPABILITIES:
        raise ExecutionShadowError(f"capability_class is not allowlisted: {capability}")
    if not isinstance(action_payload, dict):
        raise ExecutionShadowError("action_payload must be an object")
    revision = _sha(source_revision, "source_revision", _SHA40)
    source_digest = _sha(source_evidence_sha256, "source_evidence_sha256", _SHA64)
    trust_digest = _sha(trust_report_sha256, "trust_report_sha256", _SHA64)
    target_fingerprint = _sha(
        target_precondition_fingerprint,
        "target_precondition_fingerprint",
        _SHA64,
    )
    rollback_digest = _sha(rollback_evidence_sha256, "rollback_evidence_sha256", _SHA64)
    risk_band = _non_empty(trust_risk_band, "trust_risk_band").upper()
    if risk_band not in {"R0", "R1", "R2", "R3", "R4"}:
        raise ExecutionShadowError(f"unsupported trust_risk_band: {risk_band}")

    request: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "request_id": "",
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "mode": MODE,
        "production_execution_authorized": False,
        "external_side_effect_permitted": False,
        "project_id": _non_empty(project_id, "project_id"),
        "source_binding": {
            "revision": revision,
            "evidence_sha256": source_digest,
        },
        "trust_binding": {
            "report_id": _non_empty(trust_report_id, "trust_report_id"),
            "report_sha256": trust_digest,
            "risk_model_version": _non_empty(trust_risk_model_version, "trust_risk_model_version"),
            "risk_band": risk_band,
        },
        "capability": {
            "class": capability,
            "operation": _non_empty(operation, "operation"),
        },
        "action": {
            "payload": deepcopy(action_payload),
            "payload_sha256": canonical_json_sha256(action_payload),
        },
        "target": {
            "provider": _non_empty(target_provider, "target_provider"),
            "account": _non_empty(target_account, "target_account"),
            "resource": _non_empty(target_resource, "target_resource"),
            "environment": _non_empty(target_environment, "target_environment"),
            "precondition_fingerprint": target_fingerprint,
        },
        "authorization": {
            "required": True,
            "synthetic_only": True,
            "authorization_id": None,
            "authorized": False,
        },
        "pre_dispatch": {
            "required_checks": list(_REQUIRED_PRE_DISPATCH_CHECKS),
            "evaluated": False,
            "all_satisfied": False,
        },
        "execution": {
            "state": "PREPARED",
            "dispatch_attempted": False,
            "external_effect_observed": False,
            "effect_receipt": None,
            "postcondition_verified": False,
        },
        "rollback": {
            "required": True,
            "evidence_ref": _non_empty(rollback_evidence_ref, "rollback_evidence_ref"),
            "evidence_sha256": rollback_digest,
            "dispatch_attempted": False,
            "verified": False,
        },
        "contract_blockers": [],
        "execution_blockers": [
            "EXPLICIT_EXECUTION_AUTHORIZATION_REQUIRED",
            "SHADOW_MODE_NO_EXTERNAL_DISPATCH",
        ],
        "status": "SHADOW_CONTRACT_READY",
        "next_step": "RUN_SHADOW_DRY_RUN_CALIBRATION",
        "evidence_snapshot_sha256": "",
        "report_sha256": "",
    }
    snapshot = canonical_json_sha256(_request_snapshot(request))
    request["evidence_snapshot_sha256"] = snapshot
    request["request_id"] = _request_id(request, snapshot)
    request["report_sha256"] = canonical_json_sha256(_request_payload(request))
    errors = verify_shadow_request_data(request)
    if errors:
        raise ExecutionShadowVerificationError(errors)
    return request


def verify_shadow_request_data(value: Any) -> list[str]:
    errors = _schema_errors(value, "production-execution-shadow-request.schema.json")
    if not isinstance(value, dict):
        return sorted(set(errors or ["request must contain an object"]))
    try:
        if value.get("contract_version") != CONTRACT_VERSION:
            errors.append("contract_version mismatch")
        if value.get("mode") != MODE:
            errors.append("mode must remain SHADOW_REPORT_ONLY")
        if value.get("production_execution_authorized") is not False:
            errors.append("production_execution_authorized must remain false")
        if value.get("external_side_effect_permitted") is not False:
            errors.append("external_side_effect_permitted must remain false")

        capability = value.get("capability") if isinstance(value.get("capability"), dict) else {}
        if capability.get("class") not in ALLOWED_CAPABILITIES:
            errors.append("capability.class is not allowlisted")

        action = value.get("action") if isinstance(value.get("action"), dict) else {}
        if isinstance(action.get("payload"), dict):
            if action.get("payload_sha256") != canonical_json_sha256(action["payload"]):
                errors.append("action.payload_sha256 mismatch")

        authorization = value.get("authorization") if isinstance(value.get("authorization"), dict) else {}
        if authorization != {
            "required": True,
            "synthetic_only": True,
            "authorization_id": None,
            "authorized": False,
        }:
            errors.append("authorization must remain an ungranted synthetic-only shadow envelope")

        pre_dispatch = value.get("pre_dispatch") if isinstance(value.get("pre_dispatch"), dict) else {}
        if pre_dispatch.get("required_checks") != list(_REQUIRED_PRE_DISPATCH_CHECKS):
            errors.append("pre_dispatch.required_checks projection mismatch")
        if pre_dispatch.get("evaluated") is not False or pre_dispatch.get("all_satisfied") is not False:
            errors.append("request pre_dispatch state must remain unevaluated")

        execution = value.get("execution") if isinstance(value.get("execution"), dict) else {}
        expected_execution = {
            "state": "PREPARED",
            "dispatch_attempted": False,
            "external_effect_observed": False,
            "effect_receipt": None,
            "postcondition_verified": False,
        }
        if execution != expected_execution:
            errors.append("execution must remain PREPARED with no external side effect")

        rollback = value.get("rollback") if isinstance(value.get("rollback"), dict) else {}
        if rollback.get("dispatch_attempted") is not False or rollback.get("verified") is not False:
            errors.append("rollback execution must remain inactive in shadow request")

        if value.get("contract_blockers") != []:
            errors.append("built shadow request must have no contract blockers")
        expected_execution_blockers = [
            "EXPLICIT_EXECUTION_AUTHORIZATION_REQUIRED",
            "SHADOW_MODE_NO_EXTERNAL_DISPATCH",
        ]
        if value.get("execution_blockers") != expected_execution_blockers:
            errors.append("execution_blockers projection mismatch")
        if value.get("status") != "SHADOW_CONTRACT_READY":
            errors.append("status must remain SHADOW_CONTRACT_READY")
        if value.get("next_step") != "RUN_SHADOW_DRY_RUN_CALIBRATION":
            errors.append("next_step projection mismatch")

        snapshot = canonical_json_sha256(_request_snapshot(value))
        if value.get("evidence_snapshot_sha256") != snapshot:
            errors.append("evidence_snapshot_sha256 mismatch")
        if value.get("request_id") != _request_id(value, snapshot):
            errors.append("request_id mismatch")
        if value.get("report_sha256") != canonical_json_sha256(_request_payload(value)):
            errors.append("report_sha256 mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"shadow request semantic verification failed: {exc}")
    return sorted(set(errors))


def _run_payload(value: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(value)
    payload.pop("report_sha256", None)
    return payload


def _run_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    payload = _run_payload(value)
    payload.pop("evidence_snapshot_sha256", None)
    payload.pop("run_id", None)
    payload.pop("generated_at", None)
    return payload


def _run_id(value: dict[str, Any], snapshot_sha256: str) -> str:
    identity = {
        "contract_version": value.get("contract_version"),
        "request_id": value.get("request_id"),
        "request_report_sha256": value.get("request_report_sha256"),
        "adapter_assessment": deepcopy(value.get("adapter_assessment")),
        "checks": deepcopy(value.get("checks")),
        "evidence_snapshot_sha256": snapshot_sha256,
    }
    return f"production-execution-shadow-run-{canonical_json_sha256(identity)[:32]}"


def assess_adapter_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(descriptor, dict):
        raise ExecutionShadowError("adapter descriptor must be an object")
    adapter_id = _non_empty(descriptor.get("adapter_id"), "adapter_id")
    capability_classes = descriptor.get("capability_classes")
    if not isinstance(capability_classes, list) or not capability_classes:
        raise ExecutionShadowError("adapter capability_classes must be a non-empty list")
    normalized = sorted({_non_empty(item, "capability class").upper() for item in capability_classes})
    blockers: list[str] = []
    if any(item not in ALLOWED_CAPABILITIES for item in normalized):
        blockers.append("ADAPTER_CAPABILITY_NOT_ALLOWLISTED")
    if descriptor.get("arbitrary_command_surface") is not False:
        blockers.append("ARBITRARY_COMMAND_SURFACE_FORBIDDEN")
    if descriptor.get("target_binding_supported") is not True:
        blockers.append("EXACT_TARGET_BINDING_REQUIRED")
    if descriptor.get("effect_receipt_supported") is not True:
        blockers.append("EFFECT_RECEIPT_REQUIRED")
    if descriptor.get("postcondition_verifier_supported") is not True:
        blockers.append("POSTCONDITION_VERIFIER_REQUIRED")
    if descriptor.get("rollback_supported") is not True:
        blockers.append("ROLLBACK_CAPABILITY_REQUIRED")
    if descriptor.get("external_side_effects_enabled") is not False:
        blockers.append("SHADOW_ADAPTER_MUST_DISABLE_EXTERNAL_SIDE_EFFECTS")
    blockers = sorted(set(blockers))
    return {
        "adapter_id": adapter_id,
        "capability_classes": normalized,
        "arbitrary_command_surface": descriptor.get("arbitrary_command_surface") is True,
        "target_binding_supported": descriptor.get("target_binding_supported") is True,
        "effect_receipt_supported": descriptor.get("effect_receipt_supported") is True,
        "postcondition_verifier_supported": descriptor.get("postcondition_verifier_supported") is True,
        "rollback_supported": descriptor.get("rollback_supported") is True,
        "external_side_effects_enabled": descriptor.get("external_side_effects_enabled") is True,
        "blockers": blockers,
        "status": (
            "ELIGIBLE_FOR_CONTROLLED_NON_PRODUCTION_IMPLEMENTATION_REVIEW"
            if not blockers
            else "NOT_ELIGIBLE_FOR_GOVERNED_EXECUTION_ADAPTER"
        ),
    }


def run_shadow_dry_run(
    request: dict[str, Any],
    *,
    adapter_descriptor: dict[str, Any],
    observed_source_revision: str,
    observed_target_precondition_fingerprint: str,
    synthetic_authorization: bool,
    kill_switch_active: bool = False,
    rollback_evidence_available: bool = True,
    generated_at: str | None = None,
) -> dict[str, Any]:
    request_errors = verify_shadow_request_data(request)
    if request_errors:
        raise ExecutionShadowVerificationError(request_errors)

    adapter = assess_adapter_descriptor(adapter_descriptor)
    source_match = _sha(observed_source_revision, "observed_source_revision", _SHA40) == request["source_binding"]["revision"]
    target_match = (
        _sha(
            observed_target_precondition_fingerprint,
            "observed_target_precondition_fingerprint",
            _SHA64,
        )
        == request["target"]["precondition_fingerprint"]
    )
    checks = [
        {"id": "EXACT_SOURCE_REVISION", "passed": source_match},
        {"id": "EXACT_TARGET_PRECONDITION", "passed": target_match},
        {"id": "SYNTHETIC_AUTHORIZATION_PRESENT", "passed": synthetic_authorization is True},
        {"id": "KILL_SWITCH_CLEAR", "passed": kill_switch_active is False},
        {"id": "ROLLBACK_EVIDENCE_AVAILABLE", "passed": rollback_evidence_available is True},
        {"id": "ADAPTER_BOUNDARY_ELIGIBLE", "passed": not adapter["blockers"]},
        {
            "id": "REQUESTED_CAPABILITY_SUPPORTED",
            "passed": request["capability"]["class"] in adapter["capability_classes"],
        },
    ]
    failed = [item["id"] for item in checks if not item["passed"]]
    trace = ["PREPARED"]
    if synthetic_authorization is True:
        trace.append("SHADOW_AUTHORIZED")
    if not failed:
        trace.append("PRECONDITIONS_VERIFIED")
        trace.append("DISPATCH_SUPPRESSED")
        status = "SHADOW_CALIBRATION_PASS"
        next_step = "CONTROLLED_NON_PRODUCTION_EXECUTION_REQUIRED"
    else:
        trace.append("BLOCKED")
        status = "SHADOW_CALIBRATION_BLOCKED"
        next_step = "REPAIR_SHADOW_PRECONDITIONS"

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "run_id": "",
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "mode": MODE,
        "request_id": request["request_id"],
        "request_report_sha256": request["report_sha256"],
        "production_execution_authorized": False,
        "external_side_effect_permitted": False,
        "adapter_assessment": adapter,
        "checks": checks,
        "trace": trace,
        "dispatch_attempted": False,
        "external_effect_observed": False,
        "effect_receipt": None,
        "postcondition_verified": False,
        "rollback_dispatch_attempted": False,
        "calibration_blockers": sorted(set(failed)),
        "execution_blockers": [
            "EXPLICIT_EXECUTION_AUTHORIZATION_REQUIRED",
            "SHADOW_MODE_NO_EXTERNAL_DISPATCH",
        ],
        "status": status,
        "next_step": next_step,
        "evidence_snapshot_sha256": "",
        "report_sha256": "",
    }
    snapshot = canonical_json_sha256(_run_snapshot(report))
    report["evidence_snapshot_sha256"] = snapshot
    report["run_id"] = _run_id(report, snapshot)
    report["report_sha256"] = canonical_json_sha256(_run_payload(report))
    errors = verify_shadow_run_data(report)
    if errors:
        raise ExecutionShadowVerificationError(errors)
    return report


def verify_shadow_run_data(value: Any) -> list[str]:
    errors = _schema_errors(value, "production-execution-shadow-run.schema.json")
    if not isinstance(value, dict):
        return sorted(set(errors or ["run must contain an object"]))
    try:
        if value.get("contract_version") != CONTRACT_VERSION:
            errors.append("contract_version mismatch")
        if value.get("mode") != MODE:
            errors.append("mode must remain SHADOW_REPORT_ONLY")
        if value.get("production_execution_authorized") is not False:
            errors.append("production_execution_authorized must remain false")
        if value.get("external_side_effect_permitted") is not False:
            errors.append("external_side_effect_permitted must remain false")
        if value.get("dispatch_attempted") is not False:
            errors.append("dispatch_attempted must remain false")
        if value.get("external_effect_observed") is not False or value.get("effect_receipt") is not None:
            errors.append("shadow run must not claim an external effect")
        if value.get("postcondition_verified") is not False:
            errors.append("shadow run must not claim production postcondition verification")
        if value.get("rollback_dispatch_attempted") is not False:
            errors.append("shadow run must not dispatch rollback")

        checks = value.get("checks") if isinstance(value.get("checks"), list) else []
        expected_check_ids = [
            *_REQUIRED_PRE_DISPATCH_CHECKS,
            "ADAPTER_BOUNDARY_ELIGIBLE",
            "REQUESTED_CAPABILITY_SUPPORTED",
        ]
        check_ids = [
            item.get("id")
            for item in checks
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        if check_ids != expected_check_ids:
            errors.append("checks canonical projection mismatch")
        failed = sorted(
            item.get("id")
            for item in checks
            if isinstance(item, dict) and item.get("passed") is False and isinstance(item.get("id"), str)
        )
        expected_status = "SHADOW_CALIBRATION_PASS" if not failed else "SHADOW_CALIBRATION_BLOCKED"
        expected_next = (
            "CONTROLLED_NON_PRODUCTION_EXECUTION_REQUIRED"
            if not failed
            else "REPAIR_SHADOW_PRECONDITIONS"
        )
        if value.get("calibration_blockers") != failed:
            errors.append("calibration_blockers projection mismatch")
        if value.get("status") != expected_status:
            errors.append("status projection mismatch")
        if value.get("next_step") != expected_next:
            errors.append("next_step projection mismatch")

        trace = value.get("trace") if isinstance(value.get("trace"), list) else []
        expected_trace = ["PREPARED"]
        synthetic_check = next(
            (item for item in checks if isinstance(item, dict) and item.get("id") == "SYNTHETIC_AUTHORIZATION_PRESENT"),
            None,
        )
        if synthetic_check is not None and synthetic_check.get("passed") is True:
            expected_trace.append("SHADOW_AUTHORIZED")
        if expected_status == "SHADOW_CALIBRATION_PASS":
            expected_trace.extend(["PRECONDITIONS_VERIFIED", "DISPATCH_SUPPRESSED"])
        else:
            expected_trace.append("BLOCKED")
        if trace != expected_trace:
            errors.append("trace projection mismatch")
        if "DISPATCHED" in trace or "APPLIED" in trace or "VERIFIED" in trace:
            errors.append("shadow trace must not contain real execution states")

        expected_execution_blockers = [
            "EXPLICIT_EXECUTION_AUTHORIZATION_REQUIRED",
            "SHADOW_MODE_NO_EXTERNAL_DISPATCH",
        ]
        if value.get("execution_blockers") != expected_execution_blockers:
            errors.append("execution_blockers projection mismatch")

        adapter = value.get("adapter_assessment") if isinstance(value.get("adapter_assessment"), dict) else {}
        if adapter:
            expected_adapter = assess_adapter_descriptor(adapter)
            if adapter != expected_adapter:
                errors.append("adapter_assessment projection mismatch")
        adapter_blockers = adapter.get("blockers") if isinstance(adapter.get("blockers"), list) else []
        adapter_check = next(
            (item for item in checks if isinstance(item, dict) and item.get("id") == "ADAPTER_BOUNDARY_ELIGIBLE"),
            None,
        )
        if adapter_check is not None and adapter_check.get("passed") is not (not adapter_blockers):
            errors.append("adapter boundary check mismatch")

        snapshot = canonical_json_sha256(_run_snapshot(value))
        if value.get("evidence_snapshot_sha256") != snapshot:
            errors.append("evidence_snapshot_sha256 mismatch")
        if value.get("run_id") != _run_id(value, snapshot):
            errors.append("run_id mismatch")
        if value.get("report_sha256") != canonical_json_sha256(_run_payload(value)):
            errors.append("report_sha256 mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"shadow run semantic verification failed: {exc}")
    return sorted(set(errors))

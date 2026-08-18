from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .identity import canonical_json_sha256
from .io import load_data
from . import trust_reconciliation as legacy
from . import trust_reconciliation_authority as authority


TrustReconciliationError = legacy.TrustReconciliationError
TrustReconciliationVerificationError = legacy.TrustReconciliationVerificationError
load_source_manifest = authority.load_source_manifest
manifest_sha256 = authority.manifest_sha256
reconcile_sources = authority.reconcile_sources
CONCLUSIVE_VERDICTS = legacy.CONCLUSIVE_VERDICTS


_AUDIT_PROVENANCE_INPUTS = (
    "authority_source_declared",
    "source_present",
    "artifact_valid",
    "authority_registry_valid",
    "project_match",
    "assessment_match",
    "trust_report_match",
    "revision_match",
    "outcome_reference_match",
    "issuer_match",
    "issued_before_outcome",
    "verdict_match",
    "authority_binding_valid",
)


def _audit_projection_errors(item: dict[str, Any], index: int) -> list[str]:
    errors: list[str] = []
    checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
    expected_provenance = all(checks.get(field) is True for field in _AUDIT_PROVENANCE_INPUTS)
    if checks.get("independent_provenance_verified") is not expected_provenance:
        errors.append(f"outcome_reconciliation[{index}] independent_provenance_verified projection mismatch")
    expected_base = authority._audit_status(checks)
    if item.get("base_status") != expected_base:
        errors.append(f"outcome_reconciliation[{index}] audit base_status projection mismatch")
    projected_authority = item.get("authority")
    authority_key = item.get("authority_key")
    if expected_provenance:
        if not isinstance(projected_authority, dict):
            errors.append(f"outcome_reconciliation[{index}] verified audit authority projection missing")
        else:
            artifact_sha = projected_authority.get("artifact_sha256")
            identity = (
                projected_authority.get("audit_id"),
                projected_authority.get("issuer_id"),
                projected_authority.get("grant_id"),
                projected_authority.get("trust_root_id"),
            )
            if not isinstance(artifact_sha, str) or len(artifact_sha) != 64 or not all(isinstance(value, str) and value for value in identity):
                errors.append(f"outcome_reconciliation[{index}] verified audit authority identity incomplete")
            if isinstance(artifact_sha, str) and authority_key != f"audit:{artifact_sha}":
                errors.append(f"outcome_reconciliation[{index}] audit authority_key projection mismatch")
            if item.get("verdict") in {"SAFE", "UNSAFE"} and projected_authority.get("evidence_ref_count", 0) < 1:
                errors.append(f"outcome_reconciliation[{index}] conclusive audit evidence projection missing")
    return errors


def _expected_base(item: dict[str, Any]) -> str:
    if item.get("outcome_type") == "INDEPENDENT_AUDIT":
        return authority._audit_status(item.get("checks") if isinstance(item.get("checks"), dict) else {})
    return legacy._expected_outcome_base_status(item)


def verify_reconciliation_report_data(report: Any) -> list[str]:
    errors = legacy._schema_errors("trust-reconciliation-report.schema.json", report)
    if not isinstance(report, dict):
        return sorted(set(errors or ["report must contain an object"]))
    try:
        if report.get("mode") != legacy.MODE:
            errors.append("mode must remain REPORT_ONLY")
        if report.get("automation_authorized") is not False:
            errors.append("automation_authorized must remain false")
        if report.get("pilot_authorized") is not False:
            errors.append("pilot_authorized must remain false")

        assessments = report.get("assessment_reconciliation") if isinstance(report.get("assessment_reconciliation"), list) else []
        if assessments != sorted(assessments, key=lambda item: item.get("assessment_id", "")):
            errors.append("assessment_reconciliation canonical order mismatch")
        assessment_ids: set[str] = set()
        for index, item in enumerate(assessments):
            if not isinstance(item, dict):
                continue
            identifier = item.get("assessment_id")
            if identifier in assessment_ids:
                errors.append(f"duplicate assessment reconciliation: {identifier}")
            assessment_ids.add(identifier)
            expected_status = legacy._assessment_status(item.get("checks", {}))
            if item.get("status") != expected_status:
                errors.append(f"assessment_reconciliation[{index}] status projection mismatch")
            if item.get("reconciled") is not (expected_status == "RECONCILED"):
                errors.append(f"assessment_reconciliation[{index}] reconciled projection mismatch")

        outcomes = report.get("outcome_reconciliation") if isinstance(report.get("outcome_reconciliation"), list) else []
        if outcomes != sorted(outcomes, key=lambda item: item.get("event_id", "")):
            errors.append("outcome_reconciliation canonical order mismatch")
        event_ids: set[str] = set()
        projected: list[dict[str, Any]] = []
        for index, item in enumerate(outcomes):
            if not isinstance(item, dict):
                continue
            identifier = item.get("event_id")
            if identifier in event_ids:
                errors.append(f"duplicate Outcome reconciliation: {identifier}")
            event_ids.add(identifier)
            expected_conclusive = item.get("verdict") in CONCLUSIVE_VERDICTS
            if item.get("conclusive") is not expected_conclusive:
                errors.append(f"outcome_reconciliation[{index}] conclusive projection mismatch")
            if item.get("outcome_type") == "INDEPENDENT_AUDIT":
                errors.extend(_audit_projection_errors(item, index))
            expected_base = _expected_base(item)
            if item.get("base_status") != expected_base:
                errors.append(f"outcome_reconciliation[{index}] base_status projection mismatch")
            normalized = deepcopy(item)
            normalized["base_status"] = expected_base
            normalized["status"] = expected_base
            normalized["reconciled"] = expected_base == "RECONCILED"
            projected.append(normalized)

        expected_outcomes = legacy._apply_duplicate_authority(projected)
        if len(expected_outcomes) == len(outcomes):
            for index, (recorded, expected) in enumerate(zip(outcomes, expected_outcomes)):
                if recorded.get("status") != expected.get("status"):
                    errors.append(f"outcome_reconciliation[{index}] status projection mismatch")
                if recorded.get("reconciled") is not expected.get("reconciled"):
                    errors.append(f"outcome_reconciliation[{index}] reconciled projection mismatch")

        expected_summary = legacy._summary(assessments, expected_outcomes)
        if report.get("summary") != expected_summary:
            errors.append("summary projection mismatch")
        expected_status = "RECONCILED" if expected_summary["source_reconciliation_complete"] else "UNRECONCILED"
        if report.get("status") != expected_status:
            errors.append("status projection mismatch")
        expected_snapshot = canonical_json_sha256(legacy._snapshot_payload(report))
        if report.get("evidence_snapshot_sha256") != expected_snapshot:
            errors.append("evidence_snapshot_sha256 mismatch")
        expected_id = legacy._report_id(report, expected_snapshot)
        if report.get("report_id") != expected_id:
            errors.append("report_id mismatch")
        expected_hash = canonical_json_sha256(legacy._report_payload(report))
        if report.get("report_sha256") != expected_hash:
            errors.append("report_sha256 mismatch")
    except (KeyError, TypeError, ValueError, TrustReconciliationError) as exc:
        errors.append(f"report structure invalid: {exc}")
    return sorted(set(errors))


authority.verify_reconciliation_report_data = verify_reconciliation_report_data


def load_reconciliation_report(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = legacy._safe_input(path, "Trust reconciliation report")
    try:
        value = load_data(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TrustReconciliationError(f"cannot load Trust reconciliation report: {exc}") from exc
    errors = verify_reconciliation_report_data(value)
    if errors:
        raise TrustReconciliationVerificationError(errors)
    return source, value


def verify_reconciliation_report_sources(
    report: dict[str, Any], *, registry_path: str | Path, source_manifest_path: str | Path,
) -> list[str]:
    errors = verify_reconciliation_report_data(report)
    if errors:
        return errors
    try:
        replay = reconcile_sources(registry_path, source_manifest_path, generated_at=report["generated_at"])
    except Exception as exc:
        return [f"source replay failed: {exc}"]
    output: list[str] = []
    for field in (
        "comparison_registry", "source_manifest", "assessment_reconciliation", "outcome_reconciliation",
        "summary", "status", "evidence_snapshot_sha256", "report_id", "report_sha256",
    ):
        if replay.get(field) != report.get(field):
            output.append(f"source replay {field} mismatch")
    return output


def write_reconciliation_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_reconciliation_report_data(report)
    if errors:
        raise TrustReconciliationVerificationError(errors)
    target = legacy._safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target

from __future__ import annotations

import json
from pathlib import Path
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
    expected_reconciled = expected_base == "RECONCILED"
    if item.get("reconciled") is not expected_reconciled and item.get("status") != "DUPLICATE_AUTHORITY":
        errors.append(f"outcome_reconciliation[{index}] audit reconciled projection mismatch")
    projected_authority = item.get("authority")
    authority_key = item.get("authority_key")
    if expected_provenance:
        if not isinstance(projected_authority, dict):
            errors.append(f"outcome_reconciliation[{index}] verified audit authority projection missing")
        else:
            artifact_sha = projected_authority.get("artifact_sha256")
            audit_id = projected_authority.get("audit_id")
            issuer_id = projected_authority.get("issuer_id")
            grant_id = projected_authority.get("grant_id")
            trust_root_id = projected_authority.get("trust_root_id")
            if not all(isinstance(value, str) and value for value in (artifact_sha, audit_id, issuer_id, grant_id, trust_root_id)):
                errors.append(f"outcome_reconciliation[{index}] verified audit authority identity incomplete")
            if isinstance(artifact_sha, str) and authority_key != f"audit:{artifact_sha}":
                errors.append(f"outcome_reconciliation[{index}] audit authority_key projection mismatch")
            if item.get("verdict") in {"SAFE", "UNSAFE"} and projected_authority.get("evidence_ref_count", 0) < 1:
                errors.append(f"outcome_reconciliation[{index}] conclusive audit evidence projection missing")
    return errors


def verify_reconciliation_report_data(report: Any) -> list[str]:
    errors = list(legacy.verify_reconciliation_report_data(report))
    if not isinstance(report, dict):
        return sorted(set(errors))
    outcomes = report.get("outcome_reconciliation")
    if not isinstance(outcomes, list):
        return sorted(set(errors))
    for index, item in enumerate(outcomes):
        if isinstance(item, dict) and item.get("outcome_type") == "INDEPENDENT_AUDIT":
            errors.extend(_audit_projection_errors(item, index))
    return sorted(set(errors))


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
    return legacy.write_reconciliation_report(path, report)

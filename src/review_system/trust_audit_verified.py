from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from . import trust_audit as base
from .trust_comparison import (
    TrustComparisonError,
    TrustComparisonVerificationError,
    load_registry,
    verify_registry_data,
)


TrustAuditError = base.TrustAuditError
TrustAuditVerificationError = base.TrustAuditVerificationError
new_authority_registry = base.new_authority_registry
add_trust_root = base.add_trust_root
authorize_issuer = base.authorize_issuer
revoke_issuer = base.revoke_issuer
verify_authority_registry_data = base.verify_authority_registry_data
verify_audit_artifact_data = base.verify_audit_artifact_data
evaluate_audit_authority = base.evaluate_audit_authority
load_authority_registry = base.load_authority_registry
load_audit_artifact = base.load_audit_artifact
write_authority_registry = base.write_authority_registry
write_audit_artifact = base.write_audit_artifact


def _validate_issuance_time(comparison_registry: dict[str, Any], assessment_id: str, issued_at: str) -> None:
    assessment = next(
        (item for item in comparison_registry.get("assessments", []) if item.get("assessment_id") == assessment_id),
        None,
    )
    if assessment is None:
        raise TrustAuditError(f"unknown assessment: {assessment_id}")
    issued = base._as_datetime(base._timestamp(issued_at, "issued_at"))
    captured = base._as_datetime(base._timestamp(assessment["captured_at"], "assessment.captured_at"))
    if issued < captured:
        raise TrustAuditError("audit issued_at must not precede assessment.captured_at")


def verify_audit_assessment_binding(artifact: dict[str, Any], comparison_registry: dict[str, Any]) -> dict[str, Any]:
    artifact_errors = verify_audit_artifact_data(artifact)
    registry_errors = verify_registry_data(comparison_registry)
    checks = {
        "artifact_valid": not artifact_errors,
        "comparison_registry_valid": not registry_errors,
        "project_match": False,
        "assessment_present": False,
        "trust_report_match": False,
        "revision_match": False,
        "issued_after_assessment": False,
    }
    errors = [f"AUDIT_ARTIFACT:{item}" for item in artifact_errors] + [f"COMPARISON_REGISTRY:{item}" for item in registry_errors]
    if artifact_errors or registry_errors:
        return {"valid": False, "checks": checks, "errors": sorted(set(errors))}
    checks["project_match"] = artifact["project_id"] == comparison_registry["project_id"]
    assessment = next(
        (item for item in comparison_registry["assessments"] if item["assessment_id"] == artifact["assessment_id"]),
        None,
    )
    checks["assessment_present"] = assessment is not None
    if assessment is not None:
        checks["trust_report_match"] = (
            artifact["trust_report_id"] == assessment["trust_report_id"]
            and artifact["trust_report_sha256"] == assessment["trust_report_sha256"]
        )
        checks["revision_match"] = artifact["source_revision"] == assessment["source_revision"]
        checks["issued_after_assessment"] = (
            base._as_datetime(artifact["issued_at"])
            >= base._as_datetime(assessment["captured_at"])
        )
    for name, passed in checks.items():
        if not passed:
            errors.append(name.upper())
    return {"valid": all(checks.values()), "checks": checks, "errors": sorted(set(errors))}


def issue_audit_data(
    comparison_registry: dict[str, Any], authority_registry: dict[str, Any], *, assessment_id: str,
    grant_id: str, verdict: str, evidence_refs: Iterable[str], issued_at: str | None = None,
) -> dict[str, Any]:
    issued = base._timestamp(issued_at or base.utc_now(), "issued_at")
    _validate_issuance_time(comparison_registry, assessment_id, issued)
    return base.issue_audit_data(
        comparison_registry,
        authority_registry,
        assessment_id=assessment_id,
        grant_id=grant_id,
        verdict=verdict,
        evidence_refs=evidence_refs,
        issued_at=issued,
    )


def issue_audit(
    comparison_registry_path: str | Path, authority_registry_path: str | Path, *, assessment_id: str,
    grant_id: str, verdict: str, evidence_refs: Iterable[str], issued_at: str | None = None,
) -> dict[str, Any]:
    try:
        _, comparison = load_registry(comparison_registry_path)
    except (TrustComparisonError, TrustComparisonVerificationError) as exc:
        raise TrustAuditError(str(exc)) from exc
    _, authority = load_authority_registry(authority_registry_path)
    return issue_audit_data(
        comparison,
        authority,
        assessment_id=assessment_id,
        grant_id=grant_id,
        verdict=verdict,
        evidence_refs=evidence_refs,
        issued_at=issued_at,
    )

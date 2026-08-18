from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from . import trust_audit as base
from .trust_comparison import TrustComparisonError, TrustComparisonVerificationError, load_registry


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

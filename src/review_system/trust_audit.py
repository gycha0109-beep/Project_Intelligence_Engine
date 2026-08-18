from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .io import load_data
from .paths import asset
from .trust_comparison import (
    TrustComparisonError,
    TrustComparisonVerificationError,
    load_registry,
    write_json_atomic,
)


SCHEMA_VERSION = "1.0"
MODE = "REPORT_ONLY"
IDENTITY_KINDS = {"ORGANIZATION", "TEAM", "EXTERNAL_AUDITOR"}
VERDICTS = {"SAFE", "UNSAFE", "INCONCLUSIVE"}


class TrustAuditError(RuntimeError):
    pass


class TrustAuditVerificationError(TrustAuditError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid Independent Audit authority artifact: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustAuditError(f"{field} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustAuditError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise TrustAuditError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _within(value: str, start: str, end: str | None) -> bool:
    moment = _as_datetime(value)
    if moment < _as_datetime(start):
        return False
    return end is None or moment <= _as_datetime(end)


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
        raise TrustAuditError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise TrustAuditError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise TrustAuditError(f"{field} must be a regular file: {resolved}")
    return resolved


def _schema_errors(name: str, value: Any) -> list[str]:
    schema = load_data(asset(f"schemas/{name}"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _without(value: dict[str, Any], field: str) -> dict[str, Any]:
    output = deepcopy(value)
    output.pop(field, None)
    return output


def _registry_id(project_id: str, created_at: str) -> str:
    return f"trust-audit-authority-{canonical_json_sha256({'project_id': project_id, 'created_at': created_at})[:32]}"


def _trust_root_id(project_id: str, root: dict[str, Any]) -> str:
    key = {
        "project_id": project_id,
        "identity_kind": root.get("identity_kind"),
        "subject": root.get("subject"),
        "fingerprint": root.get("fingerprint"),
        "valid_from": root.get("valid_from"),
        "valid_until": root.get("valid_until"),
        "registered_at": root.get("registered_at"),
    }
    return f"audit-trust-root-{canonical_json_sha256(key)[:32]}"


def _issuer_id(project_id: str, subject: str) -> str:
    return f"audit-issuer-{canonical_json_sha256({'project_id': project_id, 'subject': subject})[:32]}"


def _grant_id(project_id: str, grant: dict[str, Any]) -> str:
    key = {
        "project_id": project_id,
        "issuer_id": grant.get("issuer_id"),
        "issuer_subject": grant.get("issuer_subject"),
        "trust_root_id": grant.get("trust_root_id"),
        "trust_root_sha256": grant.get("trust_root_sha256"),
        "valid_from": grant.get("valid_from"),
        "valid_until": grant.get("valid_until"),
        "granted_at": grant.get("granted_at"),
    }
    return f"audit-grant-{canonical_json_sha256(key)[:32]}"


def _revocation_id(registry_id: str, revocation: dict[str, Any]) -> str:
    key = {
        "registry_id": registry_id,
        "grant_id": revocation.get("grant_id"),
        "effective_at": revocation.get("effective_at"),
        "recorded_at": revocation.get("recorded_at"),
        "retroactive": revocation.get("retroactive"),
        "reason_codes": revocation.get("reason_codes"),
    }
    return f"audit-revocation-{canonical_json_sha256(key)[:32]}"


def _audit_id(artifact: dict[str, Any]) -> str:
    key = {
        "project_id": artifact.get("project_id"),
        "assessment_id": artifact.get("assessment_id"),
        "trust_report_id": artifact.get("trust_report_id"),
        "trust_report_sha256": artifact.get("trust_report_sha256"),
        "source_revision": artifact.get("source_revision"),
        "issuer_id": artifact.get("issuer_id"),
        "issuer_subject": artifact.get("issuer_subject"),
        "authority": artifact.get("authority"),
        "verdict": artifact.get("verdict"),
        "issued_at": artifact.get("issued_at"),
        "evidence_refs": artifact.get("evidence_refs"),
        "mode": MODE,
        "automation_authorized": False,
        "pilot_authorized": False,
    }
    return f"independent-audit-{canonical_json_sha256(key)[:32]}"


def _finalize_registry(registry: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(registry)
    output["trust_roots"] = sorted(output.get("trust_roots", []), key=lambda item: item["trust_root_id"])
    output["grants"] = sorted(output.get("grants", []), key=lambda item: item["grant_id"])
    output["revocations"] = sorted(output.get("revocations", []), key=lambda item: item["revocation_id"])
    output["registry_sha256"] = canonical_json_sha256(_without(output, "registry_sha256"))
    errors = verify_authority_registry_data(output)
    if errors:
        raise TrustAuditVerificationError(errors)
    return output


def new_authority_registry(project_id: str, *, created_at: str | None = None) -> dict[str, Any]:
    project = _text(project_id, "project_id")
    created = _timestamp(created_at or utc_now(), "created_at")
    return _finalize_registry({
        "schema_version": SCHEMA_VERSION,
        "registry_id": _registry_id(project, created),
        "project_id": project,
        "created_at": created,
        "trust_roots": [],
        "grants": [],
        "revocations": [],
        "registry_sha256": "",
    })


def add_trust_root(
    registry: dict[str, Any], *, identity_kind: str, subject: str, fingerprint: str,
    valid_from: str, valid_until: str | None = None, registered_at: str | None = None,
) -> dict[str, Any]:
    errors = verify_authority_registry_data(registry)
    if errors:
        raise TrustAuditVerificationError(errors)
    kind = identity_kind.upper()
    if kind not in IDENTITY_KINDS:
        raise TrustAuditError("invalid identity_kind")
    registered = _timestamp(registered_at or utc_now(), "registered_at")
    start = _timestamp(valid_from, "valid_from")
    end = None if valid_until is None else _timestamp(valid_until, "valid_until")
    if start < registered:
        raise TrustAuditError("trust root valid_from must not precede registered_at")
    if end is not None and end <= start:
        raise TrustAuditError("trust root valid_until must be after valid_from")
    root = {
        "trust_root_id": "",
        "identity_kind": kind,
        "subject": _text(subject, "subject"),
        "fingerprint": _text(fingerprint, "fingerprint"),
        "valid_from": start,
        "valid_until": end,
        "registered_at": registered,
        "trust_root_sha256": "",
    }
    root["trust_root_id"] = _trust_root_id(registry["project_id"], root)
    root["trust_root_sha256"] = canonical_json_sha256(_without(root, "trust_root_sha256"))
    if any(item["trust_root_id"] == root["trust_root_id"] for item in registry["trust_roots"]):
        raise TrustAuditError(f"duplicate trust root: {root['trust_root_id']}")
    output = deepcopy(registry)
    output["trust_roots"].append(root)
    return _finalize_registry(output)


def authorize_issuer(
    registry: dict[str, Any], *, trust_root_id: str, issuer_subject: str,
    valid_from: str, valid_until: str | None = None, granted_at: str | None = None,
) -> dict[str, Any]:
    errors = verify_authority_registry_data(registry)
    if errors:
        raise TrustAuditVerificationError(errors)
    root = next((item for item in registry["trust_roots"] if item["trust_root_id"] == trust_root_id), None)
    if root is None:
        raise TrustAuditError(f"unknown trust root: {trust_root_id}")
    granted = _timestamp(granted_at or utc_now(), "granted_at")
    start = _timestamp(valid_from, "valid_from")
    end = None if valid_until is None else _timestamp(valid_until, "valid_until")
    if start < granted:
        raise TrustAuditError("issuer grant valid_from must not precede granted_at")
    if not _within(start, root["valid_from"], root["valid_until"]):
        raise TrustAuditError("issuer grant valid_from falls outside trust root validity")
    if end is not None:
        if end <= start:
            raise TrustAuditError("issuer grant valid_until must be after valid_from")
        if root["valid_until"] is not None and end > root["valid_until"]:
            raise TrustAuditError("issuer grant valid_until exceeds trust root validity")
    subject = _text(issuer_subject, "issuer_subject")
    grant = {
        "grant_id": "",
        "issuer_id": _issuer_id(registry["project_id"], subject),
        "issuer_subject": subject,
        "trust_root_id": root["trust_root_id"],
        "trust_root_sha256": root["trust_root_sha256"],
        "valid_from": start,
        "valid_until": end,
        "granted_at": granted,
        "grant_sha256": "",
    }
    grant["grant_id"] = _grant_id(registry["project_id"], grant)
    grant["grant_sha256"] = canonical_json_sha256(_without(grant, "grant_sha256"))
    if any(item["grant_id"] == grant["grant_id"] for item in registry["grants"]):
        raise TrustAuditError(f"duplicate issuer grant: {grant['grant_id']}")
    output = deepcopy(registry)
    output["grants"].append(grant)
    return _finalize_registry(output)


def revoke_issuer(
    registry: dict[str, Any], *, grant_id: str, effective_at: str, recorded_at: str | None = None,
    retroactive: bool = False, reason_codes: Iterable[str] = (),
) -> dict[str, Any]:
    errors = verify_authority_registry_data(registry)
    if errors:
        raise TrustAuditVerificationError(errors)
    grant = next((item for item in registry["grants"] if item["grant_id"] == grant_id), None)
    if grant is None:
        raise TrustAuditError(f"unknown issuer grant: {grant_id}")
    if any(item["grant_id"] == grant_id for item in registry["revocations"]):
        raise TrustAuditError(f"issuer grant already revoked: {grant_id}")
    effective = _timestamp(effective_at, "effective_at")
    recorded = _timestamp(recorded_at or utc_now(), "recorded_at")
    if effective < grant["valid_from"]:
        raise TrustAuditError("revocation effective_at must not precede grant valid_from")
    if not retroactive and effective < recorded:
        raise TrustAuditError("non-retroactive revocation effective_at must not precede recorded_at")
    revocation = {
        "revocation_id": "",
        "grant_id": grant_id,
        "effective_at": effective,
        "recorded_at": recorded,
        "retroactive": bool(retroactive),
        "reason_codes": sorted({_text(value, "reason_code") for value in reason_codes}),
        "revocation_sha256": "",
    }
    revocation["revocation_id"] = _revocation_id(registry["registry_id"], revocation)
    revocation["revocation_sha256"] = canonical_json_sha256(_without(revocation, "revocation_sha256"))
    output = deepcopy(registry)
    output["revocations"].append(revocation)
    return _finalize_registry(output)


def _grant_active_at(registry: dict[str, Any], grant: dict[str, Any], issued_at: str) -> bool:
    root = next((item for item in registry["trust_roots"] if item["trust_root_id"] == grant["trust_root_id"]), None)
    if root is None:
        return False
    if not _within(issued_at, root["valid_from"], root["valid_until"]):
        return False
    if not _within(issued_at, grant["valid_from"], grant["valid_until"]):
        return False
    if _as_datetime(issued_at) < _as_datetime(grant["granted_at"]):
        return False
    revocation = next((item for item in registry["revocations"] if item["grant_id"] == grant["grant_id"]), None)
    return revocation is None or _as_datetime(issued_at) < _as_datetime(revocation["effective_at"])


def issue_audit_data(
    comparison_registry: dict[str, Any], authority_registry: dict[str, Any], *, assessment_id: str,
    grant_id: str, verdict: str, evidence_refs: Iterable[str], issued_at: str | None = None,
) -> dict[str, Any]:
    comparison_errors = []
    try:
        from .trust_comparison import verify_registry_data
        comparison_errors = verify_registry_data(comparison_registry)
    except (TrustComparisonError, TrustComparisonVerificationError) as exc:
        comparison_errors = [str(exc)]
    if comparison_errors:
        raise TrustAuditError("invalid Trust comparison registry: " + "; ".join(comparison_errors))
    authority_errors = verify_authority_registry_data(authority_registry)
    if authority_errors:
        raise TrustAuditVerificationError(authority_errors)
    if comparison_registry["project_id"] != authority_registry["project_id"]:
        raise TrustAuditError("comparison and audit authority project_id mismatch")
    assessment = next((item for item in comparison_registry["assessments"] if item["assessment_id"] == assessment_id), None)
    if assessment is None:
        raise TrustAuditError(f"unknown assessment: {assessment_id}")
    grant = next((item for item in authority_registry["grants"] if item["grant_id"] == grant_id), None)
    if grant is None:
        raise TrustAuditError(f"unknown issuer grant: {grant_id}")
    root = next(item for item in authority_registry["trust_roots"] if item["trust_root_id"] == grant["trust_root_id"])
    issued = _timestamp(issued_at or utc_now(), "issued_at")
    if not _grant_active_at(authority_registry, grant, issued):
        raise TrustAuditError("issuer grant is not active at audit issuance time")
    result = verdict.upper()
    if result not in VERDICTS:
        raise TrustAuditError("invalid audit verdict")
    refs = sorted({_text(value, "evidence_ref") for value in evidence_refs})
    if result in {"SAFE", "UNSAFE"} and not refs:
        raise TrustAuditError("conclusive audit requires at least one evidence_ref")
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": "",
        "project_id": comparison_registry["project_id"],
        "assessment_id": assessment["assessment_id"],
        "trust_report_id": assessment["trust_report_id"],
        "trust_report_sha256": assessment["trust_report_sha256"],
        "source_revision": assessment["source_revision"],
        "issuer_id": grant["issuer_id"],
        "issuer_subject": grant["issuer_subject"],
        "authority": {
            "registry_id": authority_registry["registry_id"],
            "trust_root_id": root["trust_root_id"],
            "trust_root_sha256": root["trust_root_sha256"],
            "grant_id": grant["grant_id"],
            "grant_sha256": grant["grant_sha256"],
        },
        "verdict": result,
        "issued_at": issued,
        "evidence_refs": refs,
        "mode": MODE,
        "automation_authorized": False,
        "pilot_authorized": False,
        "artifact_sha256": "",
    }
    artifact["audit_id"] = _audit_id(artifact)
    artifact["artifact_sha256"] = canonical_json_sha256(_without(artifact, "artifact_sha256"))
    errors = verify_audit_artifact_data(artifact)
    if errors:
        raise TrustAuditVerificationError(errors)
    return artifact


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


def verify_authority_registry_data(registry: Any) -> list[str]:
    errors = _schema_errors("trust-audit-authority-registry.schema.json", registry)
    if not isinstance(registry, dict):
        return sorted(set(errors or ["authority registry must contain an object"]))
    if errors:
        return sorted(set(errors))
    try:
        project = _text(registry["project_id"], "project_id")
        created = _timestamp(registry["created_at"], "created_at")
        if registry["registry_id"] != _registry_id(project, created):
            errors.append("registry_id mismatch")
        if registry["trust_roots"] != sorted(registry["trust_roots"], key=lambda item: item["trust_root_id"]):
            errors.append("trust_roots canonical order mismatch")
        if registry["grants"] != sorted(registry["grants"], key=lambda item: item["grant_id"]):
            errors.append("grants canonical order mismatch")
        if registry["revocations"] != sorted(registry["revocations"], key=lambda item: item["revocation_id"]):
            errors.append("revocations canonical order mismatch")
        roots: dict[str, dict[str, Any]] = {}
        for index, root in enumerate(registry["trust_roots"]):
            identifier = _trust_root_id(project, root)
            if root["trust_root_id"] != identifier:
                errors.append(f"trust_roots[{index}] trust_root_id mismatch")
            if identifier in roots:
                errors.append(f"duplicate trust_root_id: {identifier}")
            roots[identifier] = root
            expected_hash = canonical_json_sha256(_without(root, "trust_root_sha256"))
            if root["trust_root_sha256"] != expected_hash:
                errors.append(f"trust_roots[{index}] trust_root_sha256 mismatch")
            registered = _timestamp(root["registered_at"], f"trust_roots[{index}].registered_at")
            start = _timestamp(root["valid_from"], f"trust_roots[{index}].valid_from")
            if registered < created:
                errors.append(f"trust_roots[{index}] registered_at precedes registry creation")
            if start < registered:
                errors.append(f"trust_roots[{index}] valid_from precedes registered_at")
            if root["valid_until"] is not None:
                end = _timestamp(root["valid_until"], f"trust_roots[{index}].valid_until")
                if end <= start:
                    errors.append(f"trust_roots[{index}] invalid validity interval")
        grants: dict[str, dict[str, Any]] = {}
        for index, grant in enumerate(registry["grants"]):
            identifier = _grant_id(project, grant)
            if grant["grant_id"] != identifier:
                errors.append(f"grants[{index}] grant_id mismatch")
            if grant["issuer_id"] != _issuer_id(project, grant["issuer_subject"]):
                errors.append(f"grants[{index}] issuer_id mismatch")
            if identifier in grants:
                errors.append(f"duplicate grant_id: {identifier}")
            grants[identifier] = grant
            root = roots.get(grant["trust_root_id"])
            if root is None:
                errors.append(f"grants[{index}] references unknown trust root")
            else:
                if grant["trust_root_sha256"] != root["trust_root_sha256"]:
                    errors.append(f"grants[{index}] trust_root_sha256 mismatch")
            expected_hash = canonical_json_sha256(_without(grant, "grant_sha256"))
            if grant["grant_sha256"] != expected_hash:
                errors.append(f"grants[{index}] grant_sha256 mismatch")
            granted = _timestamp(grant["granted_at"], f"grants[{index}].granted_at")
            start = _timestamp(grant["valid_from"], f"grants[{index}].valid_from")
            if granted < created:
                errors.append(f"grants[{index}] granted_at precedes registry creation")
            if start < granted:
                errors.append(f"grants[{index}] valid_from precedes granted_at")
            if root is not None and not _within(start, root["valid_from"], root["valid_until"]):
                errors.append(f"grants[{index}] valid_from outside trust root validity")
            if grant["valid_until"] is not None:
                end = _timestamp(grant["valid_until"], f"grants[{index}].valid_until")
                if end <= start:
                    errors.append(f"grants[{index}] invalid validity interval")
                if root is not None and root["valid_until"] is not None and end > root["valid_until"]:
                    errors.append(f"grants[{index}] valid_until exceeds trust root validity")
        revoked_grants: set[str] = set()
        for index, revocation in enumerate(registry["revocations"]):
            identifier = _revocation_id(registry["registry_id"], revocation)
            if revocation["revocation_id"] != identifier:
                errors.append(f"revocations[{index}] revocation_id mismatch")
            expected_hash = canonical_json_sha256(_without(revocation, "revocation_sha256"))
            if revocation["revocation_sha256"] != expected_hash:
                errors.append(f"revocations[{index}] revocation_sha256 mismatch")
            grant = grants.get(revocation["grant_id"])
            if grant is None:
                errors.append(f"revocations[{index}] references unknown grant")
                continue
            if revocation["grant_id"] in revoked_grants:
                errors.append(f"duplicate revocation for grant: {revocation['grant_id']}")
            revoked_grants.add(revocation["grant_id"])
            effective = _timestamp(revocation["effective_at"], f"revocations[{index}].effective_at")
            recorded = _timestamp(revocation["recorded_at"], f"revocations[{index}].recorded_at")
            if recorded < grant["granted_at"]:
                errors.append(f"revocations[{index}] recorded_at precedes grant")
            if effective < grant["valid_from"]:
                errors.append(f"revocations[{index}] effective_at precedes grant validity")
            if not revocation["retroactive"] and effective < recorded:
                errors.append(f"revocations[{index}] non-retroactive effective_at precedes recorded_at")
        expected_registry_hash = canonical_json_sha256(_without(registry, "registry_sha256"))
        if registry["registry_sha256"] != expected_registry_hash:
            errors.append("registry_sha256 mismatch")
    except (KeyError, TypeError, ValueError, TrustAuditError) as exc:
        errors.append(f"authority registry structure invalid: {exc}")
    return sorted(set(errors))


def verify_audit_artifact_data(artifact: Any) -> list[str]:
    errors = _schema_errors("trust-independent-audit-artifact.schema.json", artifact)
    if not isinstance(artifact, dict):
        return sorted(set(errors or ["audit artifact must contain an object"]))
    if errors:
        return sorted(set(errors))
    try:
        if artifact["mode"] != MODE:
            errors.append("mode must remain REPORT_ONLY")
        if artifact["automation_authorized"] is not False:
            errors.append("automation_authorized must remain false")
        if artifact["pilot_authorized"] is not False:
            errors.append("pilot_authorized must remain false")
        if artifact["evidence_refs"] != sorted(set(artifact["evidence_refs"])):
            errors.append("evidence_refs canonical order mismatch")
        if artifact["verdict"] in {"SAFE", "UNSAFE"} and not artifact["evidence_refs"]:
            errors.append("conclusive audit requires evidence_refs")
        if artifact["audit_id"] != _audit_id(artifact):
            errors.append("audit_id mismatch")
        expected_hash = canonical_json_sha256(_without(artifact, "artifact_sha256"))
        if artifact["artifact_sha256"] != expected_hash:
            errors.append("artifact_sha256 mismatch")
        _timestamp(artifact["issued_at"], "issued_at")
    except (KeyError, TypeError, ValueError, TrustAuditError) as exc:
        errors.append(f"audit artifact structure invalid: {exc}")
    return sorted(set(errors))


def evaluate_audit_authority(artifact: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    artifact_errors = verify_audit_artifact_data(artifact)
    registry_errors = verify_authority_registry_data(registry)
    checks = {
        "artifact_valid": not artifact_errors,
        "authority_registry_valid": not registry_errors,
        "project_match": False,
        "registry_id_match": False,
        "trust_root_present": False,
        "trust_root_hash_match": False,
        "grant_present": False,
        "grant_hash_match": False,
        "issuer_match": False,
        "grant_active_at_issuance": False,
    }
    reasons = [f"AUDIT_ARTIFACT:{item}" for item in artifact_errors] + [f"AUDIT_AUTHORITY:{item}" for item in registry_errors]
    if artifact_errors or registry_errors:
        return {"valid": False, "checks": checks, "errors": sorted(set(reasons))}
    checks["project_match"] = artifact["project_id"] == registry["project_id"]
    checks["registry_id_match"] = artifact["authority"]["registry_id"] == registry["registry_id"]
    root = next((item for item in registry["trust_roots"] if item["trust_root_id"] == artifact["authority"]["trust_root_id"]), None)
    checks["trust_root_present"] = root is not None
    checks["trust_root_hash_match"] = bool(root and root["trust_root_sha256"] == artifact["authority"]["trust_root_sha256"])
    grant = next((item for item in registry["grants"] if item["grant_id"] == artifact["authority"]["grant_id"]), None)
    checks["grant_present"] = grant is not None
    checks["grant_hash_match"] = bool(grant and grant["grant_sha256"] == artifact["authority"]["grant_sha256"])
    checks["issuer_match"] = bool(
        grant
        and grant["issuer_id"] == artifact["issuer_id"]
        and grant["issuer_subject"] == artifact["issuer_subject"]
        and grant["trust_root_id"] == artifact["authority"]["trust_root_id"]
        and grant["trust_root_sha256"] == artifact["authority"]["trust_root_sha256"]
    )
    checks["grant_active_at_issuance"] = bool(grant and _grant_active_at(registry, grant, artifact["issued_at"]))
    for name, passed in checks.items():
        if not passed:
            reasons.append(name.upper())
    return {"valid": all(checks.values()), "checks": checks, "errors": sorted(set(reasons))}


def load_authority_registry(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "Independent Audit authority registry")
    try:
        value = load_data(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TrustAuditError(f"cannot load Independent Audit authority registry: {exc}") from exc
    errors = verify_authority_registry_data(value)
    if errors:
        raise TrustAuditVerificationError(errors)
    return source, value


def load_audit_artifact(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "Independent Audit artifact")
    try:
        value = load_data(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TrustAuditError(f"cannot load Independent Audit artifact: {exc}") from exc
    errors = verify_audit_artifact_data(value)
    if errors:
        raise TrustAuditVerificationError(errors)
    return source, value


def write_authority_registry(path: str | Path, registry: dict[str, Any]) -> Path:
    errors = verify_authority_registry_data(registry)
    if errors:
        raise TrustAuditVerificationError(errors)
    try:
        return write_json_atomic(path, registry)
    except (TrustComparisonError, OSError) as exc:
        raise TrustAuditError(str(exc)) from exc


def write_audit_artifact(path: str | Path, artifact: dict[str, Any]) -> Path:
    errors = verify_audit_artifact_data(artifact)
    if errors:
        raise TrustAuditVerificationError(errors)
    try:
        return write_json_atomic(path, artifact)
    except (TrustComparisonError, OSError) as exc:
        raise TrustAuditError(str(exc)) from exc

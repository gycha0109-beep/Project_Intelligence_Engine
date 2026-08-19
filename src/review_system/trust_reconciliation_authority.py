from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .identity import canonical_json_sha256, file_sha256
from .io import load_data
from .trust_audit import (
    TrustAuditError,
    TrustAuditVerificationError,
    evaluate_audit_authority,
    load_audit_artifact,
    load_authority_registry,
)
from .trust_comparison import TrustComparisonError, TrustComparisonVerificationError, load_registry
from . import trust_reconciliation as legacy


SCHEMA_VERSION = legacy.SCHEMA_VERSION
MODE = legacy.MODE
CONCLUSIVE_VERDICTS = legacy.CONCLUSIVE_VERDICTS
UNSUPPORTED_AUTHORITIES = legacy.UNSUPPORTED_AUTHORITIES
TrustReconciliationError = legacy.TrustReconciliationError
TrustReconciliationVerificationError = legacy.TrustReconciliationVerificationError
verify_reconciliation_report_data = legacy.verify_reconciliation_report_data
load_reconciliation_report = legacy.load_reconciliation_report
write_reconciliation_report = legacy.write_reconciliation_report


def _normalize_manifest(data: Any) -> dict[str, Any]:
    errors = legacy._schema_errors("trust-reconciliation-sources.schema.json", data)
    if errors:
        raise TrustReconciliationError("invalid Trust reconciliation source manifest: " + "; ".join(errors))
    assert isinstance(data, dict)
    assessment_ids: set[str] = set()
    assessments: list[dict[str, Any]] = []
    for index, item in enumerate(data["assessment_sources"]):
        assessment_id = str(item["assessment_id"]).strip()
        if assessment_id in assessment_ids:
            raise TrustReconciliationError(f"duplicate assessment source: {assessment_id}")
        assessment_ids.add(assessment_id)
        normalized = {
            "assessment_id": assessment_id,
            "trust_report": legacy._relative_ref(item["trust_report"], f"assessment_sources[{index}].trust_report"),
            "request": legacy._relative_ref(item["request"], f"assessment_sources[{index}].request"),
            "profile": legacy._relative_ref(item["profile"], f"assessment_sources[{index}].profile"),
        }
        for field in ("ledger", "policy_registry", "evaluation_report", "reground_report", "reground_observations"):
            value = item.get(field)
            normalized[field] = None if value is None else legacy._relative_ref(value, f"assessment_sources[{index}].{field}")
        assessments.append(normalized)
    event_ids: set[str] = set()
    outcomes: list[dict[str, Any]] = []
    for index, item in enumerate(data["outcome_sources"]):
        event_id = str(item["event_id"]).strip()
        if event_id in event_ids:
            raise TrustReconciliationError(f"duplicate Outcome source: {event_id}")
        event_ids.add(event_id)
        authority_type = item["authority_type"]
        normalized = {"event_id": event_id, "authority_type": authority_type}
        if authority_type == "PRODUCTION_DEFECT":
            normalized["defect_registry"] = legacy._relative_ref(item["defect_registry"], f"outcome_sources[{index}].defect_registry")
            normalized["ledger"] = legacy._relative_ref(item["ledger"], f"outcome_sources[{index}].ledger")
        elif authority_type == "CONTROLLED_EVALUATION":
            normalized["evaluation_report"] = legacy._relative_ref(item["evaluation_report"], f"outcome_sources[{index}].evaluation_report")
        elif authority_type == "INDEPENDENT_AUDIT":
            normalized["audit_artifact"] = legacy._relative_ref(item["audit_artifact"], f"outcome_sources[{index}].audit_artifact")
            normalized["audit_authority_registry"] = legacy._relative_ref(item["audit_authority_registry"], f"outcome_sources[{index}].audit_authority_registry")
        else:
            raise TrustReconciliationError(f"unsupported authority source mapping: {authority_type}")
        outcomes.append(normalized)
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": str(data["project_id"]).strip(),
        "assessment_sources": sorted(assessments, key=lambda item: item["assessment_id"]),
        "outcome_sources": sorted(outcomes, key=lambda item: item["event_id"]),
    }


def load_source_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = legacy._safe_input(path, "Trust reconciliation source manifest")
    try:
        data = load_data(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TrustReconciliationError(f"cannot load Trust reconciliation source manifest: {exc}") from exc
    return source, _normalize_manifest(data)


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return canonical_json_sha256(_normalize_manifest(manifest))


def _audit_checks() -> dict[str, bool]:
    return {
        "assessment_reconciled": True,
        "authority_source_declared": False,
        "source_present": False,
        "artifact_valid": False,
        "authority_registry_valid": False,
        "project_match": False,
        "assessment_match": False,
        "trust_report_match": False,
        "revision_match": False,
        "outcome_reference_match": False,
        "issuer_match": False,
        "issued_before_outcome": False,
        "verdict_match": False,
        "authority_binding_valid": False,
        "independent_provenance_verified": False,
    }


def _audit_status(checks: dict[str, bool]) -> str:
    if not checks.get("authority_source_declared", False):
        return "PROVENANCE_UNVERIFIED"
    if not checks.get("source_present", False):
        return "SOURCE_MISSING"
    if not checks.get("artifact_valid", False) or not checks.get("authority_registry_valid", False):
        return "SOURCE_VERIFICATION_FAILED"
    if not checks.get("project_match", False):
        return "PROJECT_MISMATCH"
    if not checks.get("assessment_match", False):
        return "OUTCOME_REFERENCE_MISMATCH"
    if not checks.get("trust_report_match", False):
        return "SOURCE_HASH_MISMATCH"
    if not checks.get("revision_match", False):
        return "REVISION_MISMATCH"
    if not checks.get("outcome_reference_match", False):
        return "OUTCOME_REFERENCE_MISMATCH"
    if not checks.get("verdict_match", False):
        return "OUTCOME_VERDICT_MISMATCH"
    if not checks.get("issuer_match", False) or not checks.get("issued_before_outcome", False):
        return "PROVENANCE_UNVERIFIED"
    if not checks.get("authority_binding_valid", False):
        return "PROVENANCE_UNVERIFIED"
    return "RECONCILED" if checks.get("independent_provenance_verified", False) else "PROVENANCE_UNVERIFIED"


def _audit_outcome(
    event: dict[str, Any], assessment: dict[str, Any], source_entry: dict[str, Any] | None,
    root: Path, project_id: str,
) -> tuple[str, dict[str, bool], list[str], str | None, dict[str, Any] | None]:
    checks = _audit_checks()
    reasons: list[str] = []
    checks["authority_source_declared"] = source_entry is not None
    if source_entry is None:
        reasons.append("NO_INDEPENDENT_AUDIT_AUTHORITY_SOURCE")
        return _audit_status(checks), checks, reasons, None, None

    artifact_path = legacy._resolve_ref(root, source_entry["audit_artifact"], "Outcome audit_artifact")
    authority_path = legacy._resolve_ref(root, source_entry["audit_authority_registry"], "Outcome audit_authority_registry")
    checks["source_present"] = artifact_path is not None and authority_path is not None
    if not checks["source_present"]:
        reasons.append("INDEPENDENT_AUDIT_SOURCE_MISSING")
        return _audit_status(checks), checks, reasons, None, None
    assert artifact_path is not None and authority_path is not None

    try:
        _, artifact = load_audit_artifact(artifact_path)
        checks["artifact_valid"] = True
    except (TrustAuditError, TrustAuditVerificationError, OSError, ValueError) as exc:
        reasons.append(f"AUDIT_ARTIFACT_INVALID:{type(exc).__name__}")
        return _audit_status(checks), checks, reasons, None, None
    try:
        _, authority_registry = load_authority_registry(authority_path)
        checks["authority_registry_valid"] = True
    except (TrustAuditError, TrustAuditVerificationError, OSError, ValueError) as exc:
        reasons.append(f"AUDIT_AUTHORITY_INVALID:{type(exc).__name__}")
        return _audit_status(checks), checks, reasons, None, None

    authority_result = evaluate_audit_authority(artifact, authority_registry)
    reasons.extend(f"AUDIT_AUTHORITY:{item}" for item in authority_result["errors"])
    checks["authority_binding_valid"] = bool(authority_result["valid"])
    checks["project_match"] = (
        artifact["project_id"] == project_id == authority_registry["project_id"]
        and authority_result["checks"]["project_match"]
        and authority_result["checks"]["registry_id_match"]
    )
    checks["assessment_match"] = artifact["assessment_id"] == assessment["assessment_id"] == event["assessment_id"]
    checks["trust_report_match"] = (
        artifact["trust_report_id"] == assessment["trust_report_id"]
        and artifact["trust_report_sha256"] == assessment["trust_report_sha256"]
    )
    checks["revision_match"] = artifact["source_revision"] == assessment["source_revision"]
    evidence_refs = set(event.get("payload", {}).get("evidence_refs", []))
    checks["outcome_reference_match"] = artifact["audit_id"] in evidence_refs and artifact["artifact_sha256"] in evidence_refs
    checks["issuer_match"] = (
        event.get("actor") == artifact["issuer_subject"]
        and authority_result["checks"]["issuer_match"]
    )
    checks["issued_before_outcome"] = legacy._before_or_equal(artifact["issued_at"], event["occurred_at"])
    checks["verdict_match"] = artifact["verdict"] == event["payload"]["verdict"]
    checks["independent_provenance_verified"] = all([
        checks["source_present"],
        checks["artifact_valid"],
        checks["authority_registry_valid"],
        checks["project_match"],
        checks["assessment_match"],
        checks["trust_report_match"],
        checks["revision_match"],
        checks["outcome_reference_match"],
        checks["issuer_match"],
        checks["issued_before_outcome"],
        checks["verdict_match"],
        checks["authority_binding_valid"],
    ])
    authority_key = f"audit:{artifact['artifact_sha256']}"
    authority = {
        "authority_type": "INDEPENDENT_AUDIT",
        "audit_id": artifact["audit_id"],
        "artifact_sha256": artifact["artifact_sha256"],
        "issuer_id": artifact["issuer_id"],
        "issuer_subject": artifact["issuer_subject"],
        "trust_root_id": artifact["authority"]["trust_root_id"],
        "grant_id": artifact["authority"]["grant_id"],
        "issued_at": artifact["issued_at"],
        "evidence_ref_count": len(artifact["evidence_refs"]),
    }
    return _audit_status(checks), checks, sorted(set(reasons)), authority_key, authority


def _outcome_reconciliation(
    event: dict[str, Any], assessment: dict[str, Any], assessment_result: dict[str, Any],
    assessment_report: dict[str, Any] | None, source_entry: dict[str, Any] | None, root: Path, project_id: str,
) -> dict[str, Any]:
    outcome_type = event["payload"]["outcome_type"]
    verdict = event["payload"]["verdict"]
    reasons: list[str] = []
    authority_key = None
    authority = None
    if not assessment_result["reconciled"]:
        base_status = "ASSESSMENT_UNRECONCILED"
        checks = {"assessment_reconciled": False}
    elif outcome_type == "INDEPENDENT_AUDIT":
        base_status, checks, reasons, authority_key, authority = _audit_outcome(
            event, assessment, source_entry, root, project_id
        )
    elif outcome_type in UNSUPPORTED_AUTHORITIES:
        base_status = "UNSUPPORTED_SOURCE"
        checks = {"assessment_reconciled": True, "authority_supported": False}
        reasons.append(f"NO_{outcome_type}_AUTHORITY_CONTRACT")
    elif source_entry is None:
        base_status = "SOURCE_MISSING"
        checks = {"assessment_reconciled": True, "source_present": False}
    elif source_entry.get("authority_type") != outcome_type:
        base_status = "OUTCOME_REFERENCE_MISMATCH"
        checks = {"assessment_reconciled": True, "authority_type_match": False}
    elif outcome_type == "PRODUCTION_DEFECT":
        base_status, checks, reasons, authority_key, authority = legacy._defect_outcome(event, assessment, source_entry, root, project_id)
        checks = {"assessment_reconciled": True, **checks}
    elif outcome_type == "CONTROLLED_EVALUATION":
        base_status, checks, reasons, authority_key, authority = legacy._evaluation_outcome(event, assessment, assessment_report, source_entry, root)
        checks = {"assessment_reconciled": True, **checks}
    else:
        base_status = "UNSUPPORTED_SOURCE"
        checks = {"assessment_reconciled": True, "authority_supported": False}
    return {
        "event_id": event["event_id"],
        "assessment_id": event["assessment_id"],
        "outcome_type": outcome_type,
        "verdict": verdict,
        "conclusive": verdict in CONCLUSIVE_VERDICTS,
        "base_status": base_status,
        "status": base_status,
        "reconciled": base_status == "RECONCILED",
        "checks": checks,
        "reason_codes": sorted(set(reasons)),
        "authority_key": authority_key,
        "authority": authority,
    }


def reconcile_sources(
    registry_path: str | Path, source_manifest_path: str | Path, *, generated_at: str | None = None,
) -> dict[str, Any]:
    registry_source = legacy._safe_input(registry_path, "Trust comparison registry")
    _, registry = load_registry(registry_source)
    manifest_source, manifest = load_source_manifest(source_manifest_path)
    if manifest["project_id"] != registry["project_id"]:
        raise TrustReconciliationError(
            f"source manifest project_id mismatch: expected={registry['project_id']} actual={manifest['project_id']}"
        )
    legacy._validate_manifest_registry_bindings(registry, manifest)
    root = manifest_source.parent
    assessment_entries = {item["assessment_id"]: item for item in manifest["assessment_sources"]}
    assessment_results: list[dict[str, Any]] = []
    assessment_reports: dict[str, dict[str, Any] | None] = {}
    for assessment in registry["assessments"]:
        result, trust_report = legacy._assessment_reconciliation(
            assessment, assessment_entries.get(assessment["assessment_id"]), root, registry["project_id"]
        )
        assessment_results.append(result)
        assessment_reports[assessment["assessment_id"]] = trust_report
    assessment_results.sort(key=lambda item: item["assessment_id"])
    assessment_result_by_id = {item["assessment_id"]: item for item in assessment_results}
    assessment_by_id = {item["assessment_id"]: item for item in registry["assessments"]}
    outcome_entries = {item["event_id"]: item for item in manifest["outcome_sources"]}
    outcome_results: list[dict[str, Any]] = []
    for event in registry["events"]:
        if event["event_type"] != "OUTCOME":
            continue
        assessment = assessment_by_id[event["assessment_id"]]
        outcome_results.append(_outcome_reconciliation(
            event,
            assessment,
            assessment_result_by_id[event["assessment_id"]],
            assessment_reports[event["assessment_id"]],
            outcome_entries.get(event["event_id"]),
            root,
            registry["project_id"],
        ))
    outcome_results.sort(key=lambda item: item["event_id"])
    outcome_results = legacy._apply_duplicate_authority(outcome_results)
    summary = legacy._summary(assessment_results, outcome_results)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "",
        "project_id": registry["project_id"],
        "generated_at": legacy._timestamp(generated_at or legacy.utc_now(), "generated_at"),
        "mode": MODE,
        "automation_authorized": False,
        "pilot_authorized": False,
        "comparison_registry": {
            "source": registry_source.name,
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
            "file_sha256": file_sha256(registry_source),
        },
        "source_manifest": {
            "source": manifest_source.name,
            "manifest_sha256": canonical_json_sha256(manifest),
            "assessment_source_count": len(manifest["assessment_sources"]),
            "outcome_source_count": len(manifest["outcome_sources"]),
        },
        "assessment_reconciliation": assessment_results,
        "outcome_reconciliation": outcome_results,
        "summary": summary,
        "status": "RECONCILED" if summary["source_reconciliation_complete"] else "UNRECONCILED",
        "evidence_snapshot_sha256": "",
        "report_sha256": "",
    }
    report["evidence_snapshot_sha256"] = canonical_json_sha256(legacy._snapshot_payload(report))
    report["report_id"] = legacy._report_id(report, report["evidence_snapshot_sha256"])
    report["report_sha256"] = canonical_json_sha256(legacy._report_payload(report))
    errors = verify_reconciliation_report_data(report)
    if errors:
        raise TrustReconciliationVerificationError(errors)
    return report


def verify_reconciliation_report_sources(
    report: dict[str, Any], *, registry_path: str | Path, source_manifest_path: str | Path,
) -> list[str]:
    errors = verify_reconciliation_report_data(report)
    if errors:
        return errors
    try:
        replay = reconcile_sources(registry_path, source_manifest_path, generated_at=report["generated_at"])
    except (
        TrustReconciliationError,
        TrustComparisonError,
        TrustComparisonVerificationError,
        TrustAuditError,
        TrustAuditVerificationError,
        OSError,
        ValueError,
    ) as exc:
        return [f"source replay failed: {exc}"]
    fields = (
        "comparison_registry", "source_manifest", "assessment_reconciliation", "outcome_reconciliation",
        "summary", "status", "evidence_snapshot_sha256", "report_id", "report_sha256",
    )
    return [f"source replay {field} mismatch" for field in fields if replay.get(field) != report.get(field)]

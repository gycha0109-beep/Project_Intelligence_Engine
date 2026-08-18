from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

from .evaluation import load_evaluation_report
from .trust import load_trust_report, verify_trust_report_sources
from .trust_audit import load_audit_artifact
from .trust_comparison import capture_assessment, record_decision, record_outcome
from .trust_prospective_common import (
    SHA40, SOURCE_FIELDS, SUPPORTED_OUTCOME_AUTHORITIES,
    ProspectiveEvidenceError, ProspectiveEvidenceVerificationError,
    _assessment_source_entry, _copy_exact, _json_bytes, _relative, _replace_one,
    _replace_registry_manifest, _replay_candidate, _required_workspace, _safe_input,
    _safe_root, _timestamp, _validate_manifest_candidate, utc_now,
)

def record_case_review(
    workspace_root: str | Path,
    *,
    assessment_id: str,
    review_level: str,
    decision: str,
    actor: str,
    occurred_at: str | None = None,
    confirmed_risk_band: str | None = None,
    reason_codes: Iterable[str] = (),
) -> dict[str, Any]:
    level = review_level.upper()
    if level not in {"REVIEWED", "AUDITED"}:
        raise ProspectiveEvidenceError("prospective safety review requires REVIEWED or AUDITED; workflow acceptance is not evidence")
    root = _safe_root(workspace_root)
    registry_path, _manifest_path, _policy_path, registry, manifest, _policy = _required_workspace(root)
    updated = record_decision(
        registry,
        assessment_id=assessment_id,
        review_level=level,
        decision=decision,
        actor=actor,
        occurred_at=occurred_at,
        confirmed_risk_band=confirmed_risk_band,
        reason_codes=reason_codes,
    )
    reconciliation = _replay_candidate(root, updated, manifest, generated_at=updated["events"][-1]["occurred_at"])
    if not reconciliation["summary"]["source_reconciliation_complete"]:
        raise ProspectiveEvidenceVerificationError(["review update would leave source reconciliation incomplete"])
    _replace_one(registry_path, _json_bytes(updated))
    event = updated["events"][-1]
    return {"event_id": event["event_id"], "assessment_id": assessment_id, "review_level": level, "registry_sha256": updated["registry_sha256"]}


def _copy_outcome_sources(
    root: Path,
    assessment_id: str,
    event_id: str,
    authority_type: str,
    authority_sources: dict[str, Path],
) -> tuple[Path, dict[str, Any]]:
    outcome_root = root / "cases" / assessment_id / "outcomes" / event_id
    if outcome_root.exists():
        raise ProspectiveEvidenceError(f"outcome source directory already exists: {outcome_root}")
    staging_parent = Path(tempfile.mkdtemp(prefix=".outcome-intake.", dir=root))
    staging = staging_parent / event_id
    staging.mkdir()
    names_by_type = {
        "PRODUCTION_DEFECT": {"defect_registry": "defect-registry.json", "ledger": "ledger.sqlite3"},
        "CONTROLLED_EVALUATION": {"evaluation_report": "evaluation-report.json"},
        "INDEPENDENT_AUDIT": {"audit_artifact": "audit-artifact.json", "audit_authority_registry": "audit-authority-registry.json"},
    }
    try:
        for key, filename in names_by_type[authority_type].items():
            _copy_exact(authority_sources[key], staging / filename)
        outcome_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, outcome_root)
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)
    mapping: dict[str, Any] = {"event_id": event_id, "authority_type": authority_type}
    for key, filename in names_by_type[authority_type].items():
        mapping[key] = _relative(root, outcome_root / filename)
    return outcome_root, mapping


def record_case_outcome(
    workspace_root: str | Path,
    *,
    assessment_id: str,
    outcome_type: str,
    verdict: str,
    actor: str,
    occurred_at: str | None = None,
    defect_id: str | None = None,
    evidence_refs: Iterable[str] = (),
    defect_registry: str | Path | None = None,
    ledger: str | Path | None = None,
    evaluation_report: str | Path | None = None,
    audit_artifact: str | Path | None = None,
    audit_authority_registry: str | Path | None = None,
) -> dict[str, Any]:
    authority_type = outcome_type.upper()
    if authority_type not in SUPPORTED_OUTCOME_AUTHORITIES:
        raise ProspectiveEvidenceError(f"outcome authority is not source-reconcilable in the current campaign: {authority_type}")
    root = _safe_root(workspace_root)
    registry_path, manifest_path, _policy_path, registry, manifest, _policy = _required_workspace(root)
    refs = set(evidence_refs)
    authority_sources: dict[str, Path]
    if authority_type == "PRODUCTION_DEFECT":
        if defect_id is None or defect_registry is None or ledger is None:
            raise ProspectiveEvidenceError("PRODUCTION_DEFECT requires defect_id, defect_registry, and ledger")
        authority_sources = {
            "defect_registry": _safe_input(defect_registry, "defect registry"),
            "ledger": _safe_input(ledger, "defect ledger"),
        }
    elif authority_type == "CONTROLLED_EVALUATION":
        if evaluation_report is None:
            raise ProspectiveEvidenceError("CONTROLLED_EVALUATION requires evaluation_report")
        evaluation_path = _safe_input(evaluation_report, "evaluation report")
        _, evaluation = load_evaluation_report(evaluation_path)
        refs.update({evaluation["evaluation_id"], evaluation["report_sha256"]})
        authority_sources = {"evaluation_report": evaluation_path}
    else:
        if audit_artifact is None or audit_authority_registry is None:
            raise ProspectiveEvidenceError("INDEPENDENT_AUDIT requires audit_artifact and audit_authority_registry")
        artifact_path = _safe_input(audit_artifact, "audit artifact")
        authority_path = _safe_input(audit_authority_registry, "audit authority registry")
        _, artifact = load_audit_artifact(artifact_path)
        if actor != artifact["issuer_subject"]:
            raise ProspectiveEvidenceError("Independent Audit outcome actor must equal audit artifact issuer_subject")
        refs.update({artifact["audit_id"], artifact["artifact_sha256"]})
        authority_sources = {"audit_artifact": artifact_path, "audit_authority_registry": authority_path}

    for prior in registry["events"]:
        if prior.get("event_type") != "OUTCOME" or prior.get("assessment_id") != assessment_id:
            continue
        payload = prior.get("payload", {})
        if payload.get("outcome_type") != authority_type or payload.get("verdict") != verdict.upper():
            continue
        same_authority = False
        if authority_type == "PRODUCTION_DEFECT":
            same_authority = payload.get("defect_id") == defect_id
        elif authority_type == "CONTROLLED_EVALUATION":
            same_authority = bool(refs.intersection(set(payload.get("evidence_refs", []))))
        elif authority_type == "INDEPENDENT_AUDIT":
            same_authority = artifact["artifact_sha256"] in set(payload.get("evidence_refs", []))
        if same_authority:
            return {
                "event_id": prior["event_id"],
                "assessment_id": assessment_id,
                "outcome_type": authority_type,
                "verdict": verdict.upper(),
                "registry_sha256": registry["registry_sha256"],
                "idempotent": True,
            }

    updated_registry = record_outcome(
        registry,
        assessment_id=assessment_id,
        outcome_type=authority_type,
        verdict=verdict,
        actor=actor,
        occurred_at=occurred_at,
        defect_id=defect_id,
        evidence_refs=refs,
    )
    event = updated_registry["events"][-1]
    outcome_root, mapping = _copy_outcome_sources(root, assessment_id, event["event_id"], authority_type, authority_sources)
    try:
        updated_manifest = deepcopy(manifest)
        updated_manifest["outcome_sources"].append(mapping)
        updated_manifest["outcome_sources"].sort(key=lambda value: value["event_id"])
        _validate_manifest_candidate(root, updated_manifest)
        reconciliation = _replay_candidate(root, updated_registry, updated_manifest, generated_at=event["occurred_at"])
        result = next(item for item in reconciliation["outcome_reconciliation"] if item["event_id"] == event["event_id"])
        if verdict.upper() in {"SAFE", "UNSAFE"} and not result["reconciled"]:
            raise ProspectiveEvidenceVerificationError([f"conclusive outcome source reconciliation failed: {result['status']}"])
        _replace_registry_manifest(registry_path, manifest_path, updated_registry, updated_manifest)
    except Exception:
        shutil.rmtree(outcome_root, ignore_errors=True)
        raise
    return {
        "event_id": event["event_id"],
        "assessment_id": assessment_id,
        "outcome_type": authority_type,
        "verdict": verdict.upper(),
        "registry_sha256": updated_registry["registry_sha256"],
        "idempotent": False,
    }



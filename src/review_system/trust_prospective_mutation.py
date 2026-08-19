from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable

from .evaluation import load_evaluation_report
from .identity import canonical_json_sha256
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


_PACKET_ID = re.compile(r"^prospective-review-packet-[0-9a-f]{32}$")
_PACKET_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PACKET_REASON_PREFIXES = ("REVIEW_PACKET_ID:", "REVIEW_PACKET_SHA256:")


def _load_review_packet_archive(
    root: Path,
    *,
    project_id: str,
    assessment_id: str,
    review_packet_id: str,
    review_packet_sha256: str,
) -> dict[str, Any]:
    source = _safe_input(
        root / "cases" / assessment_id / "reviews" / review_packet_id / "review-packet.json",
        "governed prospective review packet archive",
    )
    try:
        source.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ProspectiveEvidenceError("governed prospective review packet archive escaped workspace") from exc
    try:
        packet = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProspectiveEvidenceError(f"cannot load governed prospective review packet archive: {exc}") from exc
    if not isinstance(packet, dict):
        raise ProspectiveEvidenceError("governed prospective review packet archive must contain an object")
    payload = deepcopy(packet)
    payload.pop("packet_sha256", None)
    checks = {
        "packet_id": packet.get("packet_id") == review_packet_id,
        "packet_sha256": packet.get("packet_sha256") == review_packet_sha256,
        "packet_hash": canonical_json_sha256(payload) == review_packet_sha256,
        "project_id": packet.get("project_id") == project_id,
        "assessment_id": packet.get("assessment_id") == assessment_id,
        "mode": packet.get("mode") == "REPORT_ONLY",
        "automation_authorized": packet.get("automation_authorized") is False,
        "pilot_authorized": packet.get("pilot_authorized") is False,
        "human_review_recorded": packet.get("human_review_recorded") is False,
        "outcome_recorded": packet.get("outcome_recorded") is False,
    }
    failed = sorted(key for key, value in checks.items() if not value)
    if failed:
        raise ProspectiveEvidenceError(
            "governed prospective review packet archive binding failed: " + ", ".join(failed)
        )
    return packet


def _existing_packet_review(
    registry: dict[str, Any],
    assessment_id: str,
    review_packet_id: str,
    review_packet_sha256: str,
) -> dict[str, Any] | None:
    packet_id_reason = f"REVIEW_PACKET_ID:{review_packet_id}"
    packet_hash_reason = f"REVIEW_PACKET_SHA256:{review_packet_sha256}"
    for event in registry["events"]:
        if event.get("event_type") != "HUMAN_DECISION" or event.get("assessment_id") != assessment_id:
            continue
        reasons = set(event.get("payload", {}).get("reason_codes", []))
        if packet_id_reason in reasons or packet_hash_reason in reasons:
            return event
    return None


def record_case_review(
    workspace_root: str | Path,
    *,
    assessment_id: str,
    review_level: str,
    decision: str,
    actor: str,
    review_packet_id: str,
    review_packet_sha256: str,
    occurred_at: str | None = None,
    confirmed_risk_band: str | None = None,
    reason_codes: Iterable[str] = (),
) -> dict[str, Any]:
    level = review_level.upper()
    if level not in {"REVIEWED", "AUDITED"}:
        raise ProspectiveEvidenceError("prospective safety review requires REVIEWED or AUDITED; workflow acceptance is not evidence")
    if not isinstance(review_packet_id, str) or _PACKET_ID.fullmatch(review_packet_id) is None:
        raise ProspectiveEvidenceError("prospective safety review requires a valid governed review_packet_id")
    if not isinstance(review_packet_sha256, str) or _PACKET_SHA256.fullmatch(review_packet_sha256) is None:
        raise ProspectiveEvidenceError("prospective safety review requires a valid review_packet_sha256")
    supplied_reasons = list(reason_codes)
    if any(
        isinstance(value, str) and value.startswith(_PACKET_REASON_PREFIXES)
        for value in supplied_reasons
    ):
        raise ProspectiveEvidenceError("review packet binding reason codes are reserved for governed submission")
    root = _safe_root(workspace_root)
    registry_path, _manifest_path, _policy_path, registry, manifest, _policy = _required_workspace(root)
    packet = _load_review_packet_archive(
        root,
        project_id=registry["project_id"],
        assessment_id=assessment_id,
        review_packet_id=review_packet_id,
        review_packet_sha256=review_packet_sha256,
    )
    existing = _existing_packet_review(
        registry,
        assessment_id,
        review_packet_id,
        review_packet_sha256,
    )
    if existing is not None:
        raise ProspectiveEvidenceError(
            "duplicate governed prospective review packet submission: " + existing["event_id"]
        )
    when = _timestamp(occurred_at or utc_now(), "occurred_at")
    generated = _timestamp(packet.get("generated_at"), "review packet generated_at")
    if when < generated:
        raise ProspectiveEvidenceError("human review occurred_at must not precede review packet generation")
    bound_reasons = [
        *supplied_reasons,
        f"REVIEW_PACKET_ID:{review_packet_id}",
        f"REVIEW_PACKET_SHA256:{review_packet_sha256}",
    ]
    updated = record_decision(
        registry,
        assessment_id=assessment_id,
        review_level=level,
        decision=decision,
        actor=actor,
        occurred_at=when,
        confirmed_risk_band=confirmed_risk_band,
        reason_codes=bound_reasons,
    )
    reconciliation = _replay_candidate(root, updated, manifest, generated_at=updated["events"][-1]["occurred_at"])
    if not reconciliation["summary"]["source_reconciliation_complete"]:
        raise ProspectiveEvidenceVerificationError(["review update would leave source reconciliation incomplete"])
    _replace_one(registry_path, _json_bytes(updated))
    event = updated["events"][-1]
    return {
        "event_id": event["event_id"],
        "assessment_id": assessment_id,
        "review_level": level,
        "review_packet_id": review_packet_id,
        "review_packet_sha256": review_packet_sha256,
        "registry_sha256": updated["registry_sha256"],
    }


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

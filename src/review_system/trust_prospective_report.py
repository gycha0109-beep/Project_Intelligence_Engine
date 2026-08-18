from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .identity import canonical_json_sha256
from .trust_evidence_acquisition import (
    load_acquisition_report, populate_r0_evidence_package,
    verify_acquisition_report_sources, write_acquisition_report,
)
from .trust_observation import evaluate_observation_data, policy_id, policy_sha256
from .trust_reconciliation_authority import reconcile_sources
from .trust_prospective_common import (
    CAMPAIGN_CONTRACT, MODE, SCHEMA_VERSION, TARGET_BAND,
    ProspectiveEvidenceError, ProspectiveEvidenceVerificationError,
    _json_bytes, _path_has_symlink, _replace_one, _required_workspace, _safe_root,
    _timestamp, utc_now,
)
from .trust_prospective_projection import _campaign_status, _without, verify_campaign_report_data

def campaign_progress(workspace_root: str | Path, *, generated_at: str | None = None) -> dict[str, Any]:
    root = _safe_root(workspace_root)
    _registry_path, _manifest_path, _policy_path, registry, manifest, policy = _required_workspace(root)
    when = _timestamp(generated_at or utc_now(), "generated_at")
    reconciliation = reconcile_sources(root / "comparison-registry.json", root / "reconciliation-sources.json", generated_at=when)
    observation = evaluate_observation_data(registry, policy, generated_at=when)
    status, next_step = _campaign_status(observation, reconciliation)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": "r0-prospective-campaign-" + "0" * 32,
        "campaign_contract": CAMPAIGN_CONTRACT,
        "project_id": registry["project_id"],
        "generated_at": when,
        "mode": MODE,
        "target_band": TARGET_BAND,
        "automation_authorized": False,
        "pilot_authorized": False,
        "registry": {"registry_id": registry["registry_id"], "registry_sha256": registry["registry_sha256"]},
        "policy": {"policy_id": policy_id(policy), "policy_version": policy["policy_version"], "policy_sha256": policy_sha256(policy), "thresholds": deepcopy(policy["thresholds"])},
        "reconciliation": {
            "status": reconciliation["status"],
            "source_reconciliation_complete": reconciliation["summary"]["source_reconciliation_complete"],
            "assessment_unreconciled_count": reconciliation["summary"]["assessment_unreconciled_count"],
            "conclusive_outcome_unreconciled_count": reconciliation["summary"]["conclusive_outcome_unreconciled_count"],
        },
        "observation": deepcopy(observation["observation"]),
        "checks": deepcopy(observation["checks"]),
        "status": status,
        "next_step": next_step,
        "evidence_snapshot_sha256": "0" * 64,
        "report_sha256": "0" * 64,
    }
    snapshot = {
        "schema_version": report["schema_version"],
        "campaign_contract": report["campaign_contract"],
        "project_id": report["project_id"],
        "mode": report["mode"],
        "target_band": report["target_band"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "registry": report["registry"],
        "policy": report["policy"],
        "reconciliation": report["reconciliation"],
        "observation": report["observation"],
        "checks": report["checks"],
        "status": report["status"],
        "next_step": report["next_step"],
    }
    report["evidence_snapshot_sha256"] = canonical_json_sha256(snapshot)
    report["campaign_id"] = f"r0-prospective-campaign-{canonical_json_sha256({'project_id': report['project_id'], 'snapshot': report['evidence_snapshot_sha256']})[:32]}"
    report["report_sha256"] = canonical_json_sha256(_without(report, "report_sha256"))
    errors = verify_campaign_report_data(report)
    if errors:
        raise ProspectiveEvidenceVerificationError(errors)
    return report


def write_campaign_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_campaign_report_data(report)
    if errors:
        raise ProspectiveEvidenceVerificationError(errors)
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise ProspectiveEvidenceError(f"campaign report output must not contain symlinks: {target}")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    _replace_one(target, _json_bytes(report))
    return target


def snapshot_campaign(
    workspace_root: str | Path,
    snapshots_root: str | Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = _safe_root(workspace_root)
    _registry_path, _manifest_path, _policy_path, registry, _manifest, _policy = _required_workspace(root)
    destination = Path(snapshots_root).expanduser().resolve()
    if _path_has_symlink(destination):
        raise ProspectiveEvidenceError(f"snapshot root must not contain symlinks: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    suffix = registry["registry_sha256"][:16]
    package = destination / f"r0-pilot-evidence-{suffix}"
    report_path = destination / f"acquisition-{suffix}.json"
    if package.exists() or report_path.exists():
        if not package.is_dir() or not report_path.is_file():
            raise ProspectiveEvidenceError("immutable campaign snapshot is partially present")
        _, report = load_acquisition_report(report_path)
        errors = verify_acquisition_report_sources(report, workspace_root=root, package_root=package)
        if errors:
            raise ProspectiveEvidenceVerificationError([f"existing snapshot replay: {item}" for item in errors])
        return {"package": str(package), "report": str(report_path), "status": report["status"], "idempotent": True}
    report = populate_r0_evidence_package(root, package, generated_at=generated_at)
    write_acquisition_report(report_path, report)
    errors = verify_acquisition_report_sources(report, workspace_root=root, package_root=package)
    if errors:
        raise ProspectiveEvidenceVerificationError([f"new snapshot replay: {item}" for item in errors])
    return {"package": str(package), "report": str(report_path), "status": report["status"], "idempotent": False}

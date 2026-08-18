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


def intake_prospective_case(
    workspace_root: str | Path,
    *,
    trust_report: str | Path,
    request: str | Path,
    profile: str | Path,
    ledger: str | Path | None = None,
    policy_registry: str | Path | None = None,
    evaluation_report: str | Path | None = None,
    reground_report: str | Path | None = None,
    reground_observations: str | Path | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    root = _safe_root(workspace_root)
    registry_path, manifest_path, _policy_path, registry, manifest, _policy = _required_workspace(root)
    report_path = _safe_input(trust_report, "Trust report")
    request_path = _safe_input(request, "Trust request")
    profile_path = _safe_input(profile, "Trust profile")
    optional_raw = {
        "ledger": ledger,
        "policy_registry": policy_registry,
        "evaluation_report": evaluation_report,
        "reground_report": reground_report,
        "reground_observations": reground_observations,
    }
    optional: dict[str, Path | None] = {
        key: None if value is None else _safe_input(value, key) for key, value in optional_raw.items()
    }
    _, report = load_trust_report(report_path)
    if report["project_id"] != registry["project_id"]:
        raise ProspectiveEvidenceError("Trust report project_id does not match campaign workspace")
    source_revision = report.get("request", {}).get("source_revision")
    if not isinstance(source_revision, str) or not SHA40.fullmatch(source_revision):
        raise ProspectiveEvidenceError("prospective case requires an exact 40-hex git source_revision")
    replay_errors = verify_trust_report_sources(
        report,
        request=request_path,
        profile=profile_path,
        ledger=optional["ledger"],
        policy_registry=optional["policy_registry"],
        evaluation_report=optional["evaluation_report"],
        reground_report=optional["reground_report"],
        reground_observations=optional["reground_observations"],
    )
    if replay_errors:
        raise ProspectiveEvidenceVerificationError([f"Trust source replay: {item}" for item in replay_errors])
    captured = _timestamp(captured_at or utc_now(), "captured_at")
    generated = _timestamp(report["generated_at"], "Trust report generated_at")
    if captured < generated:
        raise ProspectiveEvidenceError("prospective capture must not precede Trust report generation")
    task_id = report["request"]["task_id"]
    for item in registry["assessments"]:
        if item["task_id"] == task_id and item["source_revision"] == source_revision:
            if item["trust_report_id"] == report["report_id"] and item["trust_report_sha256"] == report["report_sha256"]:
                entry = next((value for value in manifest["assessment_sources"] if value["assessment_id"] == item["assessment_id"]), None)
                if entry is None:
                    raise ProspectiveEvidenceError("existing assessment is missing reconciliation source mapping")
                return {
                    "assessment_id": item["assessment_id"],
                    "predicted_risk_band": item["predicted_risk_band"],
                    "source_revision": source_revision,
                    "idempotent": True,
                    "registry_sha256": registry["registry_sha256"],
                }
            raise ProspectiveEvidenceError("task/source_revision already captured with a different Trust report")

    updated_registry = capture_assessment(registry, report_path, captured_at=captured)
    assessment = next(
        item for item in updated_registry["assessments"]
        if item["trust_report_id"] == report["report_id"] and item["trust_report_sha256"] == report["report_sha256"]
    )
    case_root = root / "cases" / assessment["assessment_id"]
    if case_root.exists():
        raise ProspectiveEvidenceError(f"case directory already exists without registry identity: {case_root}")
    staging_parent = Path(tempfile.mkdtemp(prefix=".case-intake.", dir=root))
    staging_case = staging_parent / assessment["assessment_id"]
    staging_case.mkdir()
    try:
        sources = {
            "trust_report": report_path,
            "request": request_path,
            "profile": profile_path,
            **optional,
        }
        locations: dict[str, Path | None] = {}
        for key, source in sources.items():
            if source is None:
                locations[key] = None
                continue
            relative = Path(key) / source.name
            _copy_exact(source, staging_case / relative)
            locations[key] = relative
        case_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_case, case_root)
        stored = {key: (None if relative is None else case_root / relative) for key, relative in locations.items()}
        entry = _assessment_source_entry(assessment["assessment_id"], root, stored)
        updated_manifest = deepcopy(manifest)
        updated_manifest["assessment_sources"].append(entry)
        updated_manifest["assessment_sources"].sort(key=lambda value: value["assessment_id"])
        _validate_manifest_candidate(root, updated_manifest)
        reconciliation = _replay_candidate(root, updated_registry, updated_manifest, generated_at=captured)
        result = next(item for item in reconciliation["assessment_reconciliation"] if item["assessment_id"] == assessment["assessment_id"])
        if not result["reconciled"]:
            raise ProspectiveEvidenceVerificationError([f"new assessment source reconciliation failed: {result['status']}", *[f"reason:{x}" for x in result.get("reason_codes", [])]])
        _replace_registry_manifest(registry_path, manifest_path, updated_registry, updated_manifest)
    except Exception:
        if case_root.exists():
            shutil.rmtree(case_root, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)
    return {
        "assessment_id": assessment["assessment_id"],
        "predicted_risk_band": assessment["predicted_risk_band"],
        "source_revision": source_revision,
        "idempotent": False,
        "registry_sha256": updated_registry["registry_sha256"],
    }



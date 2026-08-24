from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

from .identity import canonical_json_sha256, file_sha256
from .prospective_evidence_bundle import verify_evidence_bundle
from .prospective_trust_bridge_result import verify_stabilized_bridge_result
from .trust_comparison import load_registry, new_registry, write_registry
from .trust_prospective_evidence import campaign_progress, intake_prospective_case


PROJECTION_SCHEMA_VERSION = "PIE_AUTO4_PROJECT_CAMPAIGN_PROJECTION_V1"
AUTO2_RESULT_CONTRACT = "PIE_AUTO2_HUMAN_REVIEW_RESULT_V1"
AUTO2_BRIDGE_CONTRACT = "PIE_AUTO2_HUMAN_REVIEW_BRIDGE_V1"
AUTO2_SOURCE_CONTRACT = "PIE_AUTO2_TRUST_REQUEST_SOURCE_V1"
_AUTHORITY_FIELDS = (
    "human_review_recorded",
    "outcome_recorded",
    "automation_authorized",
    "pilot_authorized",
    "merge_authorized",
    "deploy_authorized",
    "production_effect_authorized",
)
_OPTIONAL_SOURCES = (
    "ledger",
    "policy_registry",
    "evaluation_report",
    "reground_report",
    "reground_observations",
)


class ProspectiveCampaignProjectionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", f"{label} is invalid: {path}") from exc
    if not isinstance(value, dict):
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", f"{label} must be an object: {path}")
    return value


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _bridge_root(value: str | Path) -> Path:
    root = Path(value).expanduser()
    if _path_has_symlink(root):
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", f"bridge artifact must not contain symlinks: {root}")
    root = root.resolve()
    candidate = root / "bridge"
    if (candidate / "result.json").is_file() and (candidate / "workspace").is_dir():
        return candidate.resolve()
    if (root / "result.json").is_file() and (root / "workspace").is_dir():
        return root
    raise ProspectiveCampaignProjectionError(
        "SOURCE_ARTIFACT_INVALID",
        f"expected AUTO-2 bridge/result.json and bridge/workspace or a direct bridge root: {root}",
    )


def _require_false_authority(value: dict[str, Any], label: str) -> None:
    for field in _AUTHORITY_FIELDS:
        if value.get(field) is not False:
            raise ProspectiveCampaignProjectionError(
                "AUTHORITY_VIOLATION",
                f"{label}.{field} must remain false for AUTO-4B projection",
            )


def _safe_source_file(workspace: Path, relative: Any, field: str) -> Path | None:
    if relative is None:
        return None
    if not isinstance(relative, str) or not relative.strip():
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", f"{field} source path is invalid")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", f"{field} source path escapes workspace")
    path = workspace / raw
    if _path_has_symlink(path):
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", f"{field} source path contains a symlink")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(workspace)
    except (OSError, ValueError) as exc:
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", f"{field} source is unavailable") from exc
    if not resolved.is_file():
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", f"{field} source must be a regular file")
    return resolved


def _latest_registry_time(registry: dict[str, Any]) -> str:
    values = [registry["created_at"]]
    values.extend(item["captured_at"] for item in registry.get("assessments", []))
    values.extend(item["occurred_at"] for item in registry.get("events", []))
    return max(values)


def _read_bridge_case(value: str | Path) -> dict[str, Any]:
    bridge = _bridge_root(value)
    result = _load_json(bridge / "result.json", "AUTO-2 bridge result")
    if result.get("result_contract") != AUTO2_RESULT_CONTRACT or result.get("bridge_contract") != AUTO2_BRIDGE_CONTRACT:
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", "AUTO-2 result/bridge contract mismatch")
    if result.get("status") != "READY_FOR_HUMAN_REVIEW":
        raise ProspectiveCampaignProjectionError(
            "AUTHORITY_VIOLATION",
            "AUTO-4B accepts only AUTO-2 artifacts stopped at READY_FOR_HUMAN_REVIEW",
        )
    _require_false_authority(result, "result")

    source_evidence = _load_json(bridge / "source" / "trust-request-source.json", "AUTO-2 Trust source evidence")
    if source_evidence.get("source_contract") != AUTO2_SOURCE_CONTRACT:
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", "AUTO-2 Trust source contract mismatch")
    if source_evidence.get("mode") != "REPORT_ONLY":
        raise ProspectiveCampaignProjectionError("AUTHORITY_VIOLATION", "AUTO-2 Trust source must remain REPORT_ONLY")
    _require_false_authority(source_evidence, "source_evidence")
    if result.get("authority") != source_evidence.get("authority"):
        raise ProspectiveCampaignProjectionError("SOURCE_MISMATCH", "AUTO-2 result authority does not match source evidence")
    if result.get("target") != source_evidence.get("target"):
        raise ProspectiveCampaignProjectionError("SOURCE_MISMATCH", "AUTO-2 result target does not match source evidence")
    result_request = result.get("trust_request")
    source_request = source_evidence.get("trust_request")
    if not isinstance(result_request, dict) or not isinstance(source_request, dict):
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", "AUTO-2 Trust request binding is missing")
    for field in ("task_id", "source_revision"):
        if result_request.get(field) != source_request.get(field):
            raise ProspectiveCampaignProjectionError("SOURCE_MISMATCH", f"AUTO-2 Trust request {field} mismatch")
    authority = result.get("authority")
    if not isinstance(authority, dict):
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", "AUTO-2 authority binding is missing")
    trust_request_path = bridge / "source" / "trust-request.json"
    if not trust_request_path.is_file() or trust_request_path.is_symlink():
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", "AUTO-2 Trust request bytes are missing")
    content_sha256 = authority.get("content_sha256")
    if file_sha256(trust_request_path) != content_sha256 or result_request.get("content_sha256") != content_sha256:
        raise ProspectiveCampaignProjectionError("SOURCE_MISMATCH", "AUTO-2 Trust request content hash mismatch")

    bundle_manifests = sorted((bridge / "automation" / "bundles").glob("*/manifest.json"))
    if len(bundle_manifests) != 1:
        raise ProspectiveCampaignProjectionError(
            "SOURCE_ARTIFACT_INVALID",
            f"AUTO-2 bridge must contain exactly one automation bundle, found {len(bundle_manifests)}",
        )
    bundle = bundle_manifests[0].parent.resolve()
    bundle_errors = verify_evidence_bundle(bundle)
    if bundle_errors:
        raise ProspectiveCampaignProjectionError("EVIDENCE_HASH_MISMATCH", "; ".join(bundle_errors))
    manifest = _load_json(bundle / "manifest.json", "AUTO-2 bundle manifest")
    packet = _load_json(bundle / "review" / "packet.json", "AUTO-2 Stage 10K packet")
    bridge_errors = verify_stabilized_bridge_result(result, packet)
    if bridge_errors:
        raise ProspectiveCampaignProjectionError("NON_DETERMINISTIC_REPLAY", "; ".join(bridge_errors))

    target = result.get("target")
    if not isinstance(target, dict):
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", "AUTO-2 target binding is missing")
    target_head = target.get("head_sha")
    canonical_source_revision = result_request.get("source_revision")
    if not isinstance(target_head, str) or len(target_head) != 40:
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", "AUTO-2 target head_sha must be an exact Git SHA")
    if canonical_source_revision != "git:" + target_head.lower():
        raise ProspectiveCampaignProjectionError(
            "SOURCE_MISMATCH",
            "AUTO-2 target head_sha does not match canonical Trust request source_revision",
        )
    bindings = (
        ("repository", target.get("repository"), manifest.get("repository")),
        ("pull_request", target.get("pull_request"), manifest.get("pull_request")),
        ("source_revision", target_head.lower(), manifest.get("source_revision")),
        ("pie_revision", authority.get("revision"), manifest.get("pie_revision")),
        ("assessment_id", result.get("assessment_id"), manifest.get("assessment_id")),
        ("packet_id", result.get("packet_id"), manifest.get("packet_id")),
    )
    for field, expected, actual in bindings:
        if expected != actual:
            raise ProspectiveCampaignProjectionError(
                "SOURCE_MISMATCH",
                f"AUTO-2 bundle {field} mismatch: expected={expected!r} actual={actual!r}",
            )

    workspace = (bridge / "workspace").resolve()
    _, registry = load_registry(workspace / "comparison-registry.json")
    project_id = target.get("project_id")
    if registry.get("project_id") != project_id:
        raise ProspectiveCampaignProjectionError("PROJECT_SCOPE_MISMATCH", "AUTO-2 target project_id does not match source campaign")
    if len(registry.get("assessments", [])) != 1:
        raise ProspectiveCampaignProjectionError("SOURCE_ARTIFACT_INVALID", "AUTO-2 source campaign must contain exactly one assessment")
    if registry.get("events"):
        raise ProspectiveCampaignProjectionError(
            "AUTHORITY_VIOLATION",
            "AUTO-4B assessment projection does not accept source campaigns containing human decision or Outcome events",
        )
    assessment = registry["assessments"][0]
    if assessment.get("assessment_id") != result.get("assessment_id"):
        raise ProspectiveCampaignProjectionError("SOURCE_MISMATCH", "AUTO-2 assessment identity mismatch")
    if assessment.get("task_id") != result_request.get("task_id"):
        raise ProspectiveCampaignProjectionError("SOURCE_MISMATCH", "AUTO-2 task identity mismatch")
    if assessment.get("source_revision") != result_request.get("source_revision"):
        raise ProspectiveCampaignProjectionError("SOURCE_MISMATCH", "AUTO-2 source revision mismatch")
    if assessment.get("predicted_risk_band") != result.get("risk_band"):
        raise ProspectiveCampaignProjectionError("SOURCE_MISMATCH", "AUTO-2 predicted risk band mismatch")

    source_progress = campaign_progress(workspace, generated_at=_latest_registry_time(registry))
    if source_progress.get("reconciliation", {}).get("source_reconciliation_complete") is not True:
        raise ProspectiveCampaignProjectionError("SOURCE_RECONCILIATION_FAILED", "AUTO-2 source campaign is not reconciled")
    if source_progress.get("automation_authorized") is not False or source_progress.get("pilot_authorized") is not False:
        raise ProspectiveCampaignProjectionError("AUTHORITY_VIOLATION", "AUTO-2 source campaign authority ceiling changed")

    reconciliation = _load_json(workspace / "reconciliation-sources.json", "AUTO-2 reconciliation sources")
    entries = [
        item
        for item in reconciliation.get("assessment_sources", [])
        if isinstance(item, dict) and item.get("assessment_id") == assessment["assessment_id"]
    ]
    if len(entries) != 1:
        raise ProspectiveCampaignProjectionError("SOURCE_RECONCILIATION_FAILED", "AUTO-2 assessment source mapping is ambiguous")
    source_entry = entries[0]
    sources = {
        "trust_report": _safe_source_file(workspace, source_entry.get("trust_report"), "trust_report"),
        "request": _safe_source_file(workspace, source_entry.get("request"), "request"),
        "profile": _safe_source_file(workspace, source_entry.get("profile"), "profile"),
    }
    for field in _OPTIONAL_SOURCES:
        sources[field] = _safe_source_file(workspace, source_entry.get(field), field)
    if any(sources[field] is None for field in ("trust_report", "request", "profile")):
        raise ProspectiveCampaignProjectionError("SOURCE_RECONCILIATION_FAILED", "AUTO-2 required assessment sources are incomplete")

    policy = _load_json(workspace / "observation-policy.json", "AUTO-2 observation policy")
    return {
        "artifact_root": str(Path(value).expanduser().resolve()),
        "bridge_root": str(bridge),
        "project_id": project_id,
        "repository": target.get("repository"),
        "pull_request": target.get("pull_request"),
        "source_revision": assessment["source_revision"],
        "assessment_id": assessment["assessment_id"],
        "captured_at": assessment["captured_at"],
        "registry_created_at": registry["created_at"],
        "deterministic_result_sha256": result.get("deterministic_result_sha256"),
        "semantic_packet_sha256": result.get("semantic_packet_sha256"),
        "policy": policy,
        "policy_sha256": canonical_json_sha256(policy),
        "sources": sources,
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _initialize_workspace(workspace: Path, *, project_id: str, created_at: str, policy: dict[str, Any]) -> None:
    workspace.mkdir(parents=True, exist_ok=False)
    write_registry(workspace / "comparison-registry.json", new_registry(project_id, created_at=created_at))
    _write_json(
        workspace / "reconciliation-sources.json",
        {"schema_version": "1.0", "project_id": project_id, "assessment_sources": [], "outcome_sources": []},
    )
    _write_json(workspace / "observation-policy.json", policy)


def _apply_cases(workspace: Path, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        sources = case["sources"]
        result = intake_prospective_case(
            workspace,
            trust_report=sources["trust_report"],
            request=sources["request"],
            profile=sources["profile"],
            ledger=sources["ledger"],
            policy_registry=sources["policy_registry"],
            evaluation_report=sources["evaluation_report"],
            reground_report=sources["reground_report"],
            reground_observations=sources["reground_observations"],
            captured_at=case["captured_at"],
        )
        if result.get("assessment_id") != case["assessment_id"]:
            raise ProspectiveCampaignProjectionError(
                "SOURCE_MISMATCH",
                f"projected assessment identity changed for {case['assessment_id']}",
            )
        results.append(result)
    return results


def _workspace_policy_hash(workspace: Path) -> str:
    return canonical_json_sha256(_load_json(workspace / "observation-policy.json", "destination observation policy"))


def _progress(workspace: Path, generated_at: str | None) -> dict[str, Any]:
    _, registry = load_registry(workspace / "comparison-registry.json")
    when = generated_at or _latest_registry_time(registry)
    return campaign_progress(workspace, generated_at=when)


def _projection_hash(report: dict[str, Any]) -> str:
    projection = {
        "schema_version": report["schema_version"],
        "stage": report["stage"],
        "project_id": report["project_id"],
        "assessment_ids": report["assessment_ids"],
        "registry_sha256": report["registry_sha256"],
        "campaign_evidence_snapshot_sha256": report["campaign_evidence_snapshot_sha256"],
        "source_reconciliation_complete": report["source_reconciliation_complete"],
        "human_review_projected": report["human_review_projected"],
        "outcome_projected": report["outcome_projected"],
        "automatic_outcome_inference": report["automatic_outcome_inference"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "merge_authorized": report["merge_authorized"],
        "deploy_authorized": report["deploy_authorized"],
        "production_effect_authorized": report["production_effect_authorized"],
    }
    return canonical_json_sha256(projection)


def project_auto2_artifacts_to_campaign(
    workspace_root: str | Path,
    artifact_roots: Iterable[str | Path],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    values = list(artifact_roots)
    if not values:
        raise ProspectiveCampaignProjectionError("INVALID_INPUT", "at least one AUTO-2 bridge artifact is required")
    cases = [_read_bridge_case(value) for value in values]
    cases.sort(key=lambda item: (item["assessment_id"], item["deterministic_result_sha256"], item["semantic_packet_sha256"]))

    project_ids = {case["project_id"] for case in cases}
    if len(project_ids) != 1:
        raise ProspectiveCampaignProjectionError(
            "PROJECT_SCOPE_MISMATCH",
            "AUTO-4B accepts exactly one project_id per destination campaign workspace",
        )
    project_id = next(iter(project_ids))
    policy_hashes = {case["policy_sha256"] for case in cases}
    if len(policy_hashes) != 1:
        raise ProspectiveCampaignProjectionError("POLICY_MISMATCH", "AUTO-2 source artifacts use different observation policies")
    policy_hash = next(iter(policy_hashes))

    by_assessment: dict[str, str] = {}
    for case in cases:
        previous = by_assessment.setdefault(case["assessment_id"], case["deterministic_result_sha256"])
        if previous != case["deterministic_result_sha256"]:
            raise ProspectiveCampaignProjectionError(
                "NON_DETERMINISTIC_REPLAY",
                f"assessment {case['assessment_id']} has conflicting AUTO-2 deterministic results",
            )

    workspace = Path(workspace_root).expanduser()
    if _path_has_symlink(workspace):
        raise ProspectiveCampaignProjectionError("INVALID_INPUT", f"destination workspace must not contain symlinks: {workspace}")
    workspace = workspace.resolve()
    workspace.parent.mkdir(parents=True, exist_ok=True)
    existed = workspace.exists()
    if existed:
        if not workspace.is_dir():
            raise ProspectiveCampaignProjectionError("INVALID_INPUT", "destination campaign workspace is not a directory")
        destination_progress = _progress(workspace, generated_at)
        if destination_progress.get("project_id") != project_id:
            raise ProspectiveCampaignProjectionError("PROJECT_SCOPE_MISMATCH", "destination campaign project_id mismatch")
        if _workspace_policy_hash(workspace) != policy_hash:
            raise ProspectiveCampaignProjectionError("POLICY_MISMATCH", "destination campaign observation policy mismatch")

    created_at = min(case["registry_created_at"] for case in cases)
    temp_parent = Path(tempfile.mkdtemp(prefix=".auto4b-projection.", dir=workspace.parent))
    staging = temp_parent / "workspace"
    try:
        if existed:
            shutil.copytree(workspace, staging)
        else:
            _initialize_workspace(staging, project_id=project_id, created_at=created_at, policy=cases[0]["policy"])
        preflight_results = _apply_cases(staging, cases)
        preflight_progress = _progress(staging, generated_at)
        _, preflight_registry = load_registry(staging / "comparison-registry.json")
        if preflight_progress.get("reconciliation", {}).get("source_reconciliation_complete") is not True:
            raise ProspectiveCampaignProjectionError("SOURCE_RECONCILIATION_FAILED", "preflight campaign projection did not reconcile")
        if preflight_progress.get("automation_authorized") is not False or preflight_progress.get("pilot_authorized") is not False:
            raise ProspectiveCampaignProjectionError("AUTHORITY_VIOLATION", "preflight campaign projection elevated authority")

        if existed:
            committed_results = _apply_cases(workspace, cases)
            committed_progress = _progress(workspace, generated_at)
            _, committed_registry = load_registry(workspace / "comparison-registry.json")
            if committed_registry["registry_sha256"] != preflight_registry["registry_sha256"]:
                raise ProspectiveCampaignProjectionError("PROJECTION_COMMIT_MISMATCH", "preflight and committed registry identities differ")
            if committed_progress["evidence_snapshot_sha256"] != preflight_progress["evidence_snapshot_sha256"]:
                raise ProspectiveCampaignProjectionError("PROJECTION_COMMIT_MISMATCH", "preflight and committed campaign snapshots differ")
        else:
            os.replace(staging, workspace)
            committed_results = preflight_results
            committed_progress = _progress(workspace, generated_at)
            _, committed_registry = load_registry(workspace / "comparison-registry.json")
            if committed_registry["registry_sha256"] != preflight_registry["registry_sha256"]:
                raise ProspectiveCampaignProjectionError("PROJECTION_COMMIT_MISMATCH", "landed registry identity changed")
            if committed_progress["evidence_snapshot_sha256"] != preflight_progress["evidence_snapshot_sha256"]:
                raise ProspectiveCampaignProjectionError("PROJECTION_COMMIT_MISMATCH", "landed campaign snapshot changed")
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)

    assessment_ids = sorted({case["assessment_id"] for case in cases})
    projected_count = sum(1 for item in committed_results if item.get("idempotent") is False)
    idempotent_count = sum(1 for item in committed_results if item.get("idempotent") is True)
    report: dict[str, Any] = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "stage": "AUTO-4B",
        "status": "PROJECT_CAMPAIGN_PROJECTED",
        "project_id": project_id,
        "workspace": str(workspace),
        "source_artifact_count": len(cases),
        "unique_assessment_count": len(assessment_ids),
        "projected_assessment_count": projected_count,
        "idempotent_assessment_input_count": idempotent_count,
        "assessment_ids": assessment_ids,
        "registry_sha256": committed_registry["registry_sha256"],
        "campaign_id": committed_progress["campaign_id"],
        "campaign_status": committed_progress["status"],
        "campaign_evidence_snapshot_sha256": committed_progress["evidence_snapshot_sha256"],
        "campaign_report_sha256": committed_progress["report_sha256"],
        "source_reconciliation_complete": committed_progress["reconciliation"]["source_reconciliation_complete"],
        "r0_assessment_count": committed_progress["observation"]["r0_assessment_count"],
        "r0_reviewed_count": committed_progress["observation"]["r0_reviewed_count"],
        "r0_conclusive_outcome_count": committed_progress["observation"]["r0_conclusive_outcome_count"],
        "workspace_mutation_performed": (not existed) or projected_count > 0,
        "campaign_thresholds_evaluated": True,
        "human_review_projected": False,
        "outcome_projected": False,
        "automatic_outcome_inference": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
        "next_step": "GOVERNED_HUMAN_REVIEW_AND_OUTCOME_EVIDENCE_REQUIRED",
        "projection_sha256": "0" * 64,
    }
    report["projection_sha256"] = _projection_hash(report)
    return report


def write_projection_report(path: str | Path, report: dict[str, Any]) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise ProspectiveCampaignProjectionError("INVALID_INPUT", f"projection output must not contain symlinks: {target}")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, report)
    return target
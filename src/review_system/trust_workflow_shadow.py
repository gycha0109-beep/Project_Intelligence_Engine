from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

from .github.source import validate_pull_request_source
from .identity import canonical_json_sha256, normalize_source_revision
from .io import dump_json, load_data
from .trust import BAND_ORDER, _profile_descriptor, _risk_projection, load_trust_request
from .trust_workflow_bridge import project_candidate_risk
from .workflow_semantics import build_workflow_diff_evidence


SHADOW_SCHEMA_VERSION = "1.0"
SHADOW_CONTRACT = "TRUST_WORKFLOW_SEMANTIC_SHADOW_V1"


class TrustWorkflowShadowError(RuntimeError):
    pass


def _changed_files(source: dict[str, Any]) -> list[str]:
    return sorted(
        item["path"]
        for item in source.get("pull_request", {}).get("changed_files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"]
    )


def _source_bound_workflow_evidence(
    request: dict[str, Any],
    github_source: dict[str, Any],
    diff_text: str,
) -> dict[str, Any]:
    source_errors = validate_pull_request_source(github_source)
    if source_errors:
        raise TrustWorkflowShadowError("invalid GitHub source evidence: " + "; ".join(source_errors))
    pull_request = github_source.get("pull_request", {})
    head_oid = pull_request.get("head_oid")
    if not isinstance(head_oid, str):
        raise TrustWorkflowShadowError("GitHub source has no exact PR head")
    try:
        source_revision = normalize_source_revision(head_oid)
    except ValueError as exc:
        raise TrustWorkflowShadowError(f"GitHub source head is not exact: {head_oid}") from exc
    if request.get("source_revision") != source_revision:
        raise TrustWorkflowShadowError("Trust request source_revision does not match GitHub source head")

    source_files = _changed_files(github_source)
    if request.get("changed_files") != source_files:
        raise TrustWorkflowShadowError("Trust request changed_files do not match GitHub source")

    diff_meta = github_source.get("diff")
    if not isinstance(diff_meta, dict) or diff_meta.get("requested") is not True or diff_meta.get("available") is not True:
        raise TrustWorkflowShadowError("GitHub source does not contain available requested diff evidence")
    actual_diff_sha = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
    if diff_meta.get("sha256") != actual_diff_sha:
        raise TrustWorkflowShadowError("GitHub source diff SHA-256 does not match supplied diff")

    return build_workflow_diff_evidence(
        source_revision=source_revision,
        source_evidence_sha256=github_source["source_sha256"],
        changed_files=source_files,
        diff_text=diff_text,
    )


def build_workflow_semantic_shadow(
    *,
    request: dict[str, Any],
    profile: dict[str, Any],
    github_source: dict[str, Any],
    diff_text: str,
) -> dict[str, Any]:
    evidence = _source_bound_workflow_evidence(request, github_source, diff_text)
    authoritative = _risk_projection(request, profile)
    candidate_result = project_candidate_risk(
        request,
        profile,
        workflow_evidence=evidence,
    )
    candidate = candidate_result["risk"]
    payload = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "contract": SHADOW_CONTRACT,
        "mode": "REPORT_ONLY",
        "authority": "SHADOW_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "task_id": request.get("task_id"),
        "source_revision": request["source_revision"],
        "request_sha256": request.get("request_sha256"),
        "profile_sha256": profile["profile_sha256"],
        "github_source_sha256": github_source["source_sha256"],
        "diff_sha256": evidence["diff_sha256"],
        "changed_files_sha256": evidence["changed_files_sha256"],
        "workflow_evidence_sha256": evidence["evidence_sha256"],
        "workflow_semantics": deepcopy(candidate_result["workflow_evidence"]),
        "authoritative_risk_band": authoritative["effective_band"],
        "candidate_risk_band": candidate["effective_band"],
        "band_delta": BAND_ORDER[candidate["effective_band"]] - BAND_ORDER[authoritative["effective_band"]],
        "band_changed": candidate["effective_band"] != authoritative["effective_band"],
        "authoritative_risk": authoritative,
        "candidate_risk": candidate,
    }
    return {
        **payload,
        "shadow_sha256": canonical_json_sha256(payload),
    }


def build_workflow_semantic_shadow_from_files(
    *,
    request: str | Path,
    profile: str | Path,
    github_source: str | Path,
    diff: str | Path,
) -> dict[str, Any]:
    _, request_data = load_trust_request(request)
    _, profile_data = _profile_descriptor(profile)
    source_data = load_data(github_source)
    diff_text = Path(diff).read_text(encoding="utf-8")
    return build_workflow_semantic_shadow(
        request=request_data,
        profile=profile_data,
        github_source=source_data,
        diff_text=diff_text,
    )


def verify_workflow_semantic_shadow_sources(
    shadow: dict[str, Any],
    *,
    request: str | Path,
    profile: str | Path,
    github_source: str | Path,
    diff: str | Path,
) -> list[str]:
    try:
        expected = build_workflow_semantic_shadow_from_files(
            request=request,
            profile=profile,
            github_source=github_source,
            diff=diff,
        )
    except Exception as exc:
        return [f"source replay failed: {exc}"]
    return [] if shadow == expected else ["workflow semantic shadow source replay mismatch"]


def write_workflow_semantic_shadow(path: str | Path, shadow: dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    dump_json(target, shadow)
    return target

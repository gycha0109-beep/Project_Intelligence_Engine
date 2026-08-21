from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from .trust import (
    BAND_ORDER,
    TASK_CLASS_BANDS,
    _band_max,
    _matches_pattern,
    _path_classification,
    _review_pack_corroboration,
    _risk_projection,
)
from .workflow_semantics import normalize_workflow_diff_evidence


CANDIDATE_CONTRACT = "TRUST_WORKFLOW_SEMANTIC_BRIDGE_CANDIDATE_V1"

_WORKFLOW_RISK = {
    "CI_TEST_WIRING_ONLY": ("R2", "WORKFLOW_CI_TEST_WIRING_ONLY"),
    "AUTHORITY_MUTATION": ("R3", "WORKFLOW_AUTHORITY_MUTATION"),
    "UNKNOWN": ("R3", "WORKFLOW_SEMANTICS_UNKNOWN"),
}


def _candidate_risk_projection(
    request: dict[str, Any],
    profile: dict[str, Any],
    workflow_evidence: dict[str, Any] | None,
    *,
    path_classifier: Callable[[str], tuple[str, str]] = _path_classification,
) -> dict[str, Any]:
    workflow_by_path: dict[str, dict[str, Any]] = {}
    if workflow_evidence is not None:
        normalized = normalize_workflow_diff_evidence(
            workflow_evidence,
            source_revision=request["source_revision"],
            changed_files=request["changed_files"],
        )
        workflow_by_path = {
            item["path"]: item
            for item in normalized["workflows"]
        }

    base_band = TASK_CLASS_BANDS[request["task_class"]]
    grouped: dict[tuple[str, str], set[str]] = {}
    path_bands: list[str] = []
    for path in request["changed_files"]:
        semantic = workflow_by_path.get(path)
        if semantic is None:
            band, reason_id = path_classifier(path)
        else:
            band, reason_id = _WORKFLOW_RISK[semantic["classification"]]
        path_bands.append(band)
        grouped.setdefault((reason_id, band), set()).add(path)

    protected = sorted(
        path
        for path in request["changed_files"]
        if any(_matches_pattern(path, pattern) for pattern in profile["protected_paths"])
    )
    if protected:
        path_bands.append("R3")
        grouped.setdefault(("PROFILE_PROTECTED_PATH", "R3"), set()).update(protected)

    path_floor = _band_max(*path_bands)
    reasons = [
        {
            "reason_id": f"TASK_CLASS:{request['task_class']}",
            "band": base_band,
            "paths": [],
        },
        *[
            {"reason_id": reason_id, "band": band, "paths": sorted(paths)}
            for (reason_id, band), paths in sorted(
                grouped.items(),
                key=lambda item: (BAND_ORDER[item[0][1]], item[0][0]),
            )
        ],
    ]
    output: dict[str, Any] = {
        "base_band": base_band,
        "path_floor_band": path_floor,
        "effective_band": _band_max(base_band, path_floor),
        "protected_files": protected,
        "reasons": reasons,
    }

    corroboration = _review_pack_corroboration(profile, request["changed_files"])
    if corroboration is None:
        return output

    corroborated_floor = corroboration["floor_band"]
    semantic_floor = _band_max(path_floor, corroborated_floor)
    underdeclared = BAND_ORDER[base_band] < BAND_ORDER[semantic_floor]
    reasons.extend(corroboration["reasons"])
    if underdeclared:
        reasons.append(
            {
                "reason_id": "TASK_CLASS_UNDERDECLARED",
                "band": semantic_floor,
                "paths": [],
            }
        )
    output.update(
        {
            "corroborated_semantic_floor_band": corroborated_floor,
            "selected_review_packs": corroboration["selected_review_packs"],
            "task_class_underdeclared": underdeclared,
            "effective_band": _band_max(base_band, path_floor, corroborated_floor),
            "reasons": reasons,
        }
    )
    return output


def project_candidate_risk(
    request: dict[str, Any],
    profile: dict[str, Any],
    *,
    workflow_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project a non-authoritative D1 candidate risk result.

    Without workflow evidence this delegates exactly to the current Trust risk
    projection. With exact-bound workflow evidence it replaces only the blanket
    GitHub Actions path contribution. It does not mutate Trust reports, hard
    gates, schemas, policy, profiles, automation authority, or pilot authority.
    """

    if workflow_evidence is None:
        return {
            "candidate_contract": CANDIDATE_CONTRACT,
            "workflow_semantics_applied": False,
            "workflow_evidence": None,
            "risk": _risk_projection(request, profile),
        }

    normalized = normalize_workflow_diff_evidence(
        workflow_evidence,
        source_revision=request["source_revision"],
        changed_files=request["changed_files"],
    )
    evidence_projection = {
        "schema_version": normalized["schema_version"],
        "source_revision": normalized["source_revision"],
        "source_evidence_sha256": normalized["source_evidence_sha256"],
        "diff_sha256": normalized["diff_sha256"],
        "changed_files_sha256": normalized["changed_files_sha256"],
        "evidence_sha256": normalized["evidence_sha256"],
        "workflows": [
            {
                "path": item["path"],
                "patch_sha256": item["patch_sha256"],
                "classification": item["classification"],
                "reason_ids": deepcopy(item["reason_ids"]),
            }
            for item in normalized["workflows"]
        ],
    }
    return {
        "candidate_contract": CANDIDATE_CONTRACT,
        "workflow_semantics_applied": True,
        "workflow_evidence": evidence_projection,
        "risk": _candidate_risk_projection(request, profile, normalized),
    }

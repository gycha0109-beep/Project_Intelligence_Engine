from __future__ import annotations

from copy import deepcopy
from typing import Any

from .packs import _tokens, select_packs_with_reasons
from .trust import (
    BAND_ORDER,
    TRUST_MODE,
    _band_max,
    _is_documentation_path,
    _review_pack_corroboration,
    _risk_projection,
)


CANDIDATE_CONTRACT = "TRUST_GENERIC_POLICY_TOKEN_COLLISION_D2_SHADOW_V1"
_AUTHORIZATION_RLS_REASON = "REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS"
_GENERIC_POLICY_TOKENS = {"policy", "policies"}
_NON_GENERIC_AUTHORITY_TOKENS = {
    "rls",
    "supabase",
    "auth",
    "authentication",
    "session",
    "jwt",
    "middleware",
    "controller",
    "route",
    "routes",
    "api",
    "endpoint",
}


def _generic_policy_only_dual_selection(path: str) -> bool:
    if _is_documentation_path(path):
        return False
    tokens = _tokens(path)
    return bool(tokens & _GENERIC_POLICY_TOKENS) and not bool(tokens & _NON_GENERIC_AUTHORITY_TOKENS)


def diagnose_generic_policy_collision(
    profile: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    configured = profile.get("configured_review_packs")
    if not isinstance(configured, list):
        return {
            "collision_detected": False,
            "neutralize_authorization_rls": False,
            "generic_policy_collision_paths": [],
            "authorization_paths": [],
            "rls_paths": [],
            "surviving_authorization_paths": [],
            "surviving_rls_paths": [],
        }

    selection = select_packs_with_reasons(changed_files, configured)
    authorization_paths = sorted(
        path
        for path in selection.get("application.authorization", [])
        if not _is_documentation_path(path)
    )
    rls_paths = sorted(
        path
        for path in selection.get("data.rls", [])
        if not _is_documentation_path(path)
    )
    shared = set(authorization_paths) & set(rls_paths)
    collision_paths = sorted(path for path in shared if _generic_policy_only_dual_selection(path))
    collision_set = set(collision_paths)
    surviving_authorization = sorted(set(authorization_paths) - collision_set)
    surviving_rls = sorted(set(rls_paths) - collision_set)
    neutralize = bool(collision_paths) and not (
        surviving_authorization and surviving_rls
    )
    return {
        "collision_detected": bool(collision_paths),
        "neutralize_authorization_rls": neutralize,
        "generic_policy_collision_paths": collision_paths,
        "authorization_paths": authorization_paths,
        "rls_paths": rls_paths,
        "surviving_authorization_paths": surviving_authorization,
        "surviving_rls_paths": surviving_rls,
    }


def _without_generic_policy_collision_floor(
    risk: dict[str, Any],
    profile: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    corroboration = _review_pack_corroboration(profile, changed_files)
    if corroboration is None:
        return deepcopy(risk)

    remaining_corroboration = [
        deepcopy(reason)
        for reason in corroboration["reasons"]
        if reason["reason_id"] != _AUTHORIZATION_RLS_REASON
    ]
    if len(remaining_corroboration) == len(corroboration["reasons"]):
        return deepcopy(risk)

    output = deepcopy(risk)
    base_reasons = [
        deepcopy(reason)
        for reason in risk["reasons"]
        if not reason["reason_id"].startswith("REVIEW_PACK_CORROBORATION:")
        and reason["reason_id"] != "TASK_CLASS_UNDERDECLARED"
    ]
    corroborated_floor = _band_max(
        "R0",
        *[reason["band"] for reason in remaining_corroboration],
    )
    semantic_floor = _band_max(output["path_floor_band"], corroborated_floor)
    underdeclared = BAND_ORDER[output["base_band"]] < BAND_ORDER[semantic_floor]
    reasons = [*base_reasons, *remaining_corroboration]
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
            "task_class_underdeclared": underdeclared,
            "effective_band": _band_max(
                output["base_band"],
                output["path_floor_band"],
                corroborated_floor,
            ),
            "reasons": reasons,
        }
    )
    return output


def project_generic_policy_collision_candidate(
    request: dict[str, Any],
    profile: dict[str, Any],
    *,
    workflow_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = _risk_projection(request, profile, workflow_evidence)
    diagnosis = diagnose_generic_policy_collision(profile, request["changed_files"])
    candidate = deepcopy(current)
    if diagnosis["neutralize_authorization_rls"]:
        candidate = _without_generic_policy_collision_floor(
            current,
            profile,
            request["changed_files"],
        )

    return {
        "candidate_contract": CANDIDATE_CONTRACT,
        "mode": TRUST_MODE,
        "authority": "SHADOW_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "collision": diagnosis,
        "current_risk": current,
        "candidate_risk": candidate,
        "band_changed": current["effective_band"] != candidate["effective_band"],
    }

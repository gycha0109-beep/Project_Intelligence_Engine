from __future__ import annotations

from copy import deepcopy
from typing import Any

from .trust import BAND_ORDER, TRUST_MODE, _risk_projection
from .trust_signing_trust_root_semantics import analyze_signing_trust_root_semantics


CONTRACT_VERSION = "TRUST_SIGNING_TRUST_ROOT_AUTHORITY_SHADOW_V1"
TARGET_BAND = "R3"
REASON_ID = "SEMANTIC_R3_SIGNING_TRUST_ROOT_CANDIDATE"


def analyze_signing_trust_root_candidate(path: str, excerpt: str) -> dict[str, Any]:
    """Shadow-only projection of the frozen signing trust-root semantic boundary."""

    analysis = analyze_signing_trust_root_semantics(path, excerpt)
    candidate_triggered = analysis["candidate_triggered"]
    return {
        "contract_version": CONTRACT_VERSION,
        "mode": TRUST_MODE,
        "authority": "SHADOW_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "path": analysis["path"],
        "signals": analysis["signals"],
        "candidate_triggered": candidate_triggered,
        "candidate_band": TARGET_BAND if candidate_triggered else None,
        "reason_id": REASON_ID if candidate_triggered else None,
    }


def project_signing_trust_root_candidate(
    request: dict[str, Any],
    profile: dict[str, Any],
    file_texts: dict[str, str],
) -> dict[str, Any]:
    """Compare current Trust projection with the bounded shadow R3 candidate."""

    current = _risk_projection(request, profile)
    analyses = [
        analyze_signing_trust_root_candidate(path, file_texts.get(path, ""))
        for path in request.get("changed_files", [])
    ]
    candidate_paths = [item["path"] for item in analyses if item["candidate_triggered"]]

    candidate = deepcopy(current)
    if candidate_paths and BAND_ORDER[candidate["effective_band"]] < BAND_ORDER[TARGET_BAND]:
        candidate["effective_band"] = TARGET_BAND
        candidate.setdefault("reasons", []).append(
            {
                "reason_id": REASON_ID,
                "band": TARGET_BAND,
                "paths": candidate_paths,
            }
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "mode": TRUST_MODE,
        "authority": "SHADOW_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "current_risk": current,
        "candidate_risk": candidate,
        "analyses": analyses,
        "candidate_paths": candidate_paths,
        "band_changed": current["effective_band"] != candidate["effective_band"],
    }

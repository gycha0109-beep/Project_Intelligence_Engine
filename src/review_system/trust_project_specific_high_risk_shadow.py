from __future__ import annotations

from copy import deepcopy
from typing import Any

from .trust import BAND_ORDER, TRUST_MODE, _risk_projection


CONTRACT_VERSION = "TRUST_PROJECT_SPECIFIC_HIGH_RISK_BLIND_SPOT_SHADOW_V1"
OUTCOMES = ("UNDERCLASSIFIED", "MATCH", "OVERCLASSIFIED")


def audit_high_risk_case(
    request: dict[str, Any],
    profile: dict[str, Any],
    *,
    expected_band: str,
    workflow_evidence: dict[str, Any] | None = None,
    r4_semantic_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare current authoritative Trust output with an externally adjudicated band.

    This helper adds no risk heuristic. It only records whether the current
    authoritative projection is below, equal to, or above the supplied audit
    expectation.
    """

    if expected_band not in BAND_ORDER:
        raise ValueError(f"invalid expected risk band: {expected_band}")

    current = _risk_projection(
        request,
        profile,
        workflow_evidence,
        r4_semantic_evidence,
    )
    current_band = current["effective_band"]
    if BAND_ORDER[current_band] < BAND_ORDER[expected_band]:
        outcome = "UNDERCLASSIFIED"
    elif current_band == expected_band:
        outcome = "MATCH"
    else:
        outcome = "OVERCLASSIFIED"

    return {
        "contract_version": CONTRACT_VERSION,
        "mode": TRUST_MODE,
        "authority": "SHADOW_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "expected_band": expected_band,
        "current_band": current_band,
        "outcome": outcome,
        "current_risk": deepcopy(current),
    }

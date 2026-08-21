from __future__ import annotations

from typing import Any

from .trust import _is_documentation_path, _path_classification
from .trust_workflow_bridge import _candidate_risk_projection, project_candidate_risk


CANDIDATE_CONTRACT = "TRUST_DOCUMENTATION_PATH_PRECEDENCE_SHADOW_V1"
DOCUMENTATION_PRECEDENCE_REASON = "DOCUMENTATION_HIGH_RISK_TOKEN_NEUTRALIZED"


def classify_documentation_precedence_candidate(path: str) -> tuple[str, str]:
    """Classify one path for the documentation-precedence shadow candidate.

    The candidate changes exactly one authoritative outcome shape: a path that
    is already recognized as documentation but is currently promoted to R3 only
    by the high-risk path/token layer. R4 authority paths and every non-R3
    authoritative classification remain unchanged.
    """

    band, reason_id = _path_classification(path)
    if band == "R3" and _is_documentation_path(path):
        return "R1", DOCUMENTATION_PRECEDENCE_REASON
    return band, reason_id


def project_documentation_precedence_candidate(
    request: dict[str, Any],
    profile: dict[str, Any],
    *,
    workflow_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project D1 plus documentation precedence without authoritative mutation."""

    d1 = project_candidate_risk(
        request,
        profile,
        workflow_evidence=workflow_evidence,
    )
    neutralized_paths = sorted(
        path
        for path in request["changed_files"]
        if _path_classification(path)[0] == "R3" and _is_documentation_path(path)
    )
    return {
        "candidate_contract": CANDIDATE_CONTRACT,
        "workflow_semantics_applied": d1["workflow_semantics_applied"],
        "workflow_evidence": d1["workflow_evidence"],
        "documentation_precedence_applied": bool(neutralized_paths),
        "documentation_precedence_paths": neutralized_paths,
        "risk": _candidate_risk_projection(
            request,
            profile,
            workflow_evidence,
            path_classifier=classify_documentation_precedence_candidate,
        ),
    }

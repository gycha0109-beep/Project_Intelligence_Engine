from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .trust import BAND_ORDER, TRUST_MODE, _risk_projection
from .trust_r4_semantics_shadow import analyze_r4_semantics


CONTRACT_VERSION = "TRUST_R4_EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_SHADOW_V1"

_ACCEPTANCE_OUTCOME_RE = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:ACCEPTANCE|VERIFICATION|CLOSURE)[A-Z0-9_]*_(?:PASS|SUCCESS)\b"
)
_EXTERNAL_OBSERVATION_RE = re.compile(
    r"(?:\bfetch\s*\(|\bspawnSync\s*\(|\bcreateServiceClient\s*\(|"
    r"\b(?:requests|httpx)\.(?:get|post|put|patch|delete)\s*\(|"
    r"\bsubprocess\.(?:run|Popen)\s*\(|\bwindow\.__TAURI__\.core\.invoke\s*\()",
    re.IGNORECASE,
)
_DURABLE_EVIDENCE_RE = re.compile(
    r"(?:\bwriteFileSync\s*\(|\bwriteFile\s*\(|\bappendFileSync\s*\(|"
    r"\.write_text\s*\(|\bjson\.dump\s*\(|\bdump_json\s*\(|"
    r"\bartifacts?[/\\])",
    re.IGNORECASE,
)
_OPERATIONAL_ACCEPTANCE_CONTEXT_RE = re.compile(
    r"(?:published|production|hosted|signed[_ -]?release|stable[_ -]?channel|release[_ -]?acceptance)",
    re.IGNORECASE,
)


def _semantic_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("R4 verifier-role evidence text must be a string")
    changed: list[str] = []
    saw_patch = False
    for raw in value.splitlines():
        if raw.startswith(("+++", "---", "diff --git ", "@@")):
            saw_patch = True
            continue
        if raw.startswith("+") or raw.startswith("-"):
            saw_patch = True
            changed.append(raw[1:])
    if saw_patch and changed:
        return "\n".join(changed)
    return value


def analyze_r4_verifier_role_candidate(path: str, evidence_text: str) -> dict[str, Any]:
    """Evaluate one bounded candidate that repairs the executable acceptance-verifier role gap.

    The candidate is intentionally narrower than a generic PASS/verifier token rule.
    It may only reclassify a current SUPPORTING_REGRESSION_ONLY script when the
    source itself combines an explicit acceptance outcome, operational/external
    observation, durable evidence output, and fail-closed executable assertions.
    """

    current = analyze_r4_semantics(path, evidence_text)
    text = _semantic_text(evidence_text)
    signals = current["signals"]

    acceptance_outcome = bool(_ACCEPTANCE_OUTCOME_RE.search(text))
    external_observation = bool(_EXTERNAL_OBSERVATION_RE.search(text))
    durable_evidence = bool(_DURABLE_EVIDENCE_RE.search(text))
    operational_acceptance_context = bool(_OPERATIONAL_ACCEPTANCE_CONTEXT_RE.search(text))

    candidate_triggered = (
        current["classification"] == "SUPPORTING_REGRESSION_ONLY"
        and bool(signals["supporting_path"])
        and not bool(signals["evaluation_ceiling"])
        and bool(signals["failure_behavior"])
        and bool(signals["assertion_behavior"])
        and acceptance_outcome
        and external_observation
        and durable_evidence
        and operational_acceptance_context
    )

    candidate = deepcopy(current)
    if candidate_triggered:
        candidate["classification"] = "EXECUTABLE_VERIFICATION_GATE_AUTHORITY"
        candidate["is_r4_authority"] = True
        candidate["reason_ids"] = [
            "R4_EXECUTABLE_ACCEPTANCE_OUTCOME",
            "R4_EXTERNAL_OPERATIONAL_OBSERVATION",
            "R4_DURABLE_ACCEPTANCE_EVIDENCE",
            "R4_FAIL_CLOSED_EXECUTION",
        ]

    return {
        "contract_version": CONTRACT_VERSION,
        "mode": TRUST_MODE,
        "authority": "SHADOW_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "path": current["path"],
        "current": current,
        "candidate": candidate,
        "candidate_triggered": candidate_triggered,
        "candidate_signals": {
            "acceptance_outcome": acceptance_outcome,
            "external_observation": external_observation,
            "durable_evidence": durable_evidence,
            "operational_acceptance_context": operational_acceptance_context,
        },
    }


def project_r4_verifier_role_candidate(
    request: dict[str, Any],
    profile: dict[str, Any],
    file_evidence: dict[str, str],
    *,
    workflow_evidence: dict[str, Any] | None = None,
    current_r4_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_risk = _risk_projection(
        request,
        profile,
        workflow_evidence,
        current_r4_evidence,
    )
    analyses = [
        analyze_r4_verifier_role_candidate(path, file_evidence[path])
        for path in request["changed_files"]
        if path in file_evidence
    ]
    candidate_paths = sorted(
        item["path"] for item in analyses if item["candidate_triggered"]
    )

    candidate_risk = deepcopy(current_risk)
    if candidate_paths:
        candidate_risk["path_floor_band"] = "R4"
        candidate_risk["effective_band"] = "R4"
        if "corroborated_semantic_floor_band" in candidate_risk:
            candidate_risk["corroborated_semantic_floor_band"] = "R4"
        candidate_risk["reasons"] = [
            deepcopy(item)
            for item in candidate_risk["reasons"]
            if item["reason_id"] not in {
                "TASK_CLASS_UNDERDECLARED",
                "SEMANTIC_R4_VERIFIER_ROLE_CANDIDATE",
            }
        ]
        candidate_risk["reasons"].append(
            {
                "reason_id": "SEMANTIC_R4_VERIFIER_ROLE_CANDIDATE",
                "band": "R4",
                "paths": candidate_paths,
            }
        )
        if "task_class_underdeclared" in candidate_risk:
            candidate_risk["task_class_underdeclared"] = (
                BAND_ORDER[candidate_risk["base_band"]] < BAND_ORDER["R4"]
            )
        if BAND_ORDER[candidate_risk["base_band"]] < BAND_ORDER["R4"]:
            candidate_risk["reasons"].append(
                {
                    "reason_id": "TASK_CLASS_UNDERDECLARED",
                    "band": "R4",
                    "paths": [],
                }
            )

    return {
        "contract_version": CONTRACT_VERSION,
        "mode": TRUST_MODE,
        "authority": "SHADOW_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "analyses": analyses,
        "current_risk": current_risk,
        "candidate_risk": candidate_risk,
        "candidate_r4_paths": candidate_paths,
        "band_changed": current_risk["effective_band"] != candidate_risk["effective_band"],
    }

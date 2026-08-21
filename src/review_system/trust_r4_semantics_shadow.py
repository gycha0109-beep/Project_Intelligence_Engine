from __future__ import annotations

from copy import deepcopy
import re
from pathlib import PurePosixPath
from typing import Any

from .trust import BAND_ORDER, TRUST_MODE, _risk_projection


CONTRACT_VERSION = "TRUST_R4_SEMANTIC_UNDERDETECTION_SHADOW_V1"
CLASSIFICATIONS = (
    "NORMATIVE_DECISION_AUTHORITY",
    "EXECUTABLE_VERIFICATION_GATE_AUTHORITY",
    "SUPPORTING_EVALUATION_ONLY",
    "SUPPORTING_REGRESSION_ONLY",
    "UNKNOWN",
)

_EVALUATE_FUNCTION_RE = re.compile(
    r"\b(?:export\s+)?(?:async\s+)?function\s+evaluate[A-Za-z0-9_]*\s*\(",
    re.IGNORECASE,
)
_NORMATIVE_MARKER_RE = re.compile(
    r"(?:NORMATIVE|POLICY_VERSION|METHODOLOGY_(?:VERSION|CONTRACT)|"
    r"ACCEPTANCE_(?:VERSION|CONTRACT|OBJECTIVE)|SUFFICIENCY|PROMOTION_(?:RULE|GATE))",
    re.IGNORECASE,
)
_DECISION_MARKERS = (
    "decision_state",
    "governance_state",
    "execution_state",
    "ready_for_",
    "promotion_rule",
    "promotion_gate",
    "hard_blocker",
    "enforce_authorized",
)
_GATE_OUTCOME_RE = re.compile(
    r"(?:\bgate\s*:|\bGATE\s*=|BLOCKED[_A-Z0-9-]*|['\"]PASS['\"])",
    re.IGNORECASE,
)
_FAILURE_BEHAVIOR_RE = re.compile(
    r"(?:throw\s+new\s+Error|process\.exit(?:Code)?\s*=|process\.exit\s*\(|assert\.)",
    re.IGNORECASE,
)
_ASSERTION_RE = re.compile(r"(?:\bassert(?:\.|\s*\()|\bfail\s*\()", re.IGNORECASE)
_LIVE_EVIDENCE_RE = re.compile(
    r"(?:createServiceClient|persist[A-Za-z0-9_]*|\.from\s*\(|fetch\s*\(|"
    r"hosted|production|live[_ -]?verification)",
    re.IGNORECASE,
)
_EVALUATION_CEILING_RE = re.compile(
    r"(?:SYNTHETIC_SIMULATION_EVIDENCE|DIAGNOSTIC_ONLY|"
    r"synthetic_evidence_evaluation_only\s*:\s*true|"
    r"(?:release|judge|oracle)_authority\s*:\s*['\"]NOT_ESTABLISHED['\"]|"
    r"real_user_preference_oracle\s*:\s*['\"]NOT_ESTABLISHED['\"])",
    re.IGNORECASE,
)
_SUPPORTING_PATH_RE = re.compile(
    r"(?:^|/)(?:test|tests|scripts?)(?:/|$)|(?:^|[-_.])verify(?:[-_.]|$)",
    re.IGNORECASE,
)


def _semantic_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("R4 semantic evidence text must be a string")
    changed: list[str] = []
    has_patch_markers = False
    for raw in value.splitlines():
        if raw.startswith(("+++", "---", "diff --git ", "@@")):
            has_patch_markers = True
            continue
        if raw.startswith("+") or raw.startswith("-"):
            has_patch_markers = True
            changed.append(raw[1:])
    if has_patch_markers and changed:
        return "\n".join(changed)
    return value


def analyze_r4_semantics(path: str, evidence_text: str) -> dict[str, Any]:
    normalized_path = PurePosixPath(str(path).replace("\\", "/")).as_posix()
    text = _semantic_text(evidence_text)
    lowered = text.lower()

    evaluation_ceiling = bool(_EVALUATION_CEILING_RE.search(text))
    evaluate_function = bool(_EVALUATE_FUNCTION_RE.search(text))
    normative_marker = bool(_NORMATIVE_MARKER_RE.search(text))
    decision_markers = sorted(
        marker for marker in _DECISION_MARKERS if marker in lowered
    )
    gate_outcome = bool(_GATE_OUTCOME_RE.search(text))
    failure_behavior = bool(_FAILURE_BEHAVIOR_RE.search(text))
    assertion_behavior = bool(_ASSERTION_RE.search(text))
    live_evidence = bool(_LIVE_EVIDENCE_RE.search(text))
    live_path = "live-verification" in normalized_path.lower() or "live_verification" in normalized_path.lower()
    supporting_path = bool(_SUPPORTING_PATH_RE.search(normalized_path))

    reason_ids: list[str]
    if evaluation_ceiling:
        classification = "SUPPORTING_EVALUATION_ONLY"
        reason_ids = ["R4_EXPLICIT_EVALUATION_AUTHORITY_CEILING"]
    elif evaluate_function and normative_marker and len(decision_markers) >= 2:
        classification = "NORMATIVE_DECISION_AUTHORITY"
        reason_ids = [
            "R4_EVALUATOR_FUNCTION",
            "R4_NORMATIVE_AUTHORITY_MARKER",
            "R4_DECISION_OUTPUT_CONTRACT",
        ]
    elif gate_outcome and failure_behavior and assertion_behavior:
        classification = "EXECUTABLE_VERIFICATION_GATE_AUTHORITY"
        reason_ids = [
            "R4_EXPLICIT_GATE_OUTCOME",
            "R4_FAIL_CLOSED_EXECUTION",
            "R4_EXECUTABLE_ASSERTIONS",
        ]
    elif live_path and live_evidence and failure_behavior and assertion_behavior:
        classification = "EXECUTABLE_VERIFICATION_GATE_AUTHORITY"
        reason_ids = [
            "R4_LIVE_VERIFICATION_ROLE",
            "R4_LIVE_OR_PERSISTED_EVIDENCE",
            "R4_FAIL_CLOSED_EXECUTION",
        ]
    elif supporting_path and (assertion_behavior or failure_behavior):
        classification = "SUPPORTING_REGRESSION_ONLY"
        reason_ids = ["R4_SUPPORTING_ASSERTION_HARNESS_WITHOUT_AUTHORITY_OUTPUT"]
    else:
        classification = "UNKNOWN"
        reason_ids = ["R4_SEMANTIC_AUTHORITY_NOT_PROVEN"]

    return {
        "contract_version": CONTRACT_VERSION,
        "path": normalized_path,
        "classification": classification,
        "is_r4_authority": classification in {
            "NORMATIVE_DECISION_AUTHORITY",
            "EXECUTABLE_VERIFICATION_GATE_AUTHORITY",
        },
        "reason_ids": reason_ids,
        "signals": {
            "evaluation_ceiling": evaluation_ceiling,
            "evaluate_function": evaluate_function,
            "normative_marker": normative_marker,
            "decision_markers": decision_markers,
            "gate_outcome": gate_outcome,
            "failure_behavior": failure_behavior,
            "assertion_behavior": assertion_behavior,
            "live_evidence": live_evidence,
            "live_path": live_path,
            "supporting_path": supporting_path,
        },
    }


def project_r4_semantic_candidate(
    request: dict[str, Any],
    profile: dict[str, Any],
    file_evidence: dict[str, str],
    *,
    workflow_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = _risk_projection(request, profile, workflow_evidence)
    analyses = [
        analyze_r4_semantics(path, file_evidence[path])
        for path in request["changed_files"]
        if path in file_evidence
    ]
    r4_paths = sorted(
        item["path"] for item in analyses if item["is_r4_authority"]
    )
    candidate = deepcopy(current)
    if r4_paths:
        candidate["path_floor_band"] = "R4"
        candidate["effective_band"] = "R4"
        candidate["reasons"] = [
            deepcopy(item)
            for item in candidate["reasons"]
            if item["reason_id"] != "TASK_CLASS_UNDERDECLARED"
        ]
        candidate["reasons"].append(
            {
                "reason_id": "SEMANTIC_R4_AUTHORITY",
                "band": "R4",
                "paths": r4_paths,
            }
        )
        if "task_class_underdeclared" in candidate:
            candidate["task_class_underdeclared"] = (
                BAND_ORDER[candidate["base_band"]] < BAND_ORDER["R4"]
            )
        if BAND_ORDER[candidate["base_band"]] < BAND_ORDER["R4"]:
            candidate["reasons"].append(
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
        "current_risk": current,
        "candidate_risk": candidate,
        "r4_semantic_paths": r4_paths,
        "band_changed": current["effective_band"] != candidate["effective_band"],
    }

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterable

from .identity import canonical_json_sha256
from .operational_policy import CONTRACT_VERSION as POLICY_CONTRACT_VERSION
from .operational_policy import POLICY_AUTHORITY
from .operational_policy_binder import _matches_path


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_OPERATIONAL_POLICY_MATCH_EXPLANATION_V1"
AMBIGUITY_MECHANISMS = {
    "NONE",
    "SAME_PATH_MULTI_CLASS",
    "MULTI_PATH_MULTI_CLASS",
    "MIXED",
}


class OperationalPolicyMatchExplanationError(RuntimeError):
    pass


def _normalize_changed_files(changed_files: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for index, value in enumerate(changed_files):
        if not isinstance(value, str):
            raise OperationalPolicyMatchExplanationError(
                f"changed_files[{index}] must be a string"
            )
        raw = value.strip().replace("\\", "/")
        candidate = PurePosixPath(raw)
        if not raw or candidate.is_absolute() or ".." in candidate.parts:
            raise OperationalPolicyMatchExplanationError(
                f"changed_files[{index}] must remain project-relative: {value!r}"
            )
        normalized.append(candidate.as_posix())
    if len(set(normalized)) != len(normalized):
        raise OperationalPolicyMatchExplanationError(
            "changed_files must not contain normalized duplicates"
        )
    return sorted(normalized)


def _validate_policy(policy: Any) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise OperationalPolicyMatchExplanationError("policy must contain an object")
    if policy.get("contract_version") != POLICY_CONTRACT_VERSION:
        raise OperationalPolicyMatchExplanationError(
            f"policy contract must be {POLICY_CONTRACT_VERSION}"
        )
    if policy.get("policy_authority") != POLICY_AUTHORITY:
        raise OperationalPolicyMatchExplanationError(
            f"policy authority must be {POLICY_AUTHORITY}"
        )
    if not isinstance(policy.get("project_id"), str) or not policy["project_id"].strip():
        raise OperationalPolicyMatchExplanationError("policy project_id must be non-empty")
    if not isinstance(policy.get("policy_sha256"), str) or len(policy["policy_sha256"]) != 64:
        raise OperationalPolicyMatchExplanationError(
            "policy must be normalized and include policy_sha256"
        )
    classes = policy.get("operational_classes")
    if not isinstance(classes, dict) or not classes:
        raise OperationalPolicyMatchExplanationError(
            "policy operational_classes must be a non-empty object"
        )
    for class_id, item in classes.items():
        if not isinstance(class_id, str) or not class_id:
            raise OperationalPolicyMatchExplanationError(
                "operational class ids must be non-empty strings"
            )
        if not isinstance(item, dict) or not isinstance(item.get("paths"), list):
            raise OperationalPolicyMatchExplanationError(
                f"operational class {class_id!r} must contain paths"
            )
        if not item["paths"] or any(not isinstance(pattern, str) or not pattern for pattern in item["paths"]):
            raise OperationalPolicyMatchExplanationError(
                f"operational class {class_id!r} paths must contain non-empty strings"
            )
    return policy


def _mechanism(path_matches: list[dict[str, Any]], matched_classes: list[str]) -> str:
    if len(matched_classes) <= 1:
        return "NONE"

    multi_class_rows = [
        row for row in path_matches if len(row["matched_operational_classes"]) > 1
    ]
    if not multi_class_rows:
        return "MULTI_PATH_MULTI_CLASS"

    same_path_classes = {
        class_id
        for row in multi_class_rows
        for class_id in row["matched_operational_classes"]
    }
    if set(matched_classes) - same_path_classes:
        return "MIXED"
    return "SAME_PATH_MULTI_CLASS"


def explain_operational_policy_matches(
    policy: Any,
    changed_files: Iterable[str],
) -> dict[str, Any]:
    """Explain policy path matching without selecting or resolving an operational class."""

    normalized_policy = _validate_policy(policy)
    normalized_files = _normalize_changed_files(changed_files)
    classes = normalized_policy["operational_classes"]

    path_matches: list[dict[str, Any]] = []
    matched_class_ids: set[str] = set()
    for path in normalized_files:
        matched = sorted(
            class_id
            for class_id, item in classes.items()
            if any(_matches_path(path, pattern) for pattern in item["paths"])
        )
        matched_class_ids.update(matched)
        path_matches.append(
            {
                "path": path,
                "matched_operational_classes": matched,
            }
        )

    matched_classes = sorted(matched_class_ids)
    mechanism = _mechanism(path_matches, matched_classes)
    if mechanism not in AMBIGUITY_MECHANISMS:
        raise OperationalPolicyMatchExplanationError(
            f"unsupported ambiguity mechanism: {mechanism}"
        )

    explanation: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "project_id": normalized_policy["project_id"],
        "policy": {
            "contract_version": normalized_policy["contract_version"],
            "policy_authority": normalized_policy["policy_authority"],
            "policy_sha256": normalized_policy["policy_sha256"],
        },
        "changed_files": normalized_files,
        "matched_operational_classes": matched_classes,
        "match_cardinality": len(matched_classes),
        "ambiguous": len(matched_classes) > 1,
        "ambiguity_mechanism": mechanism,
        "path_matches": path_matches,
        "authority": {
            "operational_class_resolution_authorized": False,
            "trust_fact_inferred": False,
            "human_review_inferred": False,
            "outcome_inferred": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
    }
    explanation["explanation_sha256"] = canonical_json_sha256(explanation)
    return explanation

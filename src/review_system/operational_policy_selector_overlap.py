from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .identity import canonical_json_sha256
from .operational_policy import OperationalPolicyError, normalize_operational_policy_data

SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_OPERATIONAL_POLICY_SELECTOR_OVERLAP_V1"
DETECTION_RULES = ("EXACT_SELECTOR_DUPLICATE", "LITERAL_PREFIX_RECURSIVE_SUBSUMPTION")


class OperationalPolicySelectorOverlapError(RuntimeError):
    pass


def _validate_policy(policy: Any) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise OperationalPolicySelectorOverlapError("policy must contain an object")
    body = {key: value for key, value in policy.items() if key != "policy_sha256"}
    try:
        normalized = normalize_operational_policy_data(body)
    except OperationalPolicyError as exc:
        raise OperationalPolicySelectorOverlapError(f"invalid operational policy: {exc}") from exc
    if normalized != policy:
        raise OperationalPolicySelectorOverlapError("policy must match canonical normalized form")
    return normalized


def _literal_recursive_prefix(pattern: str) -> tuple[str, ...] | None:
    parts = tuple(PurePosixPath(pattern).parts)
    if not parts or parts[-1] != "**":
        return None
    prefix = parts[:-1]
    if any(part == "**" or any(token in part for token in ("*", "?", "[")) for part in prefix):
        return None
    return prefix


def _is_under_prefix(pattern: str, prefix: tuple[str, ...]) -> bool:
    parts = tuple(PurePosixPath(pattern).parts)
    return len(parts) >= len(prefix) and parts[: len(prefix)] == prefix


def _finding(
    class_a: str,
    selector_a: str,
    class_b: str,
    selector_b: str,
    relation: str,
    broad_class: str,
    broad_selector: str,
    narrow_class: str,
    narrow_selector: str,
) -> dict[str, Any]:
    value = {
        "class_a": class_a,
        "selector_a": selector_a,
        "class_b": class_b,
        "selector_b": selector_b,
        "relation": relation,
        "proven_overlap": True,
        "broad_class": broad_class,
        "broad_selector": broad_selector,
        "narrow_class": narrow_class,
        "narrow_selector": narrow_selector,
    }
    value["finding_sha256"] = canonical_json_sha256(value)
    return value


def diagnose_operational_policy_selector_overlaps(policy: Any) -> dict[str, Any]:
    """Return sound, deliberately non-exhaustive static selector-overlap findings."""

    normalized = _validate_policy(policy)
    classes = normalized["operational_classes"]
    class_ids = sorted(classes)
    findings: list[dict[str, Any]] = []

    for left_index, class_a in enumerate(class_ids):
        for class_b in class_ids[left_index + 1 :]:
            for selector_a in classes[class_a]["paths"]:
                for selector_b in classes[class_b]["paths"]:
                    if selector_a == selector_b:
                        findings.append(
                            _finding(
                                class_a,
                                selector_a,
                                class_b,
                                selector_b,
                                "EXACT_SELECTOR_DUPLICATE",
                                class_a,
                                selector_a,
                                class_b,
                                selector_b,
                            )
                        )
                        continue

                    prefix_a = _literal_recursive_prefix(selector_a)
                    prefix_b = _literal_recursive_prefix(selector_b)
                    if prefix_a is not None and _is_under_prefix(selector_b, prefix_a):
                        findings.append(
                            _finding(
                                class_a,
                                selector_a,
                                class_b,
                                selector_b,
                                "LITERAL_PREFIX_RECURSIVE_SUBSUMPTION",
                                class_a,
                                selector_a,
                                class_b,
                                selector_b,
                            )
                        )
                    elif prefix_b is not None and _is_under_prefix(selector_a, prefix_b):
                        findings.append(
                            _finding(
                                class_a,
                                selector_a,
                                class_b,
                                selector_b,
                                "LITERAL_PREFIX_RECURSIVE_SUBSUMPTION",
                                class_b,
                                selector_b,
                                class_a,
                                selector_a,
                            )
                        )

    findings.sort(
        key=lambda item: (
            item["class_a"],
            item["class_b"],
            item["selector_a"],
            item["selector_b"],
            item["relation"],
        )
    )
    class_pairs = sorted({f"{item['class_a']}|{item['class_b']}" for item in findings})
    affected_classes = sorted(
        {item["class_a"] for item in findings} | {item["class_b"] for item in findings}
    )

    diagnostic: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "project_id": normalized["project_id"],
        "policy": {
            "contract_version": normalized["contract_version"],
            "policy_authority": normalized["policy_authority"],
            "policy_sha256": normalized["policy_sha256"],
        },
        "detection_scope": {
            "rules": list(DETECTION_RULES),
            "proven_overlap_only": True,
            "arbitrary_glob_intersection_exhaustive": False,
        },
        "summary": {
            "finding_count": len(findings),
            "class_pair_count": len(class_pairs),
            "affected_class_count": len(affected_classes),
            "affected_classes": affected_classes,
            "class_pairs": class_pairs,
            "relation_histogram": {
                rule: sum(1 for item in findings if item["relation"] == rule)
                for rule in DETECTION_RULES
            },
        },
        "findings": findings,
        "authority": {
            "policy_defect_inferred": False,
            "policy_intent_inferred": False,
            "operational_class_resolution_authorized": False,
            "policy_change_authorized": False,
            "trust_fact_inferred": False,
            "human_review_inferred": False,
            "outcome_inferred": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
    }
    diagnostic["diagnostic_sha256"] = canonical_json_sha256(diagnostic)
    return diagnostic

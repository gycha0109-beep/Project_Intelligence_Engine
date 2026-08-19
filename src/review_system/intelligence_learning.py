from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Iterable

from .intelligence_config import normalize_path, path_matches, validate_rules


def _area_for_path(path: str, components: list[dict[str, Any]]) -> tuple[str, list[str]]:
    normalized = normalize_path(path)
    matched = [component["id"] for component in components if path_matches(normalized, component.get("paths", []))]
    if matched:
        component_id = sorted(matched)[0]
        patterns = next(component.get("paths", []) for component in components if component.get("id") == component_id)
        return f"component:{component_id}", list(patterns)
    parts = PurePosixPath(normalized).parts
    if len(parts) >= 2:
        area = "/".join(parts[:2])
        return f"path:{area}", [f"{area}/**"]
    if parts:
        return f"path:{parts[0]}", [parts[0]]
    return "path:<root>", ["*"]


def discover_rule_candidates(
    history: Iterable[dict[str, Any]],
    *,
    components: list[dict[str, Any]] | None = None,
    min_samples: int = 3,
    min_confidence: float = 0.75,
    min_support: float = 0.1,
) -> dict[str, Any]:
    if min_samples < 2:
        raise ValueError("min_samples must be at least 2")
    if not 0 < min_confidence <= 1:
        raise ValueError("min_confidence must be in (0, 1]")
    if not 0 <= min_support <= 1:
        raise ValueError("min_support must be in [0, 1]")
    component_defs = components or []
    area_count: Counter[str] = Counter()
    pair_count: Counter[tuple[str, str]] = Counter()
    area_patterns: dict[str, list[str]] = {}
    normalized_history: list[dict[str, Any]] = []

    for index, change in enumerate(history):
        if not isinstance(change, dict):
            raise ValueError(f"history[{index}] must be an object")
        change_id = change.get("id", f"change-{index + 1}")
        files = sorted({normalize_path(path) for path in change.get("changed_files", []) if isinstance(path, str) and path.strip()})
        areas: set[str] = set()
        for path in files:
            area, patterns = _area_for_path(path, component_defs)
            areas.add(area)
            area_patterns.setdefault(area, patterns)
        for area in areas:
            area_count[area] += 1
        for source in areas:
            for target in areas:
                if source != target:
                    pair_count[(source, target)] += 1
        normalized_history.append({"id": str(change_id), "changed_files": files, "areas": sorted(areas)})

    total = len(normalized_history)
    candidates: list[dict[str, Any]] = []
    for (source, target), sample_count in sorted(pair_count.items()):
        if sample_count < min_samples:
            continue
        source_count = area_count[source]
        if not source_count:
            continue
        confidence = sample_count / source_count
        support = sample_count / total if total else 0.0
        if confidence < min_confidence or support < min_support:
            continue
        digest = hashlib.sha256(f"{source}->{target}".encode("utf-8")).hexdigest()[:10].upper()
        candidates.append({
            "id": f"LC_{digest}",
            "title": f"Review {target} when {source} changes",
            "status": "candidate",
            "trigger": {"paths_any": area_patterns[source]},
            "impact": {
                "components": [target.split(":", 1)[1]] if target.startswith("component:") else [],
                "paths": area_patterns[target],
            },
            "review": {"packs": [], "required_tests": []},
            "rationale": f"Observed {source} and {target} changing together in {sample_count} historical change sets.",
            "evidence": {
                "sample_count": sample_count,
                "source_change_count": source_count,
                "history_size": total,
                "confidence": round(confidence, 4),
                "support": round(support, 4),
                "method": "asymmetric co-change association",
            },
        })
    output = {
        "schema_version": "1.0",
        "rules": sorted(candidates, key=lambda item: (-item["evidence"]["confidence"], -item["evidence"]["sample_count"], item["id"])),
        "analysis": {
            "history_size": total,
            "area_counts": dict(sorted(area_count.items())),
            "thresholds": {
                "min_samples": min_samples,
                "min_confidence": min_confidence,
                "min_support": min_support,
            },
        },
        "limitations": [
            "Co-change indicates historical association, not a causal dependency.",
            "Candidates cannot affect merge gates until explicitly approved.",
        ],
    }
    errors = validate_rules({"schema_version": "1.0", "rules": output["rules"]}, required_status="candidate")
    if errors:
        raise ValueError("generated invalid candidate rules: " + "; ".join(errors))
    return output



def merge_rule_candidates(existing: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    existing_rules = {rule.get("id"): rule for rule in existing.get("rules", []) if isinstance(rule, dict) and rule.get("id")}
    merged: list[dict[str, Any]] = []
    discovered_ids: set[str] = set()
    for rule in discovered.get("rules", []):
        rule_id = rule.get("id")
        if not isinstance(rule_id, str):
            continue
        discovered_ids.add(rule_id)
        previous = existing_rules.get(rule_id)
        if previous and previous.get("status") in {"approved", "rejected", "retired"}:
            preserved = {**previous, "latest_observation": rule.get("evidence", {})}
            merged.append(preserved)
        elif previous:
            merged.append({**rule, "first_observed": previous.get("first_observed", previous.get("evidence", {}))})
        else:
            merged.append(rule)
    for rule_id, previous in existing_rules.items():
        if rule_id not in discovered_ids:
            merged.append(previous)
    result = {
        **discovered,
        "rules": sorted(merged, key=lambda item: item["id"]),
    }
    errors = validate_rules({"schema_version": "1.0", "rules": result["rules"]})
    if errors:
        raise ValueError("merged candidate rules are invalid: " + "; ".join(errors))
    return result

def approve_candidate_rule(
    candidates: dict[str, Any],
    approved: dict[str, Any],
    candidate_id: str,
    *,
    approved_by: str,
    approved_at: str | None = None,
    rationale: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not approved_by.strip():
        raise ValueError("approved_by is required")
    candidate_rules = candidates.get("rules", [])
    approved_rules = approved.get("rules", [])
    selected = next((rule for rule in candidate_rules if rule.get("id") == candidate_id), None)
    if selected is None:
        raise ValueError(f"candidate rule not found: {candidate_id}")
    if selected.get("status") != "candidate":
        raise ValueError(f"rule is not pending approval: {candidate_id}")
    if any(rule.get("id") == candidate_id for rule in approved_rules):
        raise ValueError(f"rule already approved: {candidate_id}")
    timestamp = approved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    promoted = {key: value for key, value in selected.items()}
    promoted["status"] = "approved"
    promoted["approval"] = {
        "approved_by": approved_by,
        "approved_at": timestamp,
        "source_candidate_id": candidate_id,
    }
    if rationale:
        promoted["approval"]["rationale"] = rationale
    updated_candidates = {
        **candidates,
        "rules": [
            ({**promoted, "promoted_at": timestamp} if rule.get("id") == candidate_id else rule)
            for rule in candidate_rules
        ],
    }
    updated_approved = {
        "schema_version": "1.0",
        "rules": sorted([*approved_rules, promoted], key=lambda item: item["id"]),
    }
    approved_errors = validate_rules(updated_approved, required_status="approved")
    if approved_errors:
        raise ValueError("approval produced invalid rules: " + "; ".join(approved_errors))
    return updated_candidates, updated_approved

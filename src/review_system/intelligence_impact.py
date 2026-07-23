from __future__ import annotations

from collections import defaultdict, deque
from pathlib import PurePosixPath
import re
from typing import Any, Iterable

from .intelligence_config import match_rule, normalize_path, path_matches
from .packs import select_packs_with_reasons


_RELATION_CONFIDENCE = {
    "imports": 0.92,
    "verifies": 0.95,
    "likely_verifies": 0.60,
    "references": 0.88,
    "documents": 0.72,
    "contains": 0.85,
    "defines": 0.98,
}


def _file_id(path: str) -> str:
    return f"file:{normalize_path(path)}"


def _graph_indexes(graph: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]]]:
    nodes = {node["id"]: node for node in graph.get("nodes", []) if isinstance(node, dict) and isinstance(node.get("id"), str)}
    outbound: dict[str, list[dict[str, str]]] = defaultdict(list)
    inbound: dict[str, list[dict[str, str]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = edge.get("source")
        target = edge.get("target")
        relation = edge.get("type")
        if not all(isinstance(value, str) for value in (source, target, relation)):
            continue
        outbound[source].append(edge)
        inbound[target].append(edge)
    return nodes, outbound, inbound


def _component_paths(graph: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    nodes = {node["id"]: node for node in graph.get("nodes", []) if isinstance(node, dict)}
    for edge in graph.get("edges", []):
        if edge.get("type") != "contains":
            continue
        source = edge.get("source", "")
        target = edge.get("target", "")
        if source.startswith("component:") and target.startswith("file:") and target in nodes:
            result[source.split(":", 1)[1]].add(nodes[target].get("path", target.split(":", 1)[1]))
    return result


def _walk_dependents(
    changed_ids: set[str],
    nodes: dict[str, dict[str, Any]],
    inbound: dict[str, list[dict[str, str]]],
    *,
    max_depth: int,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    discovered: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, Any]] = []
    queue: deque[tuple[str, int, list[str], float]] = deque((node_id, 0, [node_id], 1.0) for node_id in sorted(changed_ids))
    best_depth: dict[str, int] = {node_id: 0 for node_id in changed_ids}
    while queue:
        current, depth, chain, confidence = queue.popleft()
        if depth >= max_depth:
            continue
        for edge in sorted(inbound.get(current, []), key=lambda item: (item["source"], item["type"])):
            source = edge["source"]
            relation = edge["type"]
            if source in changed_ids:
                continue
            node = nodes.get(source)
            if not node or node.get("type") != "file":
                continue
            next_depth = depth + 1
            if source in best_depth and best_depth[source] <= next_depth:
                continue
            best_depth[source] = next_depth
            relation_confidence = _RELATION_CONFIDENCE.get(relation, 0.65)
            next_confidence = round(confidence * relation_confidence * (0.92 if depth else 1.0), 4)
            path_chain = [*chain, source]
            discovered[source] = {
                "path": node.get("path", source.split(":", 1)[1]),
                "depth": next_depth,
                "confidence": next_confidence,
                "via_relation": relation,
                "path_chain": path_chain,
            }
            evidence.append({
                "classification": "inferred_structure" if relation == "likely_verifies" else "confirmed_structure",
                "confidence": next_confidence,
                "summary": f"{source} reaches changed node {current} through {relation}",
                "relation": relation,
                "source": source,
                "target": current,
            })
            queue.append((source, next_depth, path_chain, next_confidence))
    return discovered, evidence


def _direct_dependencies(
    changed_ids: set[str],
    nodes: dict[str, dict[str, Any]],
    outbound: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    dependencies: dict[str, dict[str, Any]] = {}
    for changed_id in sorted(changed_ids):
        for edge in outbound.get(changed_id, []):
            target = edge["target"]
            node = nodes.get(target)
            if not node or node.get("type") not in {"file", "database_object"}:
                continue
            relation = edge["type"]
            dependencies[target] = {
                "id": target,
                "path": node.get("path"),
                "name": node.get("name"),
                "type": node.get("type"),
                "via_relation": relation,
                "confidence": _RELATION_CONFIDENCE.get(relation, 0.65),
            }
    return sorted(dependencies.values(), key=lambda item: item["id"])


def _changed_components(changed_files: list[str], component_paths: dict[str, set[str]]) -> list[str]:
    changed = set(changed_files)
    return sorted(component_id for component_id, paths in component_paths.items() if changed & paths)


def _rule_impacts(
    rules: Iterable[dict[str, Any]],
    changed_files: list[str],
) -> tuple[list[dict[str, Any]], set[str], set[str], set[str]]:
    matches: list[dict[str, Any]] = []
    impact_paths: set[str] = set()
    packs: set[str] = set()
    required_tests: set[str] = set()
    for rule in rules:
        if rule.get("status") != "approved":
            continue
        matched, reasons = match_rule(rule, changed_files)
        if not matched:
            continue
        impact = rule.get("impact", {})
        review = rule.get("review", {})
        rule_paths = {normalize_path(path) for path in impact.get("paths", []) if isinstance(path, str)}
        rule_packs = {pack for pack in review.get("packs", []) if isinstance(pack, str)}
        tests = {test for test in review.get("required_tests", []) if isinstance(test, str)}
        impact_paths.update(rule_paths)
        packs.update(rule_packs)
        required_tests.update(tests)
        matches.append({
            "rule_id": rule.get("id"),
            "title": rule.get("title", rule.get("id")),
            "matched_files": reasons,
            "impact_paths": sorted(rule_paths),
            "impact_components": sorted(set(impact.get("components", []) or [])),
            "review_packs": sorted(rule_packs),
            "required_tests": sorted(tests),
            "rationale": rule.get("rationale", ""),
            "classification": "approved_rule",
            "confidence": 1.0,
        })
    return matches, impact_paths, packs, required_tests


def _expand_rule_patterns(rule_paths: set[str], graph_files: set[str]) -> set[str]:
    expanded: set[str] = set()
    for pattern in rule_paths:
        if any(token in pattern for token in "*?["):
            expanded.update(path for path in graph_files if path_matches(path, [pattern]))
        elif pattern in graph_files:
            expanded.add(pattern)
    return expanded


def analyze_change(
    graph: dict[str, Any],
    changed_files: Iterable[str],
    *,
    configured_packs: Iterable[str] = (),
    approved_rules: Iterable[dict[str, Any]] = (),
    max_depth: int = 3,
    change_id: str | None = None,
    base_revision: str | None = None,
    head_revision: str | None = None,
) -> dict[str, Any]:
    if max_depth < 1 or max_depth > 10:
        raise ValueError("max_depth must be between 1 and 10")
    changed = sorted({normalize_path(path) for path in changed_files if str(path).strip()})
    nodes, outbound, inbound = _graph_indexes(graph)
    graph_files = {node.get("path") for node in nodes.values() if node.get("type") == "file" and isinstance(node.get("path"), str)}
    changed_ids = {_file_id(path) for path in changed if _file_id(path) in nodes}
    missing_from_graph = sorted(path for path in changed if _file_id(path) not in nodes)
    dependents, structural_evidence = _walk_dependents(changed_ids, nodes, inbound, max_depth=max_depth)
    dependencies = _direct_dependencies(changed_ids, nodes, outbound)
    components = _component_paths(graph)
    changed_components = _changed_components(changed, components)

    pack_reasons = select_packs_with_reasons(changed, configured_packs)
    matched_rules, rule_path_patterns, rule_packs, required_tests = _rule_impacts(approved_rules, changed)
    configured_pack_set = set(configured_packs)
    unconfigured_rule_packs = sorted(rule_packs - configured_pack_set)
    for pack in sorted(rule_packs & configured_pack_set):
        pack_reasons.setdefault(pack, []).append("<approved project rule>")
    rule_paths = _expand_rule_patterns(rule_path_patterns, graph_files)

    impacted_files: dict[str, dict[str, Any]] = {
        item["path"]: {
            "path": item["path"],
            "source": "structural_graph",
            "sources": [
                {
                    "type": "structural_graph",
                    "depth": item["depth"],
                    "confidence": item["confidence"],
                    "via_relation": item["via_relation"],
                }
            ],
            "depth": item["depth"],
            "confidence": item["confidence"],
            "via_relation": item["via_relation"],
        }
        for item in dependents.values()
    }
    matching_rule_ids_by_path: dict[str, list[str]] = defaultdict(list)
    for match in matched_rules:
        for pattern in match.get("impact_paths", []):
            for path in graph_files:
                if path_matches(path, [pattern]):
                    matching_rule_ids_by_path[path].append(match["rule_id"])
    for path in sorted(rule_paths):
        previous = impacted_files.get(path)
        rule_source = {
            "type": "approved_rule",
            "confidence": 1.0,
            "rule_ids": sorted(set(matching_rule_ids_by_path.get(path, []))),
        }
        if previous:
            previous["sources"].append(rule_source)
            previous["sources"] = sorted(previous["sources"], key=lambda item: item["type"])
            previous["source"] = "structural_graph+approved_rule"
            previous["confidence"] = 1.0
        else:
            impacted_files[path] = {
                "path": path,
                "source": "approved_rule",
                "sources": [rule_source],
                "depth": None,
                "confidence": 1.0,
                "via_relation": "rule",
            }

    recommended_tests = set(required_tests)
    executable_test_languages = {"python", "java", "kotlin", "javascript", "typescript", "sql", "shell", "powershell"}
    file_nodes_by_path = {
        node.get("path"): node
        for node in nodes.values()
        if node.get("type") == "file" and isinstance(node.get("path"), str)
    }
    candidate_test_paths = set(changed)
    candidate_test_paths.update(item["path"] for item in impacted_files.values())
    for path in candidate_test_paths:
        node = file_nodes_by_path.get(path, {})
        lowered_name = PurePosixPath(path).name.lower()
        lowered_stem = PurePosixPath(path).stem.lower()
        name_tokens = {token for token in re.split(r"[^a-z0-9]+", lowered_name) if token}
        path_parts = {part.lower() for part in PurePosixPath(path).parts}
        named_test = (
            bool(name_tokens & {"test", "tests", "spec"})
            or lowered_stem.startswith(("test_", "test-"))
            or lowered_stem.endswith(("test", "tests", "_spec", "-spec", ".spec"))
        )
        verification_runner = "verification" in path_parts and lowered_stem.startswith(("run_", "run-", "verify_", "verify-"))
        looks_like_test = named_test or verification_runner or lowered_stem.startswith(("verify_", "verify-"))
        if looks_like_test and node.get("language") in executable_test_languages:
            recommended_tests.add(path)

    evidence = [
        {
            "classification": "confirmed_change",
            "confidence": 1.0,
            "summary": f"changed file present in graph: {path}",
            "path": path,
        }
        for path in changed
        if path not in missing_from_graph
    ]
    evidence.extend(structural_evidence)
    evidence.extend({
        "classification": "approved_rule",
        "confidence": 1.0,
        "summary": f"approved rule {match['rule_id']} matched",
        "rule_id": match["rule_id"],
        "matched_files": match["matched_files"],
    } for match in matched_rules)
    evidence.extend({
        "classification": "unknown",
        "confidence": 0.0,
        "summary": f"changed file is absent from graph: {path}",
        "path": path,
    } for path in missing_from_graph)

    result = {
        "schema_version": "1.0",
        "change": {
            "id": change_id,
            "base_revision": base_revision,
            "head_revision": head_revision,
            "changed_files": changed,
        },
        "graph_sha256": graph.get("graph_sha256"),
        "direct": {
            "files_in_graph": sorted(path for path in changed if path not in missing_from_graph),
            "files_missing_from_graph": missing_from_graph,
            "components": changed_components,
        },
        "impact": {
            "dependent_files": sorted(impacted_files.values(), key=lambda item: (item["path"], str(item["source"]))),
            "direct_dependencies": dependencies,
            "matched_rules": matched_rules,
        },
        "review": {
            "selected_packs": sorted(pack_reasons),
            "pack_reasons": {pack: sorted(set(reasons)) for pack, reasons in sorted(pack_reasons.items())},
            "required_tests": sorted(recommended_tests),
            "unconfigured_rule_packs": unconfigured_rule_packs,
        },
        "evidence": sorted(evidence, key=lambda item: (item["classification"], item.get("path", ""), item.get("rule_id", ""), item["summary"])),
        "limitations": [
            "Impact is structural and rule-based; runtime dispatch, reflection, generated code, and external services may be absent.",
            "A reported relation is a review signal, not proof that behavior changed.",
        ],
    }
    return result


def compare_change_sets(change_sets: Iterable[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for index, change in enumerate(change_sets):
        if not isinstance(change, dict):
            raise ValueError(f"change_sets[{index}] must be an object")
        change_id = change.get("id")
        if not isinstance(change_id, str) or not change_id:
            raise ValueError(f"change_sets[{index}].id is required")
        changed_files = sorted({normalize_path(path) for path in change.get("changed_files", []) if isinstance(path, str) and path.strip()})
        impacted_files = sorted({normalize_path(path) for path in change.get("impacted_files", []) if isinstance(path, str) and path.strip()})
        components = sorted({component for component in change.get("components", []) if isinstance(component, str) and component})
        review_packs = sorted({pack for pack in change.get("review_packs", []) if isinstance(pack, str) and pack})
        matched_rules = sorted({rule for rule in change.get("matched_rules", []) if isinstance(rule, str) and rule})
        normalized.append({
            "id": change_id,
            "base_revision": change.get("base_revision"),
            "head_revision": change.get("head_revision"),
            "changed_files": changed_files,
            "impacted_files": impacted_files,
            "components": components,
            "review_packs": review_packs,
            "matched_rules": matched_rules,
        })
    ids = [change["id"] for change in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("change set IDs must be unique")

    comparisons: list[dict[str, Any]] = []
    for left_index, left in enumerate(normalized):
        for right in normalized[left_index + 1:]:
            direct_overlap = sorted(set(left["changed_files"]) & set(right["changed_files"]))
            left_total = set(left["changed_files"]) | set(left["impacted_files"])
            right_total = set(right["changed_files"]) | set(right["impacted_files"])
            impact_overlap = sorted((left_total & right_total) - set(direct_overlap))
            component_overlap = sorted(set(left["components"]) & set(right["components"]))
            review_pack_overlap = sorted(set(left["review_packs"]) & set(right["review_packs"]))
            matched_rule_overlap = sorted(set(left["matched_rules"]) & set(right["matched_rules"]))
            base_mismatch = bool(left.get("base_revision") and right.get("base_revision") and left["base_revision"] != right["base_revision"])
            pack_score = sum(
                20 if pack.startswith("domain.") else 3 if pack.startswith("universal.") else 10
                for pack in review_pack_overlap
            )
            score = min(
                100,
                len(direct_overlap) * 35
                + len(impact_overlap) * 10
                + len(component_overlap) * 15
                + pack_score
                + len(matched_rule_overlap) * 20
                + (10 if base_mismatch else 0),
            )
            level = "high" if score >= 60 else "medium" if score >= 20 else "low" if score else "none"
            reasons: list[str] = []
            if direct_overlap:
                reasons.append("direct file overlap")
            if impact_overlap:
                reasons.append("structural or rule-derived impact overlap")
            if component_overlap:
                reasons.append("shared project component")
            if review_pack_overlap:
                reasons.append("shared review domain")
            if matched_rule_overlap:
                reasons.append("shared approved project rule")
            if base_mismatch:
                reasons.append("different base revisions")
            comparisons.append({
                "left": left["id"],
                "right": right["id"],
                "risk_score": score,
                "risk_level": level,
                "direct_file_overlap": direct_overlap,
                "impact_overlap": impact_overlap,
                "component_overlap": component_overlap,
                "review_pack_overlap": review_pack_overlap,
                "matched_rule_overlap": matched_rule_overlap,
                "base_revision_mismatch": base_mismatch,
                "reasons": reasons,
                "advisory": "Review merge order or rebase requirements." if score else "No overlap detected from supplied evidence.",
            })
    return {
        "schema_version": "1.0",
        "change_sets": normalized,
        "comparisons": sorted(comparisons, key=lambda item: (-item["risk_score"], item["left"], item["right"])),
        "limitations": [
            "No-overlap does not prove semantic independence.",
            "Risk scores are deterministic routing heuristics, not defect probabilities.",
        ],
    }

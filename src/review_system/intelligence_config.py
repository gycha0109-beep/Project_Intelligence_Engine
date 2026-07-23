from __future__ import annotations

import fnmatch
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .io import load_data


_RULE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]{2,63}$")


def normalize_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty string")
    raw = value.strip().replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise ValueError(f"absolute path is not allowed: {value!r}")
    parts = [part for part in PurePosixPath(raw).parts if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise ValueError(f"path traversal is not allowed: {value!r}")
    normalized = PurePosixPath(*parts).as_posix() if parts else ""
    if not normalized:
        raise ValueError(f"empty normalized path is not allowed: {value!r}")
    return normalized


def path_matches(path: str, patterns: list[str]) -> bool:
    normalized = normalize_path(path)
    return any(fnmatch.fnmatchcase(normalized, normalize_path(pattern)) for pattern in patterns)


def load_intelligence_config(path: str | Path) -> dict[str, Any]:
    data = load_data(path)
    if not isinstance(data, dict):
        raise ValueError("intelligence config must be an object")
    errors = validate_intelligence_config(data)
    if errors:
        raise ValueError("invalid intelligence config: " + "; ".join(errors))
    return data


def validate_intelligence_config(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    graph = data.get("graph", {})
    if graph is not None and not isinstance(graph, dict):
        errors.append("graph must be an object")
    elif isinstance(graph, dict):
        max_size = graph.get("max_file_size_bytes", 1_000_000)
        if not isinstance(max_size, int) or isinstance(max_size, bool) or not 1_024 <= max_size <= 10_000_000:
            errors.append("graph.max_file_size_bytes must be an integer between 1024 and 10000000")
    components = data.get("components", [])
    if not isinstance(components, list):
        errors.append("components must be an array")
        components = []
    ids: set[str] = set()
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            errors.append(f"components[{index}] must be an object")
            continue
        component_id = component.get("id")
        if not isinstance(component_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", component_id):
            errors.append(f"components[{index}].id is invalid")
        elif component_id in ids:
            errors.append(f"duplicate component id: {component_id}")
        else:
            ids.add(component_id)
        paths = component.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(item, str) and item for item in paths):
            errors.append(f"components[{index}].paths must be a non-empty string array")
        else:
            for pattern in paths:
                try:
                    normalize_path(pattern)
                except ValueError as exc:
                    errors.append(f"components[{index}].paths: {exc}")
    return errors


def load_rules(path: str | Path, *, required_status: str | None = None) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {"schema_version": "1.0", "rules": []}
    data = load_data(source)
    if not isinstance(data, dict):
        raise ValueError(f"rule file must be an object: {source}")
    errors = validate_rules(data, required_status=required_status)
    if errors:
        raise ValueError(f"invalid rule file {source}: " + "; ".join(errors))
    return data


def validate_rules(data: dict[str, Any], *, required_status: str | None = None) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    rules = data.get("rules")
    if not isinstance(rules, list):
        return [*errors, "rules must be an array"]
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        prefix = f"rules[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{prefix} must be an object")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not _RULE_ID_RE.fullmatch(rule_id):
            errors.append(f"{prefix}.id is invalid")
        elif rule_id in seen:
            errors.append(f"duplicate rule id: {rule_id}")
        else:
            seen.add(rule_id)
        status = rule.get("status")
        if status not in {"candidate", "approved", "rejected", "retired"}:
            errors.append(f"{prefix}.status is invalid")
        if required_status and status != required_status:
            errors.append(f"{prefix}.status must be {required_status}")
        trigger = rule.get("trigger")
        if not isinstance(trigger, dict):
            errors.append(f"{prefix}.trigger must be an object")
        else:
            paths_any = trigger.get("paths_any", [])
            paths_all = trigger.get("paths_all", [])
            if not isinstance(paths_any, list) or not all(isinstance(item, str) and item for item in paths_any):
                errors.append(f"{prefix}.trigger.paths_any must be a string array")
            if not isinstance(paths_all, list) or not all(isinstance(item, str) and item for item in paths_all):
                errors.append(f"{prefix}.trigger.paths_all must be a string array")
            if not paths_any and not paths_all:
                errors.append(f"{prefix}.trigger requires paths_any or paths_all")
            for pattern in [*paths_any, *paths_all]:
                try:
                    normalize_path(pattern)
                except ValueError as exc:
                    errors.append(f"{prefix}.trigger: {exc}")
        impact = rule.get("impact", {})
        if not isinstance(impact, dict):
            errors.append(f"{prefix}.impact must be an object")
        else:
            impact_paths = impact.get("paths", [])
            if not isinstance(impact_paths, list) or not all(isinstance(item, str) and item for item in impact_paths):
                errors.append(f"{prefix}.impact.paths must be a string array")
            else:
                for pattern in impact_paths:
                    try:
                        normalize_path(pattern)
                    except ValueError as exc:
                        errors.append(f"{prefix}.impact: {exc}")
            components = impact.get("components", [])
            if not isinstance(components, list) or not all(isinstance(item, str) and item for item in components):
                errors.append(f"{prefix}.impact.components must be a string array")
        review = rule.get("review", {})
        if not isinstance(review, dict):
            errors.append(f"{prefix}.review must be an object")
        else:
            for field in ("packs", "required_tests"):
                values = review.get(field, [])
                if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
                    errors.append(f"{prefix}.review.{field} must be a string array")
        evidence = rule.get("evidence", {})
        if status == "candidate":
            sample_count = evidence.get("sample_count", 0) if isinstance(evidence, dict) else 0
            if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 1:
                errors.append(f"{prefix}.evidence.sample_count must be positive")
        if status == "approved":
            approval = rule.get("approval")
            if not isinstance(approval, dict):
                errors.append(f"{prefix}.approval is required")
            else:
                if not approval.get("approved_by") or not approval.get("approved_at"):
                    errors.append(f"{prefix}.approval requires approved_by and approved_at")
    return errors


def match_rule(rule: dict[str, Any], changed_files: list[str]) -> tuple[bool, list[str]]:
    trigger = rule.get("trigger", {})
    any_patterns = trigger.get("paths_any", []) or []
    all_patterns = trigger.get("paths_all", []) or []
    any_matches = [path for path in changed_files if path_matches(path, any_patterns)] if any_patterns else []
    all_satisfied = all(any(path_matches(path, [pattern]) for path in changed_files) for pattern in all_patterns)
    matched = (bool(any_matches) if any_patterns else True) and all_satisfied
    reasons = sorted(set(any_matches))
    if matched and all_patterns:
        reasons.extend(f"<required pattern matched: {pattern}>" for pattern in all_patterns)
    return matched, reasons

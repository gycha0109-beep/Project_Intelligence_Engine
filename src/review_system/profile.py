from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from typing import Any, Iterable

from .io import load_data
from .paths import asset


class ProfileResolutionError(ValueError):
    pass


_UNION_LIST_PATHS = {
    ("technology", "languages"),
    ("technology", "frameworks"),
    ("review", "packs"),
}


def _unique(items: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for item in items:
        if item not in result:
            result.append(deepcopy(item))
    return result


def deep_merge(base: dict[str, Any], override: dict[str, Any], path: tuple[str, ...] = ()) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        current_path = path + (key,)
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value, current_path)
        elif key in result and isinstance(result[key], list) and isinstance(value, list) and current_path in _UNION_LIST_PATHS:
            result[key] = _unique([*result[key], *value])
        else:
            result[key] = deepcopy(value)
    return result


def _normalize_stack_fragment(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize both the V0 legacy stack shape and the V0.1 fragment shape."""
    fragment: dict[str, Any] = {}
    if isinstance(data.get("technology"), dict):
        technology = deepcopy(data["technology"])
        database = technology.get("database")
        if isinstance(database, str):
            technology["database"] = {"engine": database}
        build = technology.pop("build", None)
        if isinstance(build, str):
            technology["build"] = {"tool": build}
        fragment["technology"] = technology

    commands = data.get("commands", data.get("default_commands", {}))
    if isinstance(commands, dict):
        normalized_commands = deepcopy(commands)
        if "baseline" not in normalized_commands and "test" in normalized_commands:
            normalized_commands["baseline"] = deepcopy(normalized_commands["test"])
        fragment["commands"] = normalized_commands

    packs = data.get("review", {}).get("packs") if isinstance(data.get("review"), dict) else None
    if packs is None:
        packs = data.get("default_packs")
    if isinstance(packs, list):
        fragment["review"] = {"packs": deepcopy(packs)}
    return fragment


def default_stack_directories() -> list[Path]:
    return [asset("profiles/stacks")]


def _find_stack(stack_id: str, stack_directories: Iterable[str | Path]) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", stack_id):
        raise ProfileResolutionError(f"invalid stack ID: {stack_id!r}")
    candidates: list[Path] = []
    for raw in stack_directories:
        root = Path(raw)
        candidates.extend([root / f"{stack_id}.yml", root / f"{stack_id}.yaml", root / f"{stack_id}.json"])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise ProfileResolutionError(f"unknown inherited stack '{stack_id}'; searched: {searched}")


def resolve_profile_data(
    data: dict[str, Any],
    *,
    stack_directories: Iterable[str | Path] | None = None,
    chain: tuple[str, ...] = (),
) -> dict[str, Any]:
    directories = list(stack_directories or default_stack_directories())
    result: dict[str, Any] = {}
    inherits = data.get("inherits", [])
    if not isinstance(inherits, list):
        raise ProfileResolutionError("inherits must be an array")

    for stack_id in inherits:
        if not isinstance(stack_id, str) or not stack_id:
            raise ProfileResolutionError("inherits entries must be non-empty strings")
        if stack_id in chain:
            cycle = " -> ".join([*chain, stack_id])
            raise ProfileResolutionError(f"profile inheritance cycle: {cycle}")
        stack_path = _find_stack(stack_id, directories)
        stack_data = load_data(stack_path)
        if not isinstance(stack_data, dict):
            raise ProfileResolutionError(f"stack profile must be an object: {stack_path}")
        declared_id = stack_data.get("stack_id")
        if declared_id and declared_id != stack_id:
            raise ProfileResolutionError(
                f"stack ID mismatch: requested '{stack_id}', file declares '{declared_id}'"
            )
        parent_fragment = _normalize_stack_fragment(stack_data)
        parent_inherits = stack_data.get("inherits", [])
        if parent_inherits:
            parent_fragment["inherits"] = parent_inherits
        resolved_parent = resolve_profile_data(
            parent_fragment,
            stack_directories=directories,
            chain=(*chain, stack_id),
        )
        result = deep_merge(result, resolved_parent)

    child = deepcopy(data)
    child.pop("inherits", None)
    result = deep_merge(result, child)
    review = result.get("review", {})
    if isinstance(review, dict):
        excluded = set(review.pop("exclude_packs", []) or [])
        if excluded and isinstance(review.get("packs"), list):
            review["packs"] = [pack for pack in review["packs"] if pack not in excluded]
    result["resolved_inherits"] = list(inherits)
    return result


def resolve_profile_file(
    path: str | Path,
    *,
    stack_directories: Iterable[str | Path] | None = None,
) -> dict[str, Any]:
    source = Path(path)
    data = load_data(source)
    if not isinstance(data, dict):
        raise ProfileResolutionError("profile must be an object")
    directories = list(stack_directories) if stack_directories is not None else [source.resolve().parent / "stacks", *default_stack_directories()]
    return resolve_profile_data(data, stack_directories=directories)


def repository_root_for(profile_path: str | Path, profile: dict[str, Any]) -> Path:
    raw = Path(profile["project"]["repository_root"])
    if raw.is_absolute():
        return raw.resolve()
    source = Path(profile_path).resolve()
    base = source.parent.parent if source.parent.name == ".review" else Path.cwd()
    return (base / raw).resolve()

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from .io import dump_json, load_data
from .path_globs import expand_trailing_recursive_glob
from .profile import repository_root_for, resolve_profile_file


class BaselineError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_pattern(pattern: str) -> str:
    candidate = Path(pattern.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise BaselineError(f"unsafe protected path pattern: {pattern}")
    return candidate.as_posix()


def collect_protected_files(root: Path, patterns: Iterable[str]) -> list[Path]:
    root = root.resolve()
    if not root.exists():
        raise BaselineError(f"repository root does not exist: {root}")
    files: set[Path] = set()
    for raw_pattern in patterns:
        if not raw_pattern:
            continue
        pattern = _validate_pattern(raw_pattern)
        for expanded_pattern in expand_trailing_recursive_glob(pattern):
            for path in root.glob(expanded_pattern):
                if path.is_symlink():
                    raise BaselineError(f"protected path must not be a symlink: {path}")
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if resolved != root and root not in resolved.parents:
                    raise BaselineError(f"protected path escaped repository root: {path}")
                files.add(resolved)
    return sorted(files)


def create_snapshot(
    profile_path: str | Path,
    *,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    profile = resolve_profile_file(profile_path)
    root = Path(repository_root).resolve() if repository_root else repository_root_for(profile_path, profile)
    patterns = profile.get("protected_paths", [])
    files = collect_protected_files(root, patterns)
    return {
        "schema_version": "1.0",
        "project_id": profile["project"]["id"],
        "repository_root": str(root),
        "patterns": patterns,
        "files": {
            path.relative_to(root).as_posix(): {
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
            for path in files
        },
    }


def write_snapshot(
    profile_path: str | Path,
    output: str | Path,
    *,
    repository_root: str | Path | None = None,
) -> Path:
    snapshot = create_snapshot(profile_path, repository_root=repository_root)
    dump_json(output, snapshot)
    return Path(output)


def compare_snapshot(
    snapshot: dict[str, Any],
    *,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repository_root or snapshot["repository_root"]).resolve()
    patterns = snapshot.get("patterns", [])
    current_files = collect_protected_files(root, patterns)
    current = {
        path.relative_to(root).as_posix(): {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        for path in current_files
    }
    previous = snapshot.get("files", {})
    added = sorted(set(current) - set(previous))
    deleted = sorted(set(previous) - set(current))
    modified = sorted(
        path for path in set(previous) & set(current)
        if previous[path].get("sha256") != current[path].get("sha256")
    )
    return {
        "intact": not (added or deleted or modified),
        "repository_root": str(root),
        "added": added,
        "deleted": deleted,
        "modified": modified,
        "current_file_count": len(current),
        "snapshot_file_count": len(previous),
    }


def verify_snapshot_file(
    snapshot_path: str | Path,
    *,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    snapshot = load_data(snapshot_path)
    if not isinstance(snapshot, dict):
        raise BaselineError("snapshot must be an object")
    return compare_snapshot(snapshot, repository_root=repository_root)

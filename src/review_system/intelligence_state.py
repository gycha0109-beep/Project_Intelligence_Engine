from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .io import load_data


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip()


def git_changed_files(repository_root: str | Path, base: str, head: str = "HEAD") -> list[str]:
    root = Path(repository_root).resolve()
    output = _git(root, "diff", "--name-only", "--diff-filter=ACMRD", f"{base}...{head}")
    if output is None:
        raise RuntimeError(f"unable to calculate git diff for {base}...{head}")
    return sorted({line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()})


def file_sha256(path: str | Path) -> str | None:
    source = Path(path)
    if not source.is_file():
        return None
    return hashlib.sha256(source.read_bytes()).hexdigest()


def capture_project_state(
    repository_root: str | Path,
    *,
    project_id: str,
    baseline: str | None = None,
    graph_path: str | Path | None = None,
    approved_rules_path: str | Path | None = None,
    active_changes_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(root, "rev-parse", "HEAD")
    status = _git(root, "status", "--porcelain=v1")
    state: dict[str, Any] = {
        "schema_version": "1.0",
        "project_id": project_id,
        "repository": {
            "root": ".",
            "branch": branch,
            "head_revision": head,
            "baseline_revision": baseline,
            "working_tree_dirty": bool(status),
            "working_tree_entries": sorted(line for line in (status or "").splitlines() if line),
        },
        "artifacts": {
            "graph_sha256": file_sha256(graph_path) if graph_path else None,
            "approved_rules_sha256": file_sha256(approved_rules_path) if approved_rules_path else None,
        },
        "active_changes": [],
    }
    if active_changes_path:
        data = load_data(active_changes_path)
        if not isinstance(data, dict) or not isinstance(data.get("change_sets"), list):
            raise ValueError("active changes file must contain a change_sets array")
        state["active_changes"] = data["change_sets"]
    canonical = json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    state["state_sha256"] = hashlib.sha256(canonical).hexdigest()
    return state

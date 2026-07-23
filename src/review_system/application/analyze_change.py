from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..intelligence_config import load_rules
from ..intelligence_graph import validate_project_graph
from ..intelligence_impact import analyze_change
from ..intelligence_report import impact_markdown
from ..intelligence_state import git_changed_files
from ..io import dump_json, load_data
from ._project_context import load_profile_and_root


@dataclass(frozen=True)
class AnalyzeChangeRequest:
    profile: str | Path
    graph: str | Path
    output: str | Path
    approved_rules: str | Path | None = None
    files: str | Path | None = None
    base: str | None = None
    head: str = "HEAD"
    change_id: str | None = None
    max_depth: int = 3
    repository_root: str | Path | None = None
    markdown_output: str | Path | None = None


@dataclass(frozen=True)
class AnalyzeChangeResult:
    analysis: dict[str, Any]
    changed_files: tuple[str, ...]
    repository_root: Path
    output_path: Path
    markdown_path: Path | None


def _read_changed_files(
    request: AnalyzeChangeRequest,
    repository_root: Path,
    git_diff_reader: Callable[[Path, str, str], list[str]],
) -> tuple[str, ...]:
    has_files = bool(request.files)
    has_base = bool(request.base)
    if has_files == has_base:
        raise ValueError("provide exactly one of files or base")

    if request.files:
        values = [
            line.strip()
            for line in Path(request.files).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        values = git_diff_reader(repository_root, str(request.base), request.head)
    return tuple(values)


def analyze_project_change(
    request: AnalyzeChangeRequest,
    *,
    git_diff_reader: Callable[[Path, str, str], list[str]] = git_changed_files,
) -> AnalyzeChangeResult:
    profile, root = load_profile_and_root(request.profile, request.repository_root)

    graph = load_data(request.graph)
    if not isinstance(graph, dict):
        raise ValueError("graph must be an object")
    graph_errors = validate_project_graph(graph)
    if graph_errors:
        raise ValueError("invalid graph: " + "; ".join(graph_errors))

    if request.approved_rules and not Path(request.approved_rules).is_file():
        raise ValueError(f"approved rules file does not exist: {request.approved_rules}")
    rules = (
        load_rules(request.approved_rules, required_status="approved")
        if request.approved_rules
        else {"rules": []}
    )

    changed_files = _read_changed_files(request, root, git_diff_reader)
    analysis = analyze_change(
        graph,
        changed_files,
        configured_packs=profile.get("review", {}).get("packs", []),
        approved_rules=rules.get("rules", []),
        max_depth=request.max_depth,
        change_id=request.change_id,
        base_revision=request.base,
        head_revision=request.head if request.base else None,
    )

    output_path = Path(request.output)
    dump_json(output_path, analysis)

    markdown_path: Path | None = None
    if request.markdown_output:
        markdown_path = Path(request.markdown_output)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(impact_markdown(analysis), encoding="utf-8")

    return AnalyzeChangeResult(
        analysis=analysis,
        changed_files=changed_files,
        repository_root=root,
        output_path=output_path,
        markdown_path=markdown_path,
    )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..intelligence_config import load_intelligence_config
from ..intelligence_graph import build_project_graph
from ..io import dump_json
from ._project_context import load_profile_and_root


@dataclass(frozen=True)
class IndexProjectRequest:
    profile: str | Path
    config: str | Path
    output: str | Path
    repository_root: str | Path | None = None


@dataclass(frozen=True)
class IndexProjectResult:
    graph: dict[str, Any]
    repository_root: Path
    output_path: Path


def index_project(request: IndexProjectRequest) -> IndexProjectResult:
    profile, root = load_profile_and_root(request.profile, request.repository_root)
    config = load_intelligence_config(request.config)
    graph_config = config.get("graph", {})
    graph = build_project_graph(
        root,
        include=profile.get("scope", {}).get("include", ["**/*"]),
        exclude=profile.get("scope", {}).get("exclude", []),
        components=config.get("components", []),
        max_file_size_bytes=int(graph_config.get("max_file_size_bytes", 1_000_000)),
    )
    output_path = Path(request.output)
    dump_json(output_path, graph)
    return IndexProjectResult(
        graph=graph,
        repository_root=root,
        output_path=output_path,
    )

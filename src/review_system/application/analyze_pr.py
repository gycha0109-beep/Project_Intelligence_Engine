from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from ..github_connector import GitHubCLI, collect_pull_request, refresh_source_hash
from ..github_prospective_capture import (
    build_github_prospective_capture_candidate,
    candidate_filename,
    write_github_prospective_capture_candidate,
)
from ..identity import pull_request_run_identity, write_identity_manifest
from ..intelligence_config import load_intelligence_config, load_rules, path_matches
from ..intelligence_graph import build_project_graph
from ..intelligence_impact import analyze_change
from ..intelligence_report import pull_request_markdown
from ..intelligence_state import capture_project_state
from ..io import dump_json
from ..validation import validate_profile_file
from ..workflow_semantics import build_workflow_diff_evidence


_EXACT_SHA40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


@dataclass(frozen=True)
class AnalyzePullRequestRequest:
    pull_request: str
    repository_root: str | Path = "."
    repository: str | None = None
    profile: str | None = None
    config: str | None = None
    graph: str | None = None
    approved_rules: str | None = None
    refresh_graph: bool = False
    skip_diff: bool = False
    skip_discussion: bool = False
    allow_repository_mismatch: bool = False
    allow_head_mismatch: bool = False
    allow_dirty_worktree: bool = False
    max_depth: int = 3
    output_dir: str | Path | None = None


@dataclass(frozen=True)
class AnalyzePullRequestResult:
    source: dict[str, Any]
    impact: dict[str, Any]
    output_dir: Path
    source_path: Path
    impact_path: Path
    report_path: Path
    diff_path: Path | None
    changed_files: tuple[str, ...]
    prospective_candidate_path: Path | None = None
    workflow_semantics_path: Path | None = None


def _resolve_project_path(repository_root: Path, value: str | None, default_relative: str) -> Path:
    if value:
        path = Path(value)
        return path.resolve() if path.is_absolute() else (repository_root / path).resolve()
    return (repository_root / default_relative).resolve()


def _scoped_working_tree_changes(entries: list[str], include: list[str], exclude: list[str]) -> list[str]:
    changed: set[str] = set()
    for entry in entries:
        raw = entry[3:] if len(entry) > 3 else ""
        raw_paths = raw.split(" -> ", 1) if " -> " in raw else [raw]
        for value in raw_paths:
            path = value.strip().strip('"').replace("\\", "/")
            if path and path_matches(path, include or ["**/*"]) and not path_matches(path, exclude):
                changed.add(path)
    return sorted(changed)


def analyze_pull_request(
    request: AnalyzePullRequestRequest,
    *,
    github_cli: GitHubCLI,
    capture_state: Callable[..., dict[str, Any]] = capture_project_state,
) -> AnalyzePullRequestResult:
    requested_root = Path(request.repository_root).resolve()
    if not requested_root.is_dir():
        raise ValueError(f"repository root does not exist: {requested_root}")

    profile_path = _resolve_project_path(requested_root, request.profile, ".review/project.yml")
    config_path = _resolve_project_path(requested_root, request.config, ".review/intelligence/config.yml")
    graph_path = _resolve_project_path(requested_root, request.graph, ".review/intelligence/graph.json")
    approved_rules_path = _resolve_project_path(
        requested_root,
        request.approved_rules,
        ".review/intelligence/approved-rules.yml",
    )
    if not profile_path.is_file():
        raise ValueError(
            f"project profile does not exist: {profile_path}; "
            "run 'pie init-project --preset <name>' first"
        )
    if not config_path.is_file():
        raise ValueError(
            f"intelligence config does not exist: {config_path}; "
            "run 'pie init-project --preset <name>' first"
        )

    profile, errors = validate_profile_file(profile_path)
    if errors:
        raise ValueError("invalid project profile: " + "; ".join(errors))
    project_root = requested_root

    source, diff_text = collect_pull_request(
        github_cli,
        request.pull_request,
        cwd=project_root,
        repository=request.repository,
        include_diff=not request.skip_diff,
        include_discussion=not request.skip_discussion,
    )

    current_repo = github_cli.current_repository(project_root)
    expected_name = source["repository"]["name_with_owner"].lower()
    expected_host = source["repository"]["hostname"].lower()
    verification: dict[str, object] = {
        "status": "unverified",
        "expected_repository": source["repository"]["name_with_owner"],
        "expected_hostname": source["repository"]["hostname"],
        "local_repository": current_repo,
    }
    if current_repo:
        same_name = current_repo["name_with_owner"].lower() == expected_name
        same_host = current_repo.get("hostname", "github.com").lower() == expected_host
        verification["status"] = "matched" if same_name and same_host else "mismatch"
        if verification["status"] == "mismatch" and not request.allow_repository_mismatch:
            raise ValueError(
                "local repository does not match the pull request repository; "
                "use the correct project folder or pass --allow-repository-mismatch explicitly"
            )
    elif not request.allow_repository_mismatch:
        raise ValueError(
            "cannot verify the local repository against the pull request; "
            "run inside the matching Git repository or pass --allow-repository-mismatch explicitly"
        )
    source["local_repository_verification"] = verification

    state = capture_state(project_root, project_id=profile["project"]["id"])
    source["local_project_state"] = state["repository"]
    remote_head = source["pull_request"].get("head_oid")
    local_head = state["repository"].get("head_revision")
    if remote_head and local_head and remote_head != local_head:
        if not request.allow_head_mismatch:
            raise ValueError(
                "local HEAD does not match the PR head; check out the exact PR head or pass "
                "--allow-head-mismatch explicitly for degraded analysis"
            )
        source["warnings"].append(
            "local HEAD does not match the PR head; analysis was explicitly allowed and the graph may be degraded"
        )

    scope = profile.get("scope", {})
    scoped_dirty = _scoped_working_tree_changes(
        state["repository"].get("working_tree_entries", []),
        scope.get("include", ["**/*"]),
        scope.get("exclude", []),
    )
    if scoped_dirty:
        if not request.allow_dirty_worktree:
            raise ValueError(
                "working tree has changes inside the analysis scope: "
                f"{', '.join(scoped_dirty)}; commit/stash them or pass --allow-dirty-worktree explicitly"
            )
        source["warnings"].append(
            "analysis includes explicit dirty-worktree changes and may not represent the PR head: "
            + ", ".join(scoped_dirty)
        )
    refresh_source_hash(source)

    config = load_intelligence_config(config_path)
    graph_config = config.get("graph", {})
    graph = build_project_graph(
        project_root,
        include=profile.get("scope", {}).get("include", ["**/*"]),
        exclude=profile.get("scope", {}).get("exclude", []),
        components=config.get("components", []),
        max_file_size_bytes=int(graph_config.get("max_file_size_bytes", 1_000_000)),
    )
    dump_json(graph_path, graph)

    if approved_rules_path.exists():
        rules = load_rules(approved_rules_path, required_status="approved")
    else:
        rules = {"schema_version": "1.0", "rules": []}
        source["warnings"].append(f"approved rules file does not exist: {approved_rules_path}")
        refresh_source_hash(source)

    changed_files = tuple(
        item["path"]
        for item in source["pull_request"].get("changed_files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    )
    if not changed_files:
        raise ValueError("GitHub returned no changed files for this pull request")

    pr_number = source["pull_request"]["number"]
    impact = analyze_change(
        graph,
        changed_files,
        configured_packs=profile.get("review", {}).get("packs", []),
        approved_rules=rules.get("rules", []),
        max_depth=request.max_depth,
        change_id=f"PR-{pr_number}",
        base_revision=source["pull_request"].get("base_oid"),
        head_revision=source["pull_request"].get("head_oid"),
    )
    impact["source_evidence_sha256"] = source["source_sha256"]

    output_dir = (
        Path(request.output_dir).resolve()
        if request.output_dir
        else (project_root / ".pie" / f"pr-{pr_number}").resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = output_dir / "github-source.json"
    impact_path = output_dir / "impact.json"
    report_path = output_dir / "REPORT.md"
    dump_json(source_path, source)
    dump_json(impact_path, impact)
    report_path.write_text(pull_request_markdown(source, impact), encoding="utf-8")

    diff_file = output_dir / "pull-request.diff"
    if diff_text is not None:
        diff_file.write_bytes(diff_text.encode("utf-8"))
        diff_path: Path | None = diff_file
    else:
        if diff_file.exists():
            diff_file.unlink()
        diff_path = None

    workflow_semantics_file = output_dir / "workflow-semantics.json"
    workflow_semantics_path: Path | None = None
    if (
        diff_text is not None
        and isinstance(remote_head, str)
        and _EXACT_SHA40.fullmatch(remote_head) is not None
    ):
        workflow_evidence = build_workflow_diff_evidence(
            source_revision=remote_head,
            source_evidence_sha256=source["source_sha256"],
            changed_files=changed_files,
            diff_text=diff_text,
        )
        dump_json(workflow_semantics_file, workflow_evidence)
        workflow_semantics_path = workflow_semantics_file
    else:
        workflow_semantics_file.unlink(missing_ok=True)

    candidate = build_github_prospective_capture_candidate(source, profile_path)
    prospective_candidate_path = output_dir / candidate_filename(candidate)
    write_github_prospective_capture_candidate(prospective_candidate_path, candidate)

    identity = pull_request_run_identity(profile["project"]["id"], source)
    write_identity_manifest(output_dir, identity)

    return AnalyzePullRequestResult(
        source=source,
        impact=impact,
        output_dir=output_dir,
        source_path=source_path,
        impact_path=impact_path,
        report_path=report_path,
        diff_path=diff_path,
        changed_files=changed_files,
        prospective_candidate_path=prospective_candidate_path,
        workflow_semantics_path=workflow_semantics_path,
    )

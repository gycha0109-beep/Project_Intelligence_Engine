from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .baseline import verify_snapshot_file, write_snapshot
from .gate import calculate_gate_from_run
from .github_connector import GitHubCLI, collect_pull_request, doctor, refresh_source_hash, validate_pull_request_source
from .project_init import available_presets, initialize_project
from .io import dump_json, dump_yaml, dump_yaml_pair_atomic, load_data
from .intelligence_config import (
    load_intelligence_config,
    load_rules,
    path_matches,
    validate_intelligence_config,
    validate_rules,
)
from .intelligence_graph import build_project_graph, validate_project_graph
from .intelligence_impact import analyze_change, compare_change_sets
from .intelligence_learning import approve_candidate_rule, discover_rule_candidates, merge_rule_candidates
from .intelligence_report import comparison_markdown, impact_markdown, pull_request_markdown
from .intelligence_state import capture_project_state, git_changed_files
from .merge import merge_findings
from .packs import select_packs_with_reasons
from .paths import asset
from .profile import repository_root_for, resolve_profile_file
from .run import (
    archive_run,
    calculate_gate_directory,
    initialize_run,
    sync_run,
    validate_run_directory,
    verify_manifest,
)
from .validation import validate_findings_file, validate_profile_file, validate_review_run_file
from .version import get_version


def _print_errors(errors: list[str], prefix: str = "") -> None:
    for error in errors:
        print(f"ERROR {prefix}{error}", file=sys.stderr)


def _error(exc: Exception) -> int:
    print(f"ERROR {exc}", file=sys.stderr)
    return 2


def cmd_version(args: argparse.Namespace) -> int:
    print(get_version())
    return 0


def cmd_validate_profile(args: argparse.Namespace) -> int:
    profile, errors = validate_profile_file(args.profile)
    if errors:
        _print_errors(errors)
        return 2
    print(f"VALID profile: {args.profile}; packs={len(profile['review']['packs'])}; inherits={profile.get('resolved_inherits', [])}")
    return 0


def cmd_resolve_profile(args: argparse.Namespace) -> int:
    try:
        profile = resolve_profile_file(args.profile)
        if args.output:
            dump_yaml(args.output, profile)
            print(args.output)
        else:
            print(json.dumps(profile, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        return _error(exc)


def cmd_validate_findings(args: argparse.Namespace) -> int:
    try:
        findings, failures = validate_findings_file(args.findings)
    except Exception as exc:
        return _error(exc)
    if failures:
        for fid, errors in failures.items():
            _print_errors(errors, prefix=f"{fid}: ")
        return 2
    print(f"VALID findings: {len(findings)}")
    return 0


def cmd_validate_run(args: argparse.Namespace) -> int:
    _, errors = validate_review_run_file(args.run)
    if errors:
        _print_errors(errors)
        return 2
    print(f"VALID review run: {args.run}")
    return 0


def cmd_validate_run_dir(args: argparse.Namespace) -> int:
    try:
        errors = validate_run_directory(args.directory, require_gate=args.require_gate)
    except Exception as exc:
        return _error(exc)
    if errors:
        _print_errors(errors)
        return 2
    print(f"VALID run directory: {args.directory}")
    return 0


def cmd_init_run(args: argparse.Namespace) -> int:
    _, errors = validate_profile_file(args.profile)
    if errors:
        _print_errors(errors)
        return 2
    try:
        target = initialize_run(
            args.profile,
            args.output,
            args.mode,
            snapshot_protected=args.snapshot_protected,
            repository_root=args.repository_root,
        )
    except Exception as exc:
        return _error(exc)
    print(target)
    return 0


def cmd_sync_run(args: argparse.Namespace) -> int:
    try:
        run = sync_run(args.directory)
    except Exception as exc:
        return _error(exc)
    print(f"SYNCED run: {args.directory}; findings={len(run.get('findings', []))}")
    return 0


def cmd_merge_findings(args: argparse.Namespace) -> int:
    groups = []
    for source in args.inputs:
        try:
            data, failures = validate_findings_file(source)
        except Exception as exc:
            return _error(exc)
        if failures:
            for fid, errors in failures.items():
                _print_errors(errors, prefix=f"{source}:{fid}: ")
            return 2
        groups.append(data)
    result = merge_findings(groups)
    dump_json(args.output, result["findings"])
    conflicts_output = args.conflicts_output or f"{args.output}.conflicts.json"
    dump_json(conflicts_output, result["merge_conflicts"])
    print(f"MERGED {len(result['findings'])} findings; conflicts={len(result['merge_conflicts'])}; conflicts_file={conflicts_output}")
    return 0


def cmd_calculate_gate(args: argparse.Namespace) -> int:
    run, errors = validate_review_run_file(args.run)
    if errors:
        _print_errors(errors)
        return 2
    try:
        policy = load_data(args.policy or asset("core/default-gate-policy.yml"))
        result = calculate_gate_from_run(run, policy, trust_metrics=args.trust_metrics)
    except Exception as exc:
        return _error(exc)
    if args.output:
        dump_json(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["decision"] in {"PASS", "CONDITIONAL_PASS"} else 3


def cmd_calculate_gate_dir(args: argparse.Namespace) -> int:
    try:
        result = calculate_gate_directory(
            args.directory,
            policy_path=args.policy,
            repository_root=args.repository_root,
        )
    except Exception as exc:
        return _error(exc)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["decision"] in {"PASS", "CONDITIONAL_PASS"} else 3

def cmd_select_packs(args: argparse.Namespace) -> int:
    profile, errors = validate_profile_file(args.profile)
    if errors:
        _print_errors(errors)
        return 2
    try:
        files = Path(args.files).read_text(encoding="utf-8").splitlines()
        selected = select_packs_with_reasons(files, profile["review"]["packs"])
    except Exception as exc:
        return _error(exc)
    if args.json:
        print(json.dumps({"selected_packs": list(selected), "reasons": selected}, indent=2, ensure_ascii=False))
    else:
        print("\n".join(selected))
    return 0


def cmd_snapshot_protected(args: argparse.Namespace) -> int:
    try:
        target = write_snapshot(args.profile, args.output, repository_root=args.repository_root)
    except Exception as exc:
        return _error(exc)
    print(target)
    return 0


def cmd_verify_protected(args: argparse.Namespace) -> int:
    try:
        result = verify_snapshot_file(args.snapshot, repository_root=args.repository_root)
    except Exception as exc:
        return _error(exc)
    if args.output:
        dump_json(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["intact"] else 4


def cmd_archive_run(args: argparse.Namespace) -> int:
    try:
        target = archive_run(args.directory, args.output)
    except Exception as exc:
        return _error(exc)
    print(target)
    return 0


def cmd_verify_manifest(args: argparse.Namespace) -> int:
    try:
        result = verify_manifest(args.directory, args.manifest)
    except Exception as exc:
        return _error(exc)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["valid"] else 4



def cmd_validate_graph(args: argparse.Namespace) -> int:
    try:
        graph = load_data(args.graph)
        if not isinstance(graph, dict):
            raise ValueError("graph must be an object")
        errors = validate_project_graph(graph)
    except Exception as exc:
        return _error(exc)
    if errors:
        _print_errors(errors)
        return 2
    print(f"VALID graph: {args.graph}; files={graph.get('stats', {}).get('files', 0)}; edges={len(graph.get('edges', []))}")
    return 0


def cmd_validate_intelligence_config(args: argparse.Namespace) -> int:
    try:
        data = load_data(args.config)
        if not isinstance(data, dict):
            raise ValueError("intelligence config must be an object")
        errors = validate_intelligence_config(data)
    except Exception as exc:
        return _error(exc)
    if errors:
        _print_errors(errors)
        return 2
    print(f"VALID intelligence config: {args.config}; components={len(data.get('components', []))}")
    return 0


def cmd_validate_rules(args: argparse.Namespace) -> int:
    try:
        data = load_data(args.rules)
        if not isinstance(data, dict):
            raise ValueError("rule file must be an object")
        errors = validate_rules(data, required_status=args.status)
    except Exception as exc:
        return _error(exc)
    if errors:
        _print_errors(errors)
        return 2
    print(f"VALID rules: {args.rules}; count={len(data.get('rules', []))}")
    return 0


def _profile_and_root(profile_path: str, repository_root: str | None = None) -> tuple[dict, Path]:
    profile, errors = validate_profile_file(profile_path)
    if errors:
        raise ValueError("invalid project profile: " + "; ".join(errors))
    root = Path(repository_root).resolve() if repository_root else repository_root_for(profile_path, profile)
    return profile, root


def cmd_index_project(args: argparse.Namespace) -> int:
    try:
        profile, root = _profile_and_root(args.profile, args.repository_root)
        config = load_intelligence_config(args.config)
        graph_config = config.get("graph", {})
        graph = build_project_graph(
            root,
            include=profile.get("scope", {}).get("include", ["**/*"]),
            exclude=profile.get("scope", {}).get("exclude", []),
            components=config.get("components", []),
            max_file_size_bytes=int(graph_config.get("max_file_size_bytes", 1_000_000)),
        )
        dump_json(args.output, graph)
    except Exception as exc:
        return _error(exc)
    print(f"INDEXED project: files={graph['stats']['files']}; edges={graph['stats']['edges']}; warnings={len(graph['warnings'])}; output={args.output}")
    return 0


def _read_changed_files(args: argparse.Namespace, root: Path) -> list[str]:
    if args.files:
        return [line.strip() for line in Path(args.files).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.base:
        return git_changed_files(root, args.base, args.head)
    raise ValueError("provide --files or --base")


def cmd_analyze_change(args: argparse.Namespace) -> int:
    try:
        profile, root = _profile_and_root(args.profile, args.repository_root)
        graph = load_data(args.graph)
        if not isinstance(graph, dict):
            raise ValueError("graph must be an object")
        graph_errors = validate_project_graph(graph)
        if graph_errors:
            raise ValueError("invalid graph: " + "; ".join(graph_errors))
        if args.approved_rules and not Path(args.approved_rules).is_file():
            raise ValueError(f"approved rules file does not exist: {args.approved_rules}")
        rules = load_rules(args.approved_rules, required_status="approved") if args.approved_rules else {"rules": []}
        changed_files = _read_changed_files(args, root)
        result = analyze_change(
            graph,
            changed_files,
            configured_packs=profile.get("review", {}).get("packs", []),
            approved_rules=rules.get("rules", []),
            max_depth=args.max_depth,
            change_id=args.change_id,
            base_revision=args.base,
            head_revision=args.head if args.base else None,
        )
        dump_json(args.output, result)
        if args.markdown_output:
            target = Path(args.markdown_output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(impact_markdown(result), encoding="utf-8")
    except Exception as exc:
        return _error(exc)
    print(
        f"ANALYZED change: direct={len(result['change']['changed_files'])}; "
        f"impacted={len(result['impact']['dependent_files'])}; packs={len(result['review']['selected_packs'])}; output={args.output}"
    )
    return 0


def cmd_compare_changes(args: argparse.Namespace) -> int:
    try:
        data = load_data(args.input)
        if not isinstance(data, dict) or not isinstance(data.get("change_sets"), list):
            raise ValueError("input must contain a change_sets array")
        result = compare_change_sets(data["change_sets"])
        dump_json(args.output, result)
        if args.markdown_output:
            target = Path(args.markdown_output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(comparison_markdown(result), encoding="utf-8")
    except Exception as exc:
        return _error(exc)
    risky = sum(1 for item in result["comparisons"] if item["risk_level"] in {"medium", "high"})
    print(f"COMPARED changes: sets={len(result['change_sets'])}; risky_pairs={risky}; output={args.output}")
    return 0


def cmd_capture_state(args: argparse.Namespace) -> int:
    try:
        profile, root = _profile_and_root(args.profile, args.repository_root)
        state = capture_project_state(
            root,
            project_id=profile["project"]["id"],
            baseline=args.baseline,
            graph_path=args.graph,
            approved_rules_path=args.approved_rules,
            active_changes_path=args.active_changes,
        )
        dump_json(args.output, state)
    except Exception as exc:
        return _error(exc)
    print(f"CAPTURED project state: output={args.output}; head={state['repository']['head_revision']}")
    return 0


def cmd_discover_rule_candidates(args: argparse.Namespace) -> int:
    try:
        history = load_data(args.history)
        if not isinstance(history, dict) or not isinstance(history.get("change_sets"), list):
            raise ValueError("history must contain a change_sets array")
        config = load_intelligence_config(args.config) if args.config else {"components": []}
        discovered = discover_rule_candidates(
            history["change_sets"],
            components=config.get("components", []),
            min_samples=args.min_samples,
            min_confidence=args.min_confidence,
            min_support=args.min_support,
        )
        existing = load_rules(args.output) if Path(args.output).exists() else {"schema_version": "1.0", "rules": []}
        result = merge_rule_candidates(existing, discovered)
        dump_yaml(args.output, result)
    except Exception as exc:
        return _error(exc)
    print(f"DISCOVERED rule candidates: count={len(result['rules'])}; output={args.output}")
    return 0


def cmd_approve_rule(args: argparse.Namespace) -> int:
    try:
        candidates = load_rules(args.candidates)
        approved = load_rules(args.approved, required_status="approved")
        updated_candidates, updated_approved = approve_candidate_rule(
            candidates,
            approved,
            args.rule_id,
            approved_by=args.approved_by,
            approved_at=args.approved_at,
            rationale=args.rationale,
        )
        dump_yaml_pair_atomic(args.approved, updated_approved, args.candidates, updated_candidates)
    except Exception as exc:
        return _error(exc)
    print(f"APPROVED rule: {args.rule_id}; approved_file={args.approved}")
    return 0



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



def cmd_validate_github_source(args: argparse.Namespace) -> int:
    try:
        data = load_data(args.source)
        if not isinstance(data, dict):
            raise ValueError("GitHub source evidence must be an object")
        errors = validate_pull_request_source(data)
    except Exception as exc:
        return _error(exc)
    if errors:
        _print_errors(errors)
        return 2
    print(
        f"VALID GitHub source: repo={data['repository']['name_with_owner']}; "
        f"pr=#{data['pull_request']['number']}; files={len(data['pull_request']['changed_files'])}"
    )
    return 0

def cmd_init_project(args: argparse.Namespace) -> int:
    try:
        result = initialize_project(args.repository_root, preset=args.preset, force=args.force)
    except Exception as exc:
        return _error(exc)
    created = sum(1 for item in result["files"] if item["action"] == "created")
    overwritten = sum(1 for item in result["files"] if item["action"] == "overwritten")
    skipped = sum(1 for item in result["files"] if item["action"] == "skipped")
    print(
        f"INITIALIZED project: preset={result['preset']}; created={created}; "
        f"overwritten={overwritten}; skipped={skipped}; root={result['repository_root']}"
    )
    return 0


def cmd_github_doctor(args: argparse.Namespace) -> int:
    try:
        root = Path(args.repository_root).resolve()
        result = doctor(
            GitHubCLI(executable=args.gh_executable, timeout_seconds=args.timeout),
            cwd=root,
            hostname=args.hostname,
        )
        if args.output:
            dump_json(args.output, result)
    except Exception as exc:
        return _error(exc)
    # Authentication details may contain symbols (for example gh's checkmark)
    # that legacy Windows console encodings cannot represent.
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result["ready"] else 4


def cmd_analyze_pr(args: argparse.Namespace) -> int:
    try:
        requested_root = Path(args.repository_root).resolve()
        if not requested_root.is_dir():
            raise ValueError(f"repository root does not exist: {requested_root}")

        profile_path = _resolve_project_path(requested_root, args.profile, ".review/project.yml")
        config_path = _resolve_project_path(requested_root, args.config, ".review/intelligence/config.yml")
        graph_path = _resolve_project_path(requested_root, args.graph, ".review/intelligence/graph.json")
        approved_rules_path = _resolve_project_path(
            requested_root,
            args.approved_rules,
            ".review/intelligence/approved-rules.yml",
        )
        if not profile_path.is_file():
            raise ValueError(f"project profile does not exist: {profile_path}; run 'pie init-project --preset <name>' first")
        if not config_path.is_file():
            raise ValueError(f"intelligence config does not exist: {config_path}; run 'pie init-project --preset <name>' first")

        profile, project_root = _profile_and_root(str(profile_path), str(requested_root))
        cli = GitHubCLI(executable=args.gh_executable, timeout_seconds=args.timeout)
        source, diff_text = collect_pull_request(
            cli,
            args.pull_request,
            cwd=project_root,
            repository=args.repo,
            include_diff=not args.skip_diff,
            include_discussion=not args.skip_discussion,
        )

        current_repo = cli.current_repository(project_root)
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
            if verification["status"] == "mismatch" and not args.allow_repository_mismatch:
                raise ValueError(
                    "local repository does not match the pull request repository; "
                    "use the correct project folder or pass --allow-repository-mismatch explicitly"
                )
        elif not args.allow_repository_mismatch:
            raise ValueError(
                "cannot verify the local repository against the pull request; "
                "run inside the matching Git repository or pass --allow-repository-mismatch explicitly"
            )
        source["local_repository_verification"] = verification

        state = capture_project_state(project_root, project_id=profile["project"]["id"])
        source["local_project_state"] = state["repository"]
        remote_head = source["pull_request"].get("head_oid")
        local_head = state["repository"].get("head_revision")
        if remote_head and local_head and remote_head != local_head:
            if not args.allow_head_mismatch:
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
            if not args.allow_dirty_worktree:
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
        # PR analysis is evidence-sensitive: a structurally valid cached graph
        # may belong to a different checkout. Rebuild against the verified head.
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

        changed_files = [
            item["path"]
            for item in source["pull_request"].get("changed_files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        ]
        if not changed_files:
            raise ValueError("GitHub returned no changed files for this pull request")
        pr_number = source["pull_request"]["number"]
        impact = analyze_change(
            graph,
            changed_files,
            configured_packs=profile.get("review", {}).get("packs", []),
            approved_rules=rules.get("rules", []),
            max_depth=args.max_depth,
            change_id=f"PR-{pr_number}",
            base_revision=source["pull_request"].get("base_oid"),
            head_revision=source["pull_request"].get("head_oid"),
        )
        impact["source_evidence_sha256"] = source["source_sha256"]

        output_dir = (
            Path(args.output_dir).resolve()
            if args.output_dir
            else (project_root / ".pie" / f"pr-{pr_number}").resolve()
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        source_path = output_dir / "github-source.json"
        impact_path = output_dir / "impact.json"
        report_path = output_dir / "REPORT.md"
        dump_json(source_path, source)
        dump_json(impact_path, impact)
        report_path.write_text(pull_request_markdown(source, impact), encoding="utf-8")
        diff_path = output_dir / "pull-request.diff"
        if diff_text is not None:
            # Preserve the exact bytes hashed by the connector. Path.write_text
            # performs newline translation on Windows and would invalidate the
            # companion diff SHA-256 evidence.
            diff_path.write_bytes(diff_text.encode("utf-8"))
        elif diff_path.exists():
            diff_path.unlink()
    except Exception as exc:
        return _error(exc)

    print(
        f"ANALYZED pull request: repo={source['repository']['name_with_owner']}; "
        f"pr=#{source['pull_request']['number']}; files={len(changed_files)}; "
        f"impacted={len(impact['impact']['dependent_files'])}; "
        f"packs={len(impact['review']['selected_packs'])}; output={output_dir}"
    )
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project Intelligence Engine and Universal Review System CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("validate-profile")
    p.add_argument("profile")
    p.set_defaults(func=cmd_validate_profile)

    p = sub.add_parser("resolve-profile")
    p.add_argument("profile")
    p.add_argument("--output")
    p.set_defaults(func=cmd_resolve_profile)

    p = sub.add_parser("validate-findings")
    p.add_argument("findings")
    p.set_defaults(func=cmd_validate_findings)

    p = sub.add_parser("validate-run")
    p.add_argument("run")
    p.set_defaults(func=cmd_validate_run)

    p = sub.add_parser("validate-run-dir")
    p.add_argument("directory")
    p.add_argument("--require-gate", action="store_true")
    p.set_defaults(func=cmd_validate_run_dir)

    p = sub.add_parser("init-run")
    p.add_argument("profile")
    p.add_argument("--mode", choices=["full", "change", "risk", "release", "incident"], default="full")
    p.add_argument("--output", required=True)
    p.add_argument("--snapshot-protected", action="store_true")
    p.add_argument("--repository-root")
    p.set_defaults(func=cmd_init_run)

    p = sub.add_parser("sync-run")
    p.add_argument("directory")
    p.set_defaults(func=cmd_sync_run)

    p = sub.add_parser("merge-findings")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--output", required=True)
    p.add_argument("--conflicts-output")
    p.set_defaults(func=cmd_merge_findings)

    p = sub.add_parser("calculate-gate")
    p.add_argument("run")
    p.add_argument("--policy")
    p.add_argument("--output")
    p.add_argument("--trust-metrics", action="store_true", help="Use declared finding counts instead of deriving them from findings")
    p.set_defaults(func=cmd_calculate_gate)

    p = sub.add_parser("calculate-gate-dir")
    p.add_argument("directory")
    p.add_argument("--policy")
    p.add_argument("--repository-root")
    p.set_defaults(func=cmd_calculate_gate_dir)

    p = sub.add_parser("select-packs")
    p.add_argument("profile")
    p.add_argument("--files", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_select_packs)

    p = sub.add_parser("snapshot-protected")
    p.add_argument("profile")
    p.add_argument("--output", required=True)
    p.add_argument("--repository-root")
    p.set_defaults(func=cmd_snapshot_protected)

    p = sub.add_parser("verify-protected")
    p.add_argument("snapshot")
    p.add_argument("--repository-root")
    p.add_argument("--output")
    p.set_defaults(func=cmd_verify_protected)

    p = sub.add_parser("archive-run")
    p.add_argument("directory")
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_archive_run)

    p = sub.add_parser("verify-manifest")
    p.add_argument("directory")
    p.add_argument("--manifest")
    p.set_defaults(func=cmd_verify_manifest)

    p = sub.add_parser("validate-graph")
    p.add_argument("graph")
    p.set_defaults(func=cmd_validate_graph)

    p = sub.add_parser("validate-intelligence-config")
    p.add_argument("config")
    p.set_defaults(func=cmd_validate_intelligence_config)

    p = sub.add_parser("validate-rules")
    p.add_argument("rules")
    p.add_argument("--status", choices=["candidate", "approved", "rejected", "retired"])
    p.set_defaults(func=cmd_validate_rules)

    p = sub.add_parser("index-project")
    p.add_argument("profile")
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--repository-root")
    p.set_defaults(func=cmd_index_project)

    p = sub.add_parser("analyze-change")
    p.add_argument("profile")
    p.add_argument("--graph", required=True)
    p.add_argument("--approved-rules")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--files")
    source.add_argument("--base")
    p.add_argument("--head", default="HEAD")
    p.add_argument("--change-id")
    p.add_argument("--max-depth", type=int, default=3)
    p.add_argument("--repository-root")
    p.add_argument("--output", required=True)
    p.add_argument("--markdown-output")
    p.set_defaults(func=cmd_analyze_change)

    p = sub.add_parser("compare-changes")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--markdown-output")
    p.set_defaults(func=cmd_compare_changes)

    p = sub.add_parser("capture-state")
    p.add_argument("profile")
    p.add_argument("--baseline")
    p.add_argument("--graph")
    p.add_argument("--approved-rules")
    p.add_argument("--active-changes")
    p.add_argument("--repository-root")
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_capture_state)

    p = sub.add_parser("discover-rule-candidates")
    p.add_argument("--history", required=True)
    p.add_argument("--config")
    p.add_argument("--min-samples", type=int, default=3)
    p.add_argument("--min-confidence", type=float, default=0.75)
    p.add_argument("--min-support", type=float, default=0.1)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_discover_rule_candidates)

    p = sub.add_parser("approve-rule")
    p.add_argument("--candidates", required=True)
    p.add_argument("--approved", required=True)
    p.add_argument("--rule-id", required=True)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--approved-at")
    p.add_argument("--rationale")
    p.set_defaults(func=cmd_approve_rule)


    p = sub.add_parser("validate-github-source", help="Validate GitHub PR evidence and its SHA-256 integrity hash")
    p.add_argument("source")
    p.set_defaults(func=cmd_validate_github_source)

    p = sub.add_parser("init-project", help="Create PIE project configuration in a repository")
    p.add_argument("--preset", choices=available_presets(), required=True)
    p.add_argument("--repository-root", default=".")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init_project)

    p = sub.add_parser("github-doctor", help="Check GitHub CLI installation, authentication, and repository context")
    p.add_argument("--hostname", default="github.com")
    p.add_argument("--repository-root", default=".")
    p.add_argument("--gh-executable")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--output")
    p.set_defaults(func=cmd_github_doctor)

    p = sub.add_parser("analyze-pr", help="Collect a GitHub pull request and run PIE impact analysis")
    p.add_argument("pull_request", help="PR number or https GitHub pull request URL")
    p.add_argument("--repo", help="OWNER/REPO or HOST/OWNER/REPO; required for a number outside a local Git repository")
    p.add_argument("--repository-root", default=".")
    p.add_argument("--profile")
    p.add_argument("--config")
    p.add_argument("--graph")
    p.add_argument("--approved-rules")
    p.add_argument("--refresh-graph", action="store_true")
    p.add_argument("--skip-diff", action="store_true")
    p.add_argument("--skip-discussion", action="store_true")
    p.add_argument("--allow-repository-mismatch", action="store_true")
    p.add_argument("--allow-head-mismatch", action="store_true")
    p.add_argument("--allow-dirty-worktree", action="store_true")
    p.add_argument("--max-depth", type=int, default=3)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--gh-executable", help=argparse.SUPPRESS)
    p.add_argument("--output-dir")
    p.set_defaults(func=cmd_analyze_pr)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

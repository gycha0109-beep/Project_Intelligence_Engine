from pathlib import Path


path = Path("src/review_system/cli.py")
text = path.read_text(encoding="utf-8")

application_import = (
    "from .application import AnalyzePullRequestRequest, analyze_pull_request\n"
)
if application_import not in text:
    text = text.replace(
        "from .baseline import verify_snapshot_file, write_snapshot\n",
        application_import + "from .baseline import verify_snapshot_file, write_snapshot\n",
        1,
    )

text = text.replace(
    "from .github_connector import GitHubCLI, collect_pull_request, doctor, refresh_source_hash, validate_pull_request_source",
    "from .github_connector import GitHubCLI, doctor, validate_pull_request_source",
    1,
)
text = text.replace("    path_matches,\n", "", 1)
text = text.replace(
    "from .intelligence_report import comparison_markdown, impact_markdown, pull_request_markdown",
    "from .intelligence_report import comparison_markdown, impact_markdown",
    1,
)

helper_start = text.index("\ndef _resolve_project_path")
helper_end = text.index("\ndef cmd_validate_github_source", helper_start)
text = text[:helper_start] + "\n" + text[helper_end:]

command_start = text.index("\ndef cmd_analyze_pr")
command_end = text.index("\ndef build_parser", command_start)
command = '''
def cmd_analyze_pr(args: argparse.Namespace) -> int:
    try:
        request = AnalyzePullRequestRequest(
            pull_request=args.pull_request,
            repository_root=args.repository_root,
            repository=args.repo,
            profile=args.profile,
            config=args.config,
            graph=args.graph,
            approved_rules=args.approved_rules,
            refresh_graph=args.refresh_graph,
            skip_diff=args.skip_diff,
            skip_discussion=args.skip_discussion,
            allow_repository_mismatch=args.allow_repository_mismatch,
            allow_head_mismatch=args.allow_head_mismatch,
            allow_dirty_worktree=args.allow_dirty_worktree,
            max_depth=args.max_depth,
            output_dir=args.output_dir,
        )
        result = analyze_pull_request(
            request,
            github_cli=GitHubCLI(
                executable=args.gh_executable,
                timeout_seconds=args.timeout,
            ),
            capture_state=capture_project_state,
        )
    except Exception as exc:
        return _error(exc)

    print(
        f"ANALYZED pull request: repo={result.source['repository']['name_with_owner']}; "
        f"pr=#{result.source['pull_request']['number']}; files={len(result.changed_files)}; "
        f"impacted={len(result.impact['impact']['dependent_files'])}; "
        f"packs={len(result.impact['review']['selected_packs'])}; output={result.output_dir}"
    )
    return 0
'''
text = text[:command_start] + "\n" + command + text[command_end:]

path.write_text(text, encoding="utf-8")

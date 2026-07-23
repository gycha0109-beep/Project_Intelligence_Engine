from pathlib import Path


path = Path("src/review_system/cli.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
    "from .application import AnalyzePullRequestRequest, analyze_pull_request\n",
    "from .application import (\n"
    "    AnalyzeChangeRequest,\n"
    "    AnalyzePullRequestRequest,\n"
    "    IndexProjectRequest,\n"
    "    analyze_project_change,\n"
    "    analyze_pull_request,\n"
    "    index_project,\n"
    ")\n",
    1,
)
text = text.replace("    load_intelligence_config,\n", "", 1)
text = text.replace(
    "from .intelligence_graph import build_project_graph, validate_project_graph",
    "from .intelligence_graph import validate_project_graph",
    1,
)
text = text.replace(
    "from .intelligence_impact import analyze_change, compare_change_sets",
    "from .intelligence_impact import compare_change_sets",
    1,
)
text = text.replace(
    "from .intelligence_report import comparison_markdown, impact_markdown",
    "from .intelligence_report import comparison_markdown",
    1,
)

start = text.index("\ndef cmd_index_project")
end = text.index("\ndef cmd_compare_changes", start)
replacement = '''
def cmd_index_project(args: argparse.Namespace) -> int:
    try:
        result = index_project(
            IndexProjectRequest(
                profile=args.profile,
                config=args.config,
                output=args.output,
                repository_root=args.repository_root,
            )
        )
    except Exception as exc:
        return _error(exc)
    graph = result.graph
    print(
        f"INDEXED project: files={graph['stats']['files']}; edges={graph['stats']['edges']}; "
        f"warnings={len(graph['warnings'])}; output={args.output}"
    )
    return 0


def cmd_analyze_change(args: argparse.Namespace) -> int:
    try:
        result = analyze_project_change(
            AnalyzeChangeRequest(
                profile=args.profile,
                graph=args.graph,
                approved_rules=args.approved_rules,
                files=args.files,
                base=args.base,
                head=args.head,
                change_id=args.change_id,
                max_depth=args.max_depth,
                repository_root=args.repository_root,
                output=args.output,
                markdown_output=args.markdown_output,
            ),
            git_diff_reader=git_changed_files,
        )
    except Exception as exc:
        return _error(exc)
    analysis = result.analysis
    print(
        f"ANALYZED change: direct={len(analysis['change']['changed_files'])}; "
        f"impacted={len(analysis['impact']['dependent_files'])}; "
        f"packs={len(analysis['review']['selected_packs'])}; output={args.output}"
    )
    return 0
'''
text = text[:start] + "\n" + replacement + text[end:]

path.write_text(text, encoding="utf-8")

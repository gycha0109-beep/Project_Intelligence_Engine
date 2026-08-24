from __future__ import annotations

import argparse
import json
import sys

from .github_connector import GitHubCLI
from .prospective_automation import ProspectiveAutomationError, RunGitHubPRRequest, run_github_pr
from .prospective_trust_bridge_cli import add_prospective_trust_bridge_subparser


def cmd_run_github_pr(args: argparse.Namespace) -> int:
    try:
        result = run_github_pr(
            RunGitHubPRRequest(
                pull_request=args.pull_request,
                event_head_sha=args.event_head_sha,
                pie_revision=args.pie_revision,
                repository_root=args.repository_root,
                repository=args.repo,
                profile=args.profile,
                config=args.config,
                trust_request=args.request,
                workspace=args.workspace,
                output_root=args.output_root,
                generated_at=args.generated_at,
                captured_at=args.captured_at,
            ),
            github_cli=GitHubCLI(executable=args.gh_executable, timeout_seconds=args.timeout),
        )
    except ProspectiveAutomationError as exc:
        print(
            json.dumps({"valid": False, "error_code": exc.code, "error": str(exc)}, indent=2, ensure_ascii=False),
            file=sys.stderr,
        )
        return 4
    print(json.dumps({"valid": True, **result}, indent=2, ensure_ascii=False))
    return 0


def add_prospective_automation_subparser(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser(
        "run-github-pr",
        help="Run the read-only prospective PR orchestration path bound to an exact event head",
    )
    command.add_argument("pull_request", help="PR number or HTTPS GitHub pull request URL")
    command.add_argument("--event-head-sha", required=True)
    command.add_argument("--pie-revision", required=True)
    command.add_argument("--repo")
    command.add_argument("--repository-root", default=".")
    command.add_argument("--profile", default=".review/project.yml")
    command.add_argument("--config", default=".review/intelligence/config.yml")
    command.add_argument("--request")
    command.add_argument("--workspace")
    command.add_argument("--output-root", default=".pie/automation")
    command.add_argument("--generated-at")
    command.add_argument("--captured-at")
    command.add_argument("--timeout", type=int, default=120)
    command.add_argument("--gh-executable", help=argparse.SUPPRESS)
    command.set_defaults(func=cmd_run_github_pr)

    add_prospective_trust_bridge_subparser(sub)

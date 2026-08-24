from __future__ import annotations

import argparse
import json
import sys

from .github_connector import GitHubCLI
from .prospective_automation import ProspectiveAutomationError
from .prospective_trust_bridge import (
    ProspectiveTrustBridgeError,
    TrustedGitHubPRRequest,
    run_trusted_github_pr,
)
from .prospective_trust_bridge_result import (
    ProspectiveTrustBridgeResultError,
    stabilize_trusted_bridge_result,
)


def cmd_run_github_pr_trusted(args: argparse.Namespace) -> int:
    try:
        result = run_trusted_github_pr(
            TrustedGitHubPRRequest(
                pull_request=args.pull_request,
                target_repository=args.target_repository,
                event_head_sha=args.event_head_sha,
                event_base_sha=args.event_base_sha,
                pie_revision=args.pie_revision,
                trust_request_path=args.trust_request_path,
                trust_request_sha256=args.trust_request_sha256,
                repository_root=args.repository_root,
                profile=args.profile,
                config=args.config,
                output_root=args.output_root,
            ),
            github_cli=GitHubCLI(executable=args.gh_executable, timeout_seconds=args.timeout),
        )
        result = stabilize_trusted_bridge_result(result)
    except (
        ProspectiveTrustBridgeError,
        ProspectiveTrustBridgeResultError,
        ProspectiveAutomationError,
    ) as exc:
        print(
            json.dumps(
                {
                    "valid": False,
                    "error_code": getattr(exc, "code", "AUTO2_BRIDGE_FAILED"),
                    "error": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    print(json.dumps({"valid": True, **result}, indent=2, ensure_ascii=False))
    return 0


def add_prospective_trust_bridge_subparser(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser(
        "run-github-pr-trusted",
        help="Bind an authority-repository Trust request to an exact PR and prepare Stage 10K human-review evidence",
    )
    command.add_argument("pull_request", type=int)
    command.add_argument("--target-repository", required=True)
    command.add_argument("--event-head-sha", required=True)
    command.add_argument("--event-base-sha", required=True)
    command.add_argument("--pie-revision", required=True)
    command.add_argument("--trust-request-path", required=True)
    command.add_argument("--trust-request-sha256", required=True)
    command.add_argument("--repository-root", default=".")
    command.add_argument("--profile", default=".review/project.yml")
    command.add_argument("--config", default=".review/intelligence/config.yml")
    command.add_argument("--output-root", default=".pie/human-review-bridge")
    command.add_argument("--timeout", type=int, default=120)
    command.add_argument("--gh-executable", help=argparse.SUPPRESS)
    command.set_defaults(func=cmd_run_github_pr_trusted)

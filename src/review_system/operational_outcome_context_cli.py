from __future__ import annotations

import argparse
from typing import Callable

from .github_connector import GitHubCLI
from .operational_outcome_context import (
    OperationalOutcomeContextRequest,
    run_operational_outcome_context,
)


def cmd_prepare_operational_outcome_context(
    args: argparse.Namespace,
    *,
    emit: Callable[[object], None],
) -> int:
    result = run_operational_outcome_context(
        OperationalOutcomeContextRequest(
            target_repository=args.target_repository,
            pull_request=args.pull_request,
            repository_root=args.repository_root,
            artifact_cache_root=args.artifact_cache_root,
            output=args.output,
        ),
        github_cli=GitHubCLI(
            executable=args.gh_executable,
            timeout_seconds=args.timeout,
        ),
    )
    emit({"valid": True, **result})
    return 0


def add_operational_outcome_context_subparser(
    sub: argparse._SubParsersAction,
    *,
    emit: Callable[[object], None],
) -> None:
    command = sub.add_parser(
        "prepare-operational-outcome-context",
        help=(
            "Prepare an ORL-5 source-bound AUTO-3 Outcome declaration context "
            "without declaring or recording an Outcome."
        ),
    )
    command.add_argument("--target-repository", required=True)
    command.add_argument("--pull-request", type=int, required=True)
    command.add_argument("--repository-root", default=".")
    command.add_argument("--artifact-cache-root", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--timeout", type=int, default=120)
    command.add_argument("--gh-executable", help=argparse.SUPPRESS)
    command.set_defaults(
        _emit=emit,
        func=lambda args: cmd_prepare_operational_outcome_context(
            args,
            emit=args._emit,
        ),
    )

from __future__ import annotations

import argparse
from typing import Callable

from .github_connector import GitHubCLI, GitHubCLIError
from .operational_outcome_action import (
    OperationalOutcomeActionError,
    OperationalOutcomeActionRequest,
    OperationalOutcomeActionVerificationError,
    run_operational_outcome_action,
)
from .operational_review_action import OperationalReviewActionError


def cmd_submit_operational_outcome(
    args: argparse.Namespace,
    *,
    emit: Callable[[object], None],
) -> int:
    try:
        result = run_operational_outcome_action(
            OperationalOutcomeActionRequest(
                target_repository=args.target_repository,
                pull_request=args.pull_request,
                actor=args.actor,
                authority_type=args.authority_type,
                verdict=args.verdict,
                repository_root=args.repository_root,
                artifact_cache_root=args.artifact_cache_root,
                output_root=args.output_root,
                declared_at=args.declared_at,
                defect_id=args.defect_id,
                evidence_refs=args.evidence_ref,
                defect_registry=args.defect_registry,
                ledger=args.ledger,
                evaluation_report=args.evaluation_report,
                audit_artifact=args.audit_artifact,
                audit_authority_registry=args.audit_authority_registry,
            ),
            github_cli=GitHubCLI(
                executable=args.gh_executable,
                timeout_seconds=args.timeout,
            ),
        )
    except OperationalOutcomeActionVerificationError as exc:
        emit({"valid": False, "error_code": exc.code, "errors": list(exc.errors)})
        return 4
    except (
        OperationalOutcomeActionError,
        OperationalReviewActionError,
        GitHubCLIError,
        OSError,
        ValueError,
    ) as exc:
        emit(
            {
                "valid": False,
                "error_code": getattr(exc, "code", "ORL6_OUTCOME_ACTION_FAILED"),
                "error": str(exc),
            }
        )
        return 3
    emit({"valid": True, **result})
    return 0


def add_operational_outcome_action_subparser(
    sub: argparse._SubParsersAction,
    *,
    emit: Callable[[object], None],
) -> None:
    command = sub.add_parser(
        "submit-operational-outcome",
        help=(
            "Resolve the current ORL-5 context, create an explicit AUTO-3A "
            "Outcome declaration, and transport it through existing AUTO-3B."
        ),
    )
    command.add_argument("--target-repository", required=True)
    command.add_argument("--pull-request", type=int, required=True)
    command.add_argument("--repository-root", default=".")
    command.add_argument("--artifact-cache-root", required=True)
    command.add_argument("--output-root", required=True)
    command.add_argument("--actor", required=True)
    command.add_argument(
        "--authority-type",
        choices=["PRODUCTION_DEFECT", "CONTROLLED_EVALUATION", "INDEPENDENT_AUDIT"],
        required=True,
    )
    command.add_argument(
        "--verdict",
        choices=["SAFE", "UNSAFE", "INCONCLUSIVE"],
        required=True,
    )
    command.add_argument("--declared-at")
    command.add_argument("--defect-id")
    command.add_argument("--evidence-ref", action="append", default=[])
    command.add_argument("--defect-registry")
    command.add_argument("--ledger")
    command.add_argument("--evaluation-report")
    command.add_argument("--audit-artifact")
    command.add_argument("--audit-authority-registry")
    command.add_argument("--timeout", type=int, default=120)
    command.add_argument("--gh-executable", help=argparse.SUPPRESS)
    command.set_defaults(
        _emit=emit,
        func=lambda args: cmd_submit_operational_outcome(args, emit=args._emit),
    )

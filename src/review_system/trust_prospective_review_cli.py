from __future__ import annotations

import argparse
from typing import Callable

from .github_connector import GitHubCLI
from .operational_outcome_action_cli import add_operational_outcome_action_subparser
from .operational_outcome_context_cli import add_operational_outcome_context_subparser
from .operational_review_action import (
    OperationalReviewActionRequest,
    run_operational_review_action,
)
from .trust_prospective_review import (
    ProspectiveReviewVerificationError,
    load_review_packet,
    prepare_review_packet,
    submit_review_packet,
    verify_review_packet_sources,
    write_review_packet,
)


def _github_cli(args: argparse.Namespace) -> GitHubCLI:
    return GitHubCLI(executable=args.gh_executable, timeout_seconds=args.timeout)


def cmd_prepare_prospective_review(args: argparse.Namespace, *, emit: Callable[[object], None]) -> int:
    packet = prepare_review_packet(
        args.workspace,
        assessment_id=args.assessment_id,
        github_candidate=args.github_candidate,
        repository_root=args.repository_root,
        github_cli=_github_cli(args),
        repository=args.repo,
        generated_at=args.generated_at,
    )
    output = write_review_packet(args.output, packet)
    emit({
        "valid": True,
        "output": str(output),
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "assessment_id": packet["assessment_id"],
        "source_revision": packet["source_revision"],
        "review_requirement": packet["review_requirement"],
        "mode": packet["mode"],
        "automation_authorized": packet["automation_authorized"],
        "pilot_authorized": packet["pilot_authorized"],
        "human_review_recorded": packet["human_review_recorded"],
        "outcome_recorded": packet["outcome_recorded"],
    })
    return 0


def cmd_verify_prospective_review(args: argparse.Namespace, *, emit: Callable[[object], None]) -> int:
    source, packet = load_review_packet(args.packet)
    errors = verify_review_packet_sources(
        packet,
        workspace_root=args.workspace,
        github_candidate=args.github_candidate,
        repository_root=args.repository_root,
        github_cli=_github_cli(args),
        repository=args.repo,
    )
    if errors:
        raise ProspectiveReviewVerificationError(errors)
    emit({
        "valid": True,
        "packet": str(source),
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "assessment_id": packet["assessment_id"],
        "source_replayed": True,
        "live_github_replayed": True,
        "mode": "REPORT_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
    })
    return 0


def cmd_submit_prospective_review(args: argparse.Namespace, *, emit: Callable[[object], None]) -> int:
    result = submit_review_packet(
        args.packet,
        workspace_root=args.workspace,
        github_candidate=args.github_candidate,
        repository_root=args.repository_root,
        github_cli=_github_cli(args),
        repository=args.repo,
        review_level=args.review_level,
        decision=args.decision,
        actor=args.actor,
        occurred_at=args.occurred_at,
        confirmed_risk_band=args.confirmed_risk_band,
        reason_codes=args.reason,
    )
    emit({"valid": True, **result})
    return 0


def cmd_submit_operational_review(args: argparse.Namespace, *, emit: Callable[[object], None]) -> int:
    result = run_operational_review_action(
        OperationalReviewActionRequest(
            target_repository=args.target_repository,
            pull_request=args.pull_request,
            decision=args.decision,
            reason=args.reason,
            actor=args.actor,
            repository_root=args.repository_root,
            artifact_cache_root=args.artifact_cache_root,
            confirmed_risk_band=args.confirmed_risk_band,
            occurred_at=args.occurred_at,
            output=args.output,
        ),
        github_cli=_github_cli(args),
    )
    emit({"valid": True, **result})
    return 0


def _add_live_source_args(command: argparse.ArgumentParser) -> None:
    command.add_argument("--workspace", required=True)
    command.add_argument("--github-candidate", required=True)
    command.add_argument("--repository-root", required=True)
    command.add_argument("--repo")
    command.add_argument("--timeout", type=int, default=120)
    command.add_argument("--gh-executable", help=argparse.SUPPRESS)


def _add_submit_args(command: argparse.ArgumentParser) -> None:
    _add_live_source_args(command)
    command.add_argument("--packet", required=True)
    command.add_argument("--review-level", choices=["REVIEWED", "AUDITED"], required=True)
    command.add_argument(
        "--decision",
        choices=["APPROVE", "REQUEST_CHANGES", "HOLD", "REJECT", "RECLASSIFY"],
        required=True,
    )
    command.add_argument("--confirmed-risk-band", choices=["R0", "R1", "R2", "R3", "R4"])
    command.add_argument("--reason", action="append", default=[])
    command.add_argument("--actor", required=True)
    command.add_argument("--occurred-at")
    command.set_defaults(func=lambda args: cmd_submit_prospective_review(args, emit=args._emit))


def _add_operational_submit_args(command: argparse.ArgumentParser) -> None:
    command.add_argument("--target-repository", required=True)
    command.add_argument("--pull-request", type=int, required=True)
    command.add_argument("--repository-root", required=True)
    command.add_argument("--artifact-cache-root", required=True)
    command.add_argument(
        "--decision",
        choices=["APPROVE", "REQUEST_CHANGES", "HOLD", "REJECT", "RECLASSIFY"],
        required=True,
    )
    command.add_argument("--reason", required=True)
    command.add_argument("--actor", required=True)
    command.add_argument("--confirmed-risk-band", choices=["R0", "R1", "R2", "R3", "R4"])
    command.add_argument("--occurred-at")
    command.add_argument("--output", required=True)
    command.add_argument("--timeout", type=int, default=120)
    command.add_argument("--gh-executable", help=argparse.SUPPRESS)
    command.set_defaults(func=lambda args: cmd_submit_operational_review(args, emit=args._emit))


def add_prospective_review_subparsers(
    sub: argparse._SubParsersAction,
    *,
    emit: Callable[[object], None],
) -> None:
    command = sub.add_parser("prepare-prospective-review")
    _add_live_source_args(command)
    command.add_argument("--assessment-id", required=True)
    command.add_argument("--generated-at")
    command.add_argument("--output", required=True)
    command.set_defaults(
        _emit=emit,
        func=lambda args: cmd_prepare_prospective_review(args, emit=args._emit),
    )

    command = sub.add_parser("verify-prospective-review")
    _add_live_source_args(command)
    command.add_argument("--packet", required=True)
    command.set_defaults(
        _emit=emit,
        func=lambda args: cmd_verify_prospective_review(args, emit=args._emit),
    )

    for name in ("submit-prospective-review", "record-prospective-review"):
        command = sub.add_parser(name)
        command.set_defaults(_emit=emit)
        _add_submit_args(command)

    command = sub.add_parser(
        "submit-operational-review",
        help="Resolve the current governed packet for a PR and record one explicit REVIEWED human decision.",
    )
    command.set_defaults(_emit=emit)
    _add_operational_submit_args(command)

    add_operational_outcome_context_subparser(sub, emit=emit)
    add_operational_outcome_action_subparser(sub, emit=emit)

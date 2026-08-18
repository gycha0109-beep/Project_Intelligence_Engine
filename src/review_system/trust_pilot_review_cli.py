from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .trust_pilot_review import (
    PilotSafetyReviewError,
    PilotSafetyReviewVerificationError,
    load_pilot_review_report,
    review_r0_pilot,
    verify_pilot_review_report_sources,
    write_pilot_review_report,
)


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def _add_sources(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument("--registry", required=required)
    parser.add_argument("--reconciliation-report", required=required)
    parser.add_argument("--reconciliation-sources", required=required)
    parser.add_argument("--observation-report", required=required)
    parser.add_argument("--observation-policy", required=required)


def cmd_review(args: argparse.Namespace) -> int:
    report = review_r0_pilot(
        registry_path=args.registry,
        reconciliation_report_path=args.reconciliation_report,
        reconciliation_sources_path=args.reconciliation_sources,
        observation_report_path=args.observation_report,
        observation_policy_path=args.observation_policy,
        generated_at=args.generated_at,
    )
    output = write_pilot_review_report(args.output, report)
    _print_json({
        "valid": True,
        "output": str(output),
        "review_id": report["review_id"],
        "status": report["status"],
        "next_step": report["next_step"],
        "blockers": report["blockers"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
    })
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    source, report = load_pilot_review_report(args.report)
    values = [
        args.registry,
        args.reconciliation_report,
        args.reconciliation_sources,
        args.observation_report,
        args.observation_policy,
    ]
    replay_requested = any(value is not None for value in values)
    if replay_requested and not all(value is not None for value in values):
        raise PilotSafetyReviewError(
            "source replay requires --registry, --reconciliation-report, --reconciliation-sources, "
            "--observation-report, and --observation-policy"
        )
    if replay_requested:
        errors = verify_pilot_review_report_sources(
            report,
            registry_path=args.registry,
            reconciliation_report_path=args.reconciliation_report,
            reconciliation_sources_path=args.reconciliation_sources,
            observation_report_path=args.observation_report,
            observation_policy_path=args.observation_policy,
        )
        if errors:
            raise PilotSafetyReviewVerificationError(errors)
    _print_json({
        "valid": True,
        "report": str(source),
        "review_id": report["review_id"],
        "status": report["status"],
        "source_replayed": replay_requested,
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "errors": [],
    })
    return 0


def add_pilot_review_subparsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser(
        "review-r0-pilot",
        help="Combine Stage 10B/10C/10D evidence into a report-only R0 pilot safety review.",
    )
    _add_sources(command, required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_review)

    command = sub.add_parser(
        "verify-r0-pilot-review",
        help="Verify an R0 pilot safety review report and optional exact source replay.",
    )
    command.add_argument("--report", required=True)
    _add_sources(command, required=False)
    command.set_defaults(func=cmd_verify)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust-pilot-review",
        description="Evaluate R0 pilot eligibility without granting pilot or automation authority.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_pilot_review_subparsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except PilotSafetyReviewVerificationError as exc:
        _print_json({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (PilotSafetyReviewError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .trust import (
    TrustError,
    TrustVerificationError,
    assess_trust,
    load_trust_report,
    verify_trust_report_sources,
    write_trust_report,
)


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def _add_sources(parser: argparse.ArgumentParser, *, required_core: bool) -> None:
    parser.add_argument("--request", required=required_core)
    parser.add_argument("--profile", required=required_core)
    parser.add_argument("--ledger")
    parser.add_argument("--policy-registry")
    parser.add_argument("--evaluation-report")
    parser.add_argument("--reground-report")
    parser.add_argument("--reground-observations")


def cmd_assess(args: argparse.Namespace) -> int:
    try:
        report = assess_trust(
            args.request,
            args.profile,
            ledger=args.ledger,
            policy_registry=args.policy_registry,
            evaluation_report=args.evaluation_report,
            reground_report=args.reground_report,
            reground_observations=args.reground_observations,
            generated_at=args.generated_at,
        )
        output = write_trust_report(args.output, report)
    except (TrustError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3
    _print_json(
        {
            "valid": True,
            "output": str(output),
            "report_id": report["report_id"],
            "mode": report["mode"],
            "risk_band": report["risk"]["effective_band"],
            "readiness": report["readiness"]["status"],
            "next_step": report["readiness"]["next_step"],
            "automation_authorized": report["automation_authorized"],
            "triggered_hard_gates": report["task_advisory"]["triggered_hard_gates"],
        }
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        source, report = load_trust_report(args.report)
    except TrustVerificationError as exc:
        _print_json(
            {"valid": False, "report": str(args.report), "errors": list(exc.errors)},
            stream=sys.stderr,
        )
        return 4
    except (TrustError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3

    replay_requested = any(
        value is not None
        for value in (
            args.request,
            args.profile,
            args.ledger,
            args.policy_registry,
            args.evaluation_report,
            args.reground_report,
            args.reground_observations,
        )
    )
    if replay_requested:
        if args.request is None or args.profile is None:
            _print_json(
                {
                    "valid": False,
                    "error": "source replay requires both --request and --profile",
                },
                stream=sys.stderr,
            )
            return 3
        errors = verify_trust_report_sources(
            report,
            request=args.request,
            profile=args.profile,
            ledger=args.ledger,
            policy_registry=args.policy_registry,
            evaluation_report=args.evaluation_report,
            reground_report=args.reground_report,
            reground_observations=args.reground_observations,
        )
        if errors:
            _print_json(
                {"valid": False, "report": str(source), "errors": errors},
                stream=sys.stderr,
            )
            return 4

    _print_json(
        {
            "valid": True,
            "report": str(source),
            "report_id": report["report_id"],
            "risk_band": report["risk"]["effective_band"],
            "readiness": report["readiness"]["status"],
            "automation_authorized": report["automation_authorized"],
            "source_replayed": replay_requested,
            "errors": [],
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust",
        description="Generate and verify report-only Trust Gate readiness evidence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("assess", help="Generate a report-only Trust readiness report.")
    _add_sources(command, required_core=True)
    command.add_argument("--output", required=True)
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_assess)

    command = sub.add_parser("verify-report", help="Verify a Trust readiness report and optional sources.")
    command.add_argument("--report", required=True)
    _add_sources(command, required_core=False)
    command.set_defaults(func=cmd_validate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

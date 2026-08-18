from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .trust_observation import (
    TrustObservationError,
    TrustObservationVerificationError,
    assess_observation,
    load_policy,
    load_report,
    policy_id,
    policy_sha256,
    verify_policy_data,
    verify_report_sources,
    write_report,
)


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def cmd_verify_policy(args: argparse.Namespace) -> int:
    source, policy = load_policy(args.policy)
    errors = verify_policy_data(policy)
    _print_json({
        "valid": not errors,
        "policy": str(source),
        "policy_id": policy_id(policy),
        "policy_version": policy["policy_version"],
        "policy_sha256": policy_sha256(policy),
        "mode": policy["mode"],
        "target_band": policy["target_band"],
        "errors": errors,
    })
    return 0 if not errors else 4


def cmd_observe(args: argparse.Namespace) -> int:
    report = assess_observation(
        args.registry,
        args.policy,
        generated_at=args.generated_at,
    )
    output = write_report(args.output, report)
    _print_json({
        "valid": True,
        "output": str(output),
        "report_id": report["report_id"],
        "status": report["status"],
        "next_step": report["next_step"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "blockers": report["blockers"],
    })
    return 0


def cmd_verify_report(args: argparse.Namespace) -> int:
    source, report = load_report(args.report)
    replay_requested = args.registry is not None or args.policy is not None
    if replay_requested:
        if args.registry is None or args.policy is None:
            raise TrustObservationError("source replay requires both --registry and --policy")
        errors = verify_report_sources(
            report,
            registry_path=args.registry,
            policy_path=args.policy,
        )
        if errors:
            raise TrustObservationVerificationError(errors)
    _print_json({
        "valid": True,
        "report": str(source),
        "report_id": report["report_id"],
        "status": report["status"],
        "source_replayed": replay_requested,
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "errors": [],
    })
    return 0


def add_observation_subparsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser("verify-observation-policy", help="Verify an R0 report-only observation threshold policy.")
    command.add_argument("--policy", required=True)
    command.set_defaults(func=cmd_verify_policy)

    command = sub.add_parser("observe-readiness", help="Evaluate R0 observation maturity without authorizing a pilot.")
    command.add_argument("--registry", required=True)
    command.add_argument("--policy", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_observe)

    command = sub.add_parser("verify-observation-report", help="Verify an observation report and optional source replay.")
    command.add_argument("--report", required=True)
    command.add_argument("--registry")
    command.add_argument("--policy")
    command.set_defaults(func=cmd_verify_report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust-observation",
        description="Evaluate R0 operating observation thresholds in report-only mode.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_observation_subparsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except TrustObservationVerificationError as exc:
        _print_json({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (TrustObservationError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .trust_pilot_evidence_run import (
    ELIGIBLE_STATUS,
    PilotEvidenceRunError,
    PilotEvidenceRunVerificationError,
    load_pilot_evidence_run_report,
    run_r0_pilot_evidence,
    verify_pilot_evidence_run_report_sources,
    write_pilot_evidence_run_report,
)


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def cmd_run(args: argparse.Namespace) -> int:
    report = run_r0_pilot_evidence(args.evidence_root, generated_at=args.generated_at)
    output = write_pilot_evidence_run_report(args.output, report)
    _print_json({
        "valid": True,
        "output": str(output),
        "run_id": report["run_id"],
        "status": report["status"],
        "next_step": report["next_step"],
        "package_complete": report["package_complete"],
        "source_replay_verified": report["source_replay"]["verified"],
        "blockers": report["blockers"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
    })
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    source, report = load_pilot_evidence_run_report(args.report)
    replayed = args.evidence_root is not None
    if report["status"] == ELIGIBLE_STATUS and not replayed:
        raise PilotEvidenceRunError("eligible evidence-run verification requires --evidence-root exact source replay")
    if replayed:
        errors = verify_pilot_evidence_run_report_sources(report, evidence_root=args.evidence_root)
        if errors:
            raise PilotEvidenceRunVerificationError(errors)
    _print_json({
        "valid": True,
        "report": str(source),
        "run_id": report["run_id"],
        "status": report["status"],
        "source_replayed": replayed,
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "errors": [],
    })
    return 0


def add_pilot_evidence_run_subparsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser(
        "run-r0-pilot-evidence",
        help="Inventory an R0 evidence package and run authority-aware Stage 10E eligibility replay when complete.",
    )
    command.add_argument("--evidence-root", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_run)

    command = sub.add_parser(
        "verify-r0-pilot-evidence-run",
        help="Verify a Stage 10G evidence-run report; eligible reports require exact evidence-root replay.",
    )
    command.add_argument("--report", required=True)
    command.add_argument("--evidence-root")
    command.set_defaults(func=cmd_verify)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust-pilot-evidence",
        description="Evaluate whether a real R0 evidence package reaches human pilot authorization review without granting activation authority.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_pilot_evidence_run_subparsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except PilotEvidenceRunVerificationError as exc:
        _print_json({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (PilotEvidenceRunError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .trust_evidence_acquisition import (
    EvidenceAcquisitionError,
    EvidenceAcquisitionVerificationError,
    inspect_acquisition_workspace,
    load_acquisition_report,
    populate_r0_evidence_package,
    verify_acquisition_report_sources,
    write_acquisition_report,
)


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def _result(report: dict, output: str) -> dict:
    return {
        "valid": True,
        "output": output,
        "report_id": report["report_id"],
        "status": report["status"],
        "next_step": report["next_step"],
        "workspace_complete": report["workspace_complete"],
        "package_published": report["package"]["published"],
        "pilot_evidence_status": report["generated"]["pilot_evidence_status"],
        "source_replay_verified": report["generated"]["source_replay_verified"],
        "blockers": report["blockers"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
    }


def cmd_inspect(args: argparse.Namespace) -> int:
    report = inspect_acquisition_workspace(args.workspace, generated_at=args.generated_at)
    output = write_acquisition_report(args.output, report)
    _print_json(_result(report, str(output)))
    return 0


def cmd_populate(args: argparse.Namespace) -> int:
    report = populate_r0_evidence_package(
        args.workspace,
        args.package_root,
        generated_at=args.generated_at,
    )
    output = write_acquisition_report(args.output, report)
    _print_json(_result(report, str(output)))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    source, report = load_acquisition_report(args.report)
    errors = verify_acquisition_report_sources(
        report,
        workspace_root=args.workspace,
        package_root=args.package_root,
    )
    if errors:
        raise EvidenceAcquisitionVerificationError(errors)
    _print_json({
        "valid": True,
        "report": str(source),
        "report_id": report["report_id"],
        "status": report["status"],
        "workspace_replayed": args.workspace is not None,
        "package_replayed": args.package_root is not None,
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "errors": [],
    })
    return 0


def add_evidence_acquisition_subparsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser(
        "inspect-r0-evidence-acquisition",
        help="Inspect a real R0 acquisition workspace without fabricating missing evidence.",
    )
    command.add_argument("--workspace", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_inspect)

    command = sub.add_parser(
        "populate-r0-evidence-package",
        help="Rebuild Stage 10C/10D reports from source closure, run Stage 10G replay, and publish a verified runtime package.",
    )
    command.add_argument("--workspace", required=True)
    command.add_argument("--package-root", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_populate)

    command = sub.add_parser(
        "verify-r0-evidence-acquisition",
        help="Verify a Stage 10H acquisition report and optional workspace/package source replay.",
    )
    command.add_argument("--report", required=True)
    command.add_argument("--workspace")
    command.add_argument("--package-root")
    command.set_defaults(func=cmd_verify)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust-evidence-acquisition",
        description="Acquire and package real R0 runtime evidence without synthetic substitution, threshold relaxation, or pilot activation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_evidence_acquisition_subparsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except EvidenceAcquisitionVerificationError as exc:
        _print_json({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (EvidenceAcquisitionError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

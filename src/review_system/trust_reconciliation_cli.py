from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .trust_reconciliation_authority import (
    TrustReconciliationError,
    TrustReconciliationVerificationError,
    load_reconciliation_report,
    load_source_manifest,
    manifest_sha256,
    reconcile_sources,
    verify_reconciliation_report_sources,
    write_reconciliation_report,
)


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def cmd_verify_sources(args: argparse.Namespace) -> int:
    source, manifest = load_source_manifest(args.sources)
    _print_json({
        "valid": True,
        "sources": str(source),
        "project_id": manifest["project_id"],
        "manifest_sha256": manifest_sha256(manifest),
        "assessment_source_count": len(manifest["assessment_sources"]),
        "outcome_source_count": len(manifest["outcome_sources"]),
        "errors": [],
    })
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    report = reconcile_sources(args.registry, args.sources, generated_at=args.generated_at)
    output = write_reconciliation_report(args.output, report)
    _print_json({
        "valid": True,
        "output": str(output),
        "report_id": report["report_id"],
        "status": report["status"],
        "source_reconciliation_complete": report["summary"]["source_reconciliation_complete"],
        "assessment_unreconciled_count": report["summary"]["assessment_unreconciled_count"],
        "conclusive_outcome_unreconciled_count": report["summary"]["conclusive_outcome_unreconciled_count"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
    })
    return 0


def cmd_verify_report(args: argparse.Namespace) -> int:
    source, report = load_reconciliation_report(args.report)
    replay_requested = args.registry is not None or args.sources is not None
    if replay_requested:
        if args.registry is None or args.sources is None:
            raise TrustReconciliationError("source replay requires both --registry and --sources")
        errors = verify_reconciliation_report_sources(report, registry_path=args.registry, source_manifest_path=args.sources)
        if errors:
            raise TrustReconciliationVerificationError(errors)
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


def add_reconciliation_subparsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser("verify-reconciliation-sources", help="Verify a Trust reconciliation source manifest, including Stage 10F audit authority sources.")
    command.add_argument("--sources", required=True)
    command.set_defaults(func=cmd_verify_sources)

    command = sub.add_parser("reconcile-sources", help="Replay Trust assessments and reconcile Outcome authorities in report-only mode.")
    command.add_argument("--registry", required=True)
    command.add_argument("--sources", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_reconcile)

    command = sub.add_parser("verify-reconciliation-report", help="Verify a reconciliation report and optional exact source replay.")
    command.add_argument("--report", required=True)
    command.add_argument("--registry")
    command.add_argument("--sources")
    command.set_defaults(func=cmd_verify_report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust-reconciliation",
        description="Replay and reconcile Trust/Outcome source authorities, including Independent Audit provenance, without authorizing automation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_reconciliation_subparsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except TrustReconciliationVerificationError as exc:
        _print_json({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (TrustReconciliationError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

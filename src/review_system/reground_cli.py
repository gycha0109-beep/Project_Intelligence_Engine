from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .reground import (
    RegroundError,
    RegroundVerificationError,
    analyze_reground,
    load_reground_report,
    write_reground_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-reground",
        description="Generate and verify advisory Graph/Ledger Reground reports.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Generate an advisory Reground report.")
    analyze.add_argument("--project-id", required=True)
    analyze.add_argument("--repository-root", required=True)
    analyze.add_argument("--graph", required=True)
    analyze.add_argument("--ledger", required=True)
    analyze.add_argument("--output", required=True)
    analyze.add_argument("--generated-at")

    verify = subparsers.add_parser("verify-report", help="Verify a self-contained Reground report.")
    verify.add_argument("--report", required=True)
    return parser


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "analyze":
            report = analyze_reground(
                project_id=args.project_id,
                repository_root=args.repository_root,
                graph=args.graph,
                ledger=args.ledger,
                generated_at=args.generated_at,
            )
            output = write_reground_report(args.output, report)
            _print_json(
                {
                    "valid": True,
                    "output": str(output),
                    "report_id": report["report_id"],
                    "status": report["summary"]["status"],
                    "stale_relations": report["summary"]["stale_relations"],
                    "impacted_rechecks": report["summary"]["impacted_rechecks"],
                }
            )
            return 0

        if args.command == "verify-report":
            try:
                source, _ = load_reground_report(args.report)
            except RegroundVerificationError as exc:
                _print_json(
                    {"valid": False, "report": str(args.report), "errors": list(exc.errors)},
                    stream=sys.stderr,
                )
                return 4
            _print_json({"valid": True, "report": str(source), "errors": []})
            return 0
    except (RegroundError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3
    parser.error(f"unsupported command: {args.command}")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

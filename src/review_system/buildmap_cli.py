from __future__ import annotations

import argparse
import json
import sys

from .buildmap_export import (
    BuildMapExportError,
    BuildMapExportVerificationError,
    build_buildmap_export,
    load_buildmap_export,
    verify_buildmap_export_source,
    write_buildmap_export,
)


def _error(exc: Exception) -> int:
    print(f"ERROR {exc}", file=sys.stderr)
    return 2


def cmd_export(args: argparse.Namespace) -> int:
    try:
        document = build_buildmap_export(
            args.ledger,
            project_id=args.project_id,
            run_id=args.run_id,
            redaction_paths=args.redact_path,
            generated_at=args.generated_at,
        )
        target = write_buildmap_export(args.output, document)
    except Exception as exc:
        return _error(exc)
    print(
        json.dumps(
            {
                "export_id": document["export_id"],
                "project_id": document["project_id"],
                "run_id": document["source"]["run_id"],
                "projection_sha256": document["projection_sha256"],
                "output": str(target),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        _, document = load_buildmap_export(args.export)
        errors = verify_buildmap_export_source(document, args.ledger) if args.ledger else []
    except BuildMapExportVerificationError as exc:
        for error in exc.errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 4
    except Exception as exc:
        return _error(exc)
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 4
    print(f"VALID BuildMap export: {args.export}; export_id={document['export_id']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PIE metadata-only BuildMap reference export")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("export", help="Export one verified PIE Run for BuildMap")
    command.add_argument("--ledger", required=True)
    command.add_argument("--project-id", required=True)
    command.add_argument("--run-id", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--redact-path", action="append", default=[])
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_export)

    command = sub.add_parser("validate", help="Validate a BuildMap export and optionally replay it against a Ledger")
    command.add_argument("export")
    command.add_argument("--ledger")
    command.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BuildMapExportError as exc:
        return _error(exc)


if __name__ == "__main__":
    raise SystemExit(main())

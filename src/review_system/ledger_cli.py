from __future__ import annotations

import argparse
import json
import sys

from .ledger import (
    import_artifact_directory,
    initialize_ledger,
    rebuild_ledger,
    show_run,
    verify_ledger,
)


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _error(exc: Exception) -> int:
    print(f"ERROR {exc}", file=sys.stderr)
    return 2


def cmd_init(args: argparse.Namespace) -> int:
    try:
        path = initialize_ledger(args.database)
    except Exception as exc:
        return _error(exc)
    _print({"initialized": True, "database": str(path)})
    return 0


def cmd_import_run(args: argparse.Namespace) -> int:
    try:
        result = import_artifact_directory(
            args.database,
            args.directory,
            expected_run_type="review",
        )
    except Exception as exc:
        return _error(exc)
    _print(result.to_dict())
    return 0


def cmd_import_pr(args: argparse.Namespace) -> int:
    try:
        result = import_artifact_directory(
            args.database,
            args.directory,
            expected_run_type="pull_request",
        )
    except Exception as exc:
        return _error(exc)
    _print(result.to_dict())
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        result = verify_ledger(args.database)
    except Exception as exc:
        return _error(exc)
    _print(result)
    return 0 if result["valid"] else 4


def cmd_rebuild(args: argparse.Namespace) -> int:
    try:
        result = rebuild_ledger(
            args.database,
            args.directories,
            registry_paths=args.defect_registry,
        )
    except Exception as exc:
        return _error(exc)
    _print(result)
    return 0


def cmd_show_run(args: argparse.Namespace) -> int:
    try:
        result = show_run(args.database, args.run_id)
    except Exception as exc:
        return _error(exc)
    if result is None:
        print(f"ERROR logical run not found: {args.run_id}", file=sys.stderr)
        return 4
    _print(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-ledger",
        description="Rebuildable SQLite evidence index for PIE artifact directories",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("init", help="Initialize or migrate a ledger database")
    command.add_argument("--database", required=True)
    command.set_defaults(func=cmd_init)

    command = sub.add_parser("import-run", help="Import a Review Run identity directory")
    command.add_argument("directory")
    command.add_argument("--database", required=True)
    command.set_defaults(func=cmd_import_run)

    command = sub.add_parser("import-pr", help="Import a PR analysis identity directory")
    command.add_argument("directory")
    command.add_argument("--database", required=True)
    command.set_defaults(func=cmd_import_pr)

    command = sub.add_parser("verify", help="Verify SQLite integrity and source artifact projections")
    command.add_argument("--database", required=True)
    command.set_defaults(func=cmd_verify)

    command = sub.add_parser("rebuild", help="Atomically rebuild a ledger from explicit artifact directories")
    command.add_argument("directories", nargs="+")
    command.add_argument("--database", required=True)
    command.add_argument(
        "--defect-registry",
        action="append",
        default=[],
        help="Canonical Defect Registry JSON to project after Run imports; repeatable",
    )
    command.set_defaults(func=cmd_rebuild)

    command = sub.add_parser("show-run", help="Show one logical Run and its indexed artifacts")
    command.add_argument("run_id")
    command.add_argument("--database", required=True)
    command.set_defaults(func=cmd_show_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

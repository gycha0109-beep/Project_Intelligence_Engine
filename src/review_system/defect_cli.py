from __future__ import annotations

import argparse
import json
import sys

from .defects import (
    ARTIFACT_RELATIONS,
    DEFECT_STATUSES,
    MATCH_METHODS,
    create_defect,
    initialize_defect_registry,
    link_defect_artifact,
    link_finding,
    list_defects,
    show_defect,
    sync_defect_registry,
    transition_defect,
    verify_defect_registry,
)


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _error(exc: Exception) -> int:
    print(f"ERROR {exc}", file=sys.stderr)
    return 2


def cmd_init(args: argparse.Namespace) -> int:
    try:
        path = initialize_defect_registry(args.registry, args.project_id)
    except Exception as exc:
        return _error(exc)
    _print({"initialized": True, "registry": str(path), "project_id": args.project_id})
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    try:
        result = create_defect(
            args.registry,
            args.database,
            signature=args.signature,
            title=args.title,
            category=args.category,
            actor=args.actor,
            root_cause=args.root_cause,
            owner=args.owner,
            reason=args.reason,
            occurred_at=args.occurred_at,
        )
    except Exception as exc:
        return _error(exc)
    _print(result)
    return 0


def cmd_link_finding(args: argparse.Namespace) -> int:
    try:
        result = link_finding(
            args.registry,
            args.database,
            finding_id=args.finding_id,
            defect_id=args.defect_id,
            match_method=args.match_method,
            confidence=args.confidence,
            approved_by=args.approved_by,
            occurred_at=args.occurred_at,
        )
    except Exception as exc:
        return _error(exc)
    _print(result)
    return 0


def cmd_link_artifact(args: argparse.Namespace) -> int:
    try:
        result = link_defect_artifact(
            args.registry,
            args.database,
            defect_id=args.defect_id,
            artifact_id=args.artifact_id,
            relation=args.relation,
            linked_by=args.linked_by,
            note=args.note,
            occurred_at=args.occurred_at,
        )
    except Exception as exc:
        return _error(exc)
    _print(result)
    return 0


def cmd_transition(args: argparse.Namespace) -> int:
    try:
        result = transition_defect(
            args.registry,
            args.database,
            defect_id=args.defect_id,
            target_status=args.status,
            actor=args.actor,
            reason=args.reason,
            resolution=args.resolution,
            occurred_at=args.occurred_at,
        )
    except Exception as exc:
        return _error(exc)
    _print(result)
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    try:
        result = sync_defect_registry(args.database, args.registry)
    except Exception as exc:
        return _error(exc)
    _print(result)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        result = verify_defect_registry(args.database, args.registry)
    except Exception as exc:
        return _error(exc)
    _print(result)
    return 0 if result["valid"] else 4


def cmd_show(args: argparse.Namespace) -> int:
    try:
        result = show_defect(args.database, args.defect_id)
    except Exception as exc:
        return _error(exc)
    if result is None:
        print(f"ERROR Defect not found: {args.defect_id}", file=sys.stderr)
        return 4
    _print(result)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    try:
        result = list_defects(args.database, project_id=args.project_id, status=args.status)
    except Exception as exc:
        return _error(exc)
    _print(result)
    return 0


def _registry_database(command: argparse.ArgumentParser) -> None:
    command.add_argument("--registry", required=True)
    command.add_argument("--database", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-defect",
        description="File-authoritative Defect Registry with SQLite projection",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("init", help="Initialize a canonical Defect Registry JSON file")
    command.add_argument("--registry", required=True)
    command.add_argument("--project-id", required=True)
    command.set_defaults(func=cmd_init)

    command = sub.add_parser("create", help="Create an OBSERVED Defect")
    _registry_database(command)
    command.add_argument("--signature", required=True)
    command.add_argument("--title", required=True)
    command.add_argument("--category", required=True)
    command.add_argument("--actor", required=True)
    command.add_argument("--root-cause")
    command.add_argument("--owner")
    command.add_argument("--reason", default="Defect registered")
    command.add_argument("--occurred-at")
    command.set_defaults(func=cmd_create)

    command = sub.add_parser("link-finding", help="Explicitly link one Run-local Finding")
    _registry_database(command)
    command.add_argument("--finding-id", required=True)
    command.add_argument("--defect-id", required=True)
    command.add_argument("--match-method", choices=sorted(MATCH_METHODS), required=True)
    command.add_argument("--confidence", type=float, required=True)
    command.add_argument("--approved-by", required=True)
    command.add_argument("--occurred-at")
    command.set_defaults(func=cmd_link_finding)

    command = sub.add_parser("link-artifact", help="Attach evidence or remediation Artifact metadata")
    _registry_database(command)
    command.add_argument("--defect-id", required=True)
    command.add_argument("--artifact-id", required=True)
    command.add_argument("--relation", choices=sorted(ARTIFACT_RELATIONS), required=True)
    command.add_argument("--linked-by", required=True)
    command.add_argument("--note")
    command.add_argument("--occurred-at")
    command.set_defaults(func=cmd_link_artifact)

    command = sub.add_parser("transition", help="Apply one allowed Defect lifecycle transition")
    _registry_database(command)
    command.add_argument("--defect-id", required=True)
    command.add_argument("--status", choices=DEFECT_STATUSES, required=True)
    command.add_argument("--actor", required=True)
    command.add_argument("--reason", required=True)
    command.add_argument("--resolution")
    command.add_argument("--occurred-at")
    command.set_defaults(func=cmd_transition)

    command = sub.add_parser("sync", help="Project the canonical Registry into the Ledger")
    _registry_database(command)
    command.set_defaults(func=cmd_sync)

    command = sub.add_parser("verify", help="Compare Registry JSON with its Ledger projection")
    _registry_database(command)
    command.set_defaults(func=cmd_verify)

    command = sub.add_parser("show", help="Show one Defect with linked Findings, Events, and Artifacts")
    command.add_argument("defect_id")
    command.add_argument("--database", required=True)
    command.set_defaults(func=cmd_show)

    command = sub.add_parser("list", help="List Defects")
    command.add_argument("--database", required=True)
    command.add_argument("--project-id")
    command.add_argument("--status", choices=DEFECT_STATUSES)
    command.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

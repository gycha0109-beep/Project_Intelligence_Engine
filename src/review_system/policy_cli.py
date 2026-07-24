from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .policy_registry import (
    PolicyRegistryError,
    approve_policy,
    build_policy,
    compare_policies,
    list_policies,
    materialize_active_policy,
    retire_policy,
    show_policy,
    verify_policy_registry_file,
)


def _error(exc: Exception) -> int:
    print(f"ERROR {exc}", file=sys.stderr)
    return 2


def cmd_build(args: argparse.Namespace) -> int:
    try:
        policy = build_policy(
            args.registry,
            project_id=args.project_id,
            version=args.version,
            rules=args.rules,
            evaluation_report=args.evaluation_report,
            created_by=args.created_by,
            created_at=args.created_at,
            parent_policy_id=args.parent_policy_id,
        )
    except Exception as exc:
        return _error(exc)
    print(json.dumps(policy, indent=2, ensure_ascii=False))
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    try:
        policy = approve_policy(
            args.registry,
            args.policy_id,
            approved_by=args.approved_by,
            approved_at=args.approved_at,
            effective_at=args.effective_at,
            rationale=args.rationale,
            materialized_rules=args.materialized_rules,
        )
    except Exception as exc:
        return _error(exc)
    print(json.dumps(policy, indent=2, ensure_ascii=False))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    try:
        comparison = compare_policies(args.registry, args.left_policy_id, args.right_policy_id)
    except Exception as exc:
        return _error(exc)
    print(json.dumps(comparison, indent=2, ensure_ascii=False))
    return 0


def cmd_retire(args: argparse.Namespace) -> int:
    try:
        policy = retire_policy(
            args.registry,
            args.policy_id,
            retired_by=args.retired_by,
            retired_at=args.retired_at,
            reason=args.reason,
            materialized_rules=args.materialized_rules,
        )
    except Exception as exc:
        return _error(exc)
    print(json.dumps(policy, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    errors = verify_policy_registry_file(
        args.registry,
        materialized_rules=args.materialized_rules,
        verify_evaluation_reports=not args.skip_evaluation_reports,
    )
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 4
    print(f"VALID Policy Registry: {args.registry}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    try:
        policies = list_policies(args.registry)
    except Exception as exc:
        return _error(exc)
    print(json.dumps({"policies": policies}, indent=2, ensure_ascii=False))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    try:
        policy = show_policy(args.registry, args.policy_id)
    except Exception as exc:
        return _error(exc)
    print(json.dumps(policy, indent=2, ensure_ascii=False))
    return 0


def cmd_materialize(args: argparse.Namespace) -> int:
    try:
        target = materialize_active_policy(args.registry, args.output)
    except Exception as exc:
        return _error(exc)
    print(target)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PIE versioned Policy Registry")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("build", help="Build a DRAFT Policy snapshot")
    command.add_argument("--registry", required=True)
    command.add_argument("--project-id", required=True)
    command.add_argument("--version", required=True)
    command.add_argument("--rules", required=True)
    command.add_argument("--evaluation-report", required=True)
    command.add_argument("--created-by", required=True)
    command.add_argument("--created-at")
    command.add_argument("--parent-policy-id")
    command.set_defaults(func=cmd_build)

    command = sub.add_parser("approve", help="Approve and activate a DRAFT Policy")
    command.add_argument("--registry", required=True)
    command.add_argument("--policy-id", required=True)
    command.add_argument("--approved-by", required=True)
    command.add_argument("--approved-at")
    command.add_argument("--effective-at")
    command.add_argument("--rationale")
    command.add_argument("--materialized-rules", required=True)
    command.set_defaults(func=cmd_approve)

    command = sub.add_parser("compare", help="Compare two Policy snapshots")
    command.add_argument("--registry", required=True)
    command.add_argument("--left-policy-id", required=True)
    command.add_argument("--right-policy-id", required=True)
    command.set_defaults(func=cmd_compare)

    command = sub.add_parser("retire", help="Retire an ACTIVE or SUPERSEDED Policy")
    command.add_argument("--registry", required=True)
    command.add_argument("--policy-id", required=True)
    command.add_argument("--retired-by", required=True)
    command.add_argument("--retired-at")
    command.add_argument("--reason", required=True)
    command.add_argument("--materialized-rules")
    command.set_defaults(func=cmd_retire)

    command = sub.add_parser("verify", help="Verify Registry, Policy, evaluation, and materialized view integrity")
    command.add_argument("--registry", required=True)
    command.add_argument("--materialized-rules")
    command.add_argument("--skip-evaluation-reports", action="store_true")
    command.set_defaults(func=cmd_verify)

    command = sub.add_parser("list", help="List Policy summaries")
    command.add_argument("--registry", required=True)
    command.set_defaults(func=cmd_list)

    command = sub.add_parser("show", help="Show one Policy snapshot")
    command.add_argument("--registry", required=True)
    command.add_argument("--policy-id", required=True)
    command.set_defaults(func=cmd_show)

    command = sub.add_parser("materialize", help="Write active Policy rules to approved-rules.yml")
    command.add_argument("--registry", required=True)
    command.add_argument("--output", required=True)
    command.set_defaults(func=cmd_materialize)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PolicyRegistryError as exc:
        return _error(exc)


if __name__ == "__main__":
    raise SystemExit(main())

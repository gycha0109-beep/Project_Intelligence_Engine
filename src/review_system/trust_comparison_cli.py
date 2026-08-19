from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .trust_comparison import (
    TrustComparisonError,
    TrustComparisonVerificationError,
    capture_assessment,
    load_registry,
    new_registry,
    record_decision,
    record_outcome,
    sample_audit,
    verify_registry_data,
    write_registry,
)


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def _load_or_new(path: str, project_id: str | None = None) -> dict:
    target = Path(path)
    if target.exists():
        _, registry = load_registry(target)
        if project_id is not None and registry["project_id"] != project_id:
            raise TrustComparisonError(
                f"registry project_id mismatch: expected={project_id} actual={registry['project_id']}"
            )
        return registry
    if project_id is None:
        raise TrustComparisonError("project_id is required when creating a new registry")
    return new_registry(project_id)


def cmd_init(args: argparse.Namespace) -> int:
    registry = new_registry(args.project_id, created_at=args.created_at)
    output = write_registry(args.registry, registry)
    _print_json({"valid": True, "registry": str(output), "registry_id": registry["registry_id"]})
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    from .trust import load_trust_report

    registry = _load_or_new(args.registry, args.project_id)
    _, report = load_trust_report(args.trust_report)
    updated = capture_assessment(registry, args.trust_report, captured_at=args.captured_at)
    output = write_registry(args.registry, updated)
    assessment = next(
        item for item in updated["assessments"] if item["trust_report_id"] == report["report_id"]
    )
    _print_json({"valid": True, "registry": str(output), "assessment_id": assessment["assessment_id"], "assessment_count": len(updated["assessments"])})
    return 0


def cmd_decision(args: argparse.Namespace) -> int:
    _, registry = load_registry(args.registry)
    updated = record_decision(
        registry,
        assessment_id=args.assessment_id,
        review_level=args.review_level,
        decision=args.decision,
        actor=args.actor,
        occurred_at=args.occurred_at,
        confirmed_risk_band=args.confirmed_risk_band,
        reason_codes=args.reason,
    )
    output = write_registry(args.registry, updated)
    event = updated["events"][-1]
    _print_json({"valid": True, "registry": str(output), "event_id": event["event_id"], "event_type": event["event_type"], "review_level": event["payload"]["review_level"]})
    return 0


def cmd_outcome(args: argparse.Namespace) -> int:
    _, registry = load_registry(args.registry)
    updated = record_outcome(
        registry,
        assessment_id=args.assessment_id,
        outcome_type=args.outcome_type,
        verdict=args.verdict,
        actor=args.actor,
        occurred_at=args.occurred_at,
        defect_id=args.defect_id,
        evidence_refs=args.evidence_ref,
    )
    output = write_registry(args.registry, updated)
    event = updated["events"][-1]
    _print_json({"valid": True, "registry": str(output), "event_id": event["event_id"], "event_type": event["event_type"], "confirmed_status": next(item["confirmed_status"] for item in updated["comparisons"] if item["assessment_id"] == args.assessment_id)})
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    _, registry = load_registry(args.registry)
    result = sample_audit(registry, count=args.count, seed=args.seed, bands=args.band or ["R0", "R1"])
    if args.output:
        target = Path(args.output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _print_json(result)
    return 0


def cmd_metrics(args: argparse.Namespace) -> int:
    _, registry = load_registry(args.registry)
    _print_json({"valid": True, "registry_id": registry["registry_id"], "registry_sha256": registry["registry_sha256"], "metrics": registry["metrics"]})
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    source, registry = load_registry(args.registry)
    errors = verify_registry_data(registry)
    _print_json({"valid": not errors, "registry": str(source), "registry_id": registry["registry_id"], "registry_sha256": registry["registry_sha256"], "errors": errors})
    return 0 if not errors else 4


def add_comparison_subparsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser("init-comparison-registry")
    command.add_argument("--registry", required=True)
    command.add_argument("--project-id", required=True)
    command.add_argument("--created-at")
    command.set_defaults(func=cmd_init)

    command = sub.add_parser("capture-assessment")
    command.add_argument("--registry", required=True)
    command.add_argument("--project-id")
    command.add_argument("--trust-report", required=True)
    command.add_argument("--captured-at")
    command.set_defaults(func=cmd_capture)

    command = sub.add_parser("record-decision")
    command.add_argument("--registry", required=True)
    command.add_argument("--assessment-id", required=True)
    command.add_argument("--review-level", choices=["WORKFLOW_ACCEPTED", "REVIEWED", "AUDITED"], required=True)
    command.add_argument("--decision", choices=["APPROVE", "REQUEST_CHANGES", "HOLD", "REJECT", "RECLASSIFY"], required=True)
    command.add_argument("--confirmed-risk-band", choices=["R0", "R1", "R2", "R3", "R4"])
    command.add_argument("--reason", action="append", default=[])
    command.add_argument("--actor", required=True)
    command.add_argument("--occurred-at")
    command.set_defaults(func=cmd_decision)

    command = sub.add_parser("record-outcome")
    command.add_argument("--registry", required=True)
    command.add_argument("--assessment-id", required=True)
    command.add_argument("--outcome-type", choices=["INDEPENDENT_AUDIT", "PRODUCTION_DEFECT", "REGRESSION", "SECURITY_INCIDENT", "CONTROLLED_EVALUATION", "FALSE_POSITIVE_REVIEW"], required=True)
    command.add_argument("--verdict", choices=["SAFE", "UNSAFE", "INCONCLUSIVE"], required=True)
    command.add_argument("--actor", required=True)
    command.add_argument("--occurred-at")
    command.add_argument("--defect-id")
    command.add_argument("--evidence-ref", action="append", default=[])
    command.set_defaults(func=cmd_outcome)

    command = sub.add_parser("sample-audit")
    command.add_argument("--registry", required=True)
    command.add_argument("--count", type=int, required=True)
    command.add_argument("--seed", required=True)
    command.add_argument("--band", action="append")
    command.add_argument("--output")
    command.set_defaults(func=cmd_sample)

    command = sub.add_parser("comparison-metrics")
    command.add_argument("--registry", required=True)
    command.set_defaults(func=cmd_metrics)

    command = sub.add_parser("verify-comparison-registry")
    command.add_argument("--registry", required=True)
    command.set_defaults(func=cmd_verify)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pie-trust-comparison", description="Record human decisions and confirmed outcomes without authorizing automation.")
    sub = parser.add_subparsers(dest="command", required=True)
    add_comparison_subparsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except TrustComparisonVerificationError as exc:
        _print_json({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (TrustComparisonError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

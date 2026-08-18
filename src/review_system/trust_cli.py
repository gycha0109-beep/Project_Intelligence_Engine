from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .trust import (
    TrustError,
    TrustVerificationError,
    assess_trust,
    load_trust_report,
    verify_trust_report_sources,
    write_trust_report,
)
from .trust_audit import TrustAuditError, TrustAuditVerificationError
from .trust_audit_cli import add_audit_subparsers
from .trust_comparison import TrustComparisonError, TrustComparisonVerificationError
from .trust_comparison_cli import add_comparison_subparsers
from .trust_evidence_acquisition import EvidenceAcquisitionError, EvidenceAcquisitionVerificationError
from .trust_evidence_acquisition_cli import add_evidence_acquisition_subparsers
from .trust_observation import TrustObservationError, TrustObservationVerificationError
from .trust_observation_cli import add_observation_subparsers
from .trust_pilot_evidence_run import PilotEvidenceRunError, PilotEvidenceRunVerificationError
from .trust_pilot_evidence_run_cli import add_pilot_evidence_run_subparsers
from .trust_pilot_review import PilotSafetyReviewError, PilotSafetyReviewVerificationError
from .trust_pilot_review_cli import add_pilot_review_subparsers
from .trust_reconciliation import TrustReconciliationError, TrustReconciliationVerificationError
from .trust_reconciliation_cli import add_reconciliation_subparsers


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def _add_sources(parser: argparse.ArgumentParser, *, required_core: bool) -> None:
    parser.add_argument("--request", required=required_core)
    parser.add_argument("--profile", required=required_core)
    parser.add_argument("--ledger")
    parser.add_argument("--policy-registry")
    parser.add_argument("--evaluation-report")
    parser.add_argument("--reground-report")
    parser.add_argument("--reground-observations")


def cmd_assess(args: argparse.Namespace) -> int:
    report = assess_trust(
        args.request,
        args.profile,
        ledger=args.ledger,
        policy_registry=args.policy_registry,
        evaluation_report=args.evaluation_report,
        reground_report=args.reground_report,
        reground_observations=args.reground_observations,
        generated_at=args.generated_at,
    )
    output = write_trust_report(args.output, report)
    _print_json({
        "valid": True,
        "output": str(output),
        "report_id": report["report_id"],
        "mode": report["mode"],
        "risk_band": report["risk"]["effective_band"],
        "readiness": report["readiness"]["status"],
        "next_step": report["readiness"]["next_step"],
        "automation_authorized": report["automation_authorized"],
        "triggered_hard_gates": report["task_advisory"]["triggered_hard_gates"],
    })
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    source, report = load_trust_report(args.report)
    replay_requested = any(value is not None for value in (
        args.request,
        args.profile,
        args.ledger,
        args.policy_registry,
        args.evaluation_report,
        args.reground_report,
        args.reground_observations,
    ))
    if replay_requested:
        if args.request is None or args.profile is None:
            raise TrustError("source replay requires both --request and --profile")
        errors = verify_trust_report_sources(
            report,
            request=args.request,
            profile=args.profile,
            ledger=args.ledger,
            policy_registry=args.policy_registry,
            evaluation_report=args.evaluation_report,
            reground_report=args.reground_report,
            reground_observations=args.reground_observations,
        )
        if errors:
            raise TrustVerificationError(errors)
    _print_json({
        "valid": True,
        "report": str(source),
        "report_id": report["report_id"],
        "risk_band": report["risk"]["effective_band"],
        "readiness": report["readiness"]["status"],
        "automation_authorized": report["automation_authorized"],
        "source_replayed": replay_requested,
        "errors": [],
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust",
        description="Generate report-only Trust evidence, comparison outcomes, audit authority, observation readiness, source reconciliation, R0 pilot safety review, pilot eligibility evidence-run, and runtime evidence acquisition reports.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("assess", help="Generate a report-only Trust readiness report.")
    _add_sources(command, required_core=True)
    command.add_argument("--output", required=True)
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_assess)

    command = sub.add_parser("verify-report", help="Verify a Trust readiness report and optional sources.")
    command.add_argument("--report", required=True)
    _add_sources(command, required_core=False)
    command.set_defaults(func=cmd_validate)

    add_comparison_subparsers(sub)
    add_audit_subparsers(sub)
    add_observation_subparsers(sub)
    add_reconciliation_subparsers(sub)
    add_pilot_review_subparsers(sub)
    add_pilot_evidence_run_subparsers(sub)
    add_evidence_acquisition_subparsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except (
        TrustVerificationError,
        TrustAuditVerificationError,
        TrustComparisonVerificationError,
        TrustObservationVerificationError,
        TrustReconciliationVerificationError,
        PilotSafetyReviewVerificationError,
        PilotEvidenceRunVerificationError,
        EvidenceAcquisitionVerificationError,
    ) as exc:
        _print_json({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (
        TrustError,
        TrustAuditError,
        TrustComparisonError,
        TrustObservationError,
        TrustReconciliationError,
        PilotSafetyReviewError,
        PilotEvidenceRunError,
        EvidenceAcquisitionError,
        OSError,
        ValueError,
    ) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

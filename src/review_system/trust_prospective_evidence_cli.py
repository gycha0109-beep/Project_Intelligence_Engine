from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .github_connector import GitHubCLI, GitHubCLIError
from .github_prospective_capture import (
    GitHubProspectiveCaptureError,
    GitHubProspectiveCaptureVerificationError,
    load_github_prospective_capture_candidate,
    materialize_github_prospective_capture,
)
from .trust_comparison import TrustComparisonError
from .trust_prospective_evidence import (
    ProspectiveEvidenceError,
    ProspectiveEvidenceVerificationError,
    campaign_progress,
    intake_prospective_case,
    record_case_outcome,
    record_case_review,
    snapshot_campaign,
    write_campaign_report,
)


def _print(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def cmd_intake(args: argparse.Namespace) -> int:
    result = intake_prospective_case(
        args.workspace,
        trust_report=args.trust_report,
        request=args.request,
        profile=args.profile,
        ledger=args.ledger,
        policy_registry=args.policy_registry,
        evaluation_report=args.evaluation_report,
        reground_report=args.reground_report,
        reground_observations=args.reground_observations,
        captured_at=args.captured_at,
    )
    _print({"valid": True, **result})
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    result = record_case_review(
        args.workspace,
        assessment_id=args.assessment_id,
        review_level=args.review_level,
        decision=args.decision,
        actor=args.actor,
        occurred_at=args.occurred_at,
        confirmed_risk_band=args.confirmed_risk_band,
        reason_codes=args.reason,
    )
    _print({"valid": True, **result})
    return 0


def cmd_outcome(args: argparse.Namespace) -> int:
    result = record_case_outcome(
        args.workspace,
        assessment_id=args.assessment_id,
        outcome_type=args.outcome_type,
        verdict=args.verdict,
        actor=args.actor,
        occurred_at=args.occurred_at,
        defect_id=args.defect_id,
        evidence_refs=args.evidence_ref,
        defect_registry=args.defect_registry,
        ledger=args.ledger,
        evaluation_report=args.evaluation_report,
        audit_artifact=args.audit_artifact,
        audit_authority_registry=args.audit_authority_registry,
    )
    _print({"valid": True, **result})
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    report = campaign_progress(args.workspace, generated_at=args.generated_at)
    if args.output:
        write_campaign_report(args.output, report)
    _print(report)
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    result = snapshot_campaign(args.workspace, args.snapshots_root, generated_at=args.generated_at)
    _print({"valid": True, **result})
    return 0


def cmd_verify_github_capture(args: argparse.Namespace) -> int:
    source, candidate = load_github_prospective_capture_candidate(args.candidate)
    _print({
        "valid": True,
        "candidate": str(source),
        "candidate_id": candidate["candidate_id"],
        "status": candidate["status"],
        "next_step": candidate["next_step"],
        "blockers": candidate["blockers"],
        "automation_authorized": False,
        "pilot_authorized": False,
    })
    return 0


def cmd_materialize_github_capture(args: argparse.Namespace) -> int:
    result = materialize_github_prospective_capture(
        args.candidate,
        request=args.request,
        workspace=args.workspace,
        profile=args.profile,
        repository_root=args.repository_root,
        github_cli=GitHubCLI(executable=args.gh_executable, timeout_seconds=args.timeout),
        repository=args.repo,
        ledger=args.ledger,
        policy_registry=args.policy_registry,
        evaluation_report=args.evaluation_report,
        reground_report=args.reground_report,
        reground_observations=args.reground_observations,
        trust_report_output=args.trust_report_output,
        generated_at=args.generated_at,
        captured_at=args.captured_at,
    )
    _print({"valid": True, **result})
    return 0


def _add_optional_trust_sources(command: argparse.ArgumentParser) -> None:
    command.add_argument("--ledger")
    command.add_argument("--policy-registry")
    command.add_argument("--evaluation-report")
    command.add_argument("--reground-report")
    command.add_argument("--reground-observations")


def add_prospective_subparsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser("intake-prospective-case")
    command.add_argument("--workspace", required=True)
    command.add_argument("--trust-report", required=True)
    command.add_argument("--request", required=True)
    command.add_argument("--profile", required=True)
    _add_optional_trust_sources(command)
    command.add_argument("--captured-at")
    command.set_defaults(func=cmd_intake)

    command = sub.add_parser("record-prospective-review")
    command.add_argument("--workspace", required=True)
    command.add_argument("--assessment-id", required=True)
    command.add_argument("--review-level", choices=["REVIEWED", "AUDITED"], required=True)
    command.add_argument("--decision", choices=["APPROVE", "REQUEST_CHANGES", "HOLD", "REJECT", "RECLASSIFY"], required=True)
    command.add_argument("--confirmed-risk-band", choices=["R0", "R1", "R2", "R3", "R4"])
    command.add_argument("--reason", action="append", default=[])
    command.add_argument("--actor", required=True)
    command.add_argument("--occurred-at")
    command.set_defaults(func=cmd_review)

    command = sub.add_parser("record-prospective-outcome")
    command.add_argument("--workspace", required=True)
    command.add_argument("--assessment-id", required=True)
    command.add_argument("--outcome-type", choices=["PRODUCTION_DEFECT", "CONTROLLED_EVALUATION", "INDEPENDENT_AUDIT"], required=True)
    command.add_argument("--verdict", choices=["SAFE", "UNSAFE", "INCONCLUSIVE"], required=True)
    command.add_argument("--actor", required=True)
    command.add_argument("--occurred-at")
    command.add_argument("--defect-id")
    command.add_argument("--evidence-ref", action="append", default=[])
    command.add_argument("--defect-registry")
    command.add_argument("--ledger")
    command.add_argument("--evaluation-report")
    command.add_argument("--audit-artifact")
    command.add_argument("--audit-authority-registry")
    command.set_defaults(func=cmd_outcome)

    command = sub.add_parser("prospective-campaign-progress")
    command.add_argument("--workspace", required=True)
    command.add_argument("--generated-at")
    command.add_argument("--output")
    command.set_defaults(func=cmd_progress)

    command = sub.add_parser("snapshot-prospective-campaign")
    command.add_argument("--workspace", required=True)
    command.add_argument("--snapshots-root", required=True)
    command.add_argument("--generated-at")
    command.set_defaults(func=cmd_snapshot)

    command = sub.add_parser("verify-github-prospective-capture")
    command.add_argument("--candidate", required=True)
    command.set_defaults(func=cmd_verify_github_capture)

    command = sub.add_parser("materialize-github-prospective-capture")
    command.add_argument("--candidate", required=True)
    command.add_argument("--request", required=True)
    command.add_argument("--workspace", required=True)
    command.add_argument("--profile", required=True)
    command.add_argument("--repository-root", required=True)
    command.add_argument("--repo")
    _add_optional_trust_sources(command)
    command.add_argument("--trust-report-output")
    command.add_argument("--generated-at")
    command.add_argument("--captured-at")
    command.add_argument("--timeout", type=int, default=120)
    command.add_argument("--gh-executable", help=argparse.SUPPRESS)
    command.set_defaults(func=cmd_materialize_github_capture)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pie-trust-prospective", description="Collect prospective Trust evidence without inferring human review or automation authority.")
    sub = parser.add_subparsers(dest="command", required=True)
    add_prospective_subparsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except (ProspectiveEvidenceVerificationError, GitHubProspectiveCaptureVerificationError) as exc:
        _print({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (
        ProspectiveEvidenceError,
        GitHubProspectiveCaptureError,
        GitHubCLIError,
        TrustComparisonError,
        OSError,
        ValueError,
    ) as exc:
        _print({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys

from .application import EvaluatePolicyRequest, evaluate_policy
from .evaluation import (
    EvaluationGateError,
    attach_evaluation_to_candidate,
    load_evaluation_dataset,
    verify_evaluation_report_data,
)
from .io import load_data


def _error(exc: Exception) -> int:
    print(f"ERROR {exc}", file=sys.stderr)
    return 2


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_validate_dataset(args: argparse.Namespace) -> int:
    try:
        source, data = load_evaluation_dataset(args.dataset)
    except Exception as exc:
        return _error(exc)
    split_counts = {
        split: sum(1 for case in data["cases"] if case["split"] == split)
        for split in ("development", "validation", "holdout")
    }
    _print(
        {
            "valid": True,
            "dataset": str(source),
            "dataset_id": data["dataset_id"],
            "case_count": len(data["cases"]),
            "split_counts": split_counts,
        }
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        result = evaluate_policy(
            EvaluatePolicyRequest(
                dataset=args.dataset,
                baseline_policy=args.baseline_policy,
                challenger_policy=args.challenger_policy,
                output=args.output,
                min_precision=args.min_precision,
                min_recall=args.min_recall,
                max_protected_negative_regressions=args.max_protected_negative_regressions,
                repeatability_runs=args.repeatability_runs,
            )
        )
    except Exception as exc:
        return _error(exc)
    _print(
        {
            "evaluation_id": result.report["evaluation_id"],
            "decision": result.report["gate"]["decision"],
            "report_sha256": result.report["report_sha256"],
            "output": str(result.output_path),
        }
    )
    return 0 if result.report["gate"]["decision"] == "PASS" else 3


def cmd_verify_report(args: argparse.Namespace) -> int:
    try:
        data = load_data(args.report)
    except Exception as exc:
        return _error(exc)
    errors = verify_evaluation_report_data(data)
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 4
    decision = data["gate"]["decision"]
    _print(
        {
            "valid": True,
            "evaluation_id": data["evaluation_id"],
            "decision": decision,
            "report_sha256": data["report_sha256"],
        }
    )
    return 0 if decision == "PASS" else 3


def cmd_attach(args: argparse.Namespace) -> int:
    try:
        reference = attach_evaluation_to_candidate(
            args.candidates,
            args.rule_id,
            args.report,
        )
    except EvaluationGateError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        return _error(exc)
    _print({"attached": True, "rule_id": args.rule_id, "evaluation": reference})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-eval",
        description="Deterministic baseline/challenger evaluation for PIE approved Rules",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser(
        "validate-dataset",
        help="Validate an Evaluation Lab dataset and local artifacts",
    )
    command.add_argument("dataset")
    command.set_defaults(func=cmd_validate_dataset)

    command = sub.add_parser(
        "run",
        help="Run baseline and challenger policies on one dataset",
    )
    command.add_argument("dataset")
    command.add_argument("--baseline-policy", required=True)
    command.add_argument("--challenger-policy", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--min-precision", type=float, default=0.0)
    command.add_argument("--min-recall", type=float, default=0.0)
    command.add_argument("--max-protected-negative-regressions", type=int, default=0)
    command.add_argument("--repeatability-runs", type=int, default=2)
    command.set_defaults(func=cmd_run)

    command = sub.add_parser(
        "verify-report",
        help="Verify report and outcome hashes and recomputed metrics",
    )
    command.add_argument("report")
    command.set_defaults(func=cmd_verify_report)

    command = sub.add_parser(
        "attach",
        help="Attach a PASS evaluation report to a candidate Rule",
    )
    command.add_argument("report")
    command.add_argument("--candidates", required=True)
    command.add_argument("--rule-id", required=True)
    command.set_defaults(func=cmd_attach)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

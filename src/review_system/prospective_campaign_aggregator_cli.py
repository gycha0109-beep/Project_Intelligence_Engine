from __future__ import annotations

import argparse
import json
import sys

from .prospective_campaign_aggregator import (
    ProspectiveCampaignAggregationError,
    aggregate_prospective_artifacts,
    write_aggregation_report,
)


def cmd_aggregate_prospective_artifacts(args: argparse.Namespace) -> int:
    try:
        report = aggregate_prospective_artifacts(args.artifact_root)
        if args.output:
            write_aggregation_report(args.output, report)
    except ProspectiveCampaignAggregationError as exc:
        print(
            json.dumps({"valid": False, "error_code": exc.code, "error": str(exc)}, indent=2, ensure_ascii=False),
            file=sys.stderr,
        )
        return 4
    print(json.dumps({"valid": True, **report}, indent=2, ensure_ascii=False))
    return 0


def add_prospective_campaign_aggregator_subparser(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser(
        "aggregate-prospective-artifacts",
        help="Verify and deduplicate replayable prospective PR evidence artifacts without mutating a campaign workspace.",
    )
    command.add_argument(
        "--artifact-root",
        action="append",
        required=True,
        help="Extracted Actions artifact root containing bundle/manifest.json, or a direct evidence bundle root.",
    )
    command.add_argument("--output")
    command.set_defaults(func=cmd_aggregate_prospective_artifacts)

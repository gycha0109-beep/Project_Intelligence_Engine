from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust-campaign-aggregate",
        description="Verify and deduplicate replayable prospective PR evidence artifacts without mutating campaign authority.",
    )
    parser.add_argument(
        "--artifact-root",
        action="append",
        required=True,
        help="Extracted Actions artifact root containing bundle/manifest.json, or a direct evidence bundle root.",
    )
    parser.add_argument("--output")
    parser.set_defaults(func=cmd_aggregate_prospective_artifacts)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

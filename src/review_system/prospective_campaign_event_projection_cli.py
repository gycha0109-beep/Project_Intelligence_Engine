from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .prospective_campaign_event_projection import (
    ProspectiveCampaignEventProjectionError,
    project_governed_campaign_events,
    write_event_projection_report,
)


def cmd_project(args: argparse.Namespace) -> int:
    try:
        report = project_governed_campaign_events(
            args.workspace,
            source_workspace=args.source_workspace,
            declarations=args.declaration or (),
            generated_at=args.generated_at,
        )
        if args.output:
            write_event_projection_report(args.output, report)
    except ProspectiveCampaignEventProjectionError as exc:
        print(
            json.dumps(
                {"valid": False, "error_code": exc.code, "error": str(exc)},
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    except Exception as exc:
        print(
            json.dumps(
                {"valid": False, "error_code": "PROJECTION_FAILED", "error": str(exc)},
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    print(json.dumps({"valid": True, **report}, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust-campaign-events",
        description=(
            "Replay governed REVIEWED/AUDITED decisions and explicit AUTO-3 declaration-bound Outcomes "
            "from an exact project-local campaign lineage."
        ),
    )
    parser.add_argument("--workspace", required=True, help="Destination project-local prospective campaign workspace.")
    parser.add_argument("--source-workspace", required=True, help="Governed source campaign snapshot with exact event lineage.")
    parser.add_argument(
        "--declaration",
        action="append",
        default=[],
        help="AUTO-3A explicit Outcome declaration. Repeat once for every source Outcome event.",
    )
    parser.add_argument("--generated-at")
    parser.add_argument("--output")
    parser.set_defaults(func=cmd_project)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

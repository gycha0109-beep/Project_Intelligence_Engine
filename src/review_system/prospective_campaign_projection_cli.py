from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .prospective_campaign_projection import (
    ProspectiveCampaignProjectionError,
    project_auto2_artifacts_to_campaign,
    write_projection_report,
)


def cmd_project(args: argparse.Namespace) -> int:
    try:
        report = project_auto2_artifacts_to_campaign(
            args.workspace,
            args.artifact_root,
            generated_at=args.generated_at,
        )
        if args.output:
            write_projection_report(args.output, report)
    except ProspectiveCampaignProjectionError as exc:
        print(
            json.dumps({"valid": False, "error_code": exc.code, "error": str(exc)}, indent=2, ensure_ascii=False),
            file=sys.stderr,
        )
        return 4
    print(json.dumps({"valid": True, **report}, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust-campaign-project",
        description="Replay verified AUTO-2 bridge artifacts into one project-local prospective campaign workspace.",
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--artifact-root", action="append", required=True)
    parser.add_argument("--generated-at")
    parser.add_argument("--output")
    parser.set_defaults(func=cmd_project)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

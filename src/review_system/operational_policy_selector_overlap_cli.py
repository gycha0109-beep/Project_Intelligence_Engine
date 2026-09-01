from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .operational_policy import OperationalPolicyError, load_operational_policy
from .operational_policy_selector_overlap import (
    OperationalPolicySelectorOverlapError,
    diagnose_operational_policy_selector_overlaps,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose statically provable operational-policy selector overlaps without "
            "selecting a class, inferring policy intent, or mutating policy."
        )
    )
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _source, policy = load_operational_policy(args.policy)
        diagnostic = diagnose_operational_policy_selector_overlaps(policy)
        rendered = json.dumps(diagnostic, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.output:
            target = Path(args.output).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
    except (OperationalPolicyError, OperationalPolicySelectorOverlapError, OSError) as exc:
        print(f"operational policy selector overlap diagnostic failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

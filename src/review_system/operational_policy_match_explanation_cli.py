from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .operational_policy import OperationalPolicyError, load_operational_policy
from .operational_policy_match_explanation import (
    OperationalPolicyMatchExplanationError,
    explain_operational_policy_matches,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Explain how concrete changed files match operational policy classes without "
            "selecting or resolving an operational class."
        )
    )
    parser.add_argument("--policy", required=True)
    parser.add_argument("--changed-file", action="append", required=True)
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _source, policy = load_operational_policy(args.policy)
        explanation = explain_operational_policy_matches(policy, args.changed_file)
        rendered = json.dumps(explanation, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.output:
            target = Path(args.output).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
    except (OperationalPolicyError, OperationalPolicyMatchExplanationError, OSError) as exc:
        print(f"operational policy match explanation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

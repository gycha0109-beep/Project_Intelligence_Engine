from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .calibration_policy_match_explanation import (
    CalibrationPolicyMatchExplanationError,
    build_calibration_policy_match_explanation_sidecar,
    write_calibration_policy_match_explanation_sidecar,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize the aggregate calibration policy-match explanation sidecar "
            "only when the source L3 explanation exists."
        )
    )
    parser.add_argument("--result", required=True)
    parser.add_argument("--calibration-root", required=True)
    parser.add_argument("--workspace", required=True)
    return parser


def _inside(path: Path, root: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CalibrationPolicyMatchExplanationError(
            f"{label} escaped its trusted root"
        ) from exc
    return resolved


def materialize(
    *,
    result_path: str | Path,
    calibration_root: str | Path,
    workspace: str | Path,
) -> Path | None:
    workspace_root = Path(workspace).expanduser().resolve()
    result_file = Path(result_path).expanduser().resolve()
    result = json.loads(result_file.read_text(encoding="utf-8"))
    bundle_raw = result.get("bundle")
    if not isinstance(bundle_raw, str) or not bundle_raw.strip():
        raise CalibrationPolicyMatchExplanationError("result.bundle must be a non-empty path")
    bundle = _inside(Path(bundle_raw), workspace_root, label="result bundle")

    source_path = bundle / "operational" / "policy-match-explanation.json"
    if not source_path.is_file():
        return None

    calibration_dir = Path(calibration_root).expanduser().resolve()
    calibration_path = calibration_dir / "calibration.json"
    if not calibration_path.is_file():
        raise CalibrationPolicyMatchExplanationError(
            "calibration.json is required before policy-match sidecar materialization"
        )
    calibration_record = json.loads(calibration_path.read_text(encoding="utf-8"))
    source_explanation = json.loads(source_path.read_text(encoding="utf-8"))
    sidecar = build_calibration_policy_match_explanation_sidecar(
        calibration_record=calibration_record,
        policy_match_explanation=source_explanation,
    )
    path = write_calibration_policy_match_explanation_sidecar(calibration_dir, sidecar)
    print(
        "PIE_CALIBRATION_POLICY_MATCH_EXPLANATION_V1 "
        + json.dumps(sidecar, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return path


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        materialize(
            result_path=args.result,
            calibration_root=args.calibration_root,
            workspace=args.workspace,
        )
    except (CalibrationPolicyMatchExplanationError, OSError, json.JSONDecodeError) as exc:
        print(f"calibration policy-match materialization failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

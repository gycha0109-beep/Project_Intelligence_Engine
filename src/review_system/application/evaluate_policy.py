from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..evaluation import run_evaluation, write_evaluation_report


@dataclass(frozen=True)
class EvaluatePolicyRequest:
    dataset: str | Path
    baseline_policy: str | Path
    challenger_policy: str | Path
    output: str | Path
    min_precision: float = 1.0
    min_recall: float = 1.0
    max_protected_negative_regressions: int = 0
    repeatability_runs: int = 2


@dataclass(frozen=True)
class EvaluatePolicyResult:
    report: dict[str, Any]
    output_path: Path


def evaluate_policy(request: EvaluatePolicyRequest) -> EvaluatePolicyResult:
    report = run_evaluation(
        request.dataset,
        request.baseline_policy,
        request.challenger_policy,
        min_precision=request.min_precision,
        min_recall=request.min_recall,
        max_protected_negative_regressions=request.max_protected_negative_regressions,
        repeatability_runs=request.repeatability_runs,
    )
    output_path = write_evaluation_report(request.output, report)
    return EvaluatePolicyResult(report=report, output_path=output_path)

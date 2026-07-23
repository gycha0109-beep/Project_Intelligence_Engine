from dataclasses import dataclass
from pathlib import Path

from ..gate import calculate_gate_from_run
from ..io import dump_json, load_data
from ..paths import asset
from ..validate import validate_review_run_file


class ReviewRunValidationError(ValueError):
    def __init__(self, errors: list[str] | tuple[str, ...]):
        self.errors = tuple(errors)
        super().__init__("invalid review run")


@dataclass(frozen=True)
class CalculateGateRequest:
    run: str | Path
    policy: str | Path | None = None
    output: str | Path | None = None
    trust_metrics: bool = False


@dataclass(frozen=True)
class CalculateGateResult:
    gate: dict
    output_path: Path | None


def calculate_review_gate(request: CalculateGateRequest) -> CalculateGateResult:
    run, errors = validate_review_run_file(request.run)
    if errors:
        raise ReviewRunValidationError(errors)

    policy_path = request.policy or asset("core/default-gate-policy.yml")
    policy = load_data(policy_path)
    result = calculate_gate_from_run(
        run,
        policy,
        trust_metrics=request.trust_metrics,
    )

    output_path = Path(request.output) if request.output else None
    if output_path is not None:
        dump_json(output_path, result)

    return CalculateGateResult(gate=result, output_path=output_path)

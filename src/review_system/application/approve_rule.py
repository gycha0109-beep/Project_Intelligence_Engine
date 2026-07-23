from dataclasses import dataclass
from pathlib import Path

from ..intelligence_config import load_rules
from ..intelligence_learning import approve_candidate_rule
from ..io import dump_yaml_pair_atomic


@dataclass(frozen=True)
class ApproveRuleRequest:
    candidates: str | Path
    approved: str | Path
    rule_id: str
    approved_by: str
    approved_at: str | None = None
    rationale: str | None = None


@dataclass(frozen=True)
class ApproveRuleResult:
    rule_id: str
    candidates_path: Path
    approved_path: Path
    candidates: dict
    approved: dict


def approve_rule(request: ApproveRuleRequest) -> ApproveRuleResult:
    candidates_path = Path(request.candidates)
    approved_path = Path(request.approved)
    candidates = load_rules(candidates_path)
    approved = load_rules(approved_path, required_status="approved")
    updated_candidates, updated_approved = approve_candidate_rule(
        candidates,
        approved,
        request.rule_id,
        approved_by=request.approved_by,
        approved_at=request.approved_at,
        rationale=request.rationale,
    )
    dump_yaml_pair_atomic(
        approved_path,
        updated_approved,
        candidates_path,
        updated_candidates,
    )
    return ApproveRuleResult(
        rule_id=request.rule_id,
        candidates_path=candidates_path,
        approved_path=approved_path,
        candidates=updated_candidates,
        approved=updated_approved,
    )

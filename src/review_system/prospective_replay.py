from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .identity import canonical_json_sha256


REPLAY_SCHEMA_VERSION = "PIE_PROSPECTIVE_DETERMINISTIC_RESULT_V1"
_CANDIDATE_TRANSIENT_KEYS = {
    "generated_at",
    "source_evidence_sha256",
    "evidence_snapshot_sha256",
    "report_sha256",
}
_SUMMARY_RESULT_KEYS = (
    "status",
    "next_step",
    "candidate_id",
    "assessment_id",
    "packet_id",
    "risk_band",
    "readiness",
    "auto_capture",
    "auto_analysis",
    "auto_trust_assessment",
    "auto_packet_prepare",
    "human_review_recorded",
    "outcome_recorded",
    "automation_authorized",
    "pilot_authorized",
)


def _without_keys(value: Mapping[str, Any], keys: set[str]) -> dict[str, Any]:
    output = deepcopy(dict(value))
    for key in keys:
        output.pop(key, None)
    return output


def stable_candidate_projection(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return _without_keys(candidate, _CANDIDATE_TRANSIENT_KEYS)


def stable_impact_projection(impact: Mapping[str, Any]) -> dict[str, Any]:
    return _without_keys(impact, {"source_evidence_sha256"})


def stable_workflow_semantics_projection(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return _without_keys(value, {"source_evidence_sha256", "evidence_sha256"})


def build_deterministic_result(
    *,
    identity: Mapping[str, Any],
    summary: Mapping[str, Any],
    base_revision: str | None,
    changed_files: list[str] | tuple[str, ...],
    diff_sha256: str | None,
    impact: Mapping[str, Any],
    candidate: Mapping[str, Any],
    workflow_semantics: Mapping[str, Any] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "execution_identity": deepcopy(dict(identity)),
        "result": {key: deepcopy(summary.get(key)) for key in _SUMMARY_RESULT_KEYS},
        "source": {
            "repository": summary["repository"],
            "pull_request": summary["pull_request"],
            "base_revision": base_revision,
            "source_revision": summary["source_revision"],
            "pie_revision": summary["pie_revision"],
            "changed_files": sorted(set(changed_files)),
            "diff_sha256": diff_sha256,
        },
        "analysis": stable_impact_projection(impact),
        "workflow_semantics": stable_workflow_semantics_projection(workflow_semantics),
        "prospective_candidate": stable_candidate_projection(candidate),
    }
    output = deepcopy(body)
    output["deterministic_result_sha256"] = canonical_json_sha256(body)
    return output


def verify_deterministic_result(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["deterministic result must be an object"]
    errors: list[str] = []
    if value.get("schema_version") != REPLAY_SCHEMA_VERSION:
        errors.append("deterministic result schema_version mismatch")
    body = deepcopy(value)
    recorded = body.pop("deterministic_result_sha256", None)
    if recorded != canonical_json_sha256(body):
        errors.append("deterministic_result_sha256 mismatch")
    return sorted(set(errors))

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from .identity import canonical_json_sha256
from .io import load_data
from .paths import asset


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_OPERATIONAL_REVIEW_BRIEF_V1"
_HISTORY_REASON = "ORL-7_NOT_IMPLEMENTED"
_AUTHORITY_FIELDS = (
    "human_review_recorded",
    "outcome_recorded",
    "automation_authorized",
    "pilot_authorized",
    "merge_authorized",
    "deploy_authorized",
    "production_effect_authorized",
)


class OperationalReviewBriefError(RuntimeError):
    pass


class OperationalReviewBriefVerificationError(OperationalReviewBriefError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid operational review brief: " + "; ".join(self.errors))


def _schema() -> dict[str, Any]:
    value = load_data(asset("schemas/operational-review-brief.schema.json"))
    if not isinstance(value, dict):
        raise OperationalReviewBriefError("operational review brief schema must contain an object")
    return value


def _schema_errors(value: Any) -> list[str]:
    validator = Draft202012Validator(_schema())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _sorted_strings(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    return sorted({value for value in values if isinstance(value, str) and value})


def _dependent_paths(impact: Mapping[str, Any]) -> list[str]:
    section = impact.get("impact", {})
    if not isinstance(section, Mapping):
        return []
    values = section.get("dependent_files", [])
    if not isinstance(values, list):
        return []
    return sorted({
        item["path"]
        for item in values
        if isinstance(item, Mapping) and isinstance(item.get("path"), str) and item["path"]
    })


def _assert_source_closure(
    *,
    summary: Mapping[str, Any],
    candidate: Mapping[str, Any],
    operational_binding: Mapping[str, Any] | None,
    review_packet: Mapping[str, Any] | None,
) -> None:
    repository = candidate.get("repository", {})
    pull_request = candidate.get("pull_request", {})
    if not isinstance(repository, Mapping) or not isinstance(pull_request, Mapping):
        raise OperationalReviewBriefError("candidate repository and pull_request bindings are required")
    repo_name = repository.get("name_with_owner")
    hostname = repository.get("hostname")
    pr_number = pull_request.get("number")
    base_oid = pull_request.get("base_oid")
    head_oid = pull_request.get("head_oid")
    changed_files = _sorted_strings(candidate.get("changed_files", []))

    if summary.get("repository") != (repo_name.lower() if isinstance(repo_name, str) else repo_name):
        raise OperationalReviewBriefError("summary repository does not match candidate repository")
    if summary.get("pull_request") != pr_number:
        raise OperationalReviewBriefError("summary pull_request does not match candidate")
    if summary.get("source_revision") != head_oid:
        raise OperationalReviewBriefError("summary source_revision does not match candidate PR head")
    if summary.get("candidate_id") != candidate.get("candidate_id"):
        raise OperationalReviewBriefError("summary candidate_id does not match candidate")

    if operational_binding is not None:
        binding_repo = operational_binding.get("repository", {})
        binding_pr = operational_binding.get("pull_request", {})
        if operational_binding.get("project_id") != candidate.get("project_id"):
            raise OperationalReviewBriefError("operational binding project_id does not match candidate")
        if operational_binding.get("candidate_id") != candidate.get("candidate_id"):
            raise OperationalReviewBriefError("operational binding candidate_id does not match candidate")
        if operational_binding.get("source_revision") != f"git:{head_oid}":
            raise OperationalReviewBriefError("operational binding source_revision does not match candidate PR head")
        if not isinstance(binding_repo, Mapping) or (
            str(binding_repo.get("hostname", "")).lower() != str(hostname or "").lower()
            or str(binding_repo.get("name_with_owner", "")).lower() != str(repo_name or "").lower()
        ):
            raise OperationalReviewBriefError("operational binding repository does not match candidate")
        if not isinstance(binding_pr, Mapping) or (
            binding_pr.get("number") != pr_number
            or binding_pr.get("base_oid") != base_oid
            or binding_pr.get("head_oid") != head_oid
        ):
            raise OperationalReviewBriefError("operational binding PR identity does not match candidate")
        if _sorted_strings(operational_binding.get("changed_files", [])) != changed_files:
            raise OperationalReviewBriefError("operational binding changed_files do not match candidate")

    if review_packet is None:
        if summary.get("status") != "WAITING_FOR_TRUST_INPUT":
            raise OperationalReviewBriefError("review packet is required for READY_FOR_HUMAN_REVIEW")
        return

    github = review_packet.get("github", {})
    if summary.get("status") != "READY_FOR_HUMAN_REVIEW":
        raise OperationalReviewBriefError("review packet cannot be projected while pipeline is waiting")
    if review_packet.get("project_id") != candidate.get("project_id"):
        raise OperationalReviewBriefError("review packet project_id does not match candidate")
    if review_packet.get("source_revision") != f"git:{head_oid}":
        raise OperationalReviewBriefError("review packet source_revision does not match candidate PR head")
    if review_packet.get("task_id") != candidate.get("task_id"):
        raise OperationalReviewBriefError("review packet task_id does not match candidate")
    if review_packet.get("assessment_id") != summary.get("assessment_id"):
        raise OperationalReviewBriefError("review packet assessment_id does not match run summary")
    if review_packet.get("packet_id") != summary.get("packet_id"):
        raise OperationalReviewBriefError("review packet packet_id does not match run summary")
    if isinstance(summary.get("risk_band"), str) and review_packet.get("predicted_risk_band") != summary.get("risk_band"):
        raise OperationalReviewBriefError("review packet predicted risk does not match run summary")
    if not isinstance(github, Mapping) or (
        github.get("candidate_id") != candidate.get("candidate_id")
        or str(github.get("hostname", "")).lower() != str(hostname or "").lower()
        or str(github.get("repository", "")).lower() != str(repo_name or "").lower()
        or github.get("pr_number") != pr_number
        or github.get("base_oid") != base_oid
        or github.get("head_oid") != head_oid
    ):
        raise OperationalReviewBriefError("review packet GitHub identity does not match candidate")
    if _sorted_strings(review_packet.get("changed_files", [])) != changed_files:
        raise OperationalReviewBriefError("review packet changed_files do not match candidate")


def _policy_projection(binding: Mapping[str, Any] | None) -> dict[str, Any]:
    if binding is None:
        return {
            "enabled": False,
            "binding_status": None,
            "match_status": None,
            "policy_revision": None,
            "policy_blob_sha": None,
            "policy_content_sha256": None,
            "policy_sha256": None,
            "binding_sha256": None,
        }
    policy = binding.get("policy", {})
    if not isinstance(policy, Mapping):
        policy = {}
    return {
        "enabled": True,
        "binding_status": binding.get("status"),
        "match_status": binding.get("match_status"),
        "policy_revision": policy.get("policy_revision"),
        "policy_blob_sha": policy.get("policy_blob_sha"),
        "policy_content_sha256": policy.get("policy_content_sha256"),
        "policy_sha256": policy.get("policy_sha256"),
        "binding_sha256": binding.get("binding_sha256"),
    }


def _requirements_projection(binding: Mapping[str, Any] | None, impact: Mapping[str, Any]) -> dict[str, Any]:
    requirements: Mapping[str, Any] = {}
    selected_class = None
    missing_inputs: list[str] = []
    if binding is not None:
        raw = binding.get("requirements", {})
        requirements = raw if isinstance(raw, Mapping) else {}
        selected_class = binding.get("selected_operational_class")
        missing_inputs = _sorted_strings(binding.get("missing_inputs", []))
    review = impact.get("review", {})
    review = review if isinstance(review, Mapping) else {}
    return {
        "operational_class": selected_class if isinstance(selected_class, str) and selected_class else None,
        "trust_task_class": requirements.get("trust_task_class") if isinstance(requirements.get("trust_task_class"), str) else None,
        "required_scenarios": _sorted_strings(requirements.get("required_scenarios", [])),
        "required_evidence": _sorted_strings(requirements.get("required_evidence", [])),
        "analysis_required_tests": _sorted_strings(review.get("required_tests", [])),
        "missing_inputs": missing_inputs,
    }


def _trust_projection(packet: Mapping[str, Any] | None, binding: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "assessment_id": packet.get("assessment_id") if packet else None,
        "assessment_sha256": packet.get("assessment_sha256") if packet else None,
        "trust_report_id": packet.get("trust_report_id") if packet else None,
        "trust_report_sha256": packet.get("trust_report_sha256") if packet else None,
        "review_packet_id": packet.get("packet_id") if packet else None,
        "review_packet_sha256": packet.get("packet_sha256") if packet else None,
        "operational_policy": _policy_projection(binding),
    }


def _risk_projection(summary: Mapping[str, Any], packet: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "predicted_risk_band": packet.get("predicted_risk_band") if packet else (summary.get("risk_band") if isinstance(summary.get("risk_band"), str) else None),
        "readiness": summary.get("readiness") if isinstance(summary.get("readiness"), str) else None,
        "review_requirement": packet.get("review_requirement") if packet else None,
        "hard_gates": _sorted_strings(packet.get("hard_gates", [])) if packet else [],
    }


def _brief_hash(value: Mapping[str, Any]) -> str:
    body = deepcopy(dict(value))
    body.pop("brief_sha256", None)
    return canonical_json_sha256(body)


def build_operational_review_brief(
    *,
    summary: Mapping[str, Any],
    candidate: Mapping[str, Any],
    candidate_sha256: str,
    impact: Mapping[str, Any],
    operational_binding: Mapping[str, Any] | None = None,
    review_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _assert_source_closure(
        summary=summary,
        candidate=candidate,
        operational_binding=operational_binding,
        review_packet=review_packet,
    )
    repository = candidate["repository"]
    pull_request = candidate["pull_request"]
    direct = impact.get("direct", {})
    direct = direct if isinstance(direct, Mapping) else {}
    review = impact.get("review", {})
    review = review if isinstance(review, Mapping) else {}

    brief: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "status": summary.get("status"),
        "next_step": summary.get("next_step"),
        "source": {
            "project_id": candidate.get("project_id"),
            "repository": {
                "hostname": repository.get("hostname"),
                "name_with_owner": repository.get("name_with_owner"),
            },
            "pull_request": {
                "number": pull_request.get("number"),
                "base_oid": pull_request.get("base_oid"),
                "head_oid": pull_request.get("head_oid"),
            },
            "source_revision": summary.get("source_revision"),
            "pie_revision": summary.get("pie_revision"),
            "candidate_id": candidate.get("candidate_id"),
            "candidate_sha256": candidate_sha256,
        },
        "change": {
            "changed_files": _sorted_strings(candidate.get("changed_files", [])),
            "limitations": _sorted_strings(impact.get("limitations", [])),
        },
        "affected": {
            "components": _sorted_strings(direct.get("components", [])),
            "dependent_files": _dependent_paths(impact),
            "selected_packs": _sorted_strings(review.get("selected_packs", [])),
        },
        "risk": _risk_projection(summary, review_packet),
        "required_verification": _requirements_projection(operational_binding, impact),
        "history": {"available": False, "reason": _HISTORY_REASON, "matches": []},
        "trust": _trust_projection(review_packet, operational_binding),
        "authority": {field: False for field in _AUTHORITY_FIELDS},
        "brief_sha256": "",
    }
    brief["brief_sha256"] = _brief_hash(brief)
    errors = verify_operational_review_brief_data(brief)
    if errors:
        raise OperationalReviewBriefVerificationError(errors)
    return brief


def verify_operational_review_brief_data(value: Any) -> list[str]:
    errors = _schema_errors(value)
    if not isinstance(value, dict):
        return sorted(set(errors or ["brief must contain an object"]))
    source = value.get("source", {})
    pull_request = source.get("pull_request", {}) if isinstance(source, dict) else {}
    trust = value.get("trust", {})
    policy = trust.get("operational_policy", {}) if isinstance(trust, dict) else {}
    authority = value.get("authority", {})
    risk = value.get("risk", {})

    if source.get("source_revision") != pull_request.get("head_oid"):
        errors.append("source.source_revision must equal pull_request.head_oid")
    if value.get("status") == "READY_FOR_HUMAN_REVIEW":
        if not trust.get("assessment_id") or not trust.get("review_packet_id"):
            errors.append("READY_FOR_HUMAN_REVIEW requires exact assessment and review packet bindings")
        if risk.get("review_requirement") is None:
            errors.append("READY_FOR_HUMAN_REVIEW requires review_requirement")
    elif value.get("status") == "WAITING_FOR_TRUST_INPUT":
        for field in ("assessment_id", "assessment_sha256", "trust_report_id", "trust_report_sha256", "review_packet_id", "review_packet_sha256"):
            if trust.get(field) is not None:
                errors.append(f"WAITING_FOR_TRUST_INPUT cannot bind trust.{field}")
        if risk.get("review_requirement") is not None:
            errors.append("WAITING_FOR_TRUST_INPUT cannot claim review_requirement")

    if policy.get("enabled") is False:
        for field in ("binding_status", "match_status", "policy_revision", "policy_blob_sha", "policy_content_sha256", "policy_sha256", "binding_sha256"):
            if policy.get(field) is not None:
                errors.append(f"disabled operational policy cannot bind {field}")
    elif policy.get("enabled") is True:
        expected_revision = pull_request.get("base_oid")
        if policy.get("policy_revision") != (f"git:{expected_revision}" if isinstance(expected_revision, str) else None):
            errors.append("operational policy revision must equal exact PR base revision")
        if not policy.get("binding_sha256"):
            errors.append("enabled operational policy requires binding_sha256")

    for field in _AUTHORITY_FIELDS:
        if authority.get(field) is not False:
            errors.append(f"authority.{field} must remain false")
    if value.get("history") != {"available": False, "reason": _HISTORY_REASON, "matches": []}:
        errors.append("history must remain unavailable until ORL-7")
    if value.get("brief_sha256") != _brief_hash(value):
        errors.append("brief_sha256 mismatch")
    return sorted(set(errors))


def verify_operational_review_brief_sources(
    brief: Mapping[str, Any],
    *,
    summary: Mapping[str, Any],
    candidate: Mapping[str, Any],
    candidate_sha256: str,
    impact: Mapping[str, Any],
    operational_binding: Mapping[str, Any] | None = None,
    review_packet: Mapping[str, Any] | None = None,
) -> list[str]:
    errors = verify_operational_review_brief_data(brief)
    try:
        expected = build_operational_review_brief(
            summary=summary,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
            impact=impact,
            operational_binding=operational_binding,
            review_packet=review_packet,
        )
    except OperationalReviewBriefError as exc:
        return sorted(set([*errors, f"source replay failed: {exc}"]))
    if dict(brief) != expected:
        errors.append("review brief does not exactly replay from bound sources")
    return sorted(set(errors))


def render_operational_review_brief_markdown(brief: Mapping[str, Any]) -> str:
    errors = verify_operational_review_brief_data(brief)
    if errors:
        raise OperationalReviewBriefVerificationError(errors)

    def bullets(values: list[str]) -> str:
        return "\n".join(f"- `{value}`" for value in values) if values else "- none"

    source = brief["source"]
    pr = source["pull_request"]
    risk = brief["risk"]
    verification = brief["required_verification"]
    trust = brief["trust"]
    policy = trust["operational_policy"]
    authority = brief["authority"]
    return f"""# PIE Operational Review Brief

```text
Contract: {CONTRACT_VERSION}
Status: {brief['status']}
Next step: {brief['next_step']}
Brief SHA-256: {brief['brief_sha256']}
```

## CHANGE

Repository: `{source['repository']['name_with_owner']}`  
PR: `#{pr['number']}`  
Base: `{pr['base_oid']}`  
Head: `{pr['head_oid']}`  
PIE revision: `{source['pie_revision']}`  
Candidate: `{source['candidate_id']}`  
Candidate SHA-256: `{source['candidate_sha256']}`

Changed files:

{bullets(brief['change']['changed_files'])}

## AFFECTED

Components:

{bullets(brief['affected']['components'])}

Dependent files:

{bullets(brief['affected']['dependent_files'])}

Selected review packs:

{bullets(brief['affected']['selected_packs'])}

## RISK

```text
Predicted risk band: {risk['predicted_risk_band'] or 'NOT ASSESSED'}
Readiness: {risk['readiness'] or 'NOT ASSESSED'}
Review requirement: {risk['review_requirement'] or 'NOT MATERIALIZED'}
```

Hard gates:

{bullets(risk['hard_gates'])}

## REQUIRED VERIFICATION

```text
Operational class: {verification['operational_class'] or 'NOT BOUND'}
Trust task class: {verification['trust_task_class'] or 'NOT BOUND'}
```

Required scenarios:

{bullets(verification['required_scenarios'])}

Required evidence:

{bullets(verification['required_evidence'])}

Analysis-required tests:

{bullets(verification['analysis_required_tests'])}

Missing inputs:

{bullets(verification['missing_inputs'])}

## HISTORY

```text
Available: NO
Reason: {_HISTORY_REASON}
```

No historical match is projected before ORL-7.

## TRUST

```text
Assessment ID: {trust['assessment_id'] or 'NOT MATERIALIZED'}
Assessment SHA-256: {trust['assessment_sha256'] or 'NOT MATERIALIZED'}
Trust report ID: {trust['trust_report_id'] or 'NOT MATERIALIZED'}
Trust report SHA-256: {trust['trust_report_sha256'] or 'NOT MATERIALIZED'}
Review packet ID: {trust['review_packet_id'] or 'NOT MATERIALIZED'}
Review packet SHA-256: {trust['review_packet_sha256'] or 'NOT MATERIALIZED'}
Operational Policy enabled: {'YES' if policy['enabled'] else 'NO'}
Operational binding status: {policy['binding_status'] or 'NOT BOUND'}
Operational policy revision: {policy['policy_revision'] or 'NOT BOUND'}
Operational policy SHA-256: {policy['policy_sha256'] or 'NOT BOUND'}
```

## AUTHORITY

```text
Human review: {'RECORDED' if authority['human_review_recorded'] else 'NOT RECORDED'}
Outcome: {'RECORDED' if authority['outcome_recorded'] else 'NOT RECORDED'}
Automation authority: {'GRANTED' if authority['automation_authorized'] else 'NOT GRANTED'}
Pilot authority: {'GRANTED' if authority['pilot_authorized'] else 'NOT GRANTED'}
Merge authority: {'GRANTED' if authority['merge_authorized'] else 'NOT GRANTED'}
Deploy authority: {'GRANTED' if authority['deploy_authorized'] else 'NOT GRANTED'}
Production-effect authority: {'GRANTED' if authority['production_effect_authorized'] else 'NOT GRANTED'}
```

This brief is a deterministic project-local projection. It is not a human review decision, Outcome declaration, merge approval, deploy approval, or production authorization.
"""


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise OperationalReviewBriefError(f"review brief output path must not contain symlinks: {target}")
    return target.resolve()


def _atomic_write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def write_operational_review_brief(path: str | Path, brief: Mapping[str, Any]) -> Path:
    errors = verify_operational_review_brief_data(brief)
    if errors:
        raise OperationalReviewBriefVerificationError(errors)
    target = _safe_output(path)
    payload = (json.dumps(dict(brief), indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return _atomic_write(target, payload)


def write_operational_review_brief_markdown(path: str | Path, brief: Mapping[str, Any]) -> Path:
    target = _safe_output(path)
    return _atomic_write(target, render_operational_review_brief_markdown(brief).encode("utf-8"))

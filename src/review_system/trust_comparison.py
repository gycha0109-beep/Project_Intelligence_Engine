from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path
import random
import tempfile
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .paths import asset
from .trust import load_trust_report


SCHEMA_VERSION = "1.0"
BANDS = ("R0", "R1", "R2", "R3", "R4")
BAND_ORDER = {band: index for index, band in enumerate(BANDS)}
REVIEW_LEVELS = {"WORKFLOW_ACCEPTED", "REVIEWED", "AUDITED"}
DECISIONS = {"APPROVE", "REQUEST_CHANGES", "HOLD", "REJECT", "RECLASSIFY"}
OUTCOME_TYPES = {
    "INDEPENDENT_AUDIT",
    "PRODUCTION_DEFECT",
    "REGRESSION",
    "SECURITY_INCIDENT",
    "CONTROLLED_EVALUATION",
    "FALSE_POSITIVE_REVIEW",
}
OUTCOME_VERDICTS = {"SAFE", "UNSAFE", "INCONCLUSIVE"}


class TrustComparisonError(RuntimeError):
    pass


class TrustComparisonVerificationError(TrustComparisonError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid Trust comparison registry: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustComparisonError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustComparisonError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise TrustComparisonError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustComparisonError(f"{field} must be a non-empty string")
    return value.strip()


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_input(path: str | Path, field: str) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise TrustComparisonError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise TrustComparisonError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise TrustComparisonError(f"{field} must be a regular file: {resolved}")
    return resolved


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise TrustComparisonError(f"output path must not contain symlinks: {target}")
    return target.resolve()


def _schema() -> dict[str, Any]:
    path = asset("schemas", "trust-comparison-registry.schema.json")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TrustComparisonError("Trust comparison schema must contain an object")
    return value


def _schema_errors(value: Any) -> list[str]:
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    return sorted(error.message for error in validator.iter_errors(value))


def _registry_payload(registry: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(registry)
    payload.pop("registry_sha256", None)
    return payload


def _assessment_payload(assessment: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(assessment)
    payload.pop("assessment_sha256", None)
    return payload


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(event)
    payload.pop("event_sha256", None)
    return payload


def _registry_id(project_id: str, created_at: str) -> str:
    return f"trust-comparison-{canonical_json_sha256({'project_id': project_id, 'created_at': created_at})[:32]}"


def new_registry(project_id: str, *, created_at: str | None = None) -> dict[str, Any]:
    project = _required_text(project_id, "project_id")
    created = _timestamp(created_at or utc_now(), "created_at")
    registry: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": _registry_id(project, created),
        "project_id": project,
        "created_at": created,
        "assessments": [],
        "events": [],
        "comparisons": [],
        "metrics": {},
        "registry_sha256": "",
    }
    return _finalize(registry)


def _assessment_from_report(report: dict[str, Any], captured_at: str) -> dict[str, Any]:
    if report.get("mode") != "REPORT_ONLY":
        raise TrustComparisonError("Trust report mode must be REPORT_ONLY")
    if report.get("automation_authorized") is not False:
        raise TrustComparisonError("Trust report must not authorize automation")
    if report.get("maximum_automation_band") != "NONE":
        raise TrustComparisonError("Trust report maximum_automation_band must be NONE")
    request = report.get("request")
    advisory = report.get("task_advisory")
    readiness = report.get("readiness")
    if not isinstance(request, dict) or not isinstance(advisory, dict) or not isinstance(readiness, dict):
        raise TrustComparisonError("Trust report projections are incomplete")
    natural_key = {
        "project_id": report.get("project_id"),
        "task_id": request.get("task_id"),
        "source_revision": request.get("source_revision"),
        "trust_report_id": report.get("report_id"),
        "trust_report_sha256": report.get("report_sha256"),
    }
    assessment: dict[str, Any] = {
        "assessment_id": f"assessment-{canonical_json_sha256(natural_key)[:32]}",
        "task_id": _required_text(request.get("task_id"), "Trust report request.task_id"),
        "source_revision": _required_text(request.get("source_revision"), "Trust report request.source_revision"),
        "trust_report_id": _required_text(report.get("report_id"), "Trust report report_id"),
        "trust_report_sha256": _required_text(report.get("report_sha256"), "Trust report report_sha256"),
        "predicted_risk_band": advisory.get("risk_band"),
        "readiness_status": readiness.get("status"),
        "triggered_hard_gates": sorted(set(advisory.get("triggered_hard_gates", []))),
        "captured_at": captured_at,
        "assessment_sha256": "",
    }
    if assessment["predicted_risk_band"] not in BANDS:
        raise TrustComparisonError("Trust report risk band is invalid")
    if assessment["readiness_status"] not in {"NOT_READY", "READY_FOR_HUMAN_COMPARISON"}:
        raise TrustComparisonError("Trust report readiness status is invalid")
    assessment["assessment_sha256"] = canonical_json_sha256(_assessment_payload(assessment))
    return assessment


def capture_assessment(
    registry: dict[str, Any],
    trust_report: str | Path,
    *,
    captured_at: str | None = None,
) -> dict[str, Any]:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    _, report = load_trust_report(_safe_input(trust_report, "Trust report"))
    if report["project_id"] != registry["project_id"]:
        raise TrustComparisonError(
            f"Trust report project_id mismatch: expected={registry['project_id']} actual={report['project_id']}"
        )
    captured = _timestamp(captured_at or utc_now(), "captured_at")
    assessment = _assessment_from_report(report, captured)
    existing = {item["assessment_id"]: item for item in registry["assessments"]}
    previous = existing.get(assessment["assessment_id"])
    if previous is not None:
        stable_previous = deepcopy(previous)
        stable_new = deepcopy(assessment)
        stable_previous.pop("captured_at", None)
        stable_new.pop("captured_at", None)
        stable_previous["assessment_sha256"] = ""
        stable_new["assessment_sha256"] = ""
        if stable_previous != stable_new:
            raise TrustComparisonError("assessment identity collision with different Trust report projection")
        return deepcopy(registry)
    output = deepcopy(registry)
    output["assessments"].append(assessment)
    output["assessments"] = sorted(output["assessments"], key=lambda item: item["assessment_id"])
    return _finalize(output)


def _append_event(
    registry: dict[str, Any],
    *,
    event_type: str,
    assessment_id: str,
    actor: str,
    occurred_at: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    assessments = {item["assessment_id"]: item for item in registry["assessments"]}
    assessment = assessments.get(assessment_id)
    if assessment is None:
        raise TrustComparisonError(f"unknown assessment_id: {assessment_id}")
    when = _timestamp(occurred_at, "occurred_at")
    if when < assessment["captured_at"]:
        raise TrustComparisonError("event occurred_at must not precede assessment captured_at")
    sequence = len(registry["events"]) + 1
    previous = registry["events"][-1]["event_sha256"] if registry["events"] else None
    key = {
        "registry_id": registry["registry_id"],
        "sequence": sequence,
        "event_type": event_type,
        "assessment_id": assessment_id,
        "occurred_at": when,
        "actor": actor,
        "payload": payload,
        "previous_event_sha256": previous,
    }
    event: dict[str, Any] = {
        "sequence": sequence,
        "event_id": f"event-{canonical_json_sha256(key)[:32]}",
        "event_type": event_type,
        "assessment_id": assessment_id,
        "occurred_at": when,
        "actor": _required_text(actor, "actor"),
        "payload": payload,
        "previous_event_sha256": previous,
        "event_sha256": "",
    }
    event["event_sha256"] = canonical_json_sha256(_event_payload(event))
    output = deepcopy(registry)
    output["events"].append(event)
    return _finalize(output)


def record_decision(
    registry: dict[str, Any],
    *,
    assessment_id: str,
    review_level: str,
    decision: str,
    actor: str,
    occurred_at: str | None = None,
    confirmed_risk_band: str | None = None,
    reason_codes: Iterable[str] = (),
) -> dict[str, Any]:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    level = review_level.strip().upper()
    outcome = decision.strip().upper()
    if level not in REVIEW_LEVELS:
        raise TrustComparisonError(f"invalid review_level: {review_level}")
    if outcome not in DECISIONS:
        raise TrustComparisonError(f"invalid decision: {decision}")
    if confirmed_risk_band is not None and confirmed_risk_band not in BANDS:
        raise TrustComparisonError(f"invalid confirmed_risk_band: {confirmed_risk_band}")
    if outcome == "RECLASSIFY" and confirmed_risk_band is None:
        raise TrustComparisonError("RECLASSIFY requires confirmed_risk_band")
    reasons = sorted({_required_text(value, "reason_code") for value in reason_codes})
    payload = {
        "review_level": level,
        "decision": outcome,
        "confirmed_risk_band": confirmed_risk_band,
        "reason_codes": reasons,
    }
    return _append_event(
        registry,
        event_type="HUMAN_DECISION",
        assessment_id=assessment_id,
        actor=actor,
        occurred_at=occurred_at or utc_now(),
        payload=payload,
    )


def record_outcome(
    registry: dict[str, Any],
    *,
    assessment_id: str,
    outcome_type: str,
    verdict: str,
    actor: str,
    occurred_at: str | None = None,
    defect_id: str | None = None,
    evidence_refs: Iterable[str] = (),
) -> dict[str, Any]:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    kind = outcome_type.strip().upper()
    result = verdict.strip().upper()
    if kind not in OUTCOME_TYPES:
        raise TrustComparisonError(f"invalid outcome_type: {outcome_type}")
    if result not in OUTCOME_VERDICTS:
        raise TrustComparisonError(f"invalid verdict: {verdict}")
    actor_value = _required_text(actor, "actor")
    if kind == "INDEPENDENT_AUDIT" and result in {"SAFE", "UNSAFE"}:
        reviewed_actors = {
            event["actor"]
            for event in registry["events"]
            if event["assessment_id"] == assessment_id
            and event["event_type"] == "HUMAN_DECISION"
            and event["payload"].get("review_level") in {"REVIEWED", "AUDITED"}
        }
        if actor_value in reviewed_actors:
            raise TrustComparisonError(
                "INDEPENDENT_AUDIT actor must differ from prior reviewed decision actor"
            )
    payload = {
        "outcome_type": kind,
        "verdict": result,
        "defect_id": _required_text(defect_id, "defect_id") if defect_id is not None else None,
        "evidence_refs": sorted({_required_text(value, "evidence_ref") for value in evidence_refs}),
    }
    return _append_event(
        registry,
        event_type="OUTCOME",
        assessment_id=assessment_id,
        actor=actor_value,
        occurred_at=occurred_at or utc_now(),
        payload=payload,
    )


def _latest_events(registry: dict[str, Any], assessment_id: str, event_type: str) -> list[dict[str, Any]]:
    return [
        event
        for event in registry["events"]
        if event["assessment_id"] == assessment_id and event["event_type"] == event_type
    ]


def _predicted_safe(assessment: dict[str, Any]) -> bool:
    return assessment["predicted_risk_band"] in {"R0", "R1"} and not assessment["triggered_hard_gates"]


def _human_safe(decision: str | None) -> bool | None:
    if decision == "APPROVE":
        return True
    if decision in {"REQUEST_CHANGES", "REJECT"}:
        return False
    return None


def _provisional_status(
    assessment: dict[str, Any],
    decision_event: dict[str, Any] | None,
) -> str:
    if decision_event is None:
        return "UNREVIEWED"
    payload = decision_event["payload"]
    if payload["review_level"] == "WORKFLOW_ACCEPTED":
        return "UNREVIEWED"
    confirmed = payload.get("confirmed_risk_band")
    if confirmed is not None:
        predicted_index = BAND_ORDER[assessment["predicted_risk_band"]]
        confirmed_index = BAND_ORDER[confirmed]
        if predicted_index > confirmed_index:
            return "PROVISIONAL_OVER_ESTIMATE"
        if predicted_index < confirmed_index:
            return "PROVISIONAL_UNDER_ESTIMATE"
    human_safe = _human_safe(payload.get("decision"))
    if human_safe is None:
        return "UNCOMPARABLE"
    if human_safe == _predicted_safe(assessment):
        return "PROVISIONAL_MATCH"
    return "PROVISIONAL_DECISION_MISMATCH"


def _confirmed_status(assessment: dict[str, Any], outcome_event: dict[str, Any] | None) -> str:
    if outcome_event is None:
        return "UNCONFIRMED"
    verdict = outcome_event["payload"].get("verdict")
    if verdict == "INCONCLUSIVE":
        return "CONFIRMED_INCONCLUSIVE"
    predicted_safe = _predicted_safe(assessment)
    actual_safe = verdict == "SAFE"
    if predicted_safe and actual_safe:
        return "CONFIRMED_TRUE_NEGATIVE"
    if predicted_safe and not actual_safe:
        return "CONFIRMED_FALSE_NEGATIVE"
    if not predicted_safe and not actual_safe:
        return "CONFIRMED_TRUE_POSITIVE"
    return "CONFIRMED_FALSE_POSITIVE"


def _comparison_projection(registry: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for assessment in registry["assessments"]:
        decisions = _latest_events(registry, assessment["assessment_id"], "HUMAN_DECISION")
        reviewed = [
            item
            for item in decisions
            if item["payload"].get("review_level") in {"REVIEWED", "AUDITED"}
        ]
        decision_event = reviewed[-1] if reviewed else (decisions[-1] if decisions else None)
        outcomes = _latest_events(registry, assessment["assessment_id"], "OUTCOME")
        conclusive = [item for item in outcomes if item["payload"].get("verdict") in {"SAFE", "UNSAFE"}]
        outcome_event = conclusive[-1] if conclusive else (outcomes[-1] if outcomes else None)
        decision_payload = decision_event["payload"] if decision_event else {}
        outcome_payload = outcome_event["payload"] if outcome_event else {}
        output.append(
            {
                "assessment_id": assessment["assessment_id"],
                "predicted_risk_band": assessment["predicted_risk_band"],
                "predicted_safe_candidate": _predicted_safe(assessment),
                "latest_decision_event_id": decision_event["event_id"] if decision_event else None,
                "review_level": decision_payload.get("review_level"),
                "human_decision": decision_payload.get("decision"),
                "confirmed_risk_band": decision_payload.get("confirmed_risk_band"),
                "latest_outcome_event_id": outcome_event["event_id"] if outcome_event else None,
                "outcome_verdict": outcome_payload.get("verdict"),
                "provisional_status": _provisional_status(assessment, decision_event),
                "confirmed_status": _confirmed_status(assessment, outcome_event),
            }
        )
    return sorted(output, key=lambda item: item["assessment_id"])


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics_projection(registry: dict[str, Any], comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    workflow = sum(1 for item in comparisons if item["review_level"] == "WORKFLOW_ACCEPTED")
    reviewed = sum(1 for item in comparisons if item["review_level"] in {"REVIEWED", "AUDITED"})
    audited = sum(1 for item in comparisons if item["review_level"] == "AUDITED")
    comparable = [
        item
        for item in comparisons
        if item["provisional_status"]
        in {
            "PROVISIONAL_MATCH",
            "PROVISIONAL_OVER_ESTIMATE",
            "PROVISIONAL_UNDER_ESTIMATE",
            "PROVISIONAL_DECISION_MISMATCH",
        }
    ]
    matches = sum(1 for item in comparable if item["provisional_status"] == "PROVISIONAL_MATCH")
    confirmed = [
        item
        for item in comparisons
        if item["confirmed_status"]
        in {
            "CONFIRMED_TRUE_NEGATIVE",
            "CONFIRMED_FALSE_NEGATIVE",
            "CONFIRMED_TRUE_POSITIVE",
            "CONFIRMED_FALSE_POSITIVE",
        }
    ]
    counts = {
        status: sum(1 for item in confirmed if item["confirmed_status"] == status)
        for status in (
            "CONFIRMED_TRUE_NEGATIVE",
            "CONFIRMED_FALSE_NEGATIVE",
            "CONFIRMED_TRUE_POSITIVE",
            "CONFIRMED_FALSE_POSITIVE",
        )
    }
    tn = counts["CONFIRMED_TRUE_NEGATIVE"]
    fn = counts["CONFIRMED_FALSE_NEGATIVE"]
    tp = counts["CONFIRMED_TRUE_POSITIVE"]
    fp = counts["CONFIRMED_FALSE_POSITIVE"]
    by_band = {
        band: {
            "assessments": sum(1 for item in comparisons if item["predicted_risk_band"] == band),
            "confirmed": sum(
                1
                for item in confirmed
                if item["predicted_risk_band"] == band
            ),
            "false_negatives": sum(
                1
                for item in confirmed
                if item["predicted_risk_band"] == band
                and item["confirmed_status"] == "CONFIRMED_FALSE_NEGATIVE"
            ),
        }
        for band in BANDS
    }
    independent_audits = sum(
        1
        for event in registry["events"]
        if event["event_type"] == "OUTCOME"
        and event["payload"].get("outcome_type") == "INDEPENDENT_AUDIT"
        and event["payload"].get("verdict") in {"SAFE", "UNSAFE"}
    )
    return {
        "maturity": {
            "assessment_count": len(comparisons),
            "workflow_accepted_count": workflow,
            "reviewed_count": reviewed,
            "audited_decision_count": audited,
            "conclusive_outcome_count": len(confirmed),
            "outcome_coverage": _ratio(len(confirmed), len(comparisons)),
            "independent_audit_count": independent_audits,
            "confirmed_false_negative_count": fn,
        },
        "reviewer_alignment": {
            "comparable_count": len(comparable),
            "match_count": matches,
            "alignment_rate": _ratio(matches, len(comparable)),
            "over_estimate_count": sum(
                1 for item in comparable if item["provisional_status"] == "PROVISIONAL_OVER_ESTIMATE"
            ),
            "under_estimate_count": sum(
                1 for item in comparable if item["provisional_status"] == "PROVISIONAL_UNDER_ESTIMATE"
            ),
            "decision_mismatch_count": sum(
                1 for item in comparable if item["provisional_status"] == "PROVISIONAL_DECISION_MISMATCH"
            ),
        },
        "confirmed_outcomes": {
            "sample_count": len(confirmed),
            "true_positive": tp,
            "false_positive": fp,
            "true_negative": tn,
            "false_negative": fn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "false_positive_rate": _ratio(fp, fp + tn),
            "false_negative_rate": _ratio(fn, fn + tp),
            "accuracy": _ratio(tp + tn, len(confirmed)),
            "by_predicted_band": by_band,
        },
    }


def _finalize(registry: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(registry)
    output["comparisons"] = _comparison_projection(output)
    output["metrics"] = _metrics_projection(output, output["comparisons"])
    output["registry_sha256"] = canonical_json_sha256(_registry_payload(output))
    errors = verify_registry_data(output, check_schema=True)
    if errors:
        raise TrustComparisonVerificationError(errors)
    return output


def verify_registry_data(registry: Any, *, check_schema: bool = True) -> list[str]:
    errors: list[str] = _schema_errors(registry) if check_schema else []
    if not isinstance(registry, dict):
        return sorted(set(errors or ["registry must contain an object"]))
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    try:
        project_id = _required_text(registry.get("project_id"), "project_id")
        created_at = _timestamp(registry.get("created_at"), "created_at")
    except TrustComparisonError as exc:
        errors.append(str(exc))
        project_id = ""
        created_at = "1970-01-01T00:00:00Z"
    if registry.get("registry_id") != _registry_id(project_id, created_at):
        errors.append("registry_id mismatch")

    assessments_raw = registry.get("assessments")
    assessments = assessments_raw if isinstance(assessments_raw, list) else []
    if not isinstance(assessments_raw, list):
        errors.append("assessments must be an array")
    assessment_ids: set[str] = set()
    normalized_assessments: list[dict[str, Any]] = []
    for index, item in enumerate(assessments):
        if not isinstance(item, dict):
            errors.append(f"assessments[{index}] must be an object")
            continue
        assessment_id = item.get("assessment_id")
        if assessment_id in assessment_ids:
            errors.append(f"duplicate assessment_id: {assessment_id}")
        assessment_ids.add(str(assessment_id))
        expected_hash = canonical_json_sha256(_assessment_payload(item))
        if item.get("assessment_sha256") != expected_hash:
            errors.append(f"assessment {assessment_id} hash mismatch")
        normalized_assessments.append(item)
    if assessments != sorted(normalized_assessments, key=lambda item: item.get("assessment_id", "")):
        errors.append("assessments canonical order mismatch")

    events_raw = registry.get("events")
    events = events_raw if isinstance(events_raw, list) else []
    if not isinstance(events_raw, list):
        errors.append("events must be an array")
    previous: str | None = None
    event_ids: set[str] = set()
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"events[{index}] must be an object")
            continue
        expected_sequence = index + 1
        if event.get("sequence") != expected_sequence:
            errors.append(f"events[{index}].sequence mismatch")
        if event.get("previous_event_sha256") != previous:
            errors.append(f"events[{index}].previous_event_sha256 mismatch")
        event_id = event.get("event_id")
        if event_id in event_ids:
            errors.append(f"duplicate event_id: {event_id}")
        event_ids.add(str(event_id))
        if event.get("assessment_id") not in assessment_ids:
            errors.append(f"events[{index}] references unknown assessment")
        expected_hash = canonical_json_sha256(_event_payload(event))
        if event.get("event_sha256") != expected_hash:
            errors.append(f"events[{index}].event_sha256 mismatch")
        previous = event.get("event_sha256") if isinstance(event.get("event_sha256"), str) else None
        payload = event.get("payload")
        if not isinstance(payload, dict):
            errors.append(f"events[{index}].payload must be an object")
            continue
        if event.get("event_type") == "HUMAN_DECISION":
            if set(payload) != {"review_level", "decision", "confirmed_risk_band", "reason_codes"}:
                errors.append(f"events[{index}] human decision payload fields mismatch")
            if payload.get("review_level") not in REVIEW_LEVELS:
                errors.append(f"events[{index}] invalid review_level")
            if payload.get("decision") not in DECISIONS:
                errors.append(f"events[{index}] invalid decision")
            band = payload.get("confirmed_risk_band")
            if band is not None and band not in BANDS:
                errors.append(f"events[{index}] invalid confirmed_risk_band")
            reasons = payload.get("reason_codes")
            if not isinstance(reasons, list) or reasons != sorted(set(reasons)):
                errors.append(f"events[{index}] reason_codes canonical mismatch")
        elif event.get("event_type") == "OUTCOME":
            if set(payload) != {"outcome_type", "verdict", "defect_id", "evidence_refs"}:
                errors.append(f"events[{index}] outcome payload fields mismatch")
            if payload.get("outcome_type") not in OUTCOME_TYPES:
                errors.append(f"events[{index}] invalid outcome_type")
            if payload.get("verdict") not in OUTCOME_VERDICTS:
                errors.append(f"events[{index}] invalid verdict")
            refs = payload.get("evidence_refs")
            if not isinstance(refs, list) or refs != sorted(set(refs)):
                errors.append(f"events[{index}] evidence_refs canonical mismatch")
        else:
            errors.append(f"events[{index}] invalid event_type")

    expected_comparisons = _comparison_projection({
        **registry,
        "assessments": normalized_assessments,
        "events": events,
    })
    if registry.get("comparisons") != expected_comparisons:
        errors.append("comparisons projection mismatch")
    expected_metrics = _metrics_projection(registry, expected_comparisons)
    if registry.get("metrics") != expected_metrics:
        errors.append("metrics projection mismatch")
    expected_registry_hash = canonical_json_sha256(_registry_payload(registry))
    if registry.get("registry_sha256") != expected_registry_hash:
        errors.append("registry_sha256 mismatch")
    return sorted(set(errors))


def load_registry(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "Trust comparison registry")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrustComparisonError(f"cannot load Trust comparison registry: {exc}") from exc
    errors = verify_registry_data(value)
    if errors:
        raise TrustComparisonVerificationError(errors)
    return source, value


def write_registry(path: str | Path, registry: dict[str, Any]) -> Path:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    target = _safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(registry, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def sample_audit(
    registry: dict[str, Any],
    *,
    count: int,
    seed: str,
    bands: Iterable[str] = ("R0", "R1"),
) -> dict[str, Any]:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    if count < 1:
        raise TrustComparisonError("count must be at least 1")
    selected_bands = tuple(sorted(set(bands), key=lambda band: BAND_ORDER.get(band, 99)))
    if not selected_bands or any(band not in BANDS for band in selected_bands):
        raise TrustComparisonError("bands must contain valid R0-R4 values")
    comparisons = {item["assessment_id"]: item for item in registry["comparisons"]}
    candidates: list[tuple[int, str]] = []
    for assessment in registry["assessments"]:
        comparison = comparisons[assessment["assessment_id"]]
        if assessment["predicted_risk_band"] not in selected_bands:
            continue
        if comparison["confirmed_status"] not in {"UNCONFIRMED", "CONFIRMED_INCONCLUSIVE"}:
            continue
        priority = 4
        if comparison["predicted_safe_candidate"]:
            priority = 0
        if comparison["review_level"] in {None, "WORKFLOW_ACCEPTED"}:
            priority = min(priority, 1)
        confirmed_band = comparison.get("confirmed_risk_band")
        if confirmed_band is not None and BAND_ORDER[confirmed_band] < BAND_ORDER[assessment["predicted_risk_band"]]:
            priority = min(priority, 2)
        candidates.append((priority, assessment["assessment_id"]))
    grouped: dict[int, list[str]] = {}
    for priority, assessment_id in candidates:
        grouped.setdefault(priority, []).append(assessment_id)
    rng = random.Random(canonical_json_sha256({"registry": registry["registry_sha256"], "seed": seed}))
    ordered: list[str] = []
    for priority in sorted(grouped):
        values = sorted(grouped[priority])
        rng.shuffle(values)
        ordered.extend(values)
    chosen = ordered[:count]
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": registry["registry_id"],
        "registry_sha256": registry["registry_sha256"],
        "seed": seed,
        "bands": list(selected_bands),
        "requested_count": count,
        "candidate_count": len(ordered),
        "assessment_ids": chosen,
        "sample_sha256": canonical_json_sha256(
            {
                "registry_id": registry["registry_id"],
                "registry_sha256": registry["registry_sha256"],
                "seed": seed,
                "bands": list(selected_bands),
                "assessment_ids": chosen,
            }
        ),
    }

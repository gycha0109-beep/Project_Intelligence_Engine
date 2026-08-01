from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
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
BAND_ORDER = {value: index for index, value in enumerate(BANDS)}
REVIEW_LEVELS = {"WORKFLOW_ACCEPTED", "REVIEWED", "AUDITED"}
DECISIONS = {"APPROVE", "REQUEST_CHANGES", "HOLD", "REJECT", "RECLASSIFY"}
OUTCOME_TYPES = {
    "INDEPENDENT_AUDIT", "PRODUCTION_DEFECT", "REGRESSION",
    "SECURITY_INCIDENT", "CONTROLLED_EVALUATION", "FALSE_POSITIVE_REVIEW",
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


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustComparisonError(f"{field} must be a non-empty string")
    return value.strip()


def _timestamp(value: str | None, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustComparisonError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise TrustComparisonError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _schema_errors(value: Any) -> list[str]:
    schema_path = asset("schemas/trust-comparison-registry.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(error.message for error in validator.iter_errors(value))


def _without(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(value)
    result.pop(field, None)
    return result


def _registry_id(project_id: str, created_at: str) -> str:
    return f"trust-comparison-{canonical_json_sha256({'project_id': project_id, 'created_at': created_at})[:32]}"


def _assessment_id(project_id: str, item: dict[str, Any]) -> str:
    key = {
        "project_id": project_id,
        "task_id": item.get("task_id"),
        "source_revision": item.get("source_revision"),
        "trust_report_id": item.get("trust_report_id"),
        "trust_report_sha256": item.get("trust_report_sha256"),
    }
    return f"assessment-{canonical_json_sha256(key)[:32]}"


def _event_id(registry_id: str, event: dict[str, Any]) -> str:
    key = {
        "registry_id": registry_id,
        "sequence": event.get("sequence"),
        "event_type": event.get("event_type"),
        "assessment_id": event.get("assessment_id"),
        "occurred_at": event.get("occurred_at"),
        "actor": event.get("actor"),
        "payload": event.get("payload"),
        "previous_event_sha256": event.get("previous_event_sha256"),
    }
    return f"event-{canonical_json_sha256(key)[:32]}"


def _predicted_safe(item: dict[str, Any]) -> bool:
    return item["predicted_risk_band"] in {"R0", "R1"} and not item["triggered_hard_gates"]


def _human_safe(decision: str | None) -> bool | None:
    if decision == "APPROVE":
        return True
    if decision in {"REQUEST_CHANGES", "REJECT"}:
        return False
    return None


def _events(registry: dict[str, Any], assessment_id: str, kind: str) -> list[dict[str, Any]]:
    return [item for item in registry["events"] if item["assessment_id"] == assessment_id and item["event_type"] == kind]


def _provisional(assessment: dict[str, Any], event: dict[str, Any] | None) -> str:
    if event is None or event["payload"]["review_level"] == "WORKFLOW_ACCEPTED":
        return "UNREVIEWED"
    payload = event["payload"]
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
    return "PROVISIONAL_MATCH" if human_safe == _predicted_safe(assessment) else "PROVISIONAL_DECISION_MISMATCH"


def _confirmed(assessment: dict[str, Any], event: dict[str, Any] | None) -> str:
    if event is None:
        return "UNCONFIRMED"
    verdict = event["payload"].get("verdict")
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


def _comparisons(registry: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for assessment in registry["assessments"]:
        decisions = _events(registry, assessment["assessment_id"], "HUMAN_DECISION")
        reviewed = [item for item in decisions if item["payload"].get("review_level") in {"REVIEWED", "AUDITED"}]
        decision = reviewed[-1] if reviewed else (decisions[-1] if decisions else None)
        outcomes = _events(registry, assessment["assessment_id"], "OUTCOME")
        conclusive = [item for item in outcomes if item["payload"].get("verdict") in {"SAFE", "UNSAFE"}]
        outcome = conclusive[-1] if conclusive else (outcomes[-1] if outcomes else None)
        decision_payload = decision["payload"] if decision else {}
        outcome_payload = outcome["payload"] if outcome else {}
        output.append({
            "assessment_id": assessment["assessment_id"],
            "predicted_risk_band": assessment["predicted_risk_band"],
            "predicted_safe_candidate": _predicted_safe(assessment),
            "latest_decision_event_id": decision["event_id"] if decision else None,
            "review_level": decision_payload.get("review_level"),
            "human_decision": decision_payload.get("decision"),
            "confirmed_risk_band": decision_payload.get("confirmed_risk_band"),
            "latest_outcome_event_id": outcome["event_id"] if outcome else None,
            "outcome_verdict": outcome_payload.get("verdict"),
            "provisional_status": _provisional(assessment, decision),
            "confirmed_status": _confirmed(assessment, outcome),
        })
    return sorted(output, key=lambda item: item["assessment_id"])


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics(registry: dict[str, Any], comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    comparable_states = {"PROVISIONAL_MATCH", "PROVISIONAL_OVER_ESTIMATE", "PROVISIONAL_UNDER_ESTIMATE", "PROVISIONAL_DECISION_MISMATCH"}
    comparable = [item for item in comparisons if item["provisional_status"] in comparable_states]
    confirmed_states = {"CONFIRMED_TRUE_NEGATIVE", "CONFIRMED_FALSE_NEGATIVE", "CONFIRMED_TRUE_POSITIVE", "CONFIRMED_FALSE_POSITIVE"}
    confirmed = [item for item in comparisons if item["confirmed_status"] in confirmed_states]
    count = lambda status: sum(1 for item in confirmed if item["confirmed_status"] == status)
    tn, fn, tp, fp = count("CONFIRMED_TRUE_NEGATIVE"), count("CONFIRMED_FALSE_NEGATIVE"), count("CONFIRMED_TRUE_POSITIVE"), count("CONFIRMED_FALSE_POSITIVE")
    return {
        "maturity": {
            "assessment_count": len(comparisons),
            "workflow_accepted_count": sum(1 for item in comparisons if item["review_level"] == "WORKFLOW_ACCEPTED"),
            "reviewed_count": sum(1 for item in comparisons if item["review_level"] in {"REVIEWED", "AUDITED"}),
            "audited_decision_count": sum(1 for item in comparisons if item["review_level"] == "AUDITED"),
            "conclusive_outcome_count": len(confirmed),
            "outcome_coverage": _ratio(len(confirmed), len(comparisons)),
            "independent_audit_count": sum(1 for event in registry["events"] if event["event_type"] == "OUTCOME" and event["payload"].get("outcome_type") == "INDEPENDENT_AUDIT" and event["payload"].get("verdict") in {"SAFE", "UNSAFE"}),
            "confirmed_false_negative_count": fn,
        },
        "reviewer_alignment": {
            "comparable_count": len(comparable),
            "match_count": sum(1 for item in comparable if item["provisional_status"] == "PROVISIONAL_MATCH"),
            "alignment_rate": _ratio(sum(1 for item in comparable if item["provisional_status"] == "PROVISIONAL_MATCH"), len(comparable)),
            "over_estimate_count": sum(1 for item in comparable if item["provisional_status"] == "PROVISIONAL_OVER_ESTIMATE"),
            "under_estimate_count": sum(1 for item in comparable if item["provisional_status"] == "PROVISIONAL_UNDER_ESTIMATE"),
            "decision_mismatch_count": sum(1 for item in comparable if item["provisional_status"] == "PROVISIONAL_DECISION_MISMATCH"),
        },
        "confirmed_outcomes": {
            "sample_count": len(confirmed), "true_positive": tp, "false_positive": fp,
            "true_negative": tn, "false_negative": fn,
            "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn),
            "false_positive_rate": _ratio(fp, fp + tn), "false_negative_rate": _ratio(fn, fn + tp),
            "accuracy": _ratio(tp + tn, len(confirmed)),
            "by_predicted_band": {band: {
                "assessments": sum(1 for item in comparisons if item["predicted_risk_band"] == band),
                "confirmed": sum(1 for item in confirmed if item["predicted_risk_band"] == band),
                "false_negatives": sum(1 for item in confirmed if item["predicted_risk_band"] == band and item["confirmed_status"] == "CONFIRMED_FALSE_NEGATIVE"),
            } for band in BANDS},
        },
    }


def _finalize(registry: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(registry)
    output["comparisons"] = _comparisons(output)
    output["metrics"] = _metrics(output, output["comparisons"])
    output["registry_sha256"] = canonical_json_sha256(_without(output, "registry_sha256"))
    errors = verify_registry_data(output)
    if errors:
        raise TrustComparisonVerificationError(errors)
    return output


def new_registry(project_id: str, *, created_at: str | None = None) -> dict[str, Any]:
    project = _text(project_id, "project_id")
    created = _timestamp(created_at or utc_now(), "created_at")
    return _finalize({
        "schema_version": SCHEMA_VERSION, "registry_id": _registry_id(project, created),
        "project_id": project, "created_at": created, "assessments": [], "events": [],
        "comparisons": [], "metrics": {}, "registry_sha256": "",
    })


def _assessment_from_report(report: dict[str, Any], captured_at: str) -> dict[str, Any]:
    if report.get("mode") != "REPORT_ONLY" or report.get("automation_authorized") is not False or report.get("maximum_automation_band") != "NONE":
        raise TrustComparisonError("Trust report must remain REPORT_ONLY with automation prohibited")
    request, risk, advisory, readiness = report.get("request"), report.get("risk"), report.get("task_advisory"), report.get("readiness")
    if not all(isinstance(value, dict) for value in (request, risk, advisory, readiness)):
        raise TrustComparisonError("Trust report projections are incomplete")
    item = {
        "assessment_id": "", "task_id": _text(request.get("task_id"), "request.task_id"),
        "source_revision": _text(request.get("source_revision"), "request.source_revision"),
        "trust_report_id": _text(report.get("report_id"), "report_id"),
        "trust_report_sha256": _text(report.get("report_sha256"), "report_sha256"),
        "predicted_risk_band": risk.get("effective_band"), "readiness_status": readiness.get("status"),
        "triggered_hard_gates": sorted(set(advisory.get("triggered_hard_gates", []))),
        "captured_at": captured_at, "assessment_sha256": "",
    }
    if item["predicted_risk_band"] not in BANDS:
        raise TrustComparisonError("Trust report risk band is invalid")
    if item["readiness_status"] not in {"NOT_READY", "READY_FOR_HUMAN_COMPARISON"}:
        raise TrustComparisonError("Trust report readiness status is invalid")
    item["assessment_id"] = _assessment_id(_text(report.get("project_id"), "project_id"), item)
    item["assessment_sha256"] = canonical_json_sha256(_without(item, "assessment_sha256"))
    return item


def capture_assessment(registry: dict[str, Any], trust_report: str | Path, *, captured_at: str | None = None) -> dict[str, Any]:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    _, report = load_trust_report(_safe_input(trust_report, "Trust report"))
    if report["project_id"] != registry["project_id"]:
        raise TrustComparisonError("Trust report project_id mismatch")
    item = _assessment_from_report(report, _timestamp(captured_at or utc_now(), "captured_at"))
    existing = {value["assessment_id"]: value for value in registry["assessments"]}
    if item["assessment_id"] in existing:
        return deepcopy(registry)
    output = deepcopy(registry)
    output["assessments"].append(item)
    output["assessments"].sort(key=lambda value: value["assessment_id"])
    return _finalize(output)


def _append_event(registry: dict[str, Any], kind: str, assessment_id: str, actor: str, occurred_at: str, payload: dict[str, Any]) -> dict[str, Any]:
    assessments = {item["assessment_id"]: item for item in registry["assessments"]}
    assessment = assessments.get(assessment_id)
    if assessment is None:
        raise TrustComparisonError(f"unknown assessment_id: {assessment_id}")
    when = _timestamp(occurred_at, "occurred_at")
    if when < assessment["captured_at"]:
        raise TrustComparisonError("event occurred_at must not precede assessment captured_at")
    event = {
        "sequence": len(registry["events"]) + 1, "event_id": "", "event_type": kind,
        "assessment_id": assessment_id, "occurred_at": when, "actor": _text(actor, "actor"),
        "payload": payload, "previous_event_sha256": registry["events"][-1]["event_sha256"] if registry["events"] else None,
        "event_sha256": "",
    }
    event["event_id"] = _event_id(registry["registry_id"], event)
    event["event_sha256"] = canonical_json_sha256(_without(event, "event_sha256"))
    output = deepcopy(registry)
    output["events"].append(event)
    return _finalize(output)


def record_decision(registry: dict[str, Any], *, assessment_id: str, review_level: str, decision: str, actor: str, occurred_at: str | None = None, confirmed_risk_band: str | None = None, reason_codes: Iterable[str] = ()) -> dict[str, Any]:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    level, result = review_level.upper(), decision.upper()
    if level not in REVIEW_LEVELS or result not in DECISIONS:
        raise TrustComparisonError("invalid review_level or decision")
    if confirmed_risk_band is not None and confirmed_risk_band not in BANDS:
        raise TrustComparisonError("invalid confirmed_risk_band")
    if result == "RECLASSIFY" and confirmed_risk_band is None:
        raise TrustComparisonError("RECLASSIFY requires confirmed_risk_band")
    payload = {"review_level": level, "decision": result, "confirmed_risk_band": confirmed_risk_band, "reason_codes": sorted({_text(value, "reason_code") for value in reason_codes})}
    return _append_event(registry, "HUMAN_DECISION", assessment_id, actor, occurred_at or utc_now(), payload)


def record_outcome(registry: dict[str, Any], *, assessment_id: str, outcome_type: str, verdict: str, actor: str, occurred_at: str | None = None, defect_id: str | None = None, evidence_refs: Iterable[str] = ()) -> dict[str, Any]:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    kind, result, actor_value = outcome_type.upper(), verdict.upper(), _text(actor, "actor")
    if kind not in OUTCOME_TYPES or result not in OUTCOME_VERDICTS:
        raise TrustComparisonError("invalid outcome_type or verdict")
    prior_conclusive = {event["payload"]["verdict"] for event in _events(registry, assessment_id, "OUTCOME") if event["payload"].get("verdict") in {"SAFE", "UNSAFE"}}
    if result in {"SAFE", "UNSAFE"} and prior_conclusive and result not in prior_conclusive:
        raise TrustComparisonError("conflicting conclusive Outcome requires a future supersession contract")
    if kind == "INDEPENDENT_AUDIT" and result in {"SAFE", "UNSAFE"}:
        reviewers = {event["actor"] for event in _events(registry, assessment_id, "HUMAN_DECISION") if event["payload"].get("review_level") in {"REVIEWED", "AUDITED"}}
        if actor_value in reviewers:
            raise TrustComparisonError("INDEPENDENT_AUDIT actor must differ from prior reviewed decision actor")
    payload = {"outcome_type": kind, "verdict": result, "defect_id": _text(defect_id, "defect_id") if defect_id is not None else None, "evidence_refs": sorted({_text(value, "evidence_ref") for value in evidence_refs})}
    return _append_event(registry, "OUTCOME", assessment_id, actor_value, occurred_at or utc_now(), payload)


def verify_registry_data(registry: Any) -> list[str]:
    errors = _schema_errors(registry)
    if not isinstance(registry, dict):
        return sorted(set(errors or ["registry must contain an object"]))
    try:
        project = _text(registry.get("project_id"), "project_id")
        created = _timestamp(registry.get("created_at"), "created_at")
    except TrustComparisonError as exc:
        errors.append(str(exc)); project = ""; created = "1970-01-01T00:00:00Z"
    if registry.get("registry_id") != _registry_id(project, created):
        errors.append("registry_id mismatch")
    assessment_map: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(registry.get("assessments", [])):
        if not isinstance(item, dict):
            continue
        expected_id = _assessment_id(project, item)
        if item.get("assessment_id") != expected_id:
            errors.append(f"assessments[{index}].assessment_id mismatch")
        if expected_id in assessment_map:
            errors.append(f"duplicate assessment_id: {expected_id}")
        assessment_map[expected_id] = item
        if item.get("assessment_sha256") != canonical_json_sha256(_without(item, "assessment_sha256")):
            errors.append(f"assessment {expected_id} hash mismatch")
    if registry.get("assessments") != sorted(registry.get("assessments", []), key=lambda value: value.get("assessment_id", "")):
        errors.append("assessments canonical order mismatch")
    previous = None
    reviewed_actors: dict[str, set[str]] = {}
    conclusive: dict[str, set[str]] = {}
    for index, event in enumerate(registry.get("events", [])):
        if event.get("sequence") != index + 1:
            errors.append(f"events[{index}].sequence mismatch")
        if event.get("previous_event_sha256") != previous:
            errors.append(f"events[{index}].previous_event_sha256 mismatch")
        if event.get("assessment_id") not in assessment_map:
            errors.append(f"events[{index}] references unknown assessment")
        if event.get("event_id") != _event_id(registry.get("registry_id", ""), event):
            errors.append(f"events[{index}].event_id mismatch")
        expected_hash = canonical_json_sha256(_without(event, "event_sha256"))
        if event.get("event_sha256") != expected_hash:
            errors.append(f"events[{index}].event_sha256 mismatch")
        previous = event.get("event_sha256")
        assessment = assessment_map.get(event.get("assessment_id"))
        try:
            when = _timestamp(event.get("occurred_at"), f"events[{index}].occurred_at")
            if assessment and when < assessment.get("captured_at", ""):
                errors.append(f"events[{index}] precedes assessment capture")
        except TrustComparisonError as exc:
            errors.append(str(exc))
        payload = event.get("payload", {})
        if event.get("event_type") == "HUMAN_DECISION" and payload.get("review_level") in {"REVIEWED", "AUDITED"}:
            reviewed_actors.setdefault(event["assessment_id"], set()).add(event.get("actor"))
        if event.get("event_type") == "OUTCOME" and payload.get("verdict") in {"SAFE", "UNSAFE"}:
            if payload.get("outcome_type") == "INDEPENDENT_AUDIT" and event.get("actor") in reviewed_actors.get(event["assessment_id"], set()):
                errors.append(f"events[{index}] independent audit actor matches reviewer")
            values = conclusive.setdefault(event["assessment_id"], set()); values.add(payload["verdict"])
            if len(values) > 1:
                errors.append(f"events[{index}] conflicts with prior conclusive Outcome")
    expected_comparisons = _comparisons(registry)
    if registry.get("comparisons") != expected_comparisons:
        errors.append("comparisons projection mismatch")
    if registry.get("metrics") != _metrics(registry, expected_comparisons):
        errors.append("metrics projection mismatch")
    if registry.get("registry_sha256") != canonical_json_sha256(_without(registry, "registry_sha256")):
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


def write_json_atomic(path: str | Path, value: Any) -> Path:
    target = _safe_output(path); target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True); raise
    return target


def write_registry(path: str | Path, registry: dict[str, Any]) -> Path:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    return write_json_atomic(path, registry)


def sample_audit(registry: dict[str, Any], *, count: int, seed: str, bands: Iterable[str] = ("R0", "R1")) -> dict[str, Any]:
    errors = verify_registry_data(registry)
    if errors:
        raise TrustComparisonVerificationError(errors)
    if count < 1:
        raise TrustComparisonError("count must be at least 1")
    selected_bands = tuple(sorted(set(bands), key=lambda value: BAND_ORDER.get(value, 99)))
    if not selected_bands or any(value not in BANDS for value in selected_bands):
        raise TrustComparisonError("bands must contain valid R0-R4 values")
    comparisons = {item["assessment_id"]: item for item in registry["comparisons"]}
    candidates = []
    for assessment in registry["assessments"]:
        comparison = comparisons[assessment["assessment_id"]]
        if assessment["predicted_risk_band"] not in selected_bands or comparison["confirmed_status"] not in {"UNCONFIRMED", "CONFIRMED_INCONCLUSIVE"}:
            continue
        priority = 0 if comparison["predicted_safe_candidate"] else 4
        if comparison["review_level"] in {None, "WORKFLOW_ACCEPTED"}:
            priority = min(priority, 1)
        candidates.append((priority, assessment["assessment_id"]))
    grouped: dict[int, list[str]] = {}
    for priority, identifier in candidates:
        grouped.setdefault(priority, []).append(identifier)
    rng = random.Random(canonical_json_sha256({"registry": registry["registry_sha256"], "seed": seed}))
    ordered = []
    for priority in sorted(grouped):
        values = sorted(grouped[priority]); rng.shuffle(values); ordered.extend(values)
    chosen = ordered[:count]
    result = {"schema_version": SCHEMA_VERSION, "registry_id": registry["registry_id"], "registry_sha256": registry["registry_sha256"], "seed": seed, "bands": list(selected_bands), "requested_count": count, "candidate_count": len(ordered), "assessment_ids": chosen}
    result["sample_sha256"] = canonical_json_sha256(result)
    return result

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .identity import canonical_json_sha256


CALIBRATION_RECORD_CONTRACT_VERSION = "PIE_CALIBRATION_RECORD_V1"
CALIBRATION_LEDGER_CONTRACT_VERSION = "PIE_CALIBRATION_LEDGER_V1"
_CALIBRATION_ARTIFACT_PREFIX = "pie-cal-v1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ARTIFACT_TOKEN = re.compile(r"[^A-Z0-9_]+")


class CalibrationObservationError(RuntimeError):
    pass


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibrationObservationError(f"{label} must be an object")
    return value


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CalibrationObservationError(f"{label} must be a positive integer")
    return value


def _sha40(value: Any, *, label: str) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if _SHA40.fullmatch(normalized) is None:
        raise CalibrationObservationError(f"{label} must be an exact 40-character Git SHA")
    return normalized


def _nonempty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationObservationError(f"{label} must be a non-empty string")
    return value.strip()


def _repository(value: Any) -> str:
    repository = _nonempty_string(value, label="repository").lower()
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise CalibrationObservationError("repository must be in owner/name form")
    return repository


def _signal_projection(interface: Mapping[str, Any]) -> dict[str, Any]:
    signal = _mapping(interface.get("signal"), label="interface.signal")
    status = _nonempty_string(signal.get("status"), label="signal.status")
    reason = _nonempty_string(signal.get("reason"), label="signal.reason")
    next_step = _nonempty_string(signal.get("next"), label="signal.next")
    match_status = signal.get("match_status")
    if match_status is not None and (not isinstance(match_status, str) or not match_status.strip()):
        raise CalibrationObservationError("signal.match_status must be null or a non-empty string")
    return {
        "status": status,
        "reason": reason,
        "match_status": match_status.strip() if isinstance(match_status, str) else None,
        "next": next_step,
    }


def _lazy_projection(interface: Mapping[str, Any]) -> dict[str, Any]:
    targeted_ids = interface.get("targeted_evidence_ids")
    if not isinstance(targeted_ids, list) or any(not isinstance(item, str) or not item for item in targeted_ids):
        raise CalibrationObservationError("interface.targeted_evidence_ids must be a string array")
    if len(set(targeted_ids)) != len(targeted_ids):
        raise CalibrationObservationError("interface.targeted_evidence_ids must not contain duplicates")
    return {
        "level1_materialized": isinstance(interface.get("brief"), Mapping),
        "level2_item_count": len(targeted_ids),
        "full_capsule_separate": True,
    }


def build_calibration_record(
    *,
    repository: str,
    pull_request: int,
    source_revision: str,
    pie_revision: str,
    execution_id: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
    interface: Mapping[str, Any],
) -> dict[str, Any]:
    identity = {
        "repository": _repository(repository),
        "pull_request": _positive_int(pull_request, label="pull_request"),
        "source_revision": _sha40(source_revision, label="source_revision"),
        "pie_revision": _sha40(pie_revision, label="pie_revision"),
    }
    signal = _signal_projection(interface)
    lazy_interface = _lazy_projection(interface)
    semantic_body = {
        "contract_version": CALIBRATION_RECORD_CONTRACT_VERSION,
        "identity": identity,
        "signal": signal,
        "lazy_interface": lazy_interface,
    }
    calibration_key_sha256 = canonical_json_sha256(identity)
    semantic_sha256 = canonical_json_sha256(semantic_body)
    body = {
        **semantic_body,
        "calibration_key_sha256": calibration_key_sha256,
        "semantic_sha256": semantic_sha256,
        "transport": {
            "execution_id": _nonempty_string(execution_id, label="execution_id"),
            "workflow_run_id": _nonempty_string(workflow_run_id, label="workflow_run_id"),
            "workflow_run_attempt": _positive_int(workflow_run_attempt, label="workflow_run_attempt"),
        },
        "authority": {
            "trust_fact_inferred": False,
            "human_review_inferred": False,
            "outcome_inferred": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
    }
    return {**body, "record_sha256": canonical_json_sha256(body)}


def _artifact_token(value: Any) -> str:
    if value is None:
        return "NONE"
    token = _SAFE_ARTIFACT_TOKEN.sub("_", str(value).upper()).strip("_")
    return token or "UNKNOWN"


def calibration_artifact_name(record: Mapping[str, Any]) -> str:
    if record.get("contract_version") != CALIBRATION_RECORD_CONTRACT_VERSION:
        raise CalibrationObservationError("unsupported calibration record contract")
    key = record.get("calibration_key_sha256")
    if not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{64}", key) is None:
        raise CalibrationObservationError("calibration_key_sha256 must be a lowercase SHA-256 digest")
    signal = _mapping(record.get("signal"), label="record.signal")
    lazy = _mapping(record.get("lazy_interface"), label="record.lazy_interface")
    level1 = lazy.get("level1_materialized")
    level2 = lazy.get("level2_item_count")
    if not isinstance(level1, bool):
        raise CalibrationObservationError("lazy_interface.level1_materialized must be boolean")
    if isinstance(level2, bool) or not isinstance(level2, int) or level2 < 0:
        raise CalibrationObservationError("lazy_interface.level2_item_count must be a non-negative integer")
    return (
        f"{_CALIBRATION_ARTIFACT_PREFIX}--k-{key}"
        f"--s-{_artifact_token(signal.get('status'))}"
        f"--r-{_artifact_token(signal.get('reason'))}"
        f"--m-{_artifact_token(signal.get('match_status'))}"
        f"--l1-{1 if level1 else 0}--l2-{level2}"
    )


def write_calibration_record(root: str | Path, record: Mapping[str, Any]) -> Path:
    target = Path(root).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    path = target / "calibration.json"
    path.write_text(json.dumps(dict(record), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("contract_version") != CALIBRATION_RECORD_CONTRACT_VERSION:
        raise CalibrationObservationError("unsupported calibration record contract")
    key = record.get("calibration_key_sha256")
    semantic_hash = record.get("semantic_sha256")
    record_hash = record.get("record_sha256")
    for label, value in (
        ("calibration_key_sha256", key),
        ("semantic_sha256", semantic_hash),
        ("record_sha256", record_hash),
    ):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise CalibrationObservationError(f"{label} must be a lowercase SHA-256 digest")

    identity = dict(_mapping(record.get("identity"), label="record.identity"))
    semantic_body = {
        "contract_version": CALIBRATION_RECORD_CONTRACT_VERSION,
        "identity": identity,
        "signal": dict(_mapping(record.get("signal"), label="record.signal")),
        "lazy_interface": dict(_mapping(record.get("lazy_interface"), label="record.lazy_interface")),
    }
    if canonical_json_sha256(identity) != key:
        raise CalibrationObservationError("calibration key does not match identity")
    if canonical_json_sha256(semantic_body) != semantic_hash:
        raise CalibrationObservationError("semantic hash does not match calibration projection")
    body = {key_name: deepcopy(value) for key_name, value in record.items() if key_name != "record_sha256"}
    if canonical_json_sha256(body) != record_hash:
        raise CalibrationObservationError("record hash does not match record body")
    return deepcopy(dict(record))


def build_calibration_ledger(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = [_validate_record(record) for record in records]
    if not values:
        raise CalibrationObservationError("at least one calibration record is required")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in values:
        grouped.setdefault(record["calibration_key_sha256"], []).append(record)

    entries: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        semantic_hashes = {item["semantic_sha256"] for item in items}
        if len(semantic_hashes) != 1:
            raise CalibrationObservationError(
                f"same calibration key produced conflicting semantic observations: {key}"
            )
        first = items[0]
        transports = sorted(
            [deepcopy(item["transport"]) for item in items],
            key=lambda item: (
                str(item.get("workflow_run_id")),
                int(item.get("workflow_run_attempt", 0)),
                str(item.get("execution_id")),
            ),
        )
        entries.append(
            {
                "calibration_key_sha256": key,
                "semantic_sha256": first["semantic_sha256"],
                "identity": deepcopy(first["identity"]),
                "signal": deepcopy(first["signal"]),
                "lazy_interface": deepcopy(first["lazy_interface"]),
                "observation_count": len(items),
                "transports": transports,
            }
        )

    def histogram(field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in entries:
            raw = entry["signal"].get(field)
            label = "NONE" if raw is None else str(raw)
            counts[label] = counts.get(label, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: item[0].encode("utf-8")))

    level1_count = sum(1 for entry in entries if entry["lazy_interface"]["level1_materialized"] is True)
    level2_item_total = sum(int(entry["lazy_interface"]["level2_item_count"]) for entry in entries)
    body = {
        "contract_version": CALIBRATION_LEDGER_CONTRACT_VERSION,
        "input_record_count": len(values),
        "unique_calibration_count": len(entries),
        "duplicate_observation_count": len(values) - len(entries),
        "histograms": {
            "status": histogram("status"),
            "reason": histogram("reason"),
            "match_status": histogram("match_status"),
            "next": histogram("next"),
        },
        "lazy_interface": {
            "level1_materialized_count": level1_count,
            "level0_only_count": len(entries) - level1_count,
            "level2_item_total": level2_item_total,
        },
        "entries": entries,
        "authority": {
            "calibration_only": True,
            "trust_fact_inferred": False,
            "outcome_inferred": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
    }
    return {**body, "ledger_sha256": canonical_json_sha256(body)}

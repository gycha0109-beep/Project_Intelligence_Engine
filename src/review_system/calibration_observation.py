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
_SIGNAL_CONTRACT_VERSION = "PIE_SIGNAL_V1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ARTIFACT_TOKEN = re.compile(r"[^A-Z0-9_]+")
_ARTIFACT_TOKEN_MAX = 48
_ARTIFACT_NAME_MAX = 255
_RECORD_AUTHORITY = {
    "trust_fact_inferred": False,
    "human_review_inferred": False,
    "outcome_inferred": False,
    "merge_authorized": False,
    "deploy_authorized": False,
    "production_effect_authorized": False,
}
_LEDGER_AUTHORITY = {
    "calibration_only": True,
    "trust_fact_inferred": False,
    "outcome_inferred": False,
    "merge_authorized": False,
    "deploy_authorized": False,
    "production_effect_authorized": False,
}


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


def _sha256(value: Any, *, label: str) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if _SHA256.fullmatch(normalized) is None:
        raise CalibrationObservationError(f"{label} must be a lowercase SHA-256 digest")
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
    if signal.get("contract_version") != _SIGNAL_CONTRACT_VERSION:
        raise CalibrationObservationError("interface.signal must use PIE_SIGNAL_V1")
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
    interface_sha256 = _sha256(interface.get("interface_sha256"), label="interface.interface_sha256")
    semantic_body = {
        "contract_version": CALIBRATION_RECORD_CONTRACT_VERSION,
        "identity": identity,
        "interface_sha256": interface_sha256,
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
        "authority": deepcopy(_RECORD_AUTHORITY),
    }
    return {**body, "record_sha256": canonical_json_sha256(body)}


def _artifact_token(value: Any) -> str:
    if value is None:
        return "NONE"
    raw = str(value)
    token = _SAFE_ARTIFACT_TOKEN.sub("_", raw.upper()).strip("_") or "UNKNOWN"
    if len(token) <= _ARTIFACT_TOKEN_MAX:
        return token
    suffix = canonical_json_sha256(raw)[:12].upper()
    return f"{token[: _ARTIFACT_TOKEN_MAX - len(suffix) - 1]}_{suffix}"


def calibration_artifact_name(record: Mapping[str, Any]) -> str:
    if record.get("contract_version") != CALIBRATION_RECORD_CONTRACT_VERSION:
        raise CalibrationObservationError("unsupported calibration record contract")
    key = _sha256(record.get("calibration_key_sha256"), label="calibration_key_sha256")
    signal = _mapping(record.get("signal"), label="record.signal")
    lazy = _mapping(record.get("lazy_interface"), label="record.lazy_interface")
    level1 = lazy.get("level1_materialized")
    level2 = lazy.get("level2_item_count")
    if not isinstance(level1, bool):
        raise CalibrationObservationError("lazy_interface.level1_materialized must be boolean")
    if isinstance(level2, bool) or not isinstance(level2, int) or level2 < 0:
        raise CalibrationObservationError("lazy_interface.level2_item_count must be a non-negative integer")
    name = (
        f"{_CALIBRATION_ARTIFACT_PREFIX}--k-{key}"
        f"--s-{_artifact_token(signal.get('status'))}"
        f"--r-{_artifact_token(signal.get('reason'))}"
        f"--m-{_artifact_token(signal.get('match_status'))}"
        f"--l1-{1 if level1 else 0}--l2-{level2}"
    )
    if len(name) > _ARTIFACT_NAME_MAX:
        raise CalibrationObservationError(f"calibration artifact name exceeds {_ARTIFACT_NAME_MAX} characters")
    return name


def write_calibration_record(root: str | Path, record: Mapping[str, Any]) -> Path:
    target = Path(root).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    path = target / "calibration.json"
    path.write_text(json.dumps(dict(record), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _validated_identity(value: Any) -> dict[str, Any]:
    identity = _mapping(value, label="record.identity")
    expected = {
        "repository": _repository(identity.get("repository")),
        "pull_request": _positive_int(identity.get("pull_request"), label="identity.pull_request"),
        "source_revision": _sha40(identity.get("source_revision"), label="identity.source_revision"),
        "pie_revision": _sha40(identity.get("pie_revision"), label="identity.pie_revision"),
    }
    if dict(identity) != expected:
        raise CalibrationObservationError("record.identity is not canonical")
    return expected


def _validated_signal(value: Any) -> dict[str, Any]:
    signal = _mapping(value, label="record.signal")
    expected_keys = {"status", "reason", "match_status", "next"}
    if set(signal) != expected_keys:
        raise CalibrationObservationError("record.signal has unexpected fields")
    status = _nonempty_string(signal.get("status"), label="record.signal.status")
    reason = _nonempty_string(signal.get("reason"), label="record.signal.reason")
    next_step = _nonempty_string(signal.get("next"), label="record.signal.next")
    match_status = signal.get("match_status")
    if match_status is not None and (not isinstance(match_status, str) or not match_status.strip()):
        raise CalibrationObservationError("record.signal.match_status must be null or a non-empty string")
    expected = {
        "status": status,
        "reason": reason,
        "match_status": match_status.strip() if isinstance(match_status, str) else None,
        "next": next_step,
    }
    if dict(signal) != expected:
        raise CalibrationObservationError("record.signal is not canonical")
    return expected


def _validated_lazy(value: Any) -> dict[str, Any]:
    lazy = _mapping(value, label="record.lazy_interface")
    expected_keys = {"level1_materialized", "level2_item_count", "full_capsule_separate"}
    if set(lazy) != expected_keys:
        raise CalibrationObservationError("record.lazy_interface has unexpected fields")
    level1 = lazy.get("level1_materialized")
    level2 = lazy.get("level2_item_count")
    if not isinstance(level1, bool):
        raise CalibrationObservationError("record.lazy_interface.level1_materialized must be boolean")
    if isinstance(level2, bool) or not isinstance(level2, int) or level2 < 0:
        raise CalibrationObservationError("record.lazy_interface.level2_item_count must be a non-negative integer")
    if lazy.get("full_capsule_separate") is not True:
        raise CalibrationObservationError("record.lazy_interface.full_capsule_separate must remain true")
    return {
        "level1_materialized": level1,
        "level2_item_count": level2,
        "full_capsule_separate": True,
    }


def _validated_transport(value: Any) -> dict[str, Any]:
    transport = _mapping(value, label="record.transport")
    expected_keys = {"execution_id", "workflow_run_id", "workflow_run_attempt"}
    if set(transport) != expected_keys:
        raise CalibrationObservationError("record.transport has unexpected fields")
    expected = {
        "execution_id": _nonempty_string(transport.get("execution_id"), label="record.transport.execution_id"),
        "workflow_run_id": _nonempty_string(transport.get("workflow_run_id"), label="record.transport.workflow_run_id"),
        "workflow_run_attempt": _positive_int(
            transport.get("workflow_run_attempt"), label="record.transport.workflow_run_attempt"
        ),
    }
    if dict(transport) != expected:
        raise CalibrationObservationError("record.transport is not canonical")
    return expected


def _validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    expected_top_level = {
        "contract_version",
        "identity",
        "interface_sha256",
        "signal",
        "lazy_interface",
        "calibration_key_sha256",
        "semantic_sha256",
        "transport",
        "authority",
        "record_sha256",
    }
    if set(record) != expected_top_level:
        raise CalibrationObservationError("calibration record has unexpected fields")
    if record.get("contract_version") != CALIBRATION_RECORD_CONTRACT_VERSION:
        raise CalibrationObservationError("unsupported calibration record contract")

    identity = _validated_identity(record.get("identity"))
    interface_sha256 = _sha256(record.get("interface_sha256"), label="interface_sha256")
    signal = _validated_signal(record.get("signal"))
    lazy_interface = _validated_lazy(record.get("lazy_interface"))
    transport = _validated_transport(record.get("transport"))
    authority = dict(_mapping(record.get("authority"), label="record.authority"))
    if authority != _RECORD_AUTHORITY:
        raise CalibrationObservationError("record authority boundary must remain explicitly false")

    key = _sha256(record.get("calibration_key_sha256"), label="calibration_key_sha256")
    semantic_hash = _sha256(record.get("semantic_sha256"), label="semantic_sha256")
    record_hash = _sha256(record.get("record_sha256"), label="record_sha256")
    semantic_body = {
        "contract_version": CALIBRATION_RECORD_CONTRACT_VERSION,
        "identity": identity,
        "interface_sha256": interface_sha256,
        "signal": signal,
        "lazy_interface": lazy_interface,
    }
    if canonical_json_sha256(identity) != key:
        raise CalibrationObservationError("calibration key does not match identity")
    if canonical_json_sha256(semantic_body) != semantic_hash:
        raise CalibrationObservationError("semantic hash does not match calibration projection")
    body = {
        **semantic_body,
        "calibration_key_sha256": key,
        "semantic_sha256": semantic_hash,
        "transport": transport,
        "authority": deepcopy(_RECORD_AUTHORITY),
    }
    if canonical_json_sha256(body) != record_hash:
        raise CalibrationObservationError("record hash does not match record body")
    return {**body, "record_sha256": record_hash}


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
                "interface_sha256": first["interface_sha256"],
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
        "authority": deepcopy(_LEDGER_AUTHORITY),
    }
    return {**body, "ledger_sha256": canonical_json_sha256(body)}

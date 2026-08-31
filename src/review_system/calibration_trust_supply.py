from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

from .calibration_observation import build_calibration_ledger
from .identity import canonical_json_sha256
from .operational_trust_supply import (
    CONTRACT_VERSION as OPERATIONAL_TRUST_SUPPLY_CONTRACT_VERSION,
    SCHEMA_VERSION as OPERATIONAL_TRUST_SUPPLY_SCHEMA_VERSION,
    verify_operational_trust_supply_observation,
)


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_CALIBRATION_TRUST_FACTS_SUPPLY_V1"
FILENAME = "trust-facts-supply.json"

_AUTHORITY = {
    "calibration_only": True,
    "trust_fact_inferred": False,
    "human_review_inferred": False,
    "outcome_inferred": False,
    "merge_authorized": False,
    "deploy_authorized": False,
    "production_effect_authorized": False,
}


class CalibrationTrustSupplyError(RuntimeError):
    pass


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibrationTrustSupplyError(f"{label} must be an object")
    return value


def _sidecar_hash(value: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(value))
    payload.pop("sidecar_sha256", None)
    return canonical_json_sha256(payload)


def _source_observation_from_sidecar(value: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(value.get("source_observation"), label="source_observation")
    supply = _mapping(value.get("supply"), label="supply")
    authority = _mapping(value.get("authority"), label="authority")
    return {
        "schema_version": source.get("schema_version"),
        "contract_version": source.get("contract_version"),
        "status": supply.get("status"),
        "producer_mode": supply.get("producer_mode"),
        "transport": deepcopy(supply.get("transport")),
        "binder": deepcopy(supply.get("binder")),
        "trust_fact_inferred": authority.get("trust_fact_inferred"),
        "human_review_inferred": authority.get("human_review_inferred"),
        "outcome_inferred": authority.get("outcome_inferred"),
        "merge_authorized": authority.get("merge_authorized"),
        "deploy_authorized": authority.get("deploy_authorized"),
        "production_effect_authorized": authority.get("production_effect_authorized"),
        "observation_sha256": source.get("observation_sha256"),
    }


def build_calibration_trust_supply_sidecar(
    *,
    calibration_record: Mapping[str, Any],
    trust_supply_observation: Mapping[str, Any],
) -> dict[str, Any]:
    ledger = build_calibration_ledger([calibration_record])
    entry = ledger["entries"][0]

    observation = dict(trust_supply_observation)
    observation_errors = verify_operational_trust_supply_observation(observation)
    if observation_errors:
        raise CalibrationTrustSupplyError(
            "invalid operational Trust supply observation: " + "; ".join(observation_errors)
        )

    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "identity": deepcopy(entry["identity"]),
        "calibration_key_sha256": entry["calibration_key_sha256"],
        "calibration_semantic_sha256": entry["semantic_sha256"],
        "source_observation": {
            "schema_version": observation["schema_version"],
            "contract_version": observation["contract_version"],
            "observation_sha256": observation["observation_sha256"],
        },
        "supply": {
            "status": observation["status"],
            "producer_mode": observation["producer_mode"],
            "transport": deepcopy(observation["transport"]),
            "binder": deepcopy(observation["binder"]),
        },
        "authority": deepcopy(_AUTHORITY),
    }
    return {**body, "sidecar_sha256": canonical_json_sha256(body)}


def verify_calibration_trust_supply_sidecar(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return ["sidecar must contain an object"]

    expected_top_level = {
        "schema_version",
        "contract_version",
        "identity",
        "calibration_key_sha256",
        "calibration_semantic_sha256",
        "source_observation",
        "supply",
        "authority",
        "sidecar_sha256",
    }
    if set(value) != expected_top_level:
        errors.append("sidecar has unexpected fields")
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if value.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")

    identity = value.get("identity")
    if not isinstance(identity, Mapping):
        errors.append("identity must contain an object")
    elif canonical_json_sha256(dict(identity)) != value.get("calibration_key_sha256"):
        errors.append("calibration key does not match identity")

    source = value.get("source_observation")
    if not isinstance(source, Mapping):
        errors.append("source_observation must contain an object")
    else:
        if source.get("schema_version") != OPERATIONAL_TRUST_SUPPLY_SCHEMA_VERSION:
            errors.append("source observation schema_version mismatch")
        if source.get("contract_version") != OPERATIONAL_TRUST_SUPPLY_CONTRACT_VERSION:
            errors.append("source observation contract_version mismatch")

    if value.get("authority") != _AUTHORITY:
        errors.append("authority boundary must remain calibration-only and explicitly false")

    if not errors:
        try:
            source_observation = _source_observation_from_sidecar(value)
        except CalibrationTrustSupplyError as exc:
            errors.append(str(exc))
        else:
            errors.extend(verify_operational_trust_supply_observation(source_observation))

    expected_hash = _sidecar_hash(value)
    if value.get("sidecar_sha256") != expected_hash:
        errors.append("sidecar_sha256 mismatch")
    return sorted(set(errors))


def write_calibration_trust_supply_sidecar(
    root: str | Path,
    value: Mapping[str, Any],
) -> Path:
    errors = verify_calibration_trust_supply_sidecar(value)
    if errors:
        raise CalibrationTrustSupplyError("invalid calibration Trust supply sidecar: " + "; ".join(errors))
    target = Path(root).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    path = target / FILENAME
    path.write_text(json.dumps(dict(value), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path

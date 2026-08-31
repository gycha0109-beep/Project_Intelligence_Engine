from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .calibration_observation import CalibrationObservationError, build_calibration_ledger
from .identity import canonical_json_sha256
from .operational_trust_supply import (
    CONTRACT_VERSION as OPERATIONAL_TRUST_SUPPLY_CONTRACT_VERSION,
    SCHEMA_VERSION as OPERATIONAL_TRUST_SUPPLY_SCHEMA_VERSION,
    verify_operational_trust_supply_observation,
)


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_CALIBRATION_TRUST_FACTS_SUPPLY_V1"
LEDGER_CONTRACT_VERSION = "PIE_CALIBRATION_TRUST_FACTS_SUPPLY_LEDGER_V1"
FILENAME = "trust-facts-supply.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

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

    if not isinstance(value.get("calibration_semantic_sha256"), str) or _SHA256.fullmatch(
        value.get("calibration_semantic_sha256", "")
    ) is None:
        errors.append("calibration_semantic_sha256 must be a lowercase SHA-256 digest")

    source = value.get("source_observation")
    if not isinstance(source, Mapping):
        errors.append("source_observation must contain an object")
    else:
        if set(source) != {"schema_version", "contract_version", "observation_sha256"}:
            errors.append("source_observation has unexpected fields")
        if source.get("schema_version") != OPERATIONAL_TRUST_SUPPLY_SCHEMA_VERSION:
            errors.append("source observation schema_version mismatch")
        if source.get("contract_version") != OPERATIONAL_TRUST_SUPPLY_CONTRACT_VERSION:
            errors.append("source observation contract_version mismatch")
        if not isinstance(source.get("observation_sha256"), str) or _SHA256.fullmatch(
            source.get("observation_sha256", "")
        ) is None:
            errors.append("source observation hash must be a lowercase SHA-256 digest")

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


def verify_calibration_trust_supply_binding(
    calibration_record: Mapping[str, Any],
    sidecar: Mapping[str, Any],
) -> list[str]:
    errors = list(verify_calibration_trust_supply_sidecar(sidecar))
    try:
        ledger = build_calibration_ledger([calibration_record])
    except CalibrationObservationError as exc:
        errors.append(f"invalid calibration record: {exc}")
        return sorted(set(errors))

    entry = ledger["entries"][0]
    if sidecar.get("identity") != entry["identity"]:
        errors.append("sidecar identity does not match calibration record")
    if sidecar.get("calibration_key_sha256") != entry["calibration_key_sha256"]:
        errors.append("sidecar calibration key does not match calibration record")
    if sidecar.get("calibration_semantic_sha256") != entry["semantic_sha256"]:
        errors.append("sidecar semantic hash does not match calibration record")
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


def build_calibration_trust_supply_ledger(
    sidecars: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for sidecar in sidecars:
        errors = verify_calibration_trust_supply_sidecar(sidecar)
        if errors:
            raise CalibrationTrustSupplyError("invalid calibration Trust supply sidecar: " + "; ".join(errors))
        values.append(deepcopy(dict(sidecar)))
    if not values:
        raise CalibrationTrustSupplyError("at least one calibration Trust supply sidecar is required")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for sidecar in values:
        grouped.setdefault(sidecar["calibration_key_sha256"], []).append(sidecar)

    entries: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        sidecar_hashes = {item["sidecar_sha256"] for item in items}
        if len(sidecar_hashes) != 1:
            raise CalibrationTrustSupplyError(
                f"same calibration key produced conflicting Trust supply observations: {key}"
            )
        first = items[0]
        entries.append(
            {
                "calibration_key_sha256": key,
                "calibration_semantic_sha256": first["calibration_semantic_sha256"],
                "identity": deepcopy(first["identity"]),
                "source_observation": deepcopy(first["source_observation"]),
                "supply": deepcopy(first["supply"]),
                "sidecar_sha256": first["sidecar_sha256"],
                "observation_count": len(items),
            }
        )

    def histogram(selector: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in entries:
            raw = selector(entry)
            if isinstance(raw, bool):
                label = "true" if raw else "false"
            elif raw is None:
                label = "NONE"
            else:
                label = str(raw)
            counts[label] = counts.get(label, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: item[0].encode("utf-8")))

    body = {
        "contract_version": LEDGER_CONTRACT_VERSION,
        "input_sidecar_count": len(values),
        "unique_calibration_count": len(entries),
        "duplicate_observation_count": len(values) - len(entries),
        "histograms": {
            "status": histogram(lambda entry: entry["supply"]["status"]),
            "producer_mode": histogram(lambda entry: entry["supply"]["producer_mode"]),
            "operational_policy_requested": histogram(
                lambda entry: entry["supply"]["transport"]["operational_policy_requested"]
            ),
            "explicit_input_declared": histogram(
                lambda entry: entry["supply"]["transport"]["explicit_input_declared"]
            ),
            "explicit_input_available": histogram(
                lambda entry: entry["supply"]["transport"]["explicit_input_available"]
            ),
            "binder_attempted": histogram(lambda entry: entry["supply"]["binder"]["attempted"]),
            "binding_status": histogram(lambda entry: entry["supply"]["binder"]["binding_status"]),
            "match_status": histogram(lambda entry: entry["supply"]["binder"]["match_status"]),
            "facts_consumed": histogram(lambda entry: entry["supply"]["binder"]["facts_consumed"]),
        },
        "entries": entries,
        "authority": deepcopy(_AUTHORITY),
    }
    return {**body, "ledger_sha256": canonical_json_sha256(body)}

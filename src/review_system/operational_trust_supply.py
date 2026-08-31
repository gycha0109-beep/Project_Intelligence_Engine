from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from .identity import canonical_json_sha256


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_OPERATIONAL_TRUST_FACTS_SUPPLY_V1"
PRODUCER_MODE = "EXPLICIT_INPUT_ONLY"

_AUTHORITY_FIELDS = (
    "trust_fact_inferred",
    "human_review_inferred",
    "outcome_inferred",
    "merge_authorized",
    "deploy_authorized",
    "production_effect_authorized",
)


class OperationalTrustSupplyObservationError(RuntimeError):
    pass


def _observation_hash(value: dict[str, Any]) -> str:
    payload = deepcopy(value)
    payload.pop("observation_sha256", None)
    return canonical_json_sha256(payload)


def build_operational_trust_supply_observation(
    *,
    operational_policy_requested: bool,
    explicit_input_declared: bool,
    explicit_input_available: bool,
    operational_binding: dict[str, Any] | None,
) -> dict[str, Any]:
    if explicit_input_available and not explicit_input_declared:
        raise OperationalTrustSupplyObservationError(
            "explicit input cannot be available when it was not declared"
        )
    if explicit_input_declared and not operational_policy_requested:
        raise OperationalTrustSupplyObservationError(
            "operational Trust facts cannot be declared without Operational Policy"
        )

    binding_attempted = operational_binding is not None
    binding_status = operational_binding.get("status") if binding_attempted else None
    match_status = operational_binding.get("match_status") if binding_attempted else None
    facts = operational_binding.get("facts") if binding_attempted else None
    if not isinstance(facts, dict):
        facts = {}
    facts_consumed = facts.get("supplied") is True
    facts_sha256 = facts.get("facts_sha256") if facts_consumed else None

    if facts_consumed and not (explicit_input_declared and explicit_input_available):
        raise OperationalTrustSupplyObservationError(
            "binder cannot consume canonical Trust facts without an available explicit input"
        )
    if facts_consumed and not isinstance(facts_sha256, str):
        raise OperationalTrustSupplyObservationError(
            "consumed canonical Trust facts must expose facts_sha256"
        )

    if not operational_policy_requested:
        status = "POLICY_DISABLED"
    elif facts_consumed:
        status = "EXPLICIT_INPUT_VALIDATED_AND_CONSUMED"
    elif explicit_input_declared:
        status = "EXPLICIT_INPUT_PRESENT_NOT_CONSUMED"
    else:
        status = "EXPLICIT_INPUT_ABSENT"

    observation: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "producer_mode": PRODUCER_MODE,
        "transport": {
            "operational_policy_requested": operational_policy_requested,
            "explicit_input_declared": explicit_input_declared,
            "explicit_input_available": explicit_input_available,
        },
        "binder": {
            "attempted": binding_attempted,
            "binding_status": binding_status,
            "match_status": match_status,
            "facts_consumed": facts_consumed,
            "facts_sha256": facts_sha256,
        },
        "trust_fact_inferred": False,
        "human_review_inferred": False,
        "outcome_inferred": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
        "observation_sha256": "",
    }
    observation["observation_sha256"] = _observation_hash(observation)
    return observation


def verify_operational_trust_supply_observation(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["observation must contain an object"]
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if value.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    if value.get("producer_mode") != PRODUCER_MODE:
        errors.append("producer_mode mismatch")
    if value.get("status") not in {
        "POLICY_DISABLED",
        "EXPLICIT_INPUT_ABSENT",
        "EXPLICIT_INPUT_PRESENT_NOT_CONSUMED",
        "EXPLICIT_INPUT_VALIDATED_AND_CONSUMED",
    }:
        errors.append("status invalid")
    for field in _AUTHORITY_FIELDS:
        if value.get(field) is not False:
            errors.append(f"{field} must remain false")
    transport = value.get("transport")
    binder = value.get("binder")
    if not isinstance(transport, dict):
        errors.append("transport must contain an object")
    if not isinstance(binder, dict):
        errors.append("binder must contain an object")
    if isinstance(transport, dict):
        declared = transport.get("explicit_input_declared") is True
        available = transport.get("explicit_input_available") is True
        policy = transport.get("operational_policy_requested") is True
        if available and not declared:
            errors.append("available explicit input requires declared explicit input")
        if declared and not policy:
            errors.append("declared explicit input requires operational policy")
    else:
        declared = available = policy = False
    if isinstance(binder, dict):
        consumed = binder.get("facts_consumed") is True
        facts_sha256 = binder.get("facts_sha256")
        if consumed and not (declared and available):
            errors.append("consumed facts require available explicit input")
        if consumed and not isinstance(facts_sha256, str):
            errors.append("consumed facts require facts_sha256")
        if not consumed and facts_sha256 is not None:
            errors.append("unconsumed facts must not expose facts_sha256")
    expected = _observation_hash(value)
    if value.get("observation_sha256") != expected:
        errors.append("observation_sha256 mismatch")
    return sorted(set(errors))


def write_operational_trust_supply_observation(
    path: str | Path,
    value: dict[str, Any],
) -> Path:
    errors = verify_operational_trust_supply_observation(value)
    if errors:
        raise OperationalTrustSupplyObservationError(
            "invalid operational Trust supply observation: " + "; ".join(errors)
        )
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from itertools import combinations
from io import BytesIO
import json
from typing import Any, Iterable, Mapping
from zipfile import BadZipFile, ZipFile

from .calibration_backfill import (
    CalibrationBackfillError,
    parse_legacy_interface_artifact,
    parse_pull_request_from_interface_artifact_name,
)
from .identity import canonical_json_sha256


POLICY_AMBIGUITY_OBSERVATION_CONTRACT_VERSION = "PIE_HISTORICAL_POLICY_AMBIGUITY_OBSERVATION_V1"
POLICY_AMBIGUITY_DIAGNOSTIC_CONTRACT_VERSION = "PIE_HISTORICAL_POLICY_AMBIGUITY_DIAGNOSTIC_V1"
_OPERATIONAL_BRIEF_CONTRACT_VERSION = "PIE_OPERATIONAL_BRIEF_V1"
_TARGETED_EVIDENCE_CONTRACT_VERSION = "PIE_TARGETED_EVIDENCE_V1"
_OBSERVATION_AUTHORITY = {
    "historical_observation_only": True,
    "policy_resolution_inferred": False,
    "operational_class_selected": False,
    "trust_fact_inferred": False,
    "human_review_inferred": False,
    "outcome_inferred": False,
    "merge_authorized": False,
    "deploy_authorized": False,
    "production_effect_authorized": False,
}
_DIAGNOSTIC_AUTHORITY = {
    "calibration_only": True,
    "policy_resolution_inferred": False,
    "operational_class_selected": False,
    "trust_fact_inferred": False,
    "human_review_inferred": False,
    "outcome_inferred": False,
    "merge_authorized": False,
    "deploy_authorized": False,
    "production_effect_authorized": False,
}


class PolicyAmbiguityDiagnosticError(RuntimeError):
    pass


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyAmbiguityDiagnosticError(f"{label} must be an object")
    return value


def _nonempty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyAmbiguityDiagnosticError(f"{label} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    return _nonempty_string(value, label=label)


def _string_list(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise PolicyAmbiguityDiagnosticError(f"{label} must be an array")
    items = [_nonempty_string(item, label=f"{label}[{index}]") for index, item in enumerate(value)]
    if len(set(items)) != len(items):
        raise PolicyAmbiguityDiagnosticError(f"{label} must not contain duplicates")
    return items


def _read_json(archive: ZipFile, path: str) -> Any:
    try:
        raw = archive.read(path)
    except KeyError as exc:
        raise PolicyAmbiguityDiagnosticError(f"legacy interface artifact is missing {path}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyAmbiguityDiagnosticError(f"legacy interface artifact has invalid JSON at {path}") from exc


def parse_legacy_policy_ambiguity_artifact(payload: bytes) -> dict[str, Any] | None:
    try:
        interface = parse_legacy_interface_artifact(payload)
    except CalibrationBackfillError as exc:
        raise PolicyAmbiguityDiagnosticError(str(exc)) from exc

    signal = _mapping(interface.get("signal"), label="interface.signal")
    if signal.get("reason") != "AMBIGUOUS_POLICY_MATCH":
        return None
    if signal.get("status") != "ACTION_REQUIRED":
        raise PolicyAmbiguityDiagnosticError("AMBIGUOUS_POLICY_MATCH signal must be ACTION_REQUIRED")
    if signal.get("match_status") != "AMBIGUOUS_POLICY_MATCH":
        raise PolicyAmbiguityDiagnosticError("AMBIGUOUS_POLICY_MATCH signal must have AMBIGUOUS_POLICY_MATCH")
    if signal.get("next") != "READ_POLICY_MATCH_DETAILS":
        raise PolicyAmbiguityDiagnosticError("AMBIGUOUS_POLICY_MATCH signal must point to READ_POLICY_MATCH_DETAILS")

    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise PolicyAmbiguityDiagnosticError("legacy interface artifact is not a valid ZIP archive") from exc

    with archive:
        brief = _mapping(_read_json(archive, "brief.json"), label="brief.json")
        if brief.get("contract_version") != _OPERATIONAL_BRIEF_CONTRACT_VERSION:
            raise PolicyAmbiguityDiagnosticError("policy-ambiguity brief must use PIE_OPERATIONAL_BRIEF_V1")
        if brief.get("signal_reason") != "AMBIGUOUS_POLICY_MATCH":
            raise PolicyAmbiguityDiagnosticError("policy-ambiguity brief signal_reason does not match signal")
        if brief.get("match_status") != "AMBIGUOUS_POLICY_MATCH":
            raise PolicyAmbiguityDiagnosticError("policy-ambiguity brief match_status does not match signal")
        if brief.get("operational_class") is not None:
            raise PolicyAmbiguityDiagnosticError("ambiguous policy match must not select an operational class")
        if brief.get("trust_task_class") is not None:
            raise PolicyAmbiguityDiagnosticError("ambiguous policy match must not select a trust task class")

        read_evidence = sorted(_string_list(brief.get("read_evidence"), label="brief.read_evidence"))
        index = _mapping(_read_json(archive, "targeted/index.json"), label="targeted/index.json")
        if sorted(index) != read_evidence:
            raise PolicyAmbiguityDiagnosticError("brief.read_evidence must match targeted/index.json keys")
        if set(index) != {"policy-match-details"}:
            raise PolicyAmbiguityDiagnosticError("ambiguous policy match must expose only policy-match-details at L2")

        path = index["policy-match-details"]
        if not isinstance(path, str) or not path.startswith("targeted/") or not path.endswith(".json"):
            raise PolicyAmbiguityDiagnosticError("policy-match-details path must be targeted JSON")
        item = _mapping(_read_json(archive, path), label=path)
        if item.get("contract_version") != _TARGETED_EVIDENCE_CONTRACT_VERSION:
            raise PolicyAmbiguityDiagnosticError(f"{path} must use PIE_TARGETED_EVIDENCE_V1")
        if item.get("id") != "policy-match-details":
            raise PolicyAmbiguityDiagnosticError("policy-match-details id does not match targeted index")
        if item.get("kind") != "policy_match" or item.get("state") != "AMBIGUOUS":
            raise PolicyAmbiguityDiagnosticError("policy-match-details must be an AMBIGUOUS policy_match")
        matched_classes = sorted(
            _string_list(item.get("matched_operational_classes"), label=f"{path}.matched_operational_classes")
        )
        if len(matched_classes) < 2:
            raise PolicyAmbiguityDiagnosticError("ambiguous policy match must contain at least two matched operational classes")
        provenance = _mapping(item.get("provenance"), label=f"{path}.provenance")

    return {
        "interface_sha256": interface["interface_sha256"],
        "matched_operational_classes": matched_classes,
        "match_cardinality": len(matched_classes),
        "policy_match_details": {
            "policy_revision": _optional_string(provenance.get("policy_revision"), label="policy_revision"),
            "policy_sha256": _optional_string(provenance.get("policy_sha256"), label="policy_sha256"),
            "binding_sha256": _optional_string(provenance.get("binding_sha256"), label="binding_sha256"),
            "facts_sha256": _optional_string(provenance.get("facts_sha256"), label="facts_sha256"),
        },
    }


def build_historical_policy_ambiguity_observation(
    *, repository: str, pie_revision: str, run: Mapping[str, Any], artifact: Mapping[str, Any], artifact_zip: bytes,
) -> dict[str, Any] | None:
    parsed = parse_legacy_policy_ambiguity_artifact(artifact_zip)
    if parsed is None:
        return None

    run_id = run.get("id")
    run_attempt = run.get("run_attempt")
    head_sha = run.get("head_sha")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        raise PolicyAmbiguityDiagnosticError("workflow run id must be a positive integer")
    if isinstance(run_attempt, bool) or not isinstance(run_attempt, int) or run_attempt <= 0:
        raise PolicyAmbiguityDiagnosticError("workflow run attempt must be a positive integer")
    if not isinstance(head_sha, str) or len(head_sha) != 40:
        raise PolicyAmbiguityDiagnosticError("workflow run head_sha must be an exact Git SHA")

    artifact_id = artifact.get("id")
    artifact_name = artifact.get("name")
    artifact_run = _mapping(artifact.get("workflow_run"), label="artifact.workflow_run")
    if isinstance(artifact_id, bool) or not isinstance(artifact_id, int) or artifact_id <= 0:
        raise PolicyAmbiguityDiagnosticError("artifact id must be a positive integer")
    if not isinstance(artifact_name, str) or not artifact_name:
        raise PolicyAmbiguityDiagnosticError("artifact name must be a non-empty string")
    if artifact_run.get("id") != run_id or artifact_run.get("head_sha") != head_sha:
        raise PolicyAmbiguityDiagnosticError("artifact workflow identity does not match workflow run")
    encoded_head = artifact_name.rsplit("-interface", 1)[0].split("-")[-2]
    if encoded_head != head_sha.lower()[:12]:
        raise PolicyAmbiguityDiagnosticError("legacy compact artifact head prefix does not match workflow run")

    identity = {
        "repository": repository.strip().lower(),
        "pull_request": parse_pull_request_from_interface_artifact_name(artifact_name),
        "source_revision": head_sha.lower(),
        "pie_revision": pie_revision.strip().lower(),
    }
    semantic_body = {
        "contract_version": POLICY_AMBIGUITY_OBSERVATION_CONTRACT_VERSION,
        "identity": identity,
        "interface_sha256": parsed["interface_sha256"],
        "matched_operational_classes": parsed["matched_operational_classes"],
        "match_cardinality": parsed["match_cardinality"],
        "policy_match_details": parsed["policy_match_details"],
    }
    body = {
        **semantic_body,
        "calibration_key_sha256": canonical_json_sha256(identity),
        "semantic_sha256": canonical_json_sha256(semantic_body),
        "transport": {
            "artifact_id": artifact_id,
            "artifact_name": artifact_name,
            "workflow_run_id": str(run_id),
            "workflow_run_attempt": run_attempt,
        },
        "authority": deepcopy(_OBSERVATION_AUTHORITY),
    }
    return {**body, "observation_sha256": canonical_json_sha256(body)}


def _nested_counter_to_dict(values: Mapping[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {outer: dict(sorted(counter.items())) for outer, counter in sorted(values.items())}


def build_policy_ambiguity_diagnostic(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = [dict(item) for item in observations]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in values:
        if observation.get("contract_version") != POLICY_AMBIGUITY_OBSERVATION_CONTRACT_VERSION:
            raise PolicyAmbiguityDiagnosticError("unsupported policy-ambiguity observation contract")
        if observation.get("authority") != _OBSERVATION_AUTHORITY:
            raise PolicyAmbiguityDiagnosticError("policy-ambiguity observation authority boundary changed")
        key = _nonempty_string(observation.get("calibration_key_sha256"), label="calibration_key_sha256")
        _nonempty_string(observation.get("semantic_sha256"), label="semantic_sha256")
        body = dict(observation)
        recorded_hash = body.pop("observation_sha256", None)
        if canonical_json_sha256(body) != recorded_hash:
            raise PolicyAmbiguityDiagnosticError("policy-ambiguity observation hash mismatch")
        grouped[key].append(observation)

    unique: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        semantic_hashes = {item["semantic_sha256"] for item in items}
        if len(semantic_hashes) != 1:
            raise PolicyAmbiguityDiagnosticError(
                f"same calibration key produced conflicting policy-ambiguity observations: {key}"
            )
        unique.append(items[0])

    matched_class = Counter()
    ambiguity_set = Counter()
    cardinality = Counter()
    class_pair = Counter()
    policy_sha256 = Counter()
    policy_revision = Counter()
    facts_provenance = Counter()
    by_repository_ambiguity_set: dict[str, Counter[str]] = defaultdict(Counter)
    by_repository_matched_class: dict[str, Counter[str]] = defaultdict(Counter)
    by_policy_ambiguity_set: dict[str, Counter[str]] = defaultdict(Counter)
    max_cardinality = 0
    policy_provenance_present_count = 0

    for observation in unique:
        repository = observation["identity"]["repository"]
        classes = sorted(observation["matched_operational_classes"])
        if len(classes) < 2 or observation.get("match_cardinality") != len(classes):
            raise PolicyAmbiguityDiagnosticError("policy-ambiguity observation cardinality mismatch")
        set_key = "|".join(classes)
        ambiguity_set[set_key] += 1
        cardinality[str(len(classes))] += 1
        max_cardinality = max(max_cardinality, len(classes))
        by_repository_ambiguity_set[repository][set_key] += 1
        for item in classes:
            matched_class[item] += 1
            by_repository_matched_class[repository][item] += 1
        for left, right in combinations(classes, 2):
            class_pair[f"{left}|{right}"] += 1

        details = _mapping(observation.get("policy_match_details"), label="policy_match_details")
        policy_hash = details.get("policy_sha256")
        policy_rev = details.get("policy_revision")
        if isinstance(policy_hash, str) and policy_hash:
            policy_sha256[policy_hash] += 1
            by_policy_ambiguity_set[policy_hash][set_key] += 1
        if isinstance(policy_rev, str) and policy_rev:
            policy_revision[policy_rev] += 1
        if isinstance(policy_hash, str) and policy_hash and isinstance(policy_rev, str) and policy_rev:
            policy_provenance_present_count += 1
        facts_provenance["ABSENT" if details.get("facts_sha256") is None else "PRESENT"] += 1

    body = {
        "contract_version": POLICY_AMBIGUITY_DIAGNOSTIC_CONTRACT_VERSION,
        "input_observation_count": len(values),
        "unique_calibration_count": len(unique),
        "duplicate_observation_count": len(values) - len(unique),
        "histograms": {
            "matched_operational_class": dict(sorted(matched_class.items())),
            "ambiguity_set": dict(sorted(ambiguity_set.items())),
            "match_cardinality": dict(sorted(cardinality.items())),
            "class_pair": dict(sorted(class_pair.items())),
            "policy_sha256": dict(sorted(policy_sha256.items())),
            "policy_revision": dict(sorted(policy_revision.items())),
            "facts_provenance": dict(sorted(facts_provenance.items())),
        },
        "breakdowns": {
            "repository_ambiguity_set": _nested_counter_to_dict(by_repository_ambiguity_set),
            "repository_matched_operational_class": _nested_counter_to_dict(by_repository_matched_class),
            "policy_ambiguity_set": _nested_counter_to_dict(by_policy_ambiguity_set),
        },
        "ambiguity": {
            "observation_total": len(unique),
            "max_match_cardinality": max_cardinality,
            "policy_provenance_present_count": policy_provenance_present_count,
        },
        "authority": deepcopy(_DIAGNOSTIC_AUTHORITY),
    }
    return {**body, "diagnostic_sha256": canonical_json_sha256(body)}

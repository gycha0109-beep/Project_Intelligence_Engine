from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
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


TRUST_GAP_OBSERVATION_CONTRACT_VERSION = "PIE_HISTORICAL_TRUST_GAP_OBSERVATION_V1"
TRUST_GAP_DIAGNOSTIC_CONTRACT_VERSION = "PIE_HISTORICAL_TRUST_GAP_DIAGNOSTIC_V1"
_OPERATIONAL_BRIEF_CONTRACT_VERSION = "PIE_OPERATIONAL_BRIEF_V1"
_TARGETED_EVIDENCE_CONTRACT_VERSION = "PIE_TARGETED_EVIDENCE_V1"
_OBSERVATION_AUTHORITY = {
    "historical_observation_only": True,
    "trust_fact_inferred": False,
    "human_review_inferred": False,
    "outcome_inferred": False,
    "merge_authorized": False,
    "deploy_authorized": False,
    "production_effect_authorized": False,
}
_DIAGNOSTIC_AUTHORITY = {
    "calibration_only": True,
    "trust_fact_inferred": False,
    "human_review_inferred": False,
    "outcome_inferred": False,
    "merge_authorized": False,
    "deploy_authorized": False,
    "production_effect_authorized": False,
}


class TrustGapDiagnosticError(RuntimeError):
    pass


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TrustGapDiagnosticError(f"{label} must be an object")
    return value


def _nonempty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustGapDiagnosticError(f"{label} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise TrustGapDiagnosticError(f"{label} must be an array")
    items: list[str] = []
    for index, item in enumerate(value):
        items.append(_nonempty_string(item, label=f"{label}[{index}]"))
    if len(set(items)) != len(items):
        raise TrustGapDiagnosticError(f"{label} must not contain duplicates")
    return items


def _read_json(archive: ZipFile, path: str) -> Any:
    try:
        raw = archive.read(path)
    except KeyError as exc:
        raise TrustGapDiagnosticError(f"legacy interface artifact is missing {path}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustGapDiagnosticError(f"legacy interface artifact has invalid JSON at {path}") from exc


def parse_legacy_trust_gap_artifact(payload: bytes) -> dict[str, Any] | None:
    try:
        interface = parse_legacy_interface_artifact(payload)
    except CalibrationBackfillError as exc:
        raise TrustGapDiagnosticError(str(exc)) from exc

    signal = _mapping(interface.get("signal"), label="interface.signal")
    if signal.get("reason") != "MISSING_TRUST_FIELDS":
        return None
    if signal.get("status") != "ACTION_REQUIRED":
        raise TrustGapDiagnosticError("MISSING_TRUST_FIELDS signal must be ACTION_REQUIRED")
    if signal.get("match_status") != "UNIQUE_POLICY_MATCH":
        raise TrustGapDiagnosticError("MISSING_TRUST_FIELDS signal must have UNIQUE_POLICY_MATCH")
    if signal.get("next") != "READ_TRUST_GAPS":
        raise TrustGapDiagnosticError("MISSING_TRUST_FIELDS signal must point to READ_TRUST_GAPS")

    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise TrustGapDiagnosticError("legacy interface artifact is not a valid ZIP archive") from exc

    with archive:
        brief = _mapping(_read_json(archive, "brief.json"), label="brief.json")
        if brief.get("contract_version") != _OPERATIONAL_BRIEF_CONTRACT_VERSION:
            raise TrustGapDiagnosticError("trust-gap brief must use PIE_OPERATIONAL_BRIEF_V1")
        if brief.get("signal_reason") != "MISSING_TRUST_FIELDS":
            raise TrustGapDiagnosticError("trust-gap brief signal_reason does not match signal")
        if brief.get("match_status") != "UNIQUE_POLICY_MATCH":
            raise TrustGapDiagnosticError("trust-gap brief match_status does not match signal")

        operational_class = _nonempty_string(
            brief.get("operational_class"), label="brief.operational_class"
        )
        trust_task_class = _nonempty_string(
            brief.get("trust_task_class"), label="brief.trust_task_class"
        )
        required = _mapping(brief.get("required"), label="brief.required")
        required_scenarios = sorted(_string_list(required.get("scenarios"), label="brief.required.scenarios"))
        required_evidence = sorted(_string_list(required.get("evidence"), label="brief.required.evidence"))
        missing = sorted(_string_list(brief.get("missing"), label="brief.missing"))
        if not missing:
            raise TrustGapDiagnosticError("MISSING_TRUST_FIELDS brief must contain at least one missing field")
        read_evidence = sorted(_string_list(brief.get("read_evidence"), label="brief.read_evidence"))

        index = _mapping(_read_json(archive, "targeted/index.json"), label="targeted/index.json")
        if sorted(index) != read_evidence:
            raise TrustGapDiagnosticError("brief.read_evidence must match targeted/index.json keys")

        targeted: list[dict[str, Any]] = []
        for evidence_id, path in sorted(index.items()):
            if not isinstance(evidence_id, str) or not evidence_id:
                raise TrustGapDiagnosticError("targeted evidence id must be a non-empty string")
            if not isinstance(path, str) or not path.startswith("targeted/") or not path.endswith(".json"):
                raise TrustGapDiagnosticError("targeted evidence path must be targeted JSON")
            item = _mapping(_read_json(archive, path), label=path)
            if item.get("contract_version") != _TARGETED_EVIDENCE_CONTRACT_VERSION:
                raise TrustGapDiagnosticError(f"{path} must use PIE_TARGETED_EVIDENCE_V1")
            if item.get("id") != evidence_id:
                raise TrustGapDiagnosticError(f"{path} id does not match targeted index")
            provenance = _mapping(item.get("provenance"), label=f"{path}.provenance")
            targeted.append(
                {
                    "id": evidence_id,
                    "kind": _nonempty_string(item.get("kind"), label=f"{path}.kind"),
                    "requirement": _nonempty_string(
                        item.get("requirement"), label=f"{path}.requirement"
                    ),
                    "state": _nonempty_string(item.get("state"), label=f"{path}.state"),
                    "observed_present": item.get("observed") is not None,
                    "policy_revision": provenance.get("policy_revision"),
                    "policy_sha256": provenance.get("policy_sha256"),
                    "binding_sha256": provenance.get("binding_sha256"),
                    "facts_sha256": provenance.get("facts_sha256"),
                }
            )

    return {
        "interface_sha256": interface["interface_sha256"],
        "operational_class": operational_class,
        "trust_task_class": trust_task_class,
        "required": {
            "scenarios": required_scenarios,
            "evidence": required_evidence,
        },
        "missing_fields": missing,
        "targeted_evidence": targeted,
    }


def build_historical_trust_gap_observation(
    *,
    repository: str,
    pie_revision: str,
    run: Mapping[str, Any],
    artifact: Mapping[str, Any],
    artifact_zip: bytes,
) -> dict[str, Any] | None:
    parsed = parse_legacy_trust_gap_artifact(artifact_zip)
    if parsed is None:
        return None

    run_id = run.get("id")
    run_attempt = run.get("run_attempt")
    head_sha = run.get("head_sha")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        raise TrustGapDiagnosticError("workflow run id must be a positive integer")
    if isinstance(run_attempt, bool) or not isinstance(run_attempt, int) or run_attempt <= 0:
        raise TrustGapDiagnosticError("workflow run attempt must be a positive integer")
    if not isinstance(head_sha, str) or len(head_sha) != 40:
        raise TrustGapDiagnosticError("workflow run head_sha must be an exact Git SHA")

    artifact_id = artifact.get("id")
    artifact_name = artifact.get("name")
    artifact_run = _mapping(artifact.get("workflow_run"), label="artifact.workflow_run")
    if isinstance(artifact_id, bool) or not isinstance(artifact_id, int) or artifact_id <= 0:
        raise TrustGapDiagnosticError("artifact id must be a positive integer")
    if not isinstance(artifact_name, str) or not artifact_name:
        raise TrustGapDiagnosticError("artifact name must be a non-empty string")
    if artifact_run.get("id") != run_id or artifact_run.get("head_sha") != head_sha:
        raise TrustGapDiagnosticError("artifact workflow identity does not match workflow run")
    encoded_head = artifact_name.rsplit("-interface", 1)[0].split("-")[-2]
    if encoded_head != head_sha.lower()[:12]:
        raise TrustGapDiagnosticError("legacy compact artifact head prefix does not match workflow run")

    identity = {
        "repository": repository.strip().lower(),
        "pull_request": parse_pull_request_from_interface_artifact_name(artifact_name),
        "source_revision": head_sha.lower(),
        "pie_revision": pie_revision.strip().lower(),
    }
    key = canonical_json_sha256(identity)
    semantic_body = {
        "contract_version": TRUST_GAP_OBSERVATION_CONTRACT_VERSION,
        "identity": identity,
        "interface_sha256": parsed["interface_sha256"],
        "operational_class": parsed["operational_class"],
        "trust_task_class": parsed["trust_task_class"],
        "required": parsed["required"],
        "missing_fields": parsed["missing_fields"],
        "targeted_evidence": parsed["targeted_evidence"],
    }
    semantic_sha256 = canonical_json_sha256(semantic_body)
    body = {
        **semantic_body,
        "calibration_key_sha256": key,
        "semantic_sha256": semantic_sha256,
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
    return {
        outer: dict(sorted(counter.items()))
        for outer, counter in sorted(values.items())
    }


def build_trust_gap_diagnostic(
    observations: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    values = [dict(item) for item in observations]
    if not values:
        raise TrustGapDiagnosticError("at least one historical trust-gap observation is required")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in values:
        if observation.get("contract_version") != TRUST_GAP_OBSERVATION_CONTRACT_VERSION:
            raise TrustGapDiagnosticError("unsupported trust-gap observation contract")
        if observation.get("authority") != _OBSERVATION_AUTHORITY:
            raise TrustGapDiagnosticError("trust-gap observation authority boundary changed")
        key = _nonempty_string(
            observation.get("calibration_key_sha256"), label="calibration_key_sha256"
        )
        _nonempty_string(observation.get("semantic_sha256"), label="semantic_sha256")
        body = dict(observation)
        recorded_hash = body.pop("observation_sha256", None)
        if canonical_json_sha256(body) != recorded_hash:
            raise TrustGapDiagnosticError("trust-gap observation hash mismatch")
        grouped[key].append(observation)

    unique: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        semantic_hashes = {item["semantic_sha256"] for item in items}
        if len(semantic_hashes) != 1:
            raise TrustGapDiagnosticError(
                f"same calibration key produced conflicting trust-gap observations: {key}"
            )
        unique.append(items[0])

    missing_field = Counter()
    missing_set = Counter()
    operational_class = Counter()
    trust_task_class = Counter()
    targeted_gap_id = Counter()
    targeted_kind = Counter()
    policy_sha256 = Counter()
    facts_provenance = Counter()
    by_repository_missing_field: dict[str, Counter[str]] = defaultdict(Counter)
    by_trust_task_class_missing_field: dict[str, Counter[str]] = defaultdict(Counter)
    by_operational_class_missing_field: dict[str, Counter[str]] = defaultdict(Counter)
    by_policy_missing_field: dict[str, Counter[str]] = defaultdict(Counter)
    missing_targeted_item_total = 0
    all_missing_targeted_items_lack_facts_count = 0

    for observation in unique:
        repository = observation["identity"]["repository"]
        op_class = observation["operational_class"]
        task_class = observation["trust_task_class"]
        operational_class[op_class] += 1
        trust_task_class[task_class] += 1

        fields = sorted(observation["missing_fields"])
        missing_set["|".join(fields)] += 1
        policies: set[str] = set()
        for field in fields:
            missing_field[field] += 1
            by_repository_missing_field[repository][field] += 1
            by_trust_task_class_missing_field[task_class][field] += 1
            by_operational_class_missing_field[op_class][field] += 1

        missing_items = [
            item for item in observation["targeted_evidence"]
            if item.get("state") == "MISSING"
        ]
        if missing_items and all(item.get("facts_sha256") is None for item in missing_items):
            all_missing_targeted_items_lack_facts_count += 1
        for item in missing_items:
            missing_targeted_item_total += 1
            targeted_gap_id[item["id"]] += 1
            targeted_kind[item["kind"]] += 1
            facts_provenance["ABSENT" if item.get("facts_sha256") is None else "PRESENT"] += 1
            policy = item.get("policy_sha256")
            if isinstance(policy, str) and policy:
                policies.add(policy)
                policy_sha256[policy] += 1
        for policy in policies:
            for field in fields:
                by_policy_missing_field[policy][field] += 1

    body = {
        "contract_version": TRUST_GAP_DIAGNOSTIC_CONTRACT_VERSION,
        "input_observation_count": len(values),
        "unique_calibration_count": len(unique),
        "duplicate_observation_count": len(values) - len(unique),
        "histograms": {
            "missing_field": dict(sorted(missing_field.items())),
            "missing_set": dict(sorted(missing_set.items())),
            "operational_class": dict(sorted(operational_class.items())),
            "trust_task_class": dict(sorted(trust_task_class.items())),
            "targeted_gap_id": dict(sorted(targeted_gap_id.items())),
            "targeted_kind": dict(sorted(targeted_kind.items())),
            "policy_sha256": dict(sorted(policy_sha256.items())),
            "facts_provenance": dict(sorted(facts_provenance.items())),
        },
        "breakdowns": {
            "repository_missing_field": _nested_counter_to_dict(by_repository_missing_field),
            "trust_task_class_missing_field": _nested_counter_to_dict(
                by_trust_task_class_missing_field
            ),
            "operational_class_missing_field": _nested_counter_to_dict(
                by_operational_class_missing_field
            ),
            "policy_missing_field": _nested_counter_to_dict(by_policy_missing_field),
        },
        "targeted": {
            "missing_item_total": missing_targeted_item_total,
            "all_missing_items_lack_facts_observation_count": (
                all_missing_targeted_items_lack_facts_count
            ),
        },
        "authority": deepcopy(_DIAGNOSTIC_AUTHORITY),
    }
    return {**body, "diagnostic_sha256": canonical_json_sha256(body)}

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping

from .calibration_observation import CalibrationObservationError, build_calibration_ledger
from .identity import canonical_json_sha256
from .operational_policy_match_explanation import (
    AMBIGUITY_MECHANISMS,
    CONTRACT_VERSION as OPERATIONAL_CONTRACT_VERSION,
    SCHEMA_VERSION as OPERATIONAL_SCHEMA_VERSION,
)


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_CALIBRATION_POLICY_MATCH_EXPLANATION_V1"
LEDGER_CONTRACT_VERSION = "PIE_CALIBRATION_POLICY_MATCH_EXPLANATION_LEDGER_V1"
FILENAME = "policy-match-explanation.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_SOURCE_AUTHORITY = {
    "operational_class_resolution_authorized": False,
    "trust_fact_inferred": False,
    "human_review_inferred": False,
    "outcome_inferred": False,
    "merge_authorized": False,
    "deploy_authorized": False,
    "production_effect_authorized": False,
}
_AUTHORITY = {
    "calibration_only": True,
    **_SOURCE_AUTHORITY,
}


class CalibrationPolicyMatchExplanationError(RuntimeError):
    pass


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibrationPolicyMatchExplanationError(f"{label} must contain an object")
    return value


def _string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationPolicyMatchExplanationError(f"{label} must be a non-empty string")
    return value.strip()


def _sha256(value: Any, *, label: str) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if _SHA256.fullmatch(normalized) is None:
        raise CalibrationPolicyMatchExplanationError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return normalized


def _normalized_path(value: Any, *, label: str) -> str:
    raw = _string(value, label=label).replace("\\", "/")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise CalibrationPolicyMatchExplanationError(
            f"{label} must remain project-relative"
        )
    normalized = path.as_posix()
    if normalized != raw:
        raise CalibrationPolicyMatchExplanationError(f"{label} must already be normalized")
    return normalized


def _sorted_unique_strings(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise CalibrationPolicyMatchExplanationError(f"{label} must be an array")
    normalized = [_string(item, label=f"{label}[{index}]") for index, item in enumerate(value)]
    if normalized != sorted(set(normalized)):
        raise CalibrationPolicyMatchExplanationError(
            f"{label} must be sorted and contain no duplicates"
        )
    return normalized


def _mechanism(path_matches: list[dict[str, Any]], matched_classes: list[str]) -> str:
    if len(matched_classes) <= 1:
        return "NONE"
    multi_class_rows = [
        row for row in path_matches if len(row["matched_operational_classes"]) > 1
    ]
    if not multi_class_rows:
        return "MULTI_PATH_MULTI_CLASS"
    same_path_classes = {
        class_id
        for row in multi_class_rows
        for class_id in row["matched_operational_classes"]
    }
    if set(matched_classes) - same_path_classes:
        return "MIXED"
    return "SAME_PATH_MULTI_CLASS"


def _validate_source_explanation(value: Any) -> dict[str, Any]:
    source = _mapping(value, label="policy_match_explanation")
    expected_top_level = {
        "schema_version",
        "contract_version",
        "project_id",
        "policy",
        "changed_files",
        "matched_operational_classes",
        "match_cardinality",
        "ambiguous",
        "ambiguity_mechanism",
        "path_matches",
        "authority",
        "explanation_sha256",
    }
    if set(source) != expected_top_level:
        raise CalibrationPolicyMatchExplanationError(
            "policy match explanation has unexpected fields"
        )
    if source.get("schema_version") != OPERATIONAL_SCHEMA_VERSION:
        raise CalibrationPolicyMatchExplanationError("source explanation schema_version mismatch")
    if source.get("contract_version") != OPERATIONAL_CONTRACT_VERSION:
        raise CalibrationPolicyMatchExplanationError("source explanation contract_version mismatch")

    project_id = _string(source.get("project_id"), label="project_id")
    policy = _mapping(source.get("policy"), label="policy")
    if set(policy) != {"contract_version", "policy_authority", "policy_sha256"}:
        raise CalibrationPolicyMatchExplanationError("policy has unexpected fields")
    normalized_policy = {
        "contract_version": _string(policy.get("contract_version"), label="policy.contract_version"),
        "policy_authority": _string(policy.get("policy_authority"), label="policy.policy_authority"),
        "policy_sha256": _sha256(policy.get("policy_sha256"), label="policy.policy_sha256"),
    }

    changed_files_raw = source.get("changed_files")
    if not isinstance(changed_files_raw, list):
        raise CalibrationPolicyMatchExplanationError("changed_files must be an array")
    changed_files = [
        _normalized_path(item, label=f"changed_files[{index}]")
        for index, item in enumerate(changed_files_raw)
    ]
    if changed_files != sorted(set(changed_files)):
        raise CalibrationPolicyMatchExplanationError(
            "changed_files must be sorted and contain no normalized duplicates"
        )

    matched_classes = _sorted_unique_strings(
        source.get("matched_operational_classes"),
        label="matched_operational_classes",
    )
    cardinality = source.get("match_cardinality")
    if isinstance(cardinality, bool) or not isinstance(cardinality, int) or cardinality < 0:
        raise CalibrationPolicyMatchExplanationError(
            "match_cardinality must be a non-negative integer"
        )
    if cardinality != len(matched_classes):
        raise CalibrationPolicyMatchExplanationError(
            "match_cardinality does not match matched_operational_classes"
        )
    ambiguous = source.get("ambiguous")
    if not isinstance(ambiguous, bool):
        raise CalibrationPolicyMatchExplanationError("ambiguous must be boolean")
    if ambiguous != (cardinality > 1):
        raise CalibrationPolicyMatchExplanationError(
            "ambiguous does not match match_cardinality"
        )

    path_matches_raw = source.get("path_matches")
    if not isinstance(path_matches_raw, list):
        raise CalibrationPolicyMatchExplanationError("path_matches must be an array")
    if len(path_matches_raw) != len(changed_files):
        raise CalibrationPolicyMatchExplanationError(
            "path_matches must have exactly one row per changed file"
        )
    path_matches: list[dict[str, Any]] = []
    union: set[str] = set()
    for index, raw_row in enumerate(path_matches_raw):
        row = _mapping(raw_row, label=f"path_matches[{index}]")
        if set(row) != {"path", "matched_operational_classes"}:
            raise CalibrationPolicyMatchExplanationError(
                f"path_matches[{index}] has unexpected fields"
            )
        path = _normalized_path(row.get("path"), label=f"path_matches[{index}].path")
        if path != changed_files[index]:
            raise CalibrationPolicyMatchExplanationError(
                "path_matches order/path must exactly match changed_files"
            )
        classes = _sorted_unique_strings(
            row.get("matched_operational_classes"),
            label=f"path_matches[{index}].matched_operational_classes",
        )
        union.update(classes)
        path_matches.append({"path": path, "matched_operational_classes": classes})
    if sorted(union) != matched_classes:
        raise CalibrationPolicyMatchExplanationError(
            "path_matches class union does not match matched_operational_classes"
        )

    mechanism = source.get("ambiguity_mechanism")
    if mechanism not in AMBIGUITY_MECHANISMS:
        raise CalibrationPolicyMatchExplanationError(
            f"unsupported ambiguity_mechanism: {mechanism!r}"
        )
    if mechanism != _mechanism(path_matches, matched_classes):
        raise CalibrationPolicyMatchExplanationError(
            "ambiguity_mechanism does not match path-match structure"
        )
    if source.get("authority") != _SOURCE_AUTHORITY:
        raise CalibrationPolicyMatchExplanationError(
            "source explanation authority boundary must remain explicitly false"
        )

    body = {
        "schema_version": OPERATIONAL_SCHEMA_VERSION,
        "contract_version": OPERATIONAL_CONTRACT_VERSION,
        "project_id": project_id,
        "policy": normalized_policy,
        "changed_files": changed_files,
        "matched_operational_classes": matched_classes,
        "match_cardinality": cardinality,
        "ambiguous": ambiguous,
        "ambiguity_mechanism": mechanism,
        "path_matches": path_matches,
        "authority": deepcopy(_SOURCE_AUTHORITY),
    }
    explanation_hash = _sha256(
        source.get("explanation_sha256"), label="explanation_sha256"
    )
    if canonical_json_sha256(body) != explanation_hash:
        raise CalibrationPolicyMatchExplanationError(
            "explanation_sha256 does not match source explanation body"
        )
    return {**body, "explanation_sha256": explanation_hash}


def build_calibration_policy_match_explanation_sidecar(
    *,
    calibration_record: Mapping[str, Any],
    policy_match_explanation: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        ledger = build_calibration_ledger([calibration_record])
    except CalibrationObservationError as exc:
        raise CalibrationPolicyMatchExplanationError(
            f"invalid calibration record: {exc}"
        ) from exc
    entry = ledger["entries"][0]
    source = _validate_source_explanation(policy_match_explanation)

    explanation = {
        "project_id": source["project_id"],
        "policy": deepcopy(source["policy"]),
        "changed_files": deepcopy(source["changed_files"]),
        "matched_operational_classes": deepcopy(source["matched_operational_classes"]),
        "match_cardinality": source["match_cardinality"],
        "ambiguous": source["ambiguous"],
        "ambiguity_mechanism": source["ambiguity_mechanism"],
        "path_matches": deepcopy(source["path_matches"]),
    }
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "identity": deepcopy(entry["identity"]),
        "calibration_key_sha256": entry["calibration_key_sha256"],
        "calibration_semantic_sha256": entry["semantic_sha256"],
        "source_explanation": {
            "schema_version": source["schema_version"],
            "contract_version": source["contract_version"],
            "explanation_sha256": source["explanation_sha256"],
        },
        "explanation": explanation,
        "authority": deepcopy(_AUTHORITY),
    }
    return {**body, "sidecar_sha256": canonical_json_sha256(body)}


def _source_from_sidecar(value: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(value.get("source_explanation"), label="source_explanation")
    explanation = _mapping(value.get("explanation"), label="explanation")
    return {
        "schema_version": source.get("schema_version"),
        "contract_version": source.get("contract_version"),
        "project_id": explanation.get("project_id"),
        "policy": deepcopy(explanation.get("policy")),
        "changed_files": deepcopy(explanation.get("changed_files")),
        "matched_operational_classes": deepcopy(
            explanation.get("matched_operational_classes")
        ),
        "match_cardinality": explanation.get("match_cardinality"),
        "ambiguous": explanation.get("ambiguous"),
        "ambiguity_mechanism": explanation.get("ambiguity_mechanism"),
        "path_matches": deepcopy(explanation.get("path_matches")),
        "authority": deepcopy(_SOURCE_AUTHORITY),
        "explanation_sha256": source.get("explanation_sha256"),
    }


def verify_calibration_policy_match_explanation_sidecar(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return ["sidecar must contain an object"]
    expected_top_level = {
        "schema_version",
        "contract_version",
        "identity",
        "calibration_key_sha256",
        "calibration_semantic_sha256",
        "source_explanation",
        "explanation",
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
    if value.get("authority") != _AUTHORITY:
        errors.append("authority boundary must remain calibration-only and explicitly false")

    try:
        _validate_source_explanation(_source_from_sidecar(value))
    except CalibrationPolicyMatchExplanationError as exc:
        errors.append(str(exc))

    body = deepcopy(dict(value))
    sidecar_hash = body.pop("sidecar_sha256", None)
    if not isinstance(sidecar_hash, str) or _SHA256.fullmatch(sidecar_hash) is None:
        errors.append("sidecar_sha256 must be a lowercase SHA-256 digest")
    elif canonical_json_sha256(body) != sidecar_hash:
        errors.append("sidecar_sha256 mismatch")
    return sorted(set(errors))


def verify_calibration_policy_match_explanation_binding(
    calibration_record: Mapping[str, Any],
    sidecar: Mapping[str, Any],
) -> list[str]:
    errors = list(verify_calibration_policy_match_explanation_sidecar(sidecar))
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


def write_calibration_policy_match_explanation_sidecar(
    root: str | Path,
    value: Mapping[str, Any],
) -> Path:
    errors = verify_calibration_policy_match_explanation_sidecar(value)
    if errors:
        raise CalibrationPolicyMatchExplanationError(
            "invalid calibration policy-match explanation sidecar: " + "; ".join(errors)
        )
    target = Path(root).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    path = target / FILENAME
    path.write_text(
        json.dumps(dict(value), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def build_calibration_policy_match_explanation_ledger(
    sidecars: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for sidecar in sidecars:
        errors = verify_calibration_policy_match_explanation_sidecar(sidecar)
        if errors:
            raise CalibrationPolicyMatchExplanationError(
                "invalid calibration policy-match explanation sidecar: "
                + "; ".join(errors)
            )
        values.append(deepcopy(dict(sidecar)))
    if not values:
        raise CalibrationPolicyMatchExplanationError(
            "at least one calibration policy-match explanation sidecar is required"
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for sidecar in values:
        grouped.setdefault(sidecar["calibration_key_sha256"], []).append(sidecar)

    entries: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        explanation_hashes = {
            item["source_explanation"]["explanation_sha256"] for item in items
        }
        sidecar_hashes = {item["sidecar_sha256"] for item in items}
        if len(explanation_hashes) != 1 or len(sidecar_hashes) != 1:
            raise CalibrationPolicyMatchExplanationError(
                "same calibration key produced conflicting policy-match explanations: "
                + key
            )
        first = items[0]
        entries.append(
            {
                "calibration_key_sha256": key,
                "calibration_semantic_sha256": first["calibration_semantic_sha256"],
                "identity": deepcopy(first["identity"]),
                "source_explanation": deepcopy(first["source_explanation"]),
                "explanation": deepcopy(first["explanation"]),
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
            "ambiguity_mechanism": histogram(
                lambda entry: entry["explanation"]["ambiguity_mechanism"]
            ),
            "ambiguous": histogram(lambda entry: entry["explanation"]["ambiguous"]),
            "match_cardinality": histogram(
                lambda entry: entry["explanation"]["match_cardinality"]
            ),
            "changed_file_count": histogram(
                lambda entry: len(entry["explanation"]["changed_files"])
            ),
        },
        "entries": entries,
        "authority": deepcopy(_AUTHORITY),
    }
    return {**body, "ledger_sha256": canonical_json_sha256(body)}

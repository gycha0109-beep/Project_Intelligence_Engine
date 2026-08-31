from __future__ import annotations

from io import BytesIO
import json
import re
from typing import Any, Mapping
from zipfile import BadZipFile, ZipFile

from .calibration_observation import build_calibration_record


BACKFILL_SOURCE_CONTRACT_VERSION = "PIE_CALIBRATION_BACKFILL_SOURCE_V1"
LEGACY_INTERFACE_CONTRACT_VERSION = "PIE_GPT_OPERATIONAL_INTERFACE_V1"
_SIGNAL_CONTRACT_VERSION = "PIE_SIGNAL_V1"
_PR_FROM_ARTIFACT = re.compile(r"-pr-(?P<pr>[1-9][0-9]*)-[0-9a-f]{12}-[0-9a-f]{12}-interface$")


class CalibrationBackfillError(RuntimeError):
    pass


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibrationBackfillError(f"{label} must be an object")
    return value


def _nonempty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationBackfillError(f"{label} must be a non-empty string")
    return value.strip()


def _read_json(archive: ZipFile, path: str) -> Any:
    try:
        raw = archive.read(path)
    except KeyError as exc:
        raise CalibrationBackfillError(f"legacy interface artifact is missing {path}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalibrationBackfillError(f"legacy interface artifact has invalid JSON at {path}") from exc


def _validate_targeted_index(value: Any) -> dict[str, str]:
    mapping = _mapping(value, label="targeted/index.json")
    result: dict[str, str] = {}
    for key, path in mapping.items():
        if not isinstance(key, str) or not key:
            raise CalibrationBackfillError("targeted/index.json keys must be non-empty strings")
        if not isinstance(path, str) or not path.startswith("targeted/") or not path.endswith(".json"):
            raise CalibrationBackfillError("targeted/index.json values must be targeted JSON paths")
        result[key] = path
    return result


def parse_legacy_interface_artifact(payload: bytes) -> dict[str, Any]:
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise CalibrationBackfillError("legacy interface artifact is not a valid ZIP archive") from exc

    with archive:
        manifest = _mapping(_read_json(archive, "manifest.json"), label="manifest.json")
        if manifest.get("contract_version") != LEGACY_INTERFACE_CONTRACT_VERSION:
            raise CalibrationBackfillError("legacy interface manifest must use PIE_GPT_OPERATIONAL_INTERFACE_V1")

        level0 = _mapping(manifest.get("level0"), label="manifest.level0")
        if level0.get("signal") != "signal.json":
            raise CalibrationBackfillError("manifest.level0.signal must reference signal.json")

        signal = _mapping(_read_json(archive, "signal.json"), label="signal.json")
        if signal.get("contract_version") != _SIGNAL_CONTRACT_VERSION:
            raise CalibrationBackfillError("legacy signal must use PIE_SIGNAL_V1")

        level1 = _mapping(manifest.get("level1"), label="manifest.level1")
        brief_ref = level1.get("brief")
        if brief_ref is None:
            brief = None
        elif brief_ref == "brief.json":
            brief = _mapping(_read_json(archive, "brief.json"), label="brief.json")
        else:
            raise CalibrationBackfillError("manifest.level1.brief must be null or brief.json")

        level2 = _mapping(manifest.get("level2"), label="manifest.level2")
        if level2.get("index") != "targeted/index.json":
            raise CalibrationBackfillError("manifest.level2.index must reference targeted/index.json")
        targeted = _validate_targeted_index(_read_json(archive, "targeted/index.json"))
        items = _validate_targeted_index(level2.get("items"))
        if items != targeted:
            raise CalibrationBackfillError("manifest.level2.items must match targeted/index.json")

        level3 = _mapping(manifest.get("level3"), label="manifest.level3")
        if level3.get("full_capsule") != "SEPARATE_ARTIFACT":
            raise CalibrationBackfillError("legacy level3 full capsule must remain a separate artifact")

        interface_sha256 = _nonempty_string(manifest.get("interface_sha256"), label="manifest.interface_sha256")

        return {
            "signal": dict(signal),
            "brief": dict(brief) if isinstance(brief, Mapping) else None,
            "targeted_evidence_ids": list(targeted),
            "targeted_evidence": {},
            "interface_sha256": interface_sha256,
        }


def parse_pull_request_from_interface_artifact_name(name: str) -> int:
    normalized = _nonempty_string(name, label="artifact.name")
    match = _PR_FROM_ARTIFACT.search(normalized)
    if match is None:
        raise CalibrationBackfillError("legacy compact artifact name does not encode a PR number")
    return int(match.group("pr"))


def _run_references_revision(run: Mapping[str, Any], pie_revision: str) -> bool:
    references = run.get("referenced_workflows")
    if not isinstance(references, list):
        return False
    for item in references:
        if not isinstance(item, Mapping):
            continue
        sha = item.get("sha")
        path = item.get("path")
        if sha == pie_revision:
            return True
        if isinstance(path, str) and path.endswith(f"@{pie_revision}"):
            return True
    return False


def build_historical_calibration_record(
    *,
    repository: str,
    pie_revision: str,
    run: Mapping[str, Any],
    artifact: Mapping[str, Any],
    artifact_zip: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not _run_references_revision(run, pie_revision):
        raise CalibrationBackfillError("workflow run does not reference the requested PIE revision")

    run_id = run.get("id")
    run_attempt = run.get("run_attempt")
    head_sha = run.get("head_sha")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        raise CalibrationBackfillError("workflow run id must be a positive integer")
    if isinstance(run_attempt, bool) or not isinstance(run_attempt, int) or run_attempt <= 0:
        raise CalibrationBackfillError("workflow run attempt must be a positive integer")
    if not isinstance(head_sha, str):
        raise CalibrationBackfillError("workflow run head_sha must be a string")

    artifact_id = artifact.get("id")
    artifact_name = artifact.get("name")
    artifact_run = artifact.get("workflow_run")
    if isinstance(artifact_id, bool) or not isinstance(artifact_id, int) or artifact_id <= 0:
        raise CalibrationBackfillError("artifact id must be a positive integer")
    if not isinstance(artifact_name, str):
        raise CalibrationBackfillError("artifact name must be a string")
    artifact_run = _mapping(artifact_run, label="artifact.workflow_run")
    if artifact_run.get("id") != run_id or artifact_run.get("head_sha") != head_sha:
        raise CalibrationBackfillError("artifact workflow identity does not match workflow run")

    interface = parse_legacy_interface_artifact(artifact_zip)
    pull_request = parse_pull_request_from_interface_artifact_name(artifact_name)
    record = build_calibration_record(
        repository=repository,
        pull_request=pull_request,
        source_revision=head_sha,
        pie_revision=pie_revision,
        execution_id=f"legacy-interface-artifact:{artifact_id}",
        workflow_run_id=str(run_id),
        workflow_run_attempt=run_attempt,
        interface=interface,
    )
    source = {
        "contract_version": BACKFILL_SOURCE_CONTRACT_VERSION,
        "record_sha256": record["record_sha256"],
        "source": {
            "kind": "LEGACY_COMPACT_INTERFACE_ARTIFACT",
            "repository": repository.lower(),
            "artifact_id": artifact_id,
            "artifact_name": artifact_name,
            "artifact_digest": artifact.get("digest"),
            "artifact_created_at": artifact.get("created_at"),
            "workflow_run_id": run_id,
            "workflow_run_attempt": run_attempt,
            "head_sha": head_sha.lower(),
            "pie_revision": pie_revision.lower(),
        },
        "authority": {
            "historical_observation_only": True,
            "trust_fact_inferred": False,
            "outcome_inferred": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
    }
    return record, source

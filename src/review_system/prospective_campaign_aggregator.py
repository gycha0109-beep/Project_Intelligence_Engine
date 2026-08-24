from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Iterable

from .identity import canonical_json_sha256
from .prospective_evidence_bundle import verify_evidence_bundle


AGGREGATION_SCHEMA_VERSION = "PIE_AUTO4_ARTIFACT_AGGREGATION_V1"
WORKFLOW_CONTEXT_SCHEMA_VERSION = "PIE_PROSPECTIVE_WORKFLOW_CONTEXT_V1"
_AUTHORITY_FIELDS = (
    "human_review_recorded",
    "outcome_recorded",
    "automation_authorized",
    "pilot_authorized",
    "merge_authorized",
    "deploy_authorized",
    "production_effect_authorized",
)


class ProspectiveCampaignAggregationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProspectiveCampaignAggregationError("INVALID_INPUT", f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ProspectiveCampaignAggregationError("INVALID_INPUT", f"{label} must be a JSON object: {path}")
    return value


def _artifact_layout(value: str | Path) -> tuple[Path, Path, Path | None]:
    root = Path(value).expanduser()
    if root.is_symlink():
        raise ProspectiveCampaignAggregationError("INVALID_INPUT", f"artifact root must not be a symlink: {root}")
    root = root.resolve()
    if not root.is_dir():
        raise ProspectiveCampaignAggregationError("INVALID_INPUT", f"artifact root does not exist: {root}")

    staged_bundle = root / "bundle"
    if (staged_bundle / "manifest.json").is_file():
        context = root / "workflow-context.json"
        return root, staged_bundle.resolve(), context.resolve() if context.is_file() else None
    if (root / "manifest.json").is_file():
        return root, root, None
    raise ProspectiveCampaignAggregationError(
        "INVALID_INPUT",
        f"artifact root must contain bundle/manifest.json or manifest.json: {root}",
    )


def _require_equal(label: str, expected: Any, actual: Any) -> None:
    if expected != actual:
        raise ProspectiveCampaignAggregationError(
            "SOURCE_MISMATCH",
            f"{label} mismatch: expected={expected!r} actual={actual!r}",
        )


def _validate_authority(value: dict[str, Any], *, label: str, allow_missing: bool) -> None:
    for field in _AUTHORITY_FIELDS:
        if field not in value:
            if allow_missing:
                continue
            raise ProspectiveCampaignAggregationError(
                "AUTHORITY_VIOLATION",
                f"{label}.{field} must be explicitly present and false",
            )
        if value[field] is not False:
            raise ProspectiveCampaignAggregationError(
                "AUTHORITY_VIOLATION",
                f"{label}.{field} must remain false",
            )


def _read_observation(value: str | Path) -> dict[str, Any]:
    artifact_root, bundle_root, context_path = _artifact_layout(value)
    errors = verify_evidence_bundle(bundle_root)
    if errors:
        raise ProspectiveCampaignAggregationError(
            "EVIDENCE_HASH_MISMATCH",
            "; ".join(errors),
        )

    manifest = _load_json_object(bundle_root / "manifest.json", "evidence manifest")
    summary = _load_json_object(bundle_root / "summary.json", "prospective summary")
    identity = _load_json_object(bundle_root / "source" / "execution-identity.json", "execution identity")
    deterministic_path = bundle_root / "deterministic-result.json"
    if not deterministic_path.is_file() or deterministic_path.is_symlink():
        raise ProspectiveCampaignAggregationError(
            "NON_DETERMINISTIC_REPLAY",
            f"deterministic-result.json is required for AUTO-4A aggregation: {bundle_root}",
        )
    deterministic = _load_json_object(deterministic_path, "deterministic result")

    execution_id = manifest.get("execution_id")
    execution_key = manifest.get("execution_key_sha256")
    deterministic_hash = manifest.get("deterministic_result_sha256")
    repository = manifest.get("repository")
    pull_request = manifest.get("pull_request")
    source_revision = manifest.get("source_revision")
    pie_revision = manifest.get("pie_revision")
    raw_manifest_hash = manifest.get("manifest_sha256")

    bindings = (
        ("summary.execution_id", execution_id, summary.get("execution_id")),
        ("identity.execution_id", execution_id, identity.get("execution_id")),
        ("identity.execution_key_sha256", execution_key, identity.get("execution_key_sha256")),
        ("summary.repository", repository, summary.get("repository")),
        ("identity.repository", repository, identity.get("repository")),
        ("summary.pull_request", pull_request, summary.get("pull_request")),
        ("identity.pull_request", pull_request, identity.get("pull_request")),
        ("summary.source_revision", source_revision, summary.get("source_revision")),
        ("identity.source_revision", source_revision, identity.get("source_revision")),
        ("summary.pie_revision", pie_revision, summary.get("pie_revision")),
        ("identity.pie_revision", pie_revision, identity.get("pie_revision")),
        ("summary.deterministic_result_sha256", deterministic_hash, summary.get("deterministic_result_sha256")),
        (
            "deterministic_result.deterministic_result_sha256",
            deterministic_hash,
            deterministic.get("deterministic_result_sha256"),
        ),
    )
    for label, expected, actual in bindings:
        _require_equal(label, expected, actual)

    deterministic_identity = deterministic.get("execution_identity")
    if not isinstance(deterministic_identity, dict):
        raise ProspectiveCampaignAggregationError(
            "NON_DETERMINISTIC_REPLAY",
            "deterministic result is missing execution_identity",
        )
    _require_equal("deterministic execution_id", execution_id, deterministic_identity.get("execution_id"))
    _require_equal(
        "deterministic execution_key_sha256",
        execution_key,
        deterministic_identity.get("execution_key_sha256"),
    )

    _validate_authority(summary, label="summary", allow_missing=True)

    context: dict[str, Any] | None = None
    if context_path is not None:
        context = _load_json_object(context_path, "workflow context")
        if context.get("schema_version") != WORKFLOW_CONTEXT_SCHEMA_VERSION:
            raise ProspectiveCampaignAggregationError(
                "SOURCE_MISMATCH",
                "workflow context schema_version mismatch",
            )
        context_bindings = (
            ("workflow_context.repository", repository, context.get("repository")),
            ("workflow_context.pull_request", pull_request, context.get("pull_request")),
            ("workflow_context.source_revision", source_revision, context.get("source_revision")),
            ("workflow_context.pie_revision", pie_revision, context.get("pie_revision")),
            ("workflow_context.execution_id", execution_id, context.get("execution_id")),
            (
                "workflow_context.deterministic_result_sha256",
                deterministic_hash,
                context.get("deterministic_result_sha256"),
            ),
            (
                "workflow_context.raw_observation_manifest_sha256",
                raw_manifest_hash,
                context.get("raw_observation_manifest_sha256"),
            ),
        )
        for label, expected, actual in context_bindings:
            _require_equal(label, expected, actual)
        authority = context.get("authority")
        if not isinstance(authority, dict):
            raise ProspectiveCampaignAggregationError(
                "AUTHORITY_VIOLATION",
                "workflow context authority must be an object",
            )
        _validate_authority(authority, label="workflow_context.authority", allow_missing=False)

    observation_identity = {
        "execution_id": execution_id,
        "raw_observation_manifest_sha256": raw_manifest_hash,
        "workflow_run_id": None if context is None else context.get("workflow_run_id"),
        "workflow_run_attempt": None if context is None else context.get("workflow_run_attempt"),
        "workflow_ref": None if context is None else context.get("workflow_ref"),
    }
    observation_sha256 = canonical_json_sha256(observation_identity)
    return {
        "artifact_root": str(artifact_root),
        "execution_id": execution_id,
        "execution_key_sha256": execution_key,
        "repository": repository,
        "pull_request": pull_request,
        "source_revision": source_revision,
        "pie_revision": pie_revision,
        "status": summary.get("status"),
        "deterministic_result_sha256": deterministic_hash,
        "raw_observation_manifest_sha256": raw_manifest_hash,
        "workflow_context_present": context is not None,
        "workflow_run_id": None if context is None else context.get("workflow_run_id"),
        "workflow_run_attempt": None if context is None else context.get("workflow_run_attempt"),
        "workflow_ref": None if context is None else context.get("workflow_ref"),
        "observation_sha256": observation_sha256,
    }


def _semantic_projection(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "stage": report["stage"],
        "status": report["status"],
        "unique_execution_count": report["unique_execution_count"],
        "unique_observation_count": report["unique_observation_count"],
        "repositories": deepcopy(report["repositories"]),
        "executions": deepcopy(report["executions"]),
        "workspace_mutation_performed": report["workspace_mutation_performed"],
        "campaign_thresholds_evaluated": report["campaign_thresholds_evaluated"],
        "cross_project_knowledge_promotion_authorized": report["cross_project_knowledge_promotion_authorized"],
        "automatic_outcome_inference": report["automatic_outcome_inference"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "merge_authorized": report["merge_authorized"],
        "deploy_authorized": report["deploy_authorized"],
        "production_effect_authorized": report["production_effect_authorized"],
        "next_step": report["next_step"],
    }


def aggregate_prospective_artifacts(artifact_roots: Iterable[str | Path]) -> dict[str, Any]:
    roots = list(artifact_roots)
    if not roots:
        raise ProspectiveCampaignAggregationError("INVALID_INPUT", "at least one artifact root is required")

    observations = [_read_observation(value) for value in roots]
    unique_observations: dict[str, dict[str, Any]] = {}
    for observation in observations:
        unique_observations.setdefault(observation["observation_sha256"], observation)

    by_execution: dict[str, list[dict[str, Any]]] = {}
    execution_key_owner: dict[str, str] = {}
    for observation in unique_observations.values():
        execution_id = observation["execution_id"]
        execution_key = observation["execution_key_sha256"]
        deterministic_hash = observation["deterministic_result_sha256"]
        if not isinstance(execution_id, str) or not execution_id:
            raise ProspectiveCampaignAggregationError("SOURCE_MISMATCH", "execution_id is missing")
        if not isinstance(execution_key, str) or not execution_key:
            raise ProspectiveCampaignAggregationError("SOURCE_MISMATCH", "execution_key_sha256 is missing")
        if not isinstance(deterministic_hash, str) or not deterministic_hash:
            raise ProspectiveCampaignAggregationError("NON_DETERMINISTIC_REPLAY", "deterministic result hash is missing")

        existing_owner = execution_key_owner.setdefault(execution_key, execution_id)
        if existing_owner != execution_id:
            raise ProspectiveCampaignAggregationError(
                "NON_DETERMINISTIC_REPLAY",
                f"execution key {execution_key} maps to multiple execution ids",
            )
        by_execution.setdefault(execution_id, []).append(observation)

    executions: list[dict[str, Any]] = []
    for execution_id, items in sorted(by_execution.items()):
        keys = {item["execution_key_sha256"] for item in items}
        deterministic_hashes = {item["deterministic_result_sha256"] for item in items}
        repositories = {item["repository"] for item in items}
        pull_requests = {item["pull_request"] for item in items}
        revisions = {item["source_revision"] for item in items}
        pie_revisions = {item["pie_revision"] for item in items}
        if len(keys) != 1 or len(deterministic_hashes) != 1:
            raise ProspectiveCampaignAggregationError(
                "NON_DETERMINISTIC_REPLAY",
                f"execution {execution_id} has conflicting execution or deterministic replay identity",
            )
        if len(repositories) != 1 or len(pull_requests) != 1 or len(revisions) != 1 or len(pie_revisions) != 1:
            raise ProspectiveCampaignAggregationError(
                "SOURCE_MISMATCH",
                f"execution {execution_id} has conflicting source identity",
            )
        raw_manifests = sorted({item["raw_observation_manifest_sha256"] for item in items})
        workflow_observations = sorted(
            [
                {
                    "observation_sha256": item["observation_sha256"],
                    "raw_observation_manifest_sha256": item["raw_observation_manifest_sha256"],
                    "workflow_context_present": item["workflow_context_present"],
                    "workflow_run_id": item["workflow_run_id"],
                    "workflow_run_attempt": item["workflow_run_attempt"],
                    "workflow_ref": item["workflow_ref"],
                }
                for item in items
            ],
            key=lambda item: item["observation_sha256"],
        )
        first = items[0]
        executions.append(
            {
                "execution_id": execution_id,
                "execution_key_sha256": next(iter(keys)),
                "repository": next(iter(repositories)),
                "pull_request": next(iter(pull_requests)),
                "source_revision": next(iter(revisions)),
                "pie_revision": next(iter(pie_revisions)),
                "status": first["status"],
                "deterministic_result_sha256": next(iter(deterministic_hashes)),
                "raw_observation_count": len(items),
                "raw_observation_manifest_sha256s": raw_manifests,
                "workflow_observations": workflow_observations,
            }
        )

    repository_map: dict[str, dict[str, Any]] = {}
    for execution in executions:
        repository = execution["repository"]
        entry = repository_map.setdefault(
            repository,
            {"repository": repository, "execution_count": 0, "observation_count": 0, "pull_requests": set()},
        )
        entry["execution_count"] += 1
        entry["observation_count"] += execution["raw_observation_count"]
        entry["pull_requests"].add(execution["pull_request"])
    repositories = [
        {
            "repository": entry["repository"],
            "execution_count": entry["execution_count"],
            "observation_count": entry["observation_count"],
            "pull_requests": sorted(entry["pull_requests"]),
        }
        for _repository, entry in sorted(repository_map.items())
    ]

    report: dict[str, Any] = {
        "schema_version": AGGREGATION_SCHEMA_VERSION,
        "stage": "AUTO-4A",
        "status": "ARTIFACT_AGGREGATION_READY",
        "input_artifact_count": len(roots),
        "unique_observation_count": len(unique_observations),
        "duplicate_observation_count": len(roots) - len(unique_observations),
        "unique_execution_count": len(executions),
        "repositories": repositories,
        "executions": executions,
        "workspace_mutation_performed": False,
        "campaign_thresholds_evaluated": False,
        "cross_project_knowledge_promotion_authorized": False,
        "automatic_outcome_inference": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
        "next_step": "PROJECT_LOCAL_CAMPAIGN_PROJECTION_REQUIRED",
        "aggregation_sha256": "0" * 64,
    }
    report["aggregation_sha256"] = canonical_json_sha256(_semantic_projection(report))
    return report


def write_aggregation_report(path: str | Path, report: dict[str, Any]) -> Path:
    target = Path(path).expanduser()
    if target.is_symlink():
        raise ProspectiveCampaignAggregationError("INVALID_INPUT", f"aggregation output must not be a symlink: {target}")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target

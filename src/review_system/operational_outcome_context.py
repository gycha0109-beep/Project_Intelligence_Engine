from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from .github_connector import GitHubCLI, collect_pull_request
from .identity import canonical_json_sha256
from .io import load_data
from .operational_review_action import (
    AUTHORITY_REPOSITORY,
    OperationalReviewActionError,
    OperationalReviewActionVerificationError,
    _artifact_prefix,
    _download_artifacts,
    _list_authority_artifacts,
    _normalize_repository,
    _path_has_symlink,
    _safe_existing_dir,
    _safe_output,
    inspect_operational_review_source,
    verify_operational_review_action_data,
)
from .paths import asset
from .trust_comparison import load_registry
from .trust_outcome_declaration import (
    CONTRACT_VERSION as AUTO3_DECLARATION_CONTRACT,
    SUPPORTED_AUTHORITIES,
    SUPPORTED_VERDICTS,
)

SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_OPERATIONAL_OUTCOME_CONTEXT_V1"
STATUS = "OUTCOME_DECLARATION_CONTEXT_PREPARED"
NEXT_STEP = "PROVIDE_EXPLICIT_AUTO3A_OUTCOME_DECLARATION"
ORL5_ARTIFACT_PREFIX = "pie-orl5-"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_AUTHORITY_FIELDS_FALSE = (
    "human_outcome_declared",
    "automatic_outcome_inference",
    "outcome_recorded",
    "automation_authorized",
    "pilot_authorized",
    "merge_authorized",
    "deploy_authorized",
    "production_effect_authorized",
)


class OperationalOutcomeContextError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class OperationalOutcomeContextVerificationError(OperationalOutcomeContextError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__(
            "OUTCOME_CONTEXT_INVALID",
            "invalid operational Outcome declaration context: " + "; ".join(self.errors),
        )


@dataclass(frozen=True)
class OperationalOutcomeSource:
    artifact_root: Path
    action: dict[str, Any]
    bridge_root: Path
    workspace_root: Path
    registry: dict[str, Any]
    assessment: dict[str, Any]
    review_event: dict[str, Any]
    review_source: Any

    @property
    def action_key(self) -> str:
        return self.action["action_sha256"]


@dataclass(frozen=True)
class OperationalOutcomeContextRequest:
    target_repository: str
    pull_request: int
    repository_root: str | Path
    artifact_cache_root: str | Path
    output: str | Path


def _schema() -> dict[str, Any]:
    value = load_data(asset("schemas/operational-outcome-context.schema.json"))
    if not isinstance(value, dict):
        raise OperationalOutcomeContextError(
            "CONTRACT_INVALID",
            "operational Outcome context schema must contain an object",
        )
    return value


def _schema_errors(value: Any) -> list[str]:
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _context_hash(value: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(value))
    payload.pop("context_sha256", None)
    return canonical_json_sha256(payload)


def _observation_hash(value: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(value))
    payload.pop("observation_sha256", None)
    return canonical_json_sha256(payload)


def verify_operational_outcome_context_data(value: Any) -> list[str]:
    errors = _schema_errors(value)
    if not isinstance(value, dict):
        return sorted(set(errors or ["context must contain an object"]))
    if value.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    if value.get("status") != STATUS or value.get("next_step") != NEXT_STEP:
        errors.append("status/next_step mismatch")
    authority = value.get("authority", {})
    if authority.get("human_review_recorded") is not True:
        errors.append("authority.human_review_recorded must be true")
    for field in _AUTHORITY_FIELDS_FALSE:
        if authority.get(field) is not False:
            errors.append(f"authority.{field} must remain false")
    if authority.get("merge_observation_is_outcome_authority") is not False:
        errors.append("merge observation must not become Outcome authority")
    if authority.get("ci_observation_is_outcome_authority") is not False:
        errors.append("CI observation must not become Outcome authority")
    auto3 = value.get("auto3_declaration_context", {})
    if auto3.get("declaration_contract_version") != AUTO3_DECLARATION_CONTRACT:
        errors.append("AUTO-3 declaration contract mismatch")
    if auto3.get("declaration_materialized") is not False:
        errors.append("ORL-5 must not materialize an Outcome declaration")
    if auto3.get("selected_authority_type") is not None:
        errors.append("ORL-5 must not select an Outcome authority type")
    if auto3.get("selected_verdict") is not None:
        errors.append("ORL-5 must not select an Outcome verdict")
    observations = value.get("observations", {})
    if isinstance(observations, dict):
        if observations.get("observation_sha256") != _observation_hash(observations):
            errors.append("observations.observation_sha256 mismatch")
    if value.get("context_sha256") != _context_hash(value):
        errors.append("context_sha256 mismatch")
    return sorted(set(errors))


def write_operational_outcome_context(path: str | Path, value: Mapping[str, Any]) -> Path:
    errors = verify_operational_outcome_context_data(value)
    if errors:
        raise OperationalOutcomeContextVerificationError(errors)
    target = _safe_output(path, "operational Outcome context output")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(dict(value), indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def load_operational_outcome_context(path: str | Path) -> tuple[Path, dict[str, Any]]:
    raw = Path(path).expanduser()
    if _path_has_symlink(raw):
        raise OperationalOutcomeContextError("UNSAFE_SOURCE_PATH", f"Outcome context path must not contain symlinks: {raw}")
    try:
        source = raw.resolve(strict=True)
    except OSError as exc:
        raise OperationalOutcomeContextError("SOURCE_NOT_FOUND", f"Outcome context not found: {raw}") from exc
    if not source.is_file():
        raise OperationalOutcomeContextError("SOURCE_NOT_FOUND", f"Outcome context must be a regular file: {source}")
    try:
        raw_bytes = source.read_bytes()
        value = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperationalOutcomeContextError("SOURCE_INVALID", f"Outcome context is not canonical UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise OperationalOutcomeContextError("SOURCE_INVALID", "Outcome context must contain a JSON object")
    canonical = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    if canonical != raw_bytes:
        raise OperationalOutcomeContextVerificationError(["context byte representation is not canonical"])
    errors = verify_operational_outcome_context_data(value)
    if errors:
        raise OperationalOutcomeContextVerificationError(errors)
    return source, value


def _load_action(path: Path) -> dict[str, Any]:
    if _path_has_symlink(path):
        raise OperationalOutcomeContextError("UNSAFE_SOURCE_PATH", f"ORL-4 action path must not contain symlinks: {path}")
    try:
        source = path.resolve(strict=True)
    except OSError as exc:
        raise OperationalOutcomeContextError("SOURCE_NOT_FOUND", f"ORL-4 action not found: {path}") from exc
    if not source.is_file():
        raise OperationalOutcomeContextError("SOURCE_NOT_FOUND", f"ORL-4 action must be a regular file: {source}")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperationalOutcomeContextError("SOURCE_INVALID", f"ORL-4 action is invalid JSON: {exc}") from exc
    errors = verify_operational_review_action_data(value)
    if errors:
        raise OperationalOutcomeContextVerificationError([f"ORL-4 action: {error}" for error in errors])
    assert isinstance(value, dict)
    return value


def _review_event_binding(*, action: dict[str, Any], workspace_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _registry_path, registry = load_registry(workspace_root / "comparison-registry.json")
    source = action["source"]
    assessment = next((item for item in registry["assessments"] if item.get("assessment_id") == source["assessment_id"]), None)
    if assessment is None:
        raise OperationalOutcomeContextError("ASSESSMENT_SOURCE_MISSING", "ORL-4 action assessment is absent from the governed workspace")
    event = next((item for item in registry["events"] if item.get("event_id") == action["event"]["event_id"]), None)
    if event is None:
        raise OperationalOutcomeContextError("REVIEW_EVENT_MISSING", "ORL-4 review event is absent from the governed workspace")
    payload = event.get("payload", {})
    reasons = set(payload.get("reason_codes", []))
    checks = {
        "registry_sha256": registry.get("registry_sha256") == action["event"]["registry_sha256"],
        "event_sha256": event.get("event_sha256") == action["event"]["event_sha256"],
        "event_type": event.get("event_type") == "HUMAN_DECISION",
        "event_assessment": event.get("assessment_id") == source["assessment_id"],
        "occurred_at": event.get("occurred_at") == action["event"]["occurred_at"],
        "review_level": payload.get("review_level") == action["review"]["review_level"],
        "decision": payload.get("decision") == action["review"]["decision"],
        "confirmed_risk_band": payload.get("confirmed_risk_band") == action["review"]["confirmed_risk_band"],
        "actor": event.get("actor") == action["review"]["actor"],
        "reason": action["review"]["reason"] in reasons,
        "packet_id": f"REVIEW_PACKET_ID:{source['review_packet_id']}" in reasons,
        "packet_sha256": f"REVIEW_PACKET_SHA256:{source['review_packet_sha256']}" in reasons,
    }
    failed = sorted(key for key, ok in checks.items() if not ok)
    if failed:
        raise OperationalOutcomeContextError("STALE_REVIEW_ACTION", "ORL-4 action no longer binds the governed workspace: " + ", ".join(failed))
    outcomes = [item for item in registry["events"] if item.get("event_type") == "OUTCOME" and item.get("assessment_id") == source["assessment_id"]]
    if outcomes:
        raise OperationalOutcomeContextError("OUTCOME_ALREADY_RECORDED", "the governed assessment already contains an Outcome event")
    return registry, assessment, event


def inspect_operational_outcome_source(artifact_root: str | Path, *, target_repository: str, pull_request: int, repository_root: str | Path, github_cli: GitHubCLI) -> OperationalOutcomeSource:
    root = _safe_existing_dir(artifact_root, "ORL-4 artifact")
    action = _load_action(root / "action.json")
    repository = _normalize_repository(target_repository)
    action_source = action["source"]
    action_pr = action_source["pull_request"]
    if action_source["repository"]["name_with_owner"].lower() != repository.lower() or action_pr["number"] != pull_request:
        raise OperationalOutcomeContextError("TARGET_BINDING_FAILED", "ORL-4 action does not match requested repository/PR")
    bridge_root = _safe_existing_dir(root / "bridge", "ORL-4 governed bridge")
    try:
        review_source = inspect_operational_review_source(
            bridge_root,
            target_repository=repository,
            pull_request=pull_request,
            repository_root=repository_root,
            github_cli=github_cli,
        )
    except (OperationalReviewActionError, OperationalReviewActionVerificationError) as exc:
        raise OperationalOutcomeContextError(getattr(exc, "code", "REVIEW_SOURCE_INVALID"), str(exc)) from exc
    expected = {
        "project_id": review_source.candidate["project_id"],
        "repository": review_source.candidate["repository"]["name_with_owner"].lower(),
        "pr_number": review_source.candidate["pull_request"]["number"],
        "base_oid": review_source.candidate["pull_request"]["base_oid"],
        "head_oid": review_source.candidate["pull_request"]["head_oid"],
        "assessment_id": review_source.packet["assessment_id"],
        "review_packet_id": review_source.packet["packet_id"],
        "review_packet_sha256": review_source.packet["packet_sha256"],
        "review_brief_sha256": review_source.brief["brief_sha256"],
        "operational_binding_sha256": review_source.binding.get("binding_sha256") if review_source.binding is not None else None,
        "bridge_contract": review_source.result["bridge_contract"],
        "bridge_deterministic_result_sha256": review_source.result["deterministic_result_sha256"],
        "semantic_packet_sha256": review_source.result["semantic_packet_sha256"],
    }
    actual = {
        "project_id": action_source["project_id"],
        "repository": action_source["repository"]["name_with_owner"].lower(),
        "pr_number": action_pr["number"],
        "base_oid": action_pr["base_oid"],
        "head_oid": action_pr["head_oid"],
        "assessment_id": action_source["assessment_id"],
        "review_packet_id": action_source["review_packet_id"],
        "review_packet_sha256": action_source["review_packet_sha256"],
        "review_brief_sha256": action_source["review_brief_sha256"],
        "operational_binding_sha256": action_source["operational_binding_sha256"],
        "bridge_contract": action_source["bridge_contract"],
        "bridge_deterministic_result_sha256": action_source["bridge_deterministic_result_sha256"],
        "semantic_packet_sha256": action_source["semantic_packet_sha256"],
    }
    mismatches = sorted(key for key in expected if expected[key] != actual[key])
    if mismatches:
        raise OperationalOutcomeContextError("STALE_REVIEW_ACTION", "ORL-4 action source closure mismatch: " + ", ".join(mismatches))
    registry, assessment, event = _review_event_binding(action=action, workspace_root=review_source.workspace_root)
    return OperationalOutcomeSource(root, action, bridge_root, review_source.workspace_root, registry, assessment, event, review_source)


def _live_target_source(github_cli: GitHubCLI, *, repository_root: Path, repository: str, pull_request: int) -> dict[str, Any]:
    source, _ = collect_pull_request(github_cli, str(pull_request), cwd=repository_root, repository=repository, include_diff=False, include_discussion=False)
    repo = source.get("repository", {})
    pr = source.get("pull_request", {})
    if str(repo.get("name_with_owner") or "").lower() != repository.lower():
        raise OperationalOutcomeContextError("TARGET_BINDING_FAILED", "live GitHub repository does not match target_repository")
    if pr.get("number") != pull_request:
        raise OperationalOutcomeContextError("TARGET_BINDING_FAILED", "live GitHub PR number does not match requested PR")
    head = str(pr.get("head_oid") or "").lower()
    base = str(pr.get("base_oid") or "").lower()
    if _SHA40.fullmatch(head) is None or _SHA40.fullmatch(base) is None:
        raise OperationalOutcomeContextError("TARGET_BINDING_FAILED", "live GitHub PR must expose exact head/base SHAs")
    return source


def _github_api_json(github_cli: GitHubCLI, endpoint: str, *, cwd: Path) -> dict[str, Any]:
    result = github_cli.run(["api", endpoint], cwd=cwd)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OperationalOutcomeContextError("GITHUB_READBACK_FAILED", f"GitHub API returned invalid JSON: {endpoint}") from exc
    if not isinstance(value, dict):
        raise OperationalOutcomeContextError("GITHUB_READBACK_FAILED", f"GitHub API must return an object: {endpoint}")
    return value


def _normalize_checks(raw_checks: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_checks, list):
        return []
    output: list[dict[str, Any]] = []
    for item in raw_checks:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("context")
        if not isinstance(name, str) or not name.strip():
            continue
        kind = str(item.get("__typename") or "UNKNOWN").strip() or "UNKNOWN"
        workflow = item.get("workflowName")
        status = item.get("status")
        conclusion = item.get("conclusion")
        if kind == "StatusContext":
            status = item.get("state")
            conclusion = item.get("state")
        output.append({
            "kind": kind,
            "name": name.strip(),
            "workflow": workflow.strip() if isinstance(workflow, str) and workflow.strip() else None,
            "status": str(status).strip().upper() if status is not None and str(status).strip() else None,
            "conclusion": str(conclusion).strip().upper() if conclusion is not None and str(conclusion).strip() else None,
        })
    unique = {(item["kind"], item["name"], item["workflow"], item["status"], item["conclusion"]): item for item in output}
    return [unique[key] for key in sorted(unique, key=lambda value: tuple("" if part is None else str(part) for part in value))]


def build_github_outcome_observation(*, live_source: dict[str, Any], pr_api: dict[str, Any], expected_repository: str, expected_pull_request: int, expected_base_oid: str, expected_head_oid: str) -> dict[str, Any]:
    repository = live_source.get("repository", {})
    pr = live_source.get("pull_request", {})
    checks = {
        "repository": str(repository.get("name_with_owner") or "").lower() == expected_repository.lower(),
        "pull_request": pr.get("number") == expected_pull_request,
        "head_oid": str(pr.get("head_oid") or "").lower() == expected_head_oid,
        "base_oid": str(pr.get("base_oid") or "").lower() == expected_base_oid,
        "api_number": pr_api.get("number") == expected_pull_request,
        "api_head_oid": str(pr_api.get("head", {}).get("sha") or "").lower() == expected_head_oid,
        "api_base_oid": str(pr_api.get("base", {}).get("sha") or "").lower() == expected_base_oid,
    }
    failed = sorted(key for key, ok in checks.items() if not ok)
    if failed:
        raise OperationalOutcomeContextError("STALE_SOURCE_REVISION", "live GitHub observation no longer binds ORL-4 source: " + ", ".join(failed))
    merged_by = pr.get("merged_by")
    if isinstance(merged_by, dict):
        merged_by_value = merged_by.get("login") or merged_by.get("name")
    elif isinstance(merged_by, str):
        merged_by_value = merged_by
    else:
        merged_by_value = None
    merge_commit = pr_api.get("merge_commit_sha")
    if not isinstance(merge_commit, str) or _SHA40.fullmatch(merge_commit.lower()) is None:
        merge_commit = None
    observation: dict[str, Any] = {
        "provider": "github",
        "pull_request": {
            "state": str(pr.get("state") or "UNKNOWN").upper(),
            "merged": bool(pr_api.get("merged")),
            "merged_at": pr.get("merged_at"),
            "merged_by": str(merged_by_value).strip() if merged_by_value is not None and str(merged_by_value).strip() else None,
            "merge_commit_sha": merge_commit.lower() if isinstance(merge_commit, str) else None,
            "mergeable": str(pr.get("mergeable")).upper() if pr.get("mergeable") is not None else None,
            "merge_state_status": str(pr.get("merge_state_status")).upper() if pr.get("merge_state_status") is not None else None,
            "review_decision": str(pr.get("review_decision")).upper() if pr.get("review_decision") is not None else None,
        },
        "checks": _normalize_checks(pr.get("checks")),
        "observation_sha256": "",
    }
    observation["observation_sha256"] = _observation_hash(observation)
    return observation


def discover_operational_review_action_artifacts(github_cli: GitHubCLI, *, repository_root: str | Path, cache_root: str | Path, target_repository: str, pull_request: int) -> tuple[dict[str, Any], list[Path]]:
    root = _safe_existing_dir(repository_root, "repository root")
    repository = _normalize_repository(target_repository)
    if pull_request < 1:
        raise OperationalOutcomeContextError("INVALID_INPUT", "pull_request must be at least 1")
    live_source = _live_target_source(github_cli, repository_root=root, repository=repository, pull_request=pull_request)
    head = str(live_source["pull_request"]["head_oid"]).lower()
    prefix = _artifact_prefix(repository, pull_request, head, orl4=True)
    artifacts = _list_authority_artifacts(github_cli, cwd=root, prefixes=(prefix,))
    cache = _safe_output(cache_root, "ORL-5 artifact cache root")
    if cache.exists():
        import shutil
        shutil.rmtree(cache)
    cache.mkdir(parents=True)
    roots = _download_artifacts(github_cli, cwd=root, artifacts=artifacts, destination=cache / "orl4")
    return live_source, roots


def select_operational_outcome_source(artifact_roots: Sequence[str | Path], *, target_repository: str, pull_request: int, repository_root: str | Path, github_cli: GitHubCLI) -> OperationalOutcomeSource:
    valid: list[OperationalOutcomeSource] = []
    failures: list[str] = []
    for raw in sorted({str(Path(value).expanduser()) for value in artifact_roots}):
        try:
            valid.append(inspect_operational_outcome_source(raw, target_repository=target_repository, pull_request=pull_request, repository_root=repository_root, github_cli=github_cli))
        except Exception as exc:
            failures.append(f"{raw}: {exc}")
    if not valid:
        detail = "; ".join(failures[:5])
        if len(failures) > 5:
            detail += f"; ... {len(failures) - 5} more"
        raise OperationalOutcomeContextError("NO_CURRENT_REVIEW_ACTION", "no current ORL-4 review action survived exact source replay" + (f": {detail}" if detail else ""))
    by_action: dict[str, list[OperationalOutcomeSource]] = {}
    for source in valid:
        by_action.setdefault(source.action_key, []).append(source)
    if len(by_action) != 1:
        raise OperationalOutcomeContextError("AMBIGUOUS_REVIEW_ACTION", "multiple distinct ORL-4 review actions are valid for the current PR")
    sources = next(iter(by_action.values()))
    sources.sort(key=lambda item: str(item.artifact_root))
    return sources[0]


def _source_projection(source: OperationalOutcomeSource) -> dict[str, Any]:
    action = source.action
    action_source = action["source"]
    assessment = source.assessment
    return {
        "authority_repository": AUTHORITY_REPOSITORY,
        "project_id": action_source["project_id"],
        "repository": deepcopy(action_source["repository"]),
        "pull_request": deepcopy(action_source["pull_request"]),
        "assessment": {
            "assessment_id": assessment["assessment_id"],
            "source_revision": assessment["source_revision"],
            "trust_report_id": assessment["trust_report_id"],
            "trust_report_sha256": assessment["trust_report_sha256"],
        },
        "review_action_sha256": action["action_sha256"],
        "review_brief_sha256": action_source["review_brief_sha256"],
        "review_packet_id": action_source["review_packet_id"],
        "review_packet_sha256": action_source["review_packet_sha256"],
        "operational_binding_sha256": action_source["operational_binding_sha256"],
        "registry_sha256": source.registry["registry_sha256"],
    }


def _review_projection(source: OperationalOutcomeSource) -> dict[str, Any]:
    action = source.action
    event = source.review_event
    return {
        "event_id": event["event_id"],
        "event_sha256": event["event_sha256"],
        "occurred_at": event["occurred_at"],
        "review_level": action["review"]["review_level"],
        "decision": action["review"]["decision"],
        "confirmed_risk_band": action["review"]["confirmed_risk_band"],
        "actor": action["review"]["actor"],
        "reason": action["review"]["reason"],
    }


def _auto3_projection(source: OperationalOutcomeSource) -> dict[str, Any]:
    action = source.action
    assessment = source.assessment
    event = source.review_event
    return {
        "declaration_contract_version": AUTO3_DECLARATION_CONTRACT,
        "project_id": action["source"]["project_id"],
        "assessment": {
            "assessment_id": assessment["assessment_id"],
            "source_revision": assessment["source_revision"],
            "trust_report_id": assessment["trust_report_id"],
            "trust_report_sha256": assessment["trust_report_sha256"],
        },
        "review": {
            "event_id": event["event_id"],
            "event_sha256": event["event_sha256"],
            "review_level": action["review"]["review_level"],
            "decision": action["review"]["decision"],
            "review_packet_id": action["source"]["review_packet_id"],
            "review_packet_sha256": action["source"]["review_packet_sha256"],
        },
        "allowed_authority_types": sorted(SUPPORTED_AUTHORITIES),
        "allowed_verdicts": sorted(SUPPORTED_VERDICTS),
        "production_defect_safe_forbidden": True,
        "authority_source_requirements": [
            {"authority_type": "CONTROLLED_EVALUATION", "required_fields": ["evaluation_id", "evaluation_report_sha256"]},
            {"authority_type": "INDEPENDENT_AUDIT", "required_fields": ["audit_id", "audit_artifact_sha256", "audit_authority_registry_sha256"]},
            {"authority_type": "PRODUCTION_DEFECT", "required_fields": ["defect_id", "defect_registry_sha256", "ledger_sha256"]},
        ],
        "unresolved_human_inputs": ["actor", "authority_type", "verdict", "authority_source"],
        "selected_authority_type": None,
        "selected_verdict": None,
        "declaration_materialized": False,
    }


def build_operational_outcome_context(*, source: OperationalOutcomeSource, observations: Mapping[str, Any]) -> dict[str, Any]:
    observation = deepcopy(dict(observations))
    if observation.get("observation_sha256") != _observation_hash(observation):
        raise OperationalOutcomeContextError("OBSERVATION_INVALID", "GitHub observation semantic hash mismatch")
    context: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "status": STATUS,
        "next_step": NEXT_STEP,
        "source": _source_projection(source),
        "review": _review_projection(source),
        "observations": observation,
        "auto3_declaration_context": _auto3_projection(source),
        "authority": {
            "human_review_recorded": True,
            "human_outcome_declared": False,
            "automatic_outcome_inference": False,
            "outcome_recorded": False,
            "automation_authorized": False,
            "pilot_authorized": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
            "merge_observation_is_outcome_authority": False,
            "ci_observation_is_outcome_authority": False,
        },
        "context_sha256": "",
    }
    context["context_sha256"] = _context_hash(context)
    errors = verify_operational_outcome_context_data(context)
    if errors:
        raise OperationalOutcomeContextVerificationError(errors)
    return context


def verify_operational_outcome_context_sources(context: dict[str, Any], *, action_artifact_root: str | Path, repository_root: str | Path, github_cli: GitHubCLI) -> list[str]:
    errors = verify_operational_outcome_context_data(context)
    if errors:
        return errors
    source_projection = context["source"]
    pr = source_projection["pull_request"]
    try:
        source = inspect_operational_outcome_source(
            action_artifact_root,
            target_repository=source_projection["repository"]["name_with_owner"],
            pull_request=pr["number"],
            repository_root=repository_root,
            github_cli=github_cli,
        )
        if _source_projection(source) != source_projection:
            errors.append("source projection no longer matches ORL-4 artifact")
        if _review_projection(source) != context["review"]:
            errors.append("review projection no longer matches ORL-4 artifact")
        if _auto3_projection(source) != context["auto3_declaration_context"]:
            errors.append("AUTO-3 declaration bindings no longer match ORL-4 artifact")
        live = _live_target_source(
            github_cli,
            repository_root=_safe_existing_dir(repository_root, "repository root"),
            repository=source_projection["repository"]["name_with_owner"],
            pull_request=pr["number"],
        )
        live_pr = live["pull_request"]
        if str(live_pr.get("head_oid") or "").lower() != pr["head_oid"]:
            errors.append("live GitHub PR head no longer matches context")
        if str(live_pr.get("base_oid") or "").lower() != pr["base_oid"]:
            errors.append("live GitHub PR base no longer matches context")
    except Exception as exc:
        errors.append(f"source replay failed: {exc}")
    return sorted(set(errors))


def run_operational_outcome_context(request: OperationalOutcomeContextRequest, *, github_cli: GitHubCLI) -> dict[str, Any]:
    repository = _normalize_repository(request.target_repository)
    root = _safe_existing_dir(request.repository_root, "repository root")
    live_source, action_roots = discover_operational_review_action_artifacts(
        github_cli,
        repository_root=root,
        cache_root=request.artifact_cache_root,
        target_repository=repository,
        pull_request=request.pull_request,
    )
    if not action_roots:
        raise OperationalOutcomeContextError("NO_REVIEW_ACTION_ARTIFACT", "no non-expired ORL-4 review-action artifact exists for the current PR head")
    source = select_operational_outcome_source(
        action_roots,
        target_repository=repository,
        pull_request=request.pull_request,
        repository_root=root,
        github_cli=github_cli,
    )
    action_pr = source.action["source"]["pull_request"]
    api = _github_api_json(github_cli, f"repos/{repository}/pulls/{request.pull_request}", cwd=root)
    observations = build_github_outcome_observation(
        live_source=live_source,
        pr_api=api,
        expected_repository=repository,
        expected_pull_request=request.pull_request,
        expected_base_oid=action_pr["base_oid"],
        expected_head_oid=action_pr["head_oid"],
    )
    context = build_operational_outcome_context(source=source, observations=observations)
    output = write_operational_outcome_context(request.output, context)
    return {
        **context,
        "context_file": str(output),
        "selected_action_root": str(source.artifact_root),
        "bridge_root": str(source.bridge_root),
        "workspace_root": str(source.workspace_root),
    }

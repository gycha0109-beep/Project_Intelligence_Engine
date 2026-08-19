from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker

from .github_connector import GitHubCLI, collect_pull_request, validate_pull_request_source
from .identity import canonical_json_sha256, normalize_source_revision
from .intelligence_state import capture_project_state
from .io import load_data
from .paths import asset
from .profile import resolve_profile_file
from .trust import (
    assess_trust,
    load_trust_report,
    load_trust_request,
    verify_trust_report_sources,
    write_trust_report,
)
from .trust_prospective_intake import intake_prospective_case
from .validation import validate_profile_data


SCHEMA_VERSION = "1.0"
CAPTURE_CONTRACT = "GITHUB_PROSPECTIVE_CAPTURE_V1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
OPERATOR_BLOCKERS = (
    "TRUST_TASK_CLASS_REQUIRED",
    "TRUST_SCENARIOS_REQUIRED",
    "TRUST_ROLLBACK_EVIDENCE_REQUIRED",
    "TRUST_REPLAY_EVIDENCE_REQUIRED",
    "TRUST_READINESS_POLICY_REQUIRED",
)
EXACT_BLOCKERS = (
    "EXACT_REMOTE_HEAD_REQUIRED",
    "EXACT_REPOSITORY_MATCH_REQUIRED",
    "EXACT_LOCAL_HEAD_REQUIRED",
    "CLEAN_WORKTREE_REQUIRED",
)


class GitHubProspectiveCaptureError(RuntimeError):
    pass


class GitHubProspectiveCaptureVerificationError(GitHubProspectiveCaptureError):
    def __init__(self, errors: list[str] | tuple[str, ...]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid GitHub prospective capture candidate: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GitHubProspectiveCaptureError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GitHubProspectiveCaptureError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise GitHubProspectiveCaptureError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_input(path: str | Path, field: str) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise GitHubProspectiveCaptureError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise GitHubProspectiveCaptureError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise GitHubProspectiveCaptureError(f"{field} must be a regular file: {resolved}")
    return resolved


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise GitHubProspectiveCaptureError(f"output path must not contain symlinks: {target}")
    return target.resolve()


def _schema_errors(value: Any) -> list[str]:
    schema = load_data(asset("schemas/github-prospective-capture-candidate.schema.json"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    output: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        output.append(f"{location}: {error.message}")
    return output


def _profile_identity(path: str | Path) -> tuple[str, str]:
    source = _safe_input(path, "Project Profile")
    profile = resolve_profile_file(source)
    errors = validate_profile_data(profile)
    if errors:
        raise GitHubProspectiveCaptureError("invalid Project Profile: " + "; ".join(errors))
    project = profile.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("id"), str) or not project["id"].strip():
        raise GitHubProspectiveCaptureError("Project Profile project.id is required")
    return project["id"].strip(), canonical_json_sha256(profile)


def _task_id(repository: str, pr_number: int, head_oid: str | None) -> str:
    key = {
        "repository": repository.lower(),
        "pull_request": pr_number,
        "head_oid": head_oid if isinstance(head_oid, str) else None,
    }
    return f"github-pr:{canonical_json_sha256(key)[:32]}"


def _candidate_id(
    project_id: str,
    hostname: str,
    repository: str,
    pr_number: int,
    head_oid: str | None,
    profile_sha256: str,
) -> str:
    key = {
        "project_id": project_id,
        "hostname": hostname.lower(),
        "repository": repository.lower(),
        "pull_request": pr_number,
        "head_oid": head_oid if isinstance(head_oid, str) else None,
        "profile_sha256": profile_sha256,
    }
    return f"github-capture-{canonical_json_sha256(key)[:32]}"


def _candidate_projection(candidate: dict[str, Any]) -> tuple[list[str], str, str, dict[str, Any]]:
    repository = candidate["repository"]
    pull_request = candidate["pull_request"]
    local = candidate["local_verification"]
    head_oid = pull_request.get("head_oid")
    exact_head = isinstance(head_oid, str) and SHA40.fullmatch(head_oid) is not None
    blockers = list(OPERATOR_BLOCKERS)
    if not exact_head:
        blockers.append("EXACT_REMOTE_HEAD_REQUIRED")
    if not local.get("exact_repository_match"):
        blockers.append("EXACT_REPOSITORY_MATCH_REQUIRED")
    if not local.get("exact_head_match"):
        blockers.append("EXACT_LOCAL_HEAD_REQUIRED")
    if not local.get("clean_worktree"):
        blockers.append("CLEAN_WORKTREE_REQUIRED")
    blockers = sorted(set(blockers))
    exact_blocked = any(value in EXACT_BLOCKERS for value in blockers)
    status = "BLOCKED_EXACT_HEAD_REANALYSIS_REQUIRED" if exact_blocked else "BLOCKED_OPERATOR_INPUT_REQUIRED"
    next_step = "RERUN_PIE_ANALYZE_PR_AT_EXACT_CLEAN_HEAD" if exact_blocked else "COMPLETE_TRUST_REQUEST_AND_MATERIALIZE"
    task_id = _task_id(repository["name_with_owner"], pull_request["number"], head_oid)
    scaffold = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "source_revision": head_oid if exact_head else None,
        "task_class": None,
        "changed_files": sorted(candidate["changed_files"]),
        "required_scenarios": None,
        "completed_scenarios": None,
        "repository_match": bool(local.get("exact_repository_match")),
        "head_match": bool(local.get("exact_head_match") and exact_head),
        "rollback_evidence": None,
        "replay_evidence": None,
        "readiness_policy": None,
    }
    return blockers, status, next_step, scaffold


def _finalize(candidate: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(candidate)
    blockers, status, next_step, scaffold = _candidate_projection(output)
    output["blockers"] = blockers
    output["status"] = status
    output["next_step"] = next_step
    output["task_id"] = scaffold["task_id"]
    output["request_scaffold"] = scaffold
    snapshot = deepcopy(output)
    snapshot.pop("generated_at", None)
    snapshot.pop("evidence_snapshot_sha256", None)
    snapshot.pop("report_sha256", None)
    output["evidence_snapshot_sha256"] = canonical_json_sha256(snapshot)
    report_payload = deepcopy(output)
    report_payload.pop("report_sha256", None)
    output["report_sha256"] = canonical_json_sha256(report_payload)
    errors = verify_github_prospective_capture_candidate(output)
    if errors:
        raise GitHubProspectiveCaptureVerificationError(errors)
    return output


def build_github_prospective_capture_candidate(
    source: dict[str, Any],
    profile: str | Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    source_errors = validate_pull_request_source(source)
    if source_errors:
        raise GitHubProspectiveCaptureError("invalid GitHub source evidence: " + "; ".join(source_errors))
    project_id, profile_sha256 = _profile_identity(profile)
    repository = source["repository"]
    pull_request = source["pull_request"]
    changed_files = sorted(
        {
            item["path"]
            for item in pull_request.get("changed_files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"]
        }
    )
    if not changed_files:
        raise GitHubProspectiveCaptureError("GitHub source contains no changed files")
    head_oid = pull_request.get("head_oid") if isinstance(pull_request.get("head_oid"), str) else None
    base_oid = pull_request.get("base_oid") if isinstance(pull_request.get("base_oid"), str) else None
    repo_verification = source.get("local_repository_verification", {})
    local_state = source.get("local_project_state", {})
    repository_status = repo_verification.get("status") if isinstance(repo_verification, dict) else None
    local_head = local_state.get("head_revision") if isinstance(local_state, dict) and isinstance(local_state.get("head_revision"), str) else None
    working_tree_dirty = bool(local_state.get("working_tree_dirty", True)) if isinstance(local_state, dict) else True
    exact_repository_match = repository_status == "matched"
    exact_head_match = bool(SHA40.fullmatch(head_oid or "") and local_head == head_oid)
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "capture_contract": CAPTURE_CONTRACT,
        "candidate_id": _candidate_id(
            project_id,
            repository["hostname"],
            repository["name_with_owner"],
            pull_request["number"],
            head_oid,
            profile_sha256,
        ),
        "project_id": project_id,
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "mode": "REPORT_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "human_review_recorded": False,
        "outcome_recorded": False,
        "repository": {
            "hostname": repository["hostname"],
            "name_with_owner": repository["name_with_owner"],
        },
        "pull_request": {
            "number": pull_request["number"],
            "url": pull_request.get("url") if isinstance(pull_request.get("url"), str) else None,
            "base_oid": base_oid,
            "head_oid": head_oid,
        },
        "source_evidence_sha256": source["source_sha256"],
        "profile_sha256": profile_sha256,
        "local_verification": {
            "repository_status": repository_status if isinstance(repository_status, str) and repository_status else "unverified",
            "local_head": local_head,
            "working_tree_dirty": working_tree_dirty,
            "exact_repository_match": exact_repository_match,
            "exact_head_match": exact_head_match,
            "clean_worktree": not working_tree_dirty,
        },
        "task_id": "",
        "changed_files": changed_files,
        "request_scaffold": {},
        "blockers": [],
        "status": "BLOCKED_OPERATOR_INPUT_REQUIRED",
        "next_step": "COMPLETE_TRUST_REQUEST_AND_MATERIALIZE",
        "evidence_snapshot_sha256": "",
        "report_sha256": "",
    }
    return _finalize(candidate)


def verify_github_prospective_capture_candidate(candidate: Any) -> list[str]:
    errors = _schema_errors(candidate)
    if not isinstance(candidate, dict):
        return sorted(set(errors or ["candidate must contain an object"]))
    try:
        repository = candidate.get("repository", {})
        pull_request = candidate.get("pull_request", {})
        local = candidate.get("local_verification", {})
        project_id = candidate.get("project_id")
        profile_sha256 = candidate.get("profile_sha256")
        if not all(isinstance(value, dict) for value in (repository, pull_request, local)):
            return sorted(set(errors))
        expected_id = _candidate_id(
            str(project_id or ""),
            str(repository.get("hostname") or ""),
            str(repository.get("name_with_owner") or ""),
            int(pull_request.get("number") or 0),
            pull_request.get("head_oid") if isinstance(pull_request.get("head_oid"), str) else None,
            str(profile_sha256 or ""),
        )
        if candidate.get("candidate_id") != expected_id:
            errors.append("candidate_id mismatch")
        head_oid = pull_request.get("head_oid")
        exact_head = isinstance(head_oid, str) and SHA40.fullmatch(head_oid) is not None
        expected_repo_match = local.get("repository_status") == "matched"
        expected_head_match = bool(exact_head and local.get("local_head") == head_oid)
        expected_clean = local.get("working_tree_dirty") is False
        if local.get("exact_repository_match") is not expected_repo_match:
            errors.append("local_verification.exact_repository_match projection mismatch")
        if local.get("exact_head_match") is not expected_head_match:
            errors.append("local_verification.exact_head_match projection mismatch")
        if local.get("clean_worktree") is not expected_clean:
            errors.append("local_verification.clean_worktree projection mismatch")
        blockers, status, next_step, scaffold = _candidate_projection(candidate)
        if candidate.get("blockers") != blockers:
            errors.append("blockers projection mismatch")
        if candidate.get("status") != status:
            errors.append("status projection mismatch")
        if candidate.get("next_step") != next_step:
            errors.append("next_step projection mismatch")
        if candidate.get("task_id") != scaffold["task_id"]:
            errors.append("task_id projection mismatch")
        if candidate.get("request_scaffold") != scaffold:
            errors.append("request_scaffold projection mismatch")
        if candidate.get("changed_files") != sorted(set(candidate.get("changed_files", []))):
            errors.append("changed_files canonical order mismatch")
        snapshot = deepcopy(candidate)
        snapshot.pop("generated_at", None)
        snapshot.pop("evidence_snapshot_sha256", None)
        snapshot.pop("report_sha256", None)
        if candidate.get("evidence_snapshot_sha256") != canonical_json_sha256(snapshot):
            errors.append("evidence_snapshot_sha256 mismatch")
        report_payload = deepcopy(candidate)
        report_payload.pop("report_sha256", None)
        if candidate.get("report_sha256") != canonical_json_sha256(report_payload):
            errors.append("report_sha256 mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"candidate semantic verification failed: {exc}")
    return sorted(set(errors))


def write_github_prospective_capture_candidate(path: str | Path, candidate: dict[str, Any]) -> Path:
    errors = verify_github_prospective_capture_candidate(candidate)
    if errors:
        raise GitHubProspectiveCaptureVerificationError(errors)
    target = _safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(candidate, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
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


def load_github_prospective_capture_candidate(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "GitHub prospective capture candidate")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GitHubProspectiveCaptureError(f"cannot load GitHub prospective capture candidate: {exc}") from exc
    errors = verify_github_prospective_capture_candidate(value)
    if errors:
        raise GitHubProspectiveCaptureVerificationError(errors)
    return source, value


def candidate_filename(candidate: dict[str, Any]) -> str:
    head = candidate.get("pull_request", {}).get("head_oid")
    suffix = head[:12] if isinstance(head, str) and SHA40.fullmatch(head) else candidate["candidate_id"][-12:]
    return f"prospective-capture-{suffix}.json"


def _live_changed_files(source: dict[str, Any]) -> list[str]:
    return sorted(
        {
            item["path"]
            for item in source.get("pull_request", {}).get("changed_files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"]
        }
    )


def materialize_github_prospective_capture(
    candidate_path: str | Path,
    *,
    request: str | Path,
    workspace: str | Path,
    profile: str | Path,
    repository_root: str | Path,
    github_cli: GitHubCLI,
    repository: str | None = None,
    ledger: str | Path | None = None,
    policy_registry: str | Path | None = None,
    evaluation_report: str | Path | None = None,
    reground_report: str | Path | None = None,
    reground_observations: str | Path | None = None,
    trust_report_output: str | Path | None = None,
    generated_at: str | None = None,
    captured_at: str | None = None,
    collect_pr: Callable[..., tuple[dict[str, Any], str | None]] = collect_pull_request,
    capture_state: Callable[..., dict[str, Any]] = capture_project_state,
) -> dict[str, Any]:
    candidate_source, candidate = load_github_prospective_capture_candidate(candidate_path)
    exact_blockers = sorted(set(candidate["blockers"]).intersection(EXACT_BLOCKERS))
    if exact_blockers:
        raise GitHubProspectiveCaptureError(
            "candidate is not exact-head materializable; rerun pie analyze-pr: " + ", ".join(exact_blockers)
        )
    head_oid = candidate["pull_request"]["head_oid"]
    if not isinstance(head_oid, str) or SHA40.fullmatch(head_oid) is None:
        raise GitHubProspectiveCaptureError("candidate has no exact 40-hex PR head")
    normalized_head_revision = normalize_source_revision(head_oid)
    root = Path(repository_root).expanduser().resolve()
    if not root.is_dir():
        raise GitHubProspectiveCaptureError(f"repository root does not exist: {root}")

    target = candidate["pull_request"].get("url") or str(candidate["pull_request"]["number"])
    live_source, _ = collect_pr(
        github_cli,
        target,
        cwd=root,
        repository=repository or candidate["repository"]["name_with_owner"],
        include_diff=False,
        include_discussion=False,
    )
    live_repo = live_source["repository"]
    live_pr = live_source["pull_request"]
    if live_repo["hostname"].lower() != candidate["repository"]["hostname"].lower() or live_repo["name_with_owner"].lower() != candidate["repository"]["name_with_owner"].lower():
        raise GitHubProspectiveCaptureError("live GitHub repository does not match candidate repository")
    if live_pr["number"] != candidate["pull_request"]["number"]:
        raise GitHubProspectiveCaptureError("live GitHub PR number does not match candidate")
    if live_pr.get("head_oid") != head_oid:
        raise GitHubProspectiveCaptureError("live GitHub PR head moved; rerun pie analyze-pr before materialization")
    if live_pr.get("base_oid") != candidate["pull_request"].get("base_oid"):
        raise GitHubProspectiveCaptureError("live GitHub PR base moved; rerun pie analyze-pr before materialization")
    if _live_changed_files(live_source) != candidate["changed_files"]:
        raise GitHubProspectiveCaptureError("live GitHub changed-file set differs from candidate; rerun pie analyze-pr")

    current_repo = github_cli.current_repository(root)
    if not current_repo:
        raise GitHubProspectiveCaptureError("cannot verify local repository during materialization")
    if current_repo["name_with_owner"].lower() != candidate["repository"]["name_with_owner"].lower() or current_repo.get("hostname", "github.com").lower() != candidate["repository"]["hostname"].lower():
        raise GitHubProspectiveCaptureError("local repository does not match candidate repository")
    state = capture_state(root, project_id=candidate["project_id"])
    repository_state = state.get("repository", {})
    if repository_state.get("head_revision") != head_oid:
        raise GitHubProspectiveCaptureError("local HEAD no longer matches candidate PR head")
    if repository_state.get("working_tree_dirty"):
        raise GitHubProspectiveCaptureError("local working tree must be clean before materialization")

    project_id, profile_sha256 = _profile_identity(profile)
    if project_id != candidate["project_id"]:
        raise GitHubProspectiveCaptureError("Project Profile project_id does not match candidate")
    if profile_sha256 != candidate["profile_sha256"]:
        raise GitHubProspectiveCaptureError("Project Profile changed since candidate generation; rerun pie analyze-pr")

    request_source, trust_request = load_trust_request(_safe_input(request, "Trust request"))
    if trust_request["task_id"] != candidate["task_id"]:
        raise GitHubProspectiveCaptureError("Trust request task_id does not match candidate task_id")
    if trust_request["source_revision"] != normalized_head_revision:
        raise GitHubProspectiveCaptureError("Trust request source_revision does not match candidate PR head")
    if trust_request["changed_files"] != candidate["changed_files"]:
        raise GitHubProspectiveCaptureError("Trust request changed_files do not exactly match candidate")
    if trust_request["repository_match"] is not True or trust_request["head_match"] is not True:
        raise GitHubProspectiveCaptureError("Trust request must preserve exact repository_match=true and head_match=true")

    optional = {
        "ledger": ledger,
        "policy_registry": policy_registry,
        "evaluation_report": evaluation_report,
        "reground_report": reground_report,
        "reground_observations": reground_observations,
    }
    report_target = _safe_output(trust_report_output or (candidate_source.parent / "prospective-trust-report.json"))
    if report_target.exists():
        _, report = load_trust_report(report_target)
        replay_errors = verify_trust_report_sources(
            report,
            request=request_source,
            profile=profile,
            **optional,
        )
        if replay_errors:
            raise GitHubProspectiveCaptureVerificationError([f"existing Trust report source replay: {value}" for value in replay_errors])
        if report.get("request", {}).get("task_id") != candidate["task_id"] or report.get("request", {}).get("source_revision") != normalized_head_revision:
            raise GitHubProspectiveCaptureError("existing Trust report identity does not match candidate")
    else:
        report = assess_trust(
            request_source,
            profile,
            ledger=ledger,
            policy_registry=policy_registry,
            evaluation_report=evaluation_report,
            reground_report=reground_report,
            reground_observations=reground_observations,
            generated_at=generated_at,
        )
        write_trust_report(report_target, report)

    intake = intake_prospective_case(
        workspace,
        trust_report=report_target,
        request=request_source,
        profile=profile,
        ledger=ledger,
        policy_registry=policy_registry,
        evaluation_report=evaluation_report,
        reground_report=reground_report,
        reground_observations=reground_observations,
        captured_at=captured_at,
    )
    return {
        "candidate_id": candidate["candidate_id"],
        "assessment_id": intake["assessment_id"],
        "predicted_risk_band": intake["predicted_risk_band"],
        "source_revision": intake["source_revision"],
        "idempotent": intake["idempotent"],
        "trust_report": str(report_target),
        "mode": "REPORT_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "human_review_recorded": False,
        "outcome_recorded": False,
    }

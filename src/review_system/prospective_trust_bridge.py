from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .github_connector import GitHubCLI, collect_pull_request
from .identity import canonical_json_sha256, normalize_source_revision
from .prospective_automation import RunGitHubPRRequest, run_github_pr
from .trust import load_trust_request
from .trust_comparison import new_registry, write_registry


AUTHORITY_REPOSITORY = "gycha0109-beep/Project_Intelligence_Engine"
TRUST_REQUEST_PREFIX = "evidence/trust/requests/"
BRIDGE_CONTRACT = "PIE_AUTO2_HUMAN_REVIEW_BRIDGE_V1"
SOURCE_CONTRACT = "PIE_AUTO2_TRUST_REQUEST_SOURCE_V1"
RESULT_CONTRACT = "PIE_AUTO2_HUMAN_REVIEW_RESULT_V1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


class ProspectiveTrustBridgeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TrustedGitHubPRRequest:
    pull_request: int
    target_repository: str
    event_head_sha: str
    event_base_sha: str
    pie_revision: str
    trust_request_path: str
    trust_request_sha256: str
    repository_root: str | Path = "."
    profile: str = ".review/project.yml"
    config: str = ".review/intelligence/config.yml"
    output_root: str | Path = ".pie/human-review-bridge"


def _exact_sha(value: str, field: str) -> str:
    normalized = value.strip().lower()
    if _SHA40.fullmatch(normalized) is None:
        raise ProspectiveTrustBridgeError("INVALID_INPUT", f"{field} must be an exact 40-character Git SHA")
    return normalized


def _exact_sha256(value: str, field: str) -> str:
    normalized = value.strip().lower()
    if _SHA256.fullmatch(normalized) is None:
        raise ProspectiveTrustBridgeError("INVALID_INPUT", f"{field} must be an exact SHA-256")
    return normalized


def _safe_source_path(value: str) -> str:
    raw = value.strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
        or not raw.startswith(TRUST_REQUEST_PREFIX)
        or path.suffix.lower() != ".json"
    ):
        raise ProspectiveTrustBridgeError(
            "TRUST_SOURCE_INVALID",
            f"Trust request path must be a JSON file under {TRUST_REQUEST_PREFIX}",
        )
    return path.as_posix()


def _json_object(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProspectiveTrustBridgeError("PROVIDER_EVIDENCE_INVALID", f"{label} returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProspectiveTrustBridgeError("PROVIDER_EVIDENCE_INVALID", f"{label} must return a JSON object")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _live_changed_files(source: dict[str, Any]) -> list[str]:
    return sorted(
        {
            item["path"]
            for item in source.get("pull_request", {}).get("changed_files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"]
        }
    )


def _expected_task_id(repository: str, pull_request: int, head_oid: str) -> str:
    key = {
        "repository": repository.lower(),
        "pull_request": pull_request,
        "head_oid": head_oid,
    }
    return f"github-pr:{canonical_json_sha256(key)[:32]}"


def _provider_file(
    cli: GitHubCLI,
    *,
    cwd: Path,
    authority_revision: str,
    source_path: str,
) -> tuple[bytes, str]:
    result = cli.run(
        [
            "api",
            "--method",
            "GET",
            f"repos/{AUTHORITY_REPOSITORY}/contents/{source_path}",
            "-f",
            f"ref={authority_revision}",
        ],
        cwd=cwd,
    )
    payload = _json_object(result.stdout, "GitHub contents API")
    if payload.get("type") != "file":
        raise ProspectiveTrustBridgeError("TRUST_SOURCE_INVALID", "authority source is not a regular GitHub file")
    if payload.get("path") != source_path:
        raise ProspectiveTrustBridgeError("TRUST_SOURCE_INVALID", "provider source path does not match requested path")
    provider_sha = str(payload.get("sha") or "").lower()
    if _SHA40.fullmatch(provider_sha) is None:
        raise ProspectiveTrustBridgeError("PROVIDER_EVIDENCE_INVALID", "provider Git blob SHA is missing or invalid")
    if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        raise ProspectiveTrustBridgeError("PROVIDER_EVIDENCE_INVALID", "provider file content is not base64 encoded")
    try:
        encoded = "".join(payload["content"].split())
        raw = base64.b64decode(encoded, validate=True)
        raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProspectiveTrustBridgeError("PROVIDER_EVIDENCE_INVALID", "provider Trust request content is invalid") from exc
    return raw, provider_sha


def _provider_commit_timestamp(
    cli: GitHubCLI,
    *,
    cwd: Path,
    authority_revision: str,
) -> str:
    result = cli.run(
        [
            "api",
            "--method",
            "GET",
            f"repos/{AUTHORITY_REPOSITORY}/commits/{authority_revision}",
        ],
        cwd=cwd,
    )
    payload = _json_object(result.stdout, "GitHub commit API")
    commit = payload.get("commit")
    if not isinstance(commit, dict):
        raise ProspectiveTrustBridgeError("PROVIDER_EVIDENCE_INVALID", "authority commit metadata is missing")
    for field in ("committer", "author"):
        actor = commit.get(field)
        if isinstance(actor, dict) and isinstance(actor.get("date"), str) and actor["date"].strip():
            return actor["date"].strip()
    raise ProspectiveTrustBridgeError("PROVIDER_EVIDENCE_INVALID", "authority commit timestamp is missing")


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _initialize_workspace(workspace: Path, *, project_id: str, authority_at: str) -> None:
    workspace.mkdir(parents=True, exist_ok=False)
    write_registry(
        workspace / "comparison-registry.json",
        new_registry(project_id, created_at=authority_at),
    )
    _write_json(
        workspace / "reconciliation-sources.json",
        {
            "schema_version": "1.0",
            "project_id": project_id,
            "assessment_sources": [],
            "outcome_sources": [],
        },
    )
    _write_json(
        workspace / "observation-policy.json",
        {
            "schema_version": "1.0",
            "policy_version": "1.0.0",
            "mode": "REPORT_ONLY",
            "target_band": "R0",
            "thresholds": {
                "minimum_r0_assessment_count": 20,
                "minimum_r0_reviewed_count": 20,
                "minimum_r0_conclusive_outcome_count": 12,
                "minimum_r0_confirmed_safe_count": 12,
                "minimum_confirmed_unsafe_challenge_count": 8,
                "minimum_r0_independent_audit_count": 5,
                "minimum_r0_outcome_coverage": 0.6,
                "minimum_r0_evidence_span_days": 14,
                "maximum_r0_false_negatives": 0,
                "maximum_r0_false_negative_rate": 0.0,
            },
        },
    )


def _resolve_bridge_root(output_root: str | Path, *, pull_request: int, head: str) -> Path:
    root = Path(output_root).expanduser().resolve()
    bridge = root / f"pr-{pull_request}-{head[:12]}"
    if bridge.exists():
        raise ProspectiveTrustBridgeError("OUTPUT_EXISTS", f"bridge output already exists: {bridge}")
    bridge.mkdir(parents=True)
    return bridge


def build_bridge_result_projection(
    *,
    source_evidence: dict[str, Any],
    run_result: dict[str, Any],
    packet: dict[str, Any],
    request_sha256: str,
) -> dict[str, Any]:
    packet_id = packet.get("packet_id")
    evidence_snapshot = packet.get("evidence_snapshot_sha256")
    if not isinstance(packet_id, str) or not packet_id:
        raise ProspectiveTrustBridgeError("EVIDENCE_HASH_MISMATCH", "Stage 10K packet_id is missing")
    if not isinstance(evidence_snapshot, str) or _SHA256.fullmatch(evidence_snapshot) is None:
        raise ProspectiveTrustBridgeError("EVIDENCE_HASH_MISMATCH", "Stage 10K evidence_snapshot_sha256 is missing or invalid")
    return {
        "schema_version": "1.0",
        "result_contract": RESULT_CONTRACT,
        "bridge_contract": BRIDGE_CONTRACT,
        "authority": source_evidence["authority"],
        "target": source_evidence["target"],
        "trust_request": {
            **source_evidence["trust_request"],
            "content_sha256": request_sha256,
        },
        "status": run_result["status"],
        "assessment_id": run_result["assessment_id"],
        "packet_id": packet_id,
        "packet_evidence_snapshot_sha256": evidence_snapshot,
        "risk_band": run_result.get("risk_band"),
        "readiness": run_result.get("readiness"),
        "human_review_recorded": False,
        "outcome_recorded": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
    }


def run_trusted_github_pr(
    request: TrustedGitHubPRRequest,
    *,
    github_cli: GitHubCLI,
) -> dict[str, Any]:
    root = Path(request.repository_root).expanduser().resolve()
    if not root.is_dir():
        raise ProspectiveTrustBridgeError("INVALID_INPUT", f"repository root does not exist: {root}")
    if request.pull_request < 1:
        raise ProspectiveTrustBridgeError("INVALID_INPUT", "pull_request must be at least 1")

    target_repository = request.target_repository.strip()
    if "/" not in target_repository or target_repository.startswith("/") or target_repository.endswith("/"):
        raise ProspectiveTrustBridgeError("INVALID_INPUT", "target_repository must be owner/name")
    head = _exact_sha(request.event_head_sha, "event_head_sha")
    base = _exact_sha(request.event_base_sha, "event_base_sha")
    authority_revision = _exact_sha(request.pie_revision, "pie_revision")
    expected_request_sha256 = _exact_sha256(request.trust_request_sha256, "trust_request_sha256")
    source_path = _safe_source_path(request.trust_request_path)

    live_source, _ = collect_pull_request(
        github_cli,
        str(request.pull_request),
        cwd=root,
        repository=target_repository,
        include_diff=False,
        include_discussion=False,
    )
    live_repository = str(live_source.get("repository", {}).get("name_with_owner") or "")
    live_pr = live_source.get("pull_request", {})
    if live_repository.lower() != target_repository.lower():
        raise ProspectiveTrustBridgeError("TARGET_BINDING_FAILED", "live target repository does not match requested repository")
    if live_pr.get("number") != request.pull_request:
        raise ProspectiveTrustBridgeError("TARGET_BINDING_FAILED", "live target pull request number does not match")
    if str(live_pr.get("state") or "").upper() != "OPEN":
        raise ProspectiveTrustBridgeError("TARGET_BINDING_FAILED", "target pull request must remain open")
    if str(live_pr.get("head_oid") or "").lower() != head:
        raise ProspectiveTrustBridgeError("STALE_SOURCE_REVISION", "target pull request head moved")
    if str(live_pr.get("base_oid") or "").lower() != base:
        raise ProspectiveTrustBridgeError("STALE_SOURCE_REVISION", "target pull request base moved")
    changed_files = _live_changed_files(live_source)

    if target_repository.lower() == AUTHORITY_REPOSITORY.lower() and authority_revision != base:
        raise ProspectiveTrustBridgeError(
            "SELF_AUTHORITY_REJECTED",
            "PIE-targeted review requires authority revision to equal the exact target base revision",
        )

    raw_request, provider_blob_sha = _provider_file(
        github_cli,
        cwd=root,
        authority_revision=authority_revision,
        source_path=source_path,
    )
    actual_request_sha256 = _sha256_bytes(raw_request)
    if actual_request_sha256 != expected_request_sha256:
        raise ProspectiveTrustBridgeError(
            "TRUST_SOURCE_HASH_MISMATCH",
            f"Trust request SHA-256 mismatch: expected={expected_request_sha256} actual={actual_request_sha256}",
        )
    authority_at = _provider_commit_timestamp(
        github_cli,
        cwd=root,
        authority_revision=authority_revision,
    )

    bridge_root = _resolve_bridge_root(request.output_root, pull_request=request.pull_request, head=head)
    source_dir = bridge_root / "source"
    request_file = source_dir / "trust-request.json"
    request_file.parent.mkdir(parents=True, exist_ok=True)
    request_file.write_bytes(raw_request)
    _, trust_request = load_trust_request(request_file)

    normalized_head = normalize_source_revision(head)
    expected_task_id = _expected_task_id(live_repository, request.pull_request, head)
    if trust_request.get("task_id") != expected_task_id:
        raise ProspectiveTrustBridgeError("TRUST_TARGET_MISMATCH", "Trust request task_id does not match exact GitHub target")
    if trust_request.get("source_revision") != normalized_head:
        raise ProspectiveTrustBridgeError("TRUST_TARGET_MISMATCH", "Trust request source_revision does not match exact target head")
    if trust_request.get("changed_files") != changed_files:
        raise ProspectiveTrustBridgeError("TRUST_TARGET_MISMATCH", "Trust request changed_files do not match live GitHub target")
    if trust_request.get("repository_match") is not True or trust_request.get("head_match") is not True:
        raise ProspectiveTrustBridgeError(
            "TRUST_TARGET_MISMATCH",
            "Trust request must preserve repository_match=true and head_match=true",
        )

    source_evidence = {
        "schema_version": "1.0",
        "source_contract": SOURCE_CONTRACT,
        "bridge_contract": BRIDGE_CONTRACT,
        "mode": "REPORT_ONLY",
        "authority": {
            "repository": AUTHORITY_REPOSITORY,
            "revision": authority_revision,
            "committed_at": authority_at,
            "path": source_path,
            "provider_blob_sha": provider_blob_sha,
            "content_sha256": actual_request_sha256,
        },
        "target": {
            "repository": live_repository,
            "pull_request": request.pull_request,
            "head_sha": head,
            "base_sha": base,
            "changed_files": changed_files,
        },
        "trust_request": {
            "request_id": trust_request.get("request_id"),
            "project_id": trust_request.get("project_id"),
            "task_id": trust_request.get("task_id"),
            "source_revision": trust_request.get("source_revision"),
        },
        "human_review_recorded": False,
        "outcome_recorded": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
    }
    source_evidence_path = _write_json(source_dir / "trust-request-source.json", source_evidence)

    workspace = bridge_root / "workspace"
    _initialize_workspace(
        workspace,
        project_id=str(trust_request["project_id"]),
        authority_at=authority_at,
    )
    result = run_github_pr(
        RunGitHubPRRequest(
            pull_request=str(request.pull_request),
            event_head_sha=head,
            pie_revision=authority_revision,
            repository_root=root,
            repository=live_repository,
            profile=request.profile,
            config=request.config,
            trust_request=request_file,
            workspace=workspace,
            output_root=bridge_root / "automation",
            generated_at=authority_at,
            captured_at=authority_at,
        ),
        github_cli=github_cli,
    )
    if result.get("status") != "READY_FOR_HUMAN_REVIEW":
        raise ProspectiveTrustBridgeError("BRIDGE_TERMINAL_STATE_INVALID", "bridge did not stop at READY_FOR_HUMAN_REVIEW")
    for field in ("human_review_recorded", "outcome_recorded", "automation_authorized", "pilot_authorized"):
        if result.get(field) is not False:
            raise ProspectiveTrustBridgeError("AUTHORITY_BOUNDARY_VIOLATION", f"{field} must remain false")

    packet_path = Path(result["bundle"]) / "review" / "packet.json"
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProspectiveTrustBridgeError("EVIDENCE_HASH_MISMATCH", "Stage 10K review packet is missing or invalid") from exc
    for field in ("human_review_recorded", "outcome_recorded", "automation_authorized", "pilot_authorized"):
        if packet.get(field) is not False:
            raise ProspectiveTrustBridgeError("AUTHORITY_BOUNDARY_VIOLATION", f"packet {field} must remain false")
    projection = build_bridge_result_projection(
        source_evidence=source_evidence,
        run_result=result,
        packet=packet,
        request_sha256=actual_request_sha256,
    )
    deterministic_result_sha256 = canonical_json_sha256(projection)
    result_path = _write_json(
        bridge_root / "result.json",
        {
            **projection,
            "deterministic_result_sha256": deterministic_result_sha256,
        },
    )
    return {
        **projection,
        "deterministic_result_sha256": deterministic_result_sha256,
        "execution_id": result["execution_id"],
        "bundle": result["bundle"],
        "bridge_root": str(bridge_root),
        "source_evidence": str(source_evidence_path),
        "result_file": str(result_path),
        "raw_observation_manifest_sha256": result["manifest_sha256"],
    }

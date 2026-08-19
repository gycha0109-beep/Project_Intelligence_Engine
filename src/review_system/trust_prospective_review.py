from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Callable, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .github_connector import GitHubCLI, GitHubCLIError, collect_pull_request
from .github_prospective_capture import load_github_prospective_capture_candidate
from .identity import canonical_json_sha256, file_sha256, normalize_source_revision
from .io import load_data
from .paths import asset
from .trust import load_trust_report, verify_trust_report_sources
from .trust_comparison import TrustComparisonError, TrustComparisonVerificationError
from .trust_reconciliation_authority import TrustReconciliationError, TrustReconciliationVerificationError
from .trust_prospective_common import (
    SOURCE_FIELDS,
    ProspectiveEvidenceError,
    ProspectiveEvidenceVerificationError,
    _path_has_symlink,
    _replay_candidate,
    _required_workspace,
    _safe_input,
    _safe_root,
    _timestamp,
    utc_now,
)
from .trust_prospective_mutation import record_case_review


SCHEMA_VERSION = "1.0"
PACKET_CONTRACT = "GOVERNED_PROSPECTIVE_REVIEW_PACKET_V1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PACKET_ID = re.compile(r"^prospective-review-packet-[0-9a-f]{32}$")


class ProspectiveReviewError(ProspectiveEvidenceError):
    pass


class ProspectiveReviewVerificationError(ProspectiveEvidenceVerificationError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        ProspectiveReviewError.__init__(
            self,
            "invalid governed prospective review packet: " + "; ".join(self.errors),
        )


def _schema_errors(value: Any) -> list[str]:
    schema = load_data(asset("schemas/prospective-review-packet.schema.json"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    output: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        output.append(f"{location}: {error.message}")
    return output


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise ProspectiveReviewError(f"output path must not contain symlinks: {target}")
    return target.resolve()


def _without(value: dict[str, Any], *fields: str) -> dict[str, Any]:
    result = deepcopy(value)
    for field in fields:
        result.pop(field, None)
    return result


def _packet_snapshot(packet: dict[str, Any]) -> dict[str, Any]:
    return _without(
        packet,
        "generated_at",
        "packet_id",
        "packet_sha256",
        "evidence_snapshot_sha256",
    )


def _packet_id(packet: dict[str, Any], snapshot_sha256: str) -> str:
    key = {
        "packet_contract": packet.get("packet_contract"),
        "project_id": packet.get("project_id"),
        "assessment_id": packet.get("assessment_id"),
        "assessment_sha256": packet.get("assessment_sha256"),
        "github_candidate_id": packet.get("github", {}).get("candidate_id"),
        "github_head_oid": packet.get("github", {}).get("head_oid"),
        "evidence_snapshot_sha256": snapshot_sha256,
    }
    return f"prospective-review-packet-{canonical_json_sha256(key)[:32]}"


def _finalize(packet: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(packet)
    output["changed_files"] = sorted(set(output.get("changed_files", [])))
    output["hard_gates"] = sorted(set(output.get("hard_gates", [])))
    output["evidence_snapshot_sha256"] = canonical_json_sha256(_packet_snapshot(output))
    output["packet_id"] = _packet_id(output, output["evidence_snapshot_sha256"])
    output["packet_sha256"] = canonical_json_sha256(_without(output, "packet_sha256"))
    errors = verify_review_packet_data(output)
    if errors:
        raise ProspectiveReviewVerificationError(errors)
    return output


def verify_review_packet_data(packet: Any) -> list[str]:
    errors = _schema_errors(packet)
    if not isinstance(packet, dict):
        return sorted(set(errors or ["packet must contain an object"]))
    try:
        if packet.get("mode") != "REPORT_ONLY":
            errors.append("mode must remain REPORT_ONLY")
        if packet.get("automation_authorized") is not False:
            errors.append("automation_authorized must remain false")
        if packet.get("pilot_authorized") is not False:
            errors.append("pilot_authorized must remain false")
        if packet.get("human_review_recorded") is not False:
            errors.append("packet preparation must not record human review")
        if packet.get("outcome_recorded") is not False:
            errors.append("packet preparation must not record an Outcome")
        if packet.get("packet_contract") != PACKET_CONTRACT:
            errors.append("packet_contract mismatch")
        if packet.get("changed_files") != sorted(set(packet.get("changed_files", []))):
            errors.append("changed_files canonical order mismatch")
        if packet.get("hard_gates") != sorted(set(packet.get("hard_gates", []))):
            errors.append("hard_gates canonical order mismatch")
        snapshot = canonical_json_sha256(_packet_snapshot(packet))
        if packet.get("evidence_snapshot_sha256") != snapshot:
            errors.append("evidence_snapshot_sha256 mismatch")
        expected_id = _packet_id(packet, snapshot)
        if packet.get("packet_id") != expected_id:
            errors.append("packet_id mismatch")
        expected_hash = canonical_json_sha256(_without(packet, "packet_sha256"))
        if packet.get("packet_sha256") != expected_hash:
            errors.append("packet_sha256 mismatch")
        github = packet.get("github", {})
        source_revision = packet.get("source_revision")
        if isinstance(github, dict) and isinstance(github.get("head_oid"), str):
            expected_revision = normalize_source_revision(github["head_oid"])
            if source_revision != expected_revision:
                errors.append("source_revision does not match GitHub PR head")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"packet semantic verification failed: {exc}")
    return sorted(set(errors))


def write_review_packet(path: str | Path, packet: dict[str, Any]) -> Path:
    errors = verify_review_packet_data(packet)
    if errors:
        raise ProspectiveReviewVerificationError(errors)
    target = _safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(packet, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
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


def load_review_packet(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "prospective review packet")
    try:
        raw = source.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProspectiveReviewError(f"cannot load prospective review packet: {exc}") from exc
    canonical = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    if raw != canonical:
        raise ProspectiveReviewVerificationError(["packet byte representation is not canonical"])
    errors = verify_review_packet_data(value)
    if errors:
        raise ProspectiveReviewVerificationError(errors)
    return source, value


def _resolve_case_source(root: Path, reference: str, field: str) -> Path:
    candidate = root / reference
    if _path_has_symlink(candidate):
        raise ProspectiveReviewError(f"{field} must not contain symlinks: {candidate}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ProspectiveReviewError(f"{field} not found: {candidate}") from exc
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ProspectiveReviewError(f"{field} escaped campaign workspace: {reference}") from exc
    if not resolved.is_file():
        raise ProspectiveReviewError(f"{field} must be a regular file: {resolved}")
    return resolved


def _assessment_context(workspace_root: str | Path, assessment_id: str, *, generated_at: str) -> dict[str, Any]:
    root = _safe_root(workspace_root)
    registry_path, _manifest_path, _policy_path, registry, manifest, _policy = _required_workspace(root)
    assessment = next((item for item in registry["assessments"] if item["assessment_id"] == assessment_id), None)
    if assessment is None:
        raise ProspectiveReviewError(f"unknown assessment_id: {assessment_id}")
    source_entry = next((item for item in manifest["assessment_sources"] if item["assessment_id"] == assessment_id), None)
    if source_entry is None:
        raise ProspectiveReviewError(f"assessment source mapping missing: {assessment_id}")
    paths: dict[str, Path | None] = {}
    for field in ("trust_report", "request", "profile", *SOURCE_FIELDS):
        reference = source_entry.get(field)
        paths[field] = None if reference is None else _resolve_case_source(root, reference, f"assessment {field}")
    if paths["trust_report"] is None or paths["request"] is None or paths["profile"] is None:
        raise ProspectiveReviewError("assessment core source mapping is incomplete")
    _, report = load_trust_report(paths["trust_report"])
    replay_errors = verify_trust_report_sources(
        report,
        request=paths["request"],
        profile=paths["profile"],
        ledger=paths["ledger"],
        policy_registry=paths["policy_registry"],
        evaluation_report=paths["evaluation_report"],
        reground_report=paths["reground_report"],
        reground_observations=paths["reground_observations"],
    )
    if replay_errors:
        raise ProspectiveReviewVerificationError([f"Trust source replay: {item}" for item in replay_errors])
    reconciliation = _replay_candidate(root, registry, manifest, generated_at=generated_at)
    assessment_reconciliation = next(
        (item for item in reconciliation["assessment_reconciliation"] if item["assessment_id"] == assessment_id),
        None,
    )
    if assessment_reconciliation is None or not assessment_reconciliation["reconciled"]:
        status = assessment_reconciliation.get("status") if assessment_reconciliation is not None else "MISSING"
        raise ProspectiveReviewVerificationError([f"assessment source reconciliation is not complete: {status}"])
    source_inventory = {
        field: None if path is None else {"reference": source_entry.get(field), "file_sha256": file_sha256(path)}
        for field, path in paths.items()
    }
    assessment_source_sha256 = canonical_json_sha256(
        {
            "project_id": registry["project_id"],
            "assessment_id": assessment_id,
            "assessment_sha256": assessment["assessment_sha256"],
            "sources": source_inventory,
        }
    )
    return {
        "root": root,
        "registry_path": registry_path,
        "registry": registry,
        "manifest": manifest,
        "assessment": assessment,
        "source_entry": source_entry,
        "paths": paths,
        "report": report,
        "reconciliation": reconciliation,
        "assessment_reconciliation": assessment_reconciliation,
        "assessment_source_sha256": assessment_source_sha256,
    }


def _candidate_binding_checks(context: dict[str, Any], candidate: dict[str, Any]) -> dict[str, bool]:
    assessment = context["assessment"]
    report = context["report"]
    github = candidate["pull_request"]
    repository = candidate["repository"]
    local = candidate["local_verification"]
    request = report["request"]
    return {
        "project_match": candidate["project_id"] == context["registry"]["project_id"],
        "assessment_project_match": report["project_id"] == context["registry"]["project_id"],
        "task_match": candidate["task_id"] == assessment["task_id"] == request["task_id"],
        "revision_match": normalize_source_revision(github["head_oid"]) == assessment["source_revision"] == request["source_revision"],
        "trust_report_match": report["report_id"] == assessment["trust_report_id"] and report["report_sha256"] == assessment["trust_report_sha256"],
        "changed_files_match": candidate["changed_files"] == request["changed_files"],
        "risk_match": report["risk"]["effective_band"] == assessment["predicted_risk_band"],
        "hard_gates_match": sorted(report["task_advisory"]["triggered_hard_gates"]) == sorted(assessment["triggered_hard_gates"]),
        "profile_match": candidate["profile_sha256"] == report["profile"]["profile_sha256"],
        "candidate_exact_repository": local["exact_repository_match"] is True,
        "candidate_exact_head": local["exact_head_match"] is True,
        "candidate_clean_worktree": local["clean_worktree"] is True,
        "repository_identity_present": bool(repository.get("hostname") and repository.get("name_with_owner")),
    }


def _require_candidate_binding(context: dict[str, Any], candidate: dict[str, Any]) -> None:
    checks = _candidate_binding_checks(context, candidate)
    failed = sorted(key for key, value in checks.items() if not value)
    if failed:
        raise ProspectiveReviewError(
            "STALE_REVIEW_PACKET: GitHub candidate no longer binds the assessment: " + ", ".join(failed)
        )


def _live_changed_files(source: dict[str, Any]) -> list[str]:
    return sorted(
        {
            item["path"]
            for item in source.get("pull_request", {}).get("changed_files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"]
        }
    )


def _verify_live_github(
    candidate: dict[str, Any],
    repository_root: str | Path,
    github_cli: GitHubCLI,
    *,
    repository: str | None = None,
    collect_pr: Callable[..., tuple[dict[str, Any], str | None]] = collect_pull_request,
) -> None:
    root = Path(repository_root).expanduser().resolve()
    if not root.is_dir():
        raise ProspectiveReviewError(f"repository root does not exist: {root}")
    pull_request = candidate["pull_request"]
    target = pull_request.get("url") or str(pull_request["number"])
    live_source, _ = collect_pr(
        github_cli,
        target,
        cwd=root,
        repository=repository or candidate["repository"]["name_with_owner"],
        include_diff=False,
        include_discussion=False,
    )
    live_repository = live_source["repository"]
    live_pr = live_source["pull_request"]
    if live_repository["hostname"].lower() != candidate["repository"]["hostname"].lower() or live_repository["name_with_owner"].lower() != candidate["repository"]["name_with_owner"].lower():
        raise ProspectiveReviewError("STALE_REVIEW_PACKET: live GitHub repository changed")
    if live_pr["number"] != pull_request["number"]:
        raise ProspectiveReviewError("STALE_REVIEW_PACKET: live GitHub PR number changed")
    if live_pr.get("head_oid") != pull_request["head_oid"]:
        raise ProspectiveReviewError("STALE_REVIEW_PACKET: live GitHub PR head changed")
    if live_pr.get("base_oid") != pull_request.get("base_oid"):
        raise ProspectiveReviewError("STALE_REVIEW_PACKET: live GitHub PR base changed")
    if _live_changed_files(live_source) != candidate["changed_files"]:
        raise ProspectiveReviewError("STALE_REVIEW_PACKET: live GitHub changed-files changed")


def _evidence_references(report: dict[str, Any]) -> dict[str, Any]:
    evidence = report["evidence"]
    ledger = evidence["ledger"]
    policy = evidence["policy"]
    reground = evidence["reground"]
    return {
        "trust_evidence_fingerprint_sha256": evidence["fingerprint_sha256"],
        "ledger_sha256": ledger["sha256"],
        "policy_registry_id": policy["registry_id"],
        "policy_registry_sha256": policy["registry_sha256"],
        "evaluation_id": policy["evaluation_id"],
        "evaluation_report_sha256": policy["evaluation_report_sha256"],
        "reground_report_id": reground["report_id"],
        "reground_report_sha256": reground["report_sha256"],
        "reground_dataset_id": reground["dataset_id"],
        "reground_dataset_sha256": reground["dataset_sha256"],
    }


def _build_packet(context: dict[str, Any], candidate: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    assessment = context["assessment"]
    report = context["report"]
    reconciliation = context["reconciliation"]
    github = candidate["pull_request"]
    return _finalize(
        {
            "schema_version": SCHEMA_VERSION,
            "packet_contract": PACKET_CONTRACT,
            "packet_id": "",
            "packet_sha256": "",
            "project_id": context["registry"]["project_id"],
            "assessment_id": assessment["assessment_id"],
            "assessment_sha256": assessment["assessment_sha256"],
            "task_id": assessment["task_id"],
            "source_revision": assessment["source_revision"],
            "trust_report_id": assessment["trust_report_id"],
            "trust_report_sha256": assessment["trust_report_sha256"],
            "github": {
                "candidate_id": candidate["candidate_id"],
                "candidate_evidence_snapshot_sha256": candidate["evidence_snapshot_sha256"],
                "candidate_report_sha256": candidate["report_sha256"],
                "hostname": candidate["repository"]["hostname"],
                "repository": candidate["repository"]["name_with_owner"],
                "pr_number": github["number"],
                "pr_url": github.get("url"),
                "base_oid": github.get("base_oid"),
                "head_oid": github["head_oid"],
            },
            "predicted_risk_band": assessment["predicted_risk_band"],
            "changed_files": report["request"]["changed_files"],
            "hard_gates": report["task_advisory"]["triggered_hard_gates"],
            "review_requirement": report["task_advisory"]["review_requirement"],
            "evidence_references": _evidence_references(report),
            "source_replay_state": {
                "trust_sources_verified": True,
                "assessment_source_sha256": context["assessment_source_sha256"],
                "assessment_reconciled": True,
                "assessment_reconciliation_status": context["assessment_reconciliation"]["status"],
            },
            "reconciliation_state": {
                "status": reconciliation["status"],
                "source_reconciliation_complete": reconciliation["summary"]["source_reconciliation_complete"],
            },
            "generated_at": generated_at,
            "mode": "REPORT_ONLY",
            "automation_authorized": False,
            "pilot_authorized": False,
            "human_review_recorded": False,
            "outcome_recorded": False,
            "evidence_snapshot_sha256": "",
        }
    )


def prepare_review_packet(
    workspace_root: str | Path,
    *,
    assessment_id: str,
    github_candidate: str | Path,
    repository_root: str | Path,
    github_cli: GitHubCLI,
    repository: str | None = None,
    generated_at: str | None = None,
    collect_pr: Callable[..., tuple[dict[str, Any], str | None]] = collect_pull_request,
) -> dict[str, Any]:
    generated = _timestamp(generated_at or utc_now(), "generated_at")
    _candidate_source, candidate = load_github_prospective_capture_candidate(github_candidate)
    context = _assessment_context(workspace_root, assessment_id, generated_at=generated)
    _require_candidate_binding(context, candidate)
    _verify_live_github(candidate, repository_root, github_cli, repository=repository, collect_pr=collect_pr)
    return _build_packet(context, candidate, generated_at=generated)


def verify_review_packet_sources(
    packet: dict[str, Any],
    *,
    workspace_root: str | Path,
    github_candidate: str | Path,
    repository_root: str | Path,
    github_cli: GitHubCLI,
    repository: str | None = None,
    collect_pr: Callable[..., tuple[dict[str, Any], str | None]] = collect_pull_request,
) -> list[str]:
    errors = verify_review_packet_data(packet)
    if errors:
        return errors
    try:
        _candidate_source, candidate = load_github_prospective_capture_candidate(github_candidate)
        context = _assessment_context(workspace_root, packet["assessment_id"], generated_at=packet["generated_at"])
        _require_candidate_binding(context, candidate)
        _verify_live_github(candidate, repository_root, github_cli, repository=repository, collect_pr=collect_pr)
        replay = _build_packet(context, candidate, generated_at=packet["generated_at"])
        authoritative_fields = (
            "packet_contract",
            "packet_id",
            "packet_sha256",
            "project_id",
            "assessment_id",
            "assessment_sha256",
            "task_id",
            "source_revision",
            "trust_report_id",
            "trust_report_sha256",
            "github",
            "predicted_risk_band",
            "changed_files",
            "hard_gates",
            "review_requirement",
            "evidence_references",
            "source_replay_state",
            "reconciliation_state",
            "mode",
            "automation_authorized",
            "pilot_authorized",
            "human_review_recorded",
            "outcome_recorded",
            "evidence_snapshot_sha256",
        )
        mismatches = [field for field in authoritative_fields if replay.get(field) != packet.get(field)]
        errors.extend(f"STALE_REVIEW_PACKET: source replay {field} mismatch" for field in mismatches)
    except (
        ProspectiveReviewError,
        ProspectiveReviewVerificationError,
        ProspectiveEvidenceError,
        ProspectiveEvidenceVerificationError,
        TrustComparisonError,
        TrustComparisonVerificationError,
        TrustReconciliationError,
        TrustReconciliationVerificationError,
        GitHubCLIError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        errors.append(f"STALE_REVIEW_PACKET: source replay failed: {exc}")
    return sorted(set(errors))


def _review_dir(root: Path, assessment_id: str, packet_id: str) -> Path:
    target = root / "cases" / assessment_id / "reviews" / packet_id
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ProspectiveReviewError("review packet path escaped workspace") from exc
    if _path_has_symlink(target):
        raise ProspectiveReviewError(f"review packet path must not contain symlinks: {target}")
    return target


def _existing_packet_binding(registry: dict[str, Any], assessment_id: str, packet_id: str, packet_sha256: str) -> dict[str, Any] | None:
    for event in registry["events"]:
        if event.get("event_type") == "HUMAN_DECISION" and event.get("assessment_id") == assessment_id:
            payload = event.get("payload", {})
            if payload.get("review_packet_id") == packet_id or payload.get("review_packet_sha256") == packet_sha256:
                return event
    return None


def submit_review_packet(
    packet_path: str | Path,
    *,
    workspace_root: str | Path,
    github_candidate: str | Path,
    repository_root: str | Path,
    github_cli: GitHubCLI,
    review_level: str,
    decision: str,
    actor: str,
    repository: str | None = None,
    occurred_at: str | None = None,
    confirmed_risk_band: str | None = None,
    reason_codes: Iterable[str] = (),
    collect_pr: Callable[..., tuple[dict[str, Any], str | None]] = collect_pull_request,
) -> dict[str, Any]:
    level = review_level.upper()
    if level not in {"REVIEWED", "AUDITED"}:
        raise ProspectiveReviewError("prospective review submission requires REVIEWED or AUDITED")
    packet_source, packet = load_review_packet(packet_path)
    errors = verify_review_packet_sources(
        packet,
        workspace_root=workspace_root,
        github_candidate=github_candidate,
        repository_root=repository_root,
        github_cli=github_cli,
        repository=repository,
        collect_pr=collect_pr,
    )
    if errors:
        raise ProspectiveReviewVerificationError(errors)
    root = _safe_root(workspace_root)
    _registry_path, _manifest_path, _policy_path, registry, _manifest, _policy = _required_workspace(root)
    duplicate = _existing_packet_binding(registry, packet["assessment_id"], packet["packet_id"], packet["packet_sha256"])
    if duplicate is not None:
        raise ProspectiveReviewError("duplicate review submission for exact prospective review packet: " + duplicate["event_id"])
    candidate_source = _safe_input(github_candidate, "GitHub prospective capture candidate")
    review_root = _review_dir(root, packet["assessment_id"], packet["packet_id"])
    if review_root.exists():
        raise ProspectiveReviewError(f"review packet archive already exists without event binding: {review_root}")
    staging_parent = Path(tempfile.mkdtemp(prefix=".prospective-review.", dir=root))
    staging = staging_parent / packet["packet_id"]
    staging.mkdir()
    try:
        shutil.copyfile(packet_source, staging / "review-packet.json")
        shutil.copyfile(candidate_source, staging / "github-capture-candidate.json")
        review_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, review_root)
        result = record_case_review(
            root,
            assessment_id=packet["assessment_id"],
            review_level=level,
            decision=decision,
            actor=actor,
            occurred_at=occurred_at,
            confirmed_risk_band=confirmed_risk_band,
            reason_codes=reason_codes,
            review_packet_id=packet["packet_id"],
            review_packet_sha256=packet["packet_sha256"],
        )
    except Exception:
        shutil.rmtree(review_root, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)
    return {
        **result,
        "review_packet_id": packet["packet_id"],
        "review_packet_sha256": packet["packet_sha256"],
        "review_packet_archive": str(review_root),
        "mode": "REPORT_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "outcome_recorded": False,
    }

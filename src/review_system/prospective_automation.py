from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .application import AnalyzePullRequestRequest, analyze_pull_request
from .github_connector import GitHubCLI
from .github_prospective_capture import materialize_github_prospective_capture
from .identity import file_sha256
from .operational_policy_binder import (
    OperationalPolicyBindingError,
    bind_operational_policy,
    write_operational_policy_binding,
)
from .operational_review_brief import (
    CONTRACT_VERSION as REVIEW_BRIEF_CONTRACT_VERSION,
    OperationalReviewBriefError,
    build_operational_review_brief,
    write_operational_review_brief,
    write_operational_review_brief_markdown,
)
from .operational_trust_supply import (
    build_operational_trust_supply_observation,
    write_operational_trust_supply_observation,
)
from .prospective_evidence_bundle import verify_evidence_bundle, write_evidence_bundle
from .prospective_execution_identity import build_prospective_execution_identity
from .prospective_replay import build_deterministic_result
from .trust_prospective_review import prepare_review_packet, write_review_packet


_SHA40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_PR_NUMBER = re.compile(r"(?:^|/pull/)(\d+)(?:$|/)")


class ProspectiveAutomationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RunGitHubPRRequest:
    pull_request: str
    event_head_sha: str
    pie_revision: str
    repository_root: str | Path = "."
    repository: str | None = None
    profile: str = ".review/project.yml"
    config: str = ".review/intelligence/config.yml"
    trust_request: str | Path | None = None
    operational_policy: str | None = None
    operational_trust_facts: str | Path | None = None
    workspace: str | Path | None = None
    output_root: str | Path = ".pie/automation"
    generated_at: str | None = None
    captured_at: str | None = None


def _exact_sha(value: str, field: str) -> str:
    normalized = value.strip().lower()
    if _SHA40.fullmatch(normalized) is None:
        raise ProspectiveAutomationError("INVALID_INPUT", f"{field} must be an exact 40-character Git SHA")
    return normalized


def _project_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _pr_hint(value: str) -> str:
    match = _PR_NUMBER.search(value.strip())
    return match.group(1) if match else "unknown"


def _dump_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProspectiveAutomationError("EVIDENCE_HASH_MISMATCH", f"expected JSON object: {path}")
    return value


def _assert_exact_source_binding(*, event_head: str, source: dict[str, Any]) -> tuple[str, str]:
    pr = source.get("pull_request", {})
    remote = str(pr.get("head_oid") or "").lower()
    local = str(source.get("local_project_state", {}).get("head_revision") or "").lower()
    if not remote or not local:
        raise ProspectiveAutomationError(
            "HEAD_MISMATCH",
            "exact source binding requires both live GitHub PR head and checked-out local head",
        )
    if event_head != remote or event_head != local:
        raise ProspectiveAutomationError(
            "STALE_SOURCE_REVISION",
            f"event/live/local head mismatch: event={event_head} live={remote} local={local}",
        )
    repository = str(source.get("repository", {}).get("name_with_owner") or "").lower()
    if not repository:
        raise ProspectiveAutomationError("SOURCE_MISMATCH", "GitHub source repository identity is missing")
    return repository, remote


def run_github_pr(
    request: RunGitHubPRRequest,
    *,
    github_cli: GitHubCLI,
) -> dict[str, Any]:
    root = Path(request.repository_root).resolve()
    if not root.is_dir():
        raise ProspectiveAutomationError("INVALID_INPUT", f"repository root does not exist: {root}")
    if request.trust_request is not None and request.operational_policy is not None:
        raise ProspectiveAutomationError(
            "INVALID_INPUT",
            "explicit Trust request and Operational Policy binding are mutually exclusive inputs",
        )
    if request.operational_trust_facts is not None and request.operational_policy is None:
        raise ProspectiveAutomationError(
            "INVALID_INPUT",
            "operational Trust facts require --operational-policy",
        )

    event_head = _exact_sha(request.event_head_sha, "event_head_sha")
    pie_revision = _exact_sha(request.pie_revision, "pie_revision")
    profile_path = _project_path(root, request.profile)
    config_path = _project_path(root, request.config)
    if not profile_path.is_file():
        raise ProspectiveAutomationError("PROFILE_INVALID", f"project profile does not exist: {profile_path}")
    if not config_path.is_file():
        raise ProspectiveAutomationError("PROFILE_INVALID", f"intelligence config does not exist: {config_path}")

    output_root = _project_path(root, request.output_root)
    analysis_dir = output_root / "analysis" / f"pr-{_pr_hint(request.pull_request)}-{event_head[:12]}"
    try:
        analysis = analyze_pull_request(
            AnalyzePullRequestRequest(
                pull_request=request.pull_request,
                repository_root=root,
                repository=request.repository,
                profile=str(profile_path),
                config=str(config_path),
                graph=str(analysis_dir / "graph.json"),
                allow_repository_mismatch=False,
                allow_head_mismatch=False,
                allow_dirty_worktree=False,
                output_dir=analysis_dir,
            ),
            github_cli=github_cli,
        )
    except ValueError as exc:
        text = str(exc)
        code = "HEAD_MISMATCH" if "HEAD" in text or "head" in text else "SOURCE_MISMATCH"
        if "profile" in text or "config" in text:
            code = "PROFILE_INVALID"
        raise ProspectiveAutomationError(code, text) from exc

    repository, source_revision = _assert_exact_source_binding(event_head=event_head, source=analysis.source)
    if request.repository and request.repository.strip().lower() != repository:
        raise ProspectiveAutomationError(
            "SOURCE_MISMATCH",
            f"requested repository {request.repository!r} does not match collected source {repository!r}",
        )

    candidate_path = Path(analysis.prospective_candidate_path)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if not isinstance(candidate, dict):
        raise ProspectiveAutomationError("EVIDENCE_HASH_MISMATCH", "prospective candidate must contain an object")
    candidate_sha256 = file_sha256(candidate_path)

    operational_binding: dict[str, Any] | None = None
    operational_binding_path: Path | None = None
    operational_policy_snapshot: Path | None = None
    operational_facts_path: Path | None = None
    request_path = _project_path(root, request.trust_request) if request.trust_request is not None else None
    if request_path is not None and not request_path.is_file():
        raise ProspectiveAutomationError("INVALID_INPUT", f"Trust request does not exist: {request_path}")

    if request.operational_policy is not None:
        operational_binding_path = analysis.output_dir / "operational-policy-binding.json"
        operational_policy_snapshot = analysis.output_dir / "operational-base-policy.yml"
        generated_request = analysis.output_dir / "operational-trust-request.json"
        if request.operational_trust_facts is not None:
            operational_facts_path = _project_path(root, request.operational_trust_facts)
            if not operational_facts_path.is_file():
                raise ProspectiveAutomationError(
                    "INVALID_INPUT",
                    f"operational Trust facts do not exist: {operational_facts_path}",
                )
        try:
            operational_binding = bind_operational_policy(
                candidate_path,
                github_cli=github_cli,
                repository_root=root,
                policy_path=request.operational_policy,
                trust_facts=operational_facts_path,
                trust_request_output=generated_request,
                policy_snapshot_output=operational_policy_snapshot,
            )
            write_operational_policy_binding(operational_binding_path, operational_binding)
        except OperationalPolicyBindingError as exc:
            raise ProspectiveAutomationError(exc.code, str(exc)) from exc
        if operational_binding["trust_request"]["materialized"]:
            request_path = generated_request

    trust_supply_observation = build_operational_trust_supply_observation(
        operational_policy_requested=request.operational_policy is not None,
        explicit_input_declared=request.operational_trust_facts is not None,
        explicit_input_available=operational_facts_path is not None,
        operational_binding=operational_binding,
    )
    trust_supply_path = write_operational_trust_supply_observation(
        analysis.output_dir / "operational-trust-facts-supply.json",
        trust_supply_observation,
    )

    trust_request_sha256 = file_sha256(request_path) if request_path is not None else None
    identity = build_prospective_execution_identity(
        repository=repository,
        pull_request=int(analysis.source["pull_request"]["number"]),
        source_revision=source_revision,
        pie_revision=pie_revision,
        profile_sha256=file_sha256(profile_path),
        config_sha256=file_sha256(config_path),
        trust_request_sha256=trust_request_sha256,
    )
    bundle_root = output_root / "bundles" / identity.execution_id

    evidence_files: dict[str, str | Path] = {
        "source/github-source.json": analysis.source_path,
        "source/identity.json": analysis.output_dir / "identity.json",
        "analysis/impact.json": analysis.impact_path,
        "analysis/REPORT.md": analysis.report_path,
        "prospective/candidate.json": candidate_path,
        "operational/trust-facts-supply.json": trust_supply_path,
    }
    if analysis.diff_path is not None:
        evidence_files["source/pull-request.diff"] = analysis.diff_path
    if analysis.workflow_semantics_path is not None:
        evidence_files["analysis/workflow-semantics.json"] = analysis.workflow_semantics_path
    if operational_binding_path is not None:
        evidence_files["operational/binding.json"] = operational_binding_path
    if operational_policy_snapshot is not None and operational_policy_snapshot.is_file():
        evidence_files["operational/base-policy.yml"] = operational_policy_snapshot
    if operational_facts_path is not None:
        evidence_files["operational/trust-facts.yml"] = operational_facts_path

    summary: dict[str, Any] = {
        "schema_version": "PIE_PR_PROSPECTIVE_RUN_V1",
        "execution_id": identity.execution_id,
        "repository": repository,
        "pull_request": int(analysis.source["pull_request"]["number"]),
        "source_revision": source_revision,
        "pie_revision": pie_revision,
        "status": "WAITING_FOR_TRUST_INPUT",
        "next_step": "PROVIDE_EXPLICIT_TRUST_REQUEST",
        "candidate_id": candidate.get("candidate_id"),
        "assessment_id": None,
        "packet_id": None,
        "risk_band": None,
        "readiness": None,
        "operational_binding_status": operational_binding.get("status") if operational_binding else None,
        "operational_match_status": operational_binding.get("match_status") if operational_binding else None,
        "operational_binding_sha256": operational_binding.get("binding_sha256") if operational_binding else None,
        "operational_policy_sha256": operational_binding.get("policy", {}).get("policy_sha256") if operational_binding else None,
        "operational_missing_inputs": operational_binding.get("missing_inputs", []) if operational_binding else [],
        "review_brief_contract_version": REVIEW_BRIEF_CONTRACT_VERSION,
        "review_brief_sha256": None,
        "auto_capture": True,
        "auto_analysis": True,
        "auto_trust_assessment": False,
        "auto_packet_prepare": False,
        "human_review_recorded": False,
        "outcome_recorded": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "deterministic_replay_bound": request_path is None,
        "deterministic_result_sha256": None,
    }
    if operational_binding is not None and request_path is None:
        summary["next_step"] = "PROVIDE_EXPLICIT_OPERATIONAL_TRUST_FACTS"

    review_packet: dict[str, Any] | None = None
    if request_path is not None:
        if request.workspace is None:
            raise ProspectiveAutomationError(
                "INVALID_INPUT",
                "workspace is required when a Trust request is supplied or materialized",
            )
        workspace = _project_path(root, request.workspace)
        trust_report_path = analysis.output_dir / "prospective-trust-report.json"
        try:
            materialized = materialize_github_prospective_capture(
                candidate_path,
                request=request_path,
                workspace=workspace,
                profile=profile_path,
                repository_root=root,
                github_cli=github_cli,
                repository=repository,
                trust_report_output=trust_report_path,
                generated_at=request.generated_at,
                captured_at=request.captured_at,
            )
        except Exception as exc:
            raise ProspectiveAutomationError("PROSPECTIVE_MATERIALIZATION_FAILED", str(exc)) from exc
        materialization_path = _dump_json(analysis.output_dir / "prospective-materialization.json", materialized)
        assessment_id = materialized["assessment_id"]
        review_packet = prepare_review_packet(
            workspace,
            assessment_id=assessment_id,
            github_candidate=candidate_path,
            repository_root=root,
            github_cli=github_cli,
            repository=repository,
            generated_at=request.generated_at,
        )
        packet_path = write_review_packet(analysis.output_dir / "prospective-review-packet.json", review_packet)
        evidence_files.update({
            "trust/request.json": request_path,
            "trust/assessment.json": trust_report_path,
            "prospective/materialized-case.json": materialization_path,
            "review/packet.json": packet_path,
        })
        summary.update({
            "status": "READY_FOR_HUMAN_REVIEW",
            "next_step": "EXPLICIT_HUMAN_REVIEW_REQUIRED",
            "assessment_id": assessment_id,
            "packet_id": review_packet["packet_id"],
            "risk_band": materialized.get("predicted_risk_band"),
            "readiness": materialized.get("readiness") or materialized.get("readiness_status"),
            "auto_trust_assessment": True,
            "auto_packet_prepare": True,
            "deterministic_replay_bound": False,
        })

    deterministic_result = None
    if request_path is None:
        workflow_semantics = _load_json(analysis.workflow_semantics_path)
        deterministic_result = build_deterministic_result(
            identity=identity.to_dict(),
            summary=summary,
            base_revision=analysis.source.get("pull_request", {}).get("base_oid"),
            changed_files=list(analysis.changed_files),
            diff_sha256=file_sha256(analysis.diff_path) if analysis.diff_path is not None else None,
            impact=analysis.impact,
            candidate=candidate,
            workflow_semantics=workflow_semantics,
        )
        summary["deterministic_result_sha256"] = deterministic_result["deterministic_result_sha256"]

    try:
        review_brief = build_operational_review_brief(
            summary=summary,
            candidate=candidate,
            candidate_sha256=candidate_sha256,
            impact=analysis.impact,
            operational_binding=operational_binding,
            review_packet=review_packet,
        )
        review_brief_path = write_operational_review_brief(analysis.output_dir / "operational-review-brief.json", review_brief)
        review_brief_markdown = write_operational_review_brief_markdown(
            analysis.output_dir / "OPERATIONAL-REVIEW-BRIEF.md",
            review_brief,
        )
    except OperationalReviewBriefError as exc:
        raise ProspectiveAutomationError("REVIEW_BRIEF_INVALID", str(exc)) from exc
    summary["review_brief_sha256"] = review_brief["brief_sha256"]
    evidence_files.update({
        "review/brief.json": review_brief_path,
        "review/BRIEF.md": review_brief_markdown,
    })

    manifest = write_evidence_bundle(
        bundle_root,
        summary=summary,
        identity=identity.to_dict(),
        evidence_files=evidence_files,
        deterministic_result=deterministic_result,
    )
    errors = verify_evidence_bundle(bundle_root)
    if errors:
        raise ProspectiveAutomationError("EVIDENCE_HASH_MISMATCH", "; ".join(errors))
    return {
        **summary,
        "bundle": str(bundle_root),
        "manifest_sha256": manifest["manifest_sha256"],
        "execution_key_sha256": identity.execution_key_sha256,
    }

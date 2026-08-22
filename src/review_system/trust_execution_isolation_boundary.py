from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


CONTRACT_VERSION = "TRUST_PEB3R_ISOLATION_BOUNDARY_V1"
MODE = "REPORT_ONLY"
READY_STATUS = "READY_FOR_CONTROLLED_NON_PRODUCTION_EXECUTION_REVIEW"
BLOCKED_STATUS = "BLOCKED"

_REQUIRED_OPERATIONS = {"MARK_READY_FOR_REVIEW", "CONVERT_TO_DRAFT"}


def _truthy(value: Any) -> bool:
    return value is True


def assess_isolation_boundary(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Assess whether the external PEB-3R repository/credential boundary is proven.

    This verifier is intentionally side-effect-free. It evaluates provider/admin
    evidence supplied by a caller and never creates repositories, credentials,
    installations, tokens, pull requests, or external mutations.
    """

    data = deepcopy(dict(evidence))
    blockers: list[str] = []

    if data.get("contract_version") != CONTRACT_VERSION:
        blockers.append("CONTRACT_VERSION_MISMATCH")

    if data.get("mode") != MODE:
        blockers.append("REPORT_ONLY_MODE_REQUIRED")

    if data.get("production_execution_authorized") is not False:
        blockers.append("PRODUCTION_EXECUTION_AUTHORITY_FORBIDDEN")

    if data.get("automation_authorized") is not False:
        blockers.append("AUTOMATION_AUTHORITY_FORBIDDEN")

    if data.get("pilot_authorized") is not False:
        blockers.append("PILOT_AUTHORITY_FORBIDDEN")

    repository = data.get("dedicated_repository") or {}
    repository_ready = all(
        (
            _truthy(repository.get("exists")),
            _truthy(repository.get("calibration_only")),
            repository.get("production_deployment") is False,
            repository.get("production_secrets") is False,
            repository.get("business_source_authority") is False,
            isinstance(repository.get("full_name"), str),
            bool(repository.get("full_name")),
        )
    )
    if not repository_ready:
        blockers.append("DEDICATED_NONPRODUCTION_REPOSITORY_NOT_ESTABLISHED")

    credential = data.get("credential") or {}
    repository_full_name = repository.get("full_name")
    repository_set = credential.get("repository_set")
    github_app_scope_ready = all(
        (
            credential.get("mechanism") == "GITHUB_APP_INSTALLATION_TOKEN",
            _truthy(credential.get("installation_identity_proven")),
            _truthy(credential.get("selected_repository_scope_proven")),
            isinstance(repository_set, list),
            repository_set == [repository_full_name] if repository_full_name else False,
        )
    )
    if not github_app_scope_ready:
        blockers.append("SELECTED_REPOSITORY_GITHUB_APP_SCOPE_NOT_PROVEN")

    token_scope_ready = all(
        (
            _truthy(credential.get("token_repository_set_proven")),
            _truthy(credential.get("token_permission_set_proven")),
            _truthy(credential.get("bounded_validity_proven")),
            credential.get("pie_repository_write_authority") is False,
            credential.get("production_repository_write_authority") is False,
        )
    )
    if not token_scope_ready:
        blockers.append("SHORT_LIVED_TOKEN_SCOPE_NOT_PROVEN")

    adapter = data.get("adapter") or {}
    allowed_operations = adapter.get("allowed_operations")
    adapter_ready = all(
        (
            adapter.get("provider") == "GITHUB",
            adapter.get("repository") == repository_full_name if repository_full_name else False,
            adapter.get("resource_type") == "PULL_REQUEST",
            _truthy(adapter.get("exact_pr_binding")),
            _truthy(adapter.get("exact_head_binding")),
            _truthy(adapter.get("exact_precondition_binding")),
            set(allowed_operations or []) == _REQUIRED_OPERATIONS,
            adapter.get("arbitrary_command_surface") is False,
            adapter.get("arbitrary_api_surface") is False,
            adapter.get("merge_surface") is False,
            adapter.get("close_surface") is False,
            adapter.get("file_write_surface") is False,
            adapter.get("branch_write_surface") is False,
            adapter.get("workflow_write_surface") is False,
            adapter.get("secret_write_surface") is False,
            adapter.get("repository_settings_surface") is False,
        )
    )
    if not adapter_ready:
        blockers.append("GOVERNED_ADAPTER_BINDING_NOT_READY")

    provider_evidence = data.get("provider_evidence") or {}
    provider_evidence_ready = all(
        (
            _truthy(provider_evidence.get("repository_metadata_readback")),
            _truthy(provider_evidence.get("installation_repository_set_readback")),
            _truthy(provider_evidence.get("token_permission_set_readback")),
        )
    )
    if not provider_evidence_ready:
        blockers.append("AUTHORITATIVE_PROVIDER_SCOPE_EVIDENCE_INCOMPLETE")

    status = READY_STATUS if not blockers else BLOCKED_STATUS
    next_step = (
        "PEB-3E_CONTROLLED_NON_PRODUCTION_EXECUTION_REVIEW"
        if status == READY_STATUS
        else "ESTABLISH_EXTERNAL_ADMIN_RESOURCE_AND_CREDENTIAL_BOUNDARY"
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "mode": MODE,
        "status": status,
        "blockers": blockers,
        "next_step": next_step,
        "production_execution_authorized": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "formal_dispatch_permitted": status == READY_STATUS,
    }


def verify_isolation_boundary_assessment(
    evidence: Mapping[str, Any], assessment: Mapping[str, Any]
) -> bool:
    """Return True only when an assessment is the exact deterministic projection."""

    return dict(assessment) == assess_isolation_boundary(evidence)

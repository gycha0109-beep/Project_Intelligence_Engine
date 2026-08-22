from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any, Iterable

from .github.source import validate_pull_request_source
from .identity import canonical_json_sha256, normalize_source_revision
from .intelligence_config import normalize_path
from .workflow_semantics import split_git_diff_by_path


CONTRACT_VERSION_V1_3 = "TRUST_R4_SEMANTIC_UNDERDETECTION_SHADOW_V1"
CONTRACT_VERSION_V1_4 = "TRUST_R4_EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_AUTHORITY_V1"
CONTRACT_VERSION = CONTRACT_VERSION_V1_4
CLASSIFICATIONS = (
    "NORMATIVE_DECISION_AUTHORITY",
    "EXECUTABLE_VERIFICATION_GATE_AUTHORITY",
    "SUPPORTING_EVALUATION_ONLY",
    "SUPPORTING_REGRESSION_ONLY",
    "UNKNOWN",
)
TRUST_R4_SEMANTIC_EVIDENCE_SCHEMA_VERSION = "1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_R4_AUTHORITY_CLASSES = {
    "NORMATIVE_DECISION_AUTHORITY",
    "EXECUTABLE_VERIFICATION_GATE_AUTHORITY",
}
_SUPPORTED_RISK_MODELS = {"1.3", "1.4"}


def _contract_for_risk_model(risk_model_version: str) -> str:
    if risk_model_version == "1.3":
        return CONTRACT_VERSION_V1_3
    if risk_model_version == "1.4":
        return CONTRACT_VERSION_V1_4
    raise ValueError(f"R4 semantic evidence does not support Trust risk model {risk_model_version}")


def _normalize_changed_files(paths: Iterable[str]) -> list[str]:
    source = list(paths)
    try:
        normalized = sorted({normalize_path(path) for path in source})
    except ValueError as exc:
        raise ValueError(f"changed files are invalid: {exc}") from exc
    if not normalized:
        raise ValueError("changed files must not be empty")
    if len(normalized) != len(source):
        raise ValueError("changed files must not contain normalized duplicates")
    return normalized


def _normalize_sha256(value: Any, field: str) -> str:
    text = str(value).strip().lower()
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{field} must be a 64-hex SHA-256")
    return text


def _normalize_analysis(value: Any, *, contract_version: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("R4 semantic file evidence must be an object")
    required = {
        "contract_version",
        "path",
        "classification",
        "is_r4_authority",
        "reason_ids",
        "signals",
        "patch_sha256",
    }
    if set(value) != required:
        raise ValueError("R4 semantic file evidence fields do not match the v1 contract")
    if value.get("contract_version") != contract_version:
        raise ValueError("R4 semantic contract_version mismatch")
    path = normalize_path(value.get("path"))
    classification = value.get("classification")
    if classification not in CLASSIFICATIONS:
        raise ValueError("R4 semantic classification is unsupported")
    is_r4_authority = value.get("is_r4_authority")
    if not isinstance(is_r4_authority, bool):
        raise ValueError("R4 semantic is_r4_authority must be boolean")
    if is_r4_authority != (classification in _R4_AUTHORITY_CLASSES):
        raise ValueError("R4 semantic authority flag does not match classification")
    reason_ids = value.get("reason_ids")
    if (
        not isinstance(reason_ids, list)
        or not reason_ids
        or any(not isinstance(item, str) or not item.strip() for item in reason_ids)
    ):
        raise ValueError("R4 semantic reason_ids are invalid")
    signals = value.get("signals")
    if not isinstance(signals, dict):
        raise ValueError("R4 semantic signals must be an object")
    return {
        "contract_version": contract_version,
        "path": path,
        "classification": classification,
        "is_r4_authority": is_r4_authority,
        "reason_ids": [item.strip() for item in reason_ids],
        "signals": deepcopy(signals),
        "patch_sha256": _normalize_sha256(value.get("patch_sha256"), "patch_sha256"),
    }


def _analyze_authoritative_r4_semantics(
    path: str,
    patch: str,
    *,
    risk_model_version: str,
) -> dict[str, Any]:
    # Lazy imports avoid trust -> authority -> shadow -> trust import cycles while
    # preserving the frozen v1.3 analyzer and the separately calibrated v1.4
    # verifier-role discriminator as their single implementations.
    from .trust_r4_semantics_shadow import analyze_r4_semantics

    current = analyze_r4_semantics(path, patch)
    if risk_model_version == "1.3":
        return {
            **current,
            "contract_version": CONTRACT_VERSION_V1_3,
        }

    from .trust_r4_verifier_role_shadow import analyze_r4_verifier_role_candidate

    candidate_result = analyze_r4_verifier_role_candidate(path, patch)
    candidate = deepcopy(candidate_result["candidate"])
    signals = deepcopy(candidate["signals"])
    signals["verifier_role_candidate"] = deepcopy(candidate_result["candidate_signals"])
    signals["verifier_role_promoted"] = bool(candidate_result["candidate_triggered"])
    return {
        **candidate,
        "contract_version": CONTRACT_VERSION_V1_4,
        "signals": signals,
    }


def build_trust_r4_semantic_evidence(
    *,
    github_source: dict[str, Any],
    diff_text: str,
    source_revision: str,
    changed_files: Iterable[str],
    risk_model_version: str = "1.4",
) -> dict[str, Any]:
    contract_version = _contract_for_risk_model(risk_model_version)
    errors = validate_pull_request_source(github_source)
    if errors:
        raise ValueError("invalid GitHub source: " + "; ".join(errors))
    if not isinstance(diff_text, str):
        raise TypeError("R4 semantic diff must be a string")

    revision = normalize_source_revision(source_revision)
    if revision == "unresolved":
        raise ValueError("source revision must be stable")
    files = _normalize_changed_files(changed_files)

    pull_request = github_source["pull_request"]
    head_revision = normalize_source_revision(pull_request.get("head_oid"))
    if head_revision != revision:
        raise ValueError("GitHub source head revision does not match Trust request")
    source_files = _normalize_changed_files(
        item["path"] for item in pull_request.get("changed_files", [])
    )
    if source_files != files:
        raise ValueError("GitHub source changed files do not match Trust request")

    diff_metadata = github_source.get("diff")
    if not isinstance(diff_metadata, dict) or not diff_metadata.get("available"):
        raise ValueError("GitHub source does not contain available diff evidence")
    encoded = diff_text.encode("utf-8")
    diff_sha256 = hashlib.sha256(encoded).hexdigest()
    if diff_metadata.get("sha256") != diff_sha256:
        raise ValueError("R4 semantic diff SHA-256 does not match GitHub source")
    if diff_metadata.get("bytes") != len(encoded):
        raise ValueError("R4 semantic diff byte length does not match GitHub source")

    sections = split_git_diff_by_path(diff_text)
    missing = sorted(set(files) - set(sections))
    if missing:
        raise ValueError(
            "R4 semantic diff is missing changed file sections: " + ", ".join(missing)
        )

    analyses: list[dict[str, Any]] = []
    for path in files:
        patch = sections[path]
        analysis = _analyze_authoritative_r4_semantics(
            path,
            patch,
            risk_model_version=risk_model_version,
        )
        analyses.append(
            {
                **analysis,
                "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            }
        )

    semantics = {
        "contract_version": contract_version,
        "source_revision": revision,
        "source_evidence_sha256": github_source["source_sha256"],
        "diff_sha256": diff_sha256,
        "changed_files_sha256": canonical_json_sha256(files),
        "files": analyses,
    }
    repository = github_source["repository"]
    projection = {
        "schema_version": TRUST_R4_SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "repository_hostname": repository["hostname"],
        "repository_name_with_owner": repository["name_with_owner"],
        "pull_request_number": pull_request["number"],
        "semantics": semantics,
    }
    return {
        **projection,
        "evidence_sha256": canonical_json_sha256(projection),
    }


def normalize_trust_r4_semantic_evidence(
    value: Any,
    *,
    source_revision: str,
    changed_files: Iterable[str],
    risk_model_version: str = "1.4",
) -> dict[str, Any]:
    contract_version = _contract_for_risk_model(risk_model_version)
    if not isinstance(value, dict):
        raise ValueError("Trust R4 semantic evidence must be an object")
    required = {
        "schema_version",
        "repository_hostname",
        "repository_name_with_owner",
        "pull_request_number",
        "semantics",
        "evidence_sha256",
    }
    if set(value) != required:
        raise ValueError("Trust R4 semantic evidence fields do not match the v1 contract")
    if value.get("schema_version") != TRUST_R4_SEMANTIC_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported Trust R4 semantic evidence schema_version")

    hostname = value.get("repository_hostname")
    repository = value.get("repository_name_with_owner")
    pr_number = value.get("pull_request_number")
    if not isinstance(hostname, str) or not hostname.strip():
        raise ValueError("Trust R4 semantic evidence repository_hostname is required")
    if not isinstance(repository, str) or not repository.strip() or "/" not in repository:
        raise ValueError("Trust R4 semantic evidence repository_name_with_owner is invalid")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number < 1:
        raise ValueError("Trust R4 semantic evidence pull_request_number is invalid")

    files = _normalize_changed_files(changed_files)
    revision = normalize_source_revision(source_revision)
    semantics_value = value.get("semantics")
    if not isinstance(semantics_value, dict):
        raise ValueError("Trust R4 semantic evidence semantics must be an object")
    expected_semantic_fields = {
        "contract_version",
        "source_revision",
        "source_evidence_sha256",
        "diff_sha256",
        "changed_files_sha256",
        "files",
    }
    if set(semantics_value) != expected_semantic_fields:
        raise ValueError("Trust R4 semantic semantics fields do not match the v1 contract")
    if semantics_value.get("contract_version") != contract_version:
        raise ValueError("Trust R4 semantic contract_version mismatch")
    if normalize_source_revision(semantics_value.get("source_revision")) != revision:
        raise ValueError("Trust R4 semantic source revision does not match Trust request")
    source_hash = _normalize_sha256(
        semantics_value.get("source_evidence_sha256"),
        "source_evidence_sha256",
    )
    diff_hash = _normalize_sha256(semantics_value.get("diff_sha256"), "diff_sha256")
    changed_hash = _normalize_sha256(
        semantics_value.get("changed_files_sha256"),
        "changed_files_sha256",
    )
    if changed_hash != canonical_json_sha256(files):
        raise ValueError("Trust R4 semantic changed_files_sha256 mismatch")

    raw_analyses = semantics_value.get("files")
    if not isinstance(raw_analyses, list):
        raise ValueError("Trust R4 semantic files must be an array")
    analyses = [
        _normalize_analysis(item, contract_version=contract_version)
        for item in raw_analyses
    ]
    paths = [item["path"] for item in analyses]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError("Trust R4 semantic file evidence paths must be sorted and unique")
    if paths != files:
        raise ValueError("Trust R4 semantic file evidence does not cover changed files exactly")

    semantics = {
        "contract_version": contract_version,
        "source_revision": revision,
        "source_evidence_sha256": source_hash,
        "diff_sha256": diff_hash,
        "changed_files_sha256": changed_hash,
        "files": analyses,
    }
    projection = {
        "schema_version": TRUST_R4_SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "repository_hostname": hostname.strip().lower(),
        "repository_name_with_owner": repository.strip(),
        "pull_request_number": pr_number,
        "semantics": semantics,
    }
    expected_sha = canonical_json_sha256(projection)
    if value.get("evidence_sha256") != expected_sha:
        raise ValueError("Trust R4 semantic evidence evidence_sha256 mismatch")
    return {
        **projection,
        "evidence_sha256": expected_sha,
    }

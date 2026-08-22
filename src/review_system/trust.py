from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .evaluation import load_evaluation_report
from .identity import canonical_json_sha256, file_sha256, normalize_source_revision
from .intelligence_config import normalize_path
from .io import load_data
from .ledger import LEDGER_SCHEMA_VERSION, verify_ledger
from .path_globs import expand_trailing_recursive_glob
from .packs import _tokens, select_packs_with_reasons
from .paths import asset
from .policy_registry import load_policy_registry
from .profile import resolve_profile_file
from .reground import load_reground_report
from .trust_signing_trust_root_authority import (
    build_trust_signing_trust_root_evidence,
    normalize_trust_signing_trust_root_evidence,
)
from .trust_r4_semantics_authority import (
    build_trust_r4_semantic_evidence,
    normalize_trust_r4_semantic_evidence,
)
from .trust_workflow_authority import (
    build_trust_workflow_evidence,
    normalize_trust_workflow_evidence,
)
from .validation import validate_profile_data


TRUST_SCHEMA_VERSION = "1.0"
TRUST_RISK_MODEL_V1_1 = "1.1"
TRUST_RISK_MODEL_V1_2 = "1.2"
TRUST_RISK_MODEL_V1_3 = "1.3"
TRUST_RISK_MODEL_V1_4 = "1.4"
TRUST_RISK_MODEL_VERSION = "1.5"
_SUPPORTED_TRUST_RISK_MODEL_VERSIONS = {
    TRUST_RISK_MODEL_V1_1,
    TRUST_RISK_MODEL_V1_2,
    TRUST_RISK_MODEL_V1_3,
    TRUST_RISK_MODEL_V1_4,
    TRUST_RISK_MODEL_VERSION,
}
TRUST_MODE = "REPORT_ONLY"
BANDS = ("R0", "R1", "R2", "R3", "R4")
BAND_ORDER = {band: index for index, band in enumerate(BANDS)}
TASK_CLASS_BANDS = {
    "generated_artifact": "R0",
    "formatting": "R0",
    "documentation": "R1",
    "routine_code": "R2",
    "dependency_change": "R2",
    "authentication": "R3",
    "authorization": "R3",
    "database_migration": "R3",
    "deployment": "R3",
    "security": "R3",
    "policy": "R4",
    "verifier": "R4",
}
DEFECT_STATUSES = (
    "OBSERVED",
    "REPRODUCED",
    "CLASSIFIED",
    "RULE_CANDIDATE",
    "MITIGATED",
    "VERIFIED",
    "CLOSED",
    "REOPENED",
)
_HARD_GATE_ORDER = (
    "PROTECTED_PATH_CHANGED",
    "REQUIRED_SCENARIO_MISSING",
    "REPOSITORY_MISMATCH",
    "HEAD_MISMATCH",
    "AUTHORIZATION_OR_MIGRATION_CHANGE",
    "VERIFIER_CHANGED",
    "POLICY_EVALUATION_MISSING",
    "ROLLBACK_OR_REPLAY_EVIDENCE_MISSING",
)
_REVIEW_REQUIREMENT = {
    "R0": "HUMAN_CONFIRMATION_REQUIRED",
    "R1": "INDEPENDENT_REVIEW_REQUIRED",
    "R2": "INDEPENDENT_REVIEW_REQUIRED",
    "R3": "HUMAN_APPROVAL_REQUIRED",
    "R4": "DUAL_INDEPENDENT_REVIEW_REQUIRED",
}
_WORKFLOW_RISK = {
    "CI_TEST_WIRING_ONLY": ("R2", "WORKFLOW_CI_TEST_WIRING_ONLY"),
    "AUTHORITY_MUTATION": ("R3", "WORKFLOW_AUTHORITY_MUTATION"),
    "UNKNOWN": ("R3", "WORKFLOW_SEMANTICS_UNKNOWN"),
}
_WORKFLOW_HIGH_RISK_REASON_IDS = {
    "WORKFLOW_AUTHORITY_MUTATION",
    "WORKFLOW_SEMANTICS_UNKNOWN",
}
_DOCUMENTATION_PRECEDENCE_REASON = "DOCUMENTATION_HIGH_RISK_TOKEN_NEUTRALIZED"
_GENERIC_POLICY_TOKENS = {"policy", "policies"}
_NON_GENERIC_AUTHORITY_TOKENS = {
    "rls",
    "supabase",
    "auth",
    "authentication",
    "session",
    "jwt",
    "middleware",
    "controller",
    "route",
    "routes",
    "api",
    "endpoint",
}
_TIMESTAMPS_REQUIRE_TIMEZONE = "timestamp must include a timezone"


class TrustError(RuntimeError):
    pass


class TrustVerificationError(TrustError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        super().__init__("invalid Trust readiness report: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise TrustError(f"{field}: {_TIMESTAMPS_REQUIRE_TIMEZONE}")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_input_file(path: str | Path, field: str) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise TrustError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise TrustError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise TrustError(f"{field} must be a regular file: {resolved}")
    return resolved


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise TrustError(f"output path must not contain symlinks: {target}")
    return target.resolve()


def _schema_errors(schema_name: str, data: Any) -> list[str]:
    schema = load_data(asset(f"schemas/{schema_name}"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    output: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        output.append(f"{location}: {error.message}")
    return output


def _normalize_glob(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustError(f"{field} must be a non-empty string")
    raw = value.strip().replace("\\", "/")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise TrustError(f"{field} contains an unsafe path pattern: {value!r}")
    normalized = candidate.as_posix()
    if normalized in {"", "."}:
        raise TrustError(f"{field} must not be empty")
    return normalized


def _normalize_request_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise TrustError("Trust request must contain an object")
    candidate = deepcopy(data)
    candidate.pop("request_sha256", None)
    errors = _schema_errors("trust-request.schema.json", candidate)
    if errors:
        raise TrustError("invalid Trust request: " + "; ".join(errors))
    try:
        changed_files = sorted({normalize_path(value) for value in candidate["changed_files"]})
    except ValueError as exc:
        raise TrustError(f"Trust request changed_files: {exc}") from exc
    if len(changed_files) != len(candidate["changed_files"]):
        raise TrustError("Trust request changed_files must not contain normalized duplicates")
    required = sorted(candidate["required_scenarios"])
    completed = sorted(candidate["completed_scenarios"])
    try:
        source_revision = normalize_source_revision(candidate["source_revision"])
    except ValueError as exc:
        raise TrustError(f"Trust request source_revision: {exc}") from exc
    if source_revision == "unresolved":
        raise TrustError("Trust request source_revision must be a stable revision")
    normalized = {
        "schema_version": TRUST_SCHEMA_VERSION,
        "task_id": candidate["task_id"].strip(),
        "source_revision": source_revision,
        "task_class": candidate["task_class"],
        "changed_files": changed_files,
        "required_scenarios": required,
        "completed_scenarios": completed,
        "repository_match": bool(candidate["repository_match"]),
        "head_match": bool(candidate["head_match"]),
        "rollback_evidence": bool(candidate["rollback_evidence"]),
        "replay_evidence": bool(candidate["replay_evidence"]),
        "readiness_policy": deepcopy(candidate["readiness_policy"]),
    }
    normalized["request_sha256"] = canonical_json_sha256(normalized)
    return normalized


def load_trust_request(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input_file(path, "Trust request")
    return source, _normalize_request_data(load_data(source))


def _normalize_observations_data(data: Any) -> dict[str, Any]:
    errors = _schema_errors("reground-observations.schema.json", data)
    if errors:
        raise TrustError("invalid Reground observations: " + "; ".join(errors))
    assert isinstance(data, dict)
    observations: list[dict[str, str]] = []
    ids: set[str] = set()
    relation_ids: set[str] = set()
    for index, item in enumerate(data["observations"]):
        observation_id = item["observation_id"].strip()
        relation_id = item["relation_id"].strip()
        if observation_id in ids:
            raise TrustError(f"duplicate Reground observation_id: {observation_id}")
        if relation_id in relation_ids:
            raise TrustError(f"duplicate Reground relation_id observation: {relation_id}")
        ids.add(observation_id)
        relation_ids.add(relation_id)
        observations.append(
            {
                "observation_id": observation_id,
                "relation_id": relation_id,
                "expected_status": item["expected_status"],
                "confirmed_by": item["confirmed_by"].strip(),
                "confirmed_at": _timestamp(item["confirmed_at"], f"observations[{index}].confirmed_at"),
            }
        )
    return {
        "schema_version": TRUST_SCHEMA_VERSION,
        "dataset_id": data["dataset_id"].strip(),
        "project_id": data["project_id"].strip(),
        "reground_report_id": data["reground_report_id"].strip(),
        "observations": sorted(observations, key=lambda item: (item["relation_id"], item["observation_id"])),
    }


def load_reground_observations(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input_file(path, "Reground observations")
    return source, _normalize_observations_data(load_data(source))


def _profile_descriptor(
    path: str | Path,
    *,
    include_corroboration: bool = True,
) -> tuple[Path, dict[str, Any]]:
    source = _safe_input_file(path, "Project Profile")
    profile = resolve_profile_file(source)
    errors = validate_profile_data(profile)
    if errors:
        raise TrustError("invalid Project Profile: " + "; ".join(errors))
    project = profile.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("id"), str) or not project["id"].strip():
        raise TrustError("Project Profile project.id is required")
    patterns = sorted(
        {
            _normalize_glob(value, f"protected_paths[{index}]")
            for index, value in enumerate(profile.get("protected_paths", []))
        }
    )
    descriptor = {
        "source": source.name,
        "project_id": project["id"].strip(),
        "profile_sha256": canonical_json_sha256(profile),
        "protected_paths": patterns,
    }
    if include_corroboration:
        review = profile.get("review")
        packs = review.get("packs", []) if isinstance(review, dict) else []
        descriptor["configured_review_packs"] = sorted(
            {value.strip() for value in packs if isinstance(value, str) and value.strip()}
        )
    return source, descriptor


def _band_max(*bands: str) -> str:
    return max(bands, key=lambda band: BAND_ORDER[band])


def _path_classification(path: str) -> tuple[str, str]:
    lowered = path.lower()
    name = PurePosixPath(lowered).name
    r4_names = {
        "trust.py",
        "trust_cli.py",
        "gate.py",
        "baseline.py",
        "validation.py",
        "evaluation.py",
        "policy_registry.py",
        "reground.py",
    }
    if (
        name in r4_names
        or lowered.startswith("schemas/")
        or lowered.startswith("src/review_system/assets/schemas/")
        or "/verification/" in f"/{lowered}/"
        or "approved-rules" in name
        or "gate-policy" in name
        or "/policies/" in f"/{lowered}/"
    ):
        return "R4", "VERIFIER_OR_POLICY_PATH"
    r3_tokens = (
        "/auth/",
        "/authentication/",
        "/authorization/",
        "/security/",
        "/permissions/",
        "/roles/",
        "/migration/",
        "/migrations/",
        "/flyway/",
        "/liquibase/",
        "/deploy/",
        "/deployment/",
        "/infra/",
        "/terraform/",
        "/helm/",
        "/k8s/",
        "/kubernetes/",
        "/secrets/",
    )
    if (
        lowered.startswith(".github/workflows/")
        or name.startswith("dockerfile")
        or name in {"docker-compose.yml", "docker-compose.yaml"}
        or any(token in f"/{lowered}/" for token in r3_tokens)
        or name.startswith("auth")
        or any(
            token in name
            for token in (
                "credential", "secret", "token", "permission", "migration",
                "authentication", "authorization", "oauth", "jwt", "security",
                "role", "rls",
            )
        )
    ):
        return "R3", "HIGH_RISK_PATH"
    if (
        lowered.startswith("generated/")
        or lowered.startswith("reports/")
        or lowered.startswith("artifacts/")
        or lowered.startswith("dist/")
        or name.endswith(".report.json")
        or name.endswith(".snapshot.json")
    ):
        return "R0", "GENERATED_OR_REPORT_PATH"
    if lowered.startswith("docs/") or PurePosixPath(lowered).suffix in {".md", ".rst", ".adoc"}:
        return "R1", "DOCUMENTATION_PATH"
    return "R2", "SOURCE_OR_CONFIGURATION_PATH"


def _matches_pattern(path: str, pattern: str) -> bool:
    return any(fnmatch.fnmatchcase(path, candidate) for candidate in expand_trailing_recursive_glob(pattern))


def _is_documentation_path(path: str) -> bool:
    lowered = path.lower()
    return (
        lowered.startswith("docs/")
        or "/docs/" in f"/{lowered}"
        or PurePosixPath(lowered).suffix in {".md", ".rst", ".adoc"}
    )


def _generic_policy_only_dual_selection(path: str) -> bool:
    if _is_documentation_path(path):
        return False
    tokens = _tokens(path)
    return bool(tokens & _GENERIC_POLICY_TOKENS) and not bool(
        tokens & _NON_GENERIC_AUTHORITY_TOKENS
    )


def _authoritative_path_classification(path: str) -> tuple[str, str]:
    band, reason_id = _path_classification(path)
    if band == "R3" and _is_documentation_path(path):
        return "R1", _DOCUMENTATION_PRECEDENCE_REASON
    return band, reason_id


def _review_pack_corroboration(
    profile: dict[str, Any],
    changed_files: list[str],
    *,
    risk_model_version: str | None = TRUST_RISK_MODEL_VERSION,
) -> dict[str, Any] | None:
    configured = profile.get("configured_review_packs")
    if not isinstance(configured, list):
        return None
    selection = select_packs_with_reasons(changed_files, configured)
    non_documentation = {
        pack: sorted(path for path in paths if not _is_documentation_path(path))
        for pack, paths in selection.items()
    }
    reasons: list[dict[str, Any]] = []

    def add_reason(rule_id: str, paths: list[str]) -> None:
        if not paths:
            return
        reasons.append(
            {
                "reason_id": f"REVIEW_PACK_CORROBORATION:{rule_id}",
                "band": "R3",
                "paths": sorted(set(paths)),
            }
        )

    add_reason(
        "AUTHENTICATION",
        non_documentation.get("application.authentication", []),
    )
    add_reason(
        "MIGRATION_SAFETY",
        [
            *non_documentation.get("application.migration-safety", []),
            *non_documentation.get("data.migration-safety", []),
        ],
    )
    authorization_paths = non_documentation.get("application.authorization", [])
    rls_paths = non_documentation.get("data.rls", [])
    add_authorization_rls = bool(authorization_paths and rls_paths)
    if add_authorization_rls and risk_model_version in {
        TRUST_RISK_MODEL_V1_2,
        TRUST_RISK_MODEL_V1_3,
        TRUST_RISK_MODEL_V1_4,
        TRUST_RISK_MODEL_VERSION,
    }:
        shared = set(authorization_paths) & set(rls_paths)
        collision_paths = {
            path for path in shared if _generic_policy_only_dual_selection(path)
        }
        if collision_paths:
            surviving_authorization = set(authorization_paths) - collision_paths
            surviving_rls = set(rls_paths) - collision_paths
            add_authorization_rls = bool(
                surviving_authorization and surviving_rls
            )
    if add_authorization_rls:
        add_reason("AUTHORIZATION_RLS", [*authorization_paths, *rls_paths])

    floor = _band_max("R0", *[item["band"] for item in reasons])
    return {
        "floor_band": floor,
        "selected_review_packs": sorted(selection),
        "reasons": reasons,
    }


def _risk_projection(
    request: dict[str, Any],
    profile: dict[str, Any],
    workflow_evidence: dict[str, Any] | None = None,
    r4_semantic_evidence: dict[str, Any] | None = None,
    signing_trust_root_evidence: dict[str, Any] | None = None,
    *,
    risk_model_version: str | None = TRUST_RISK_MODEL_VERSION,
) -> dict[str, Any]:
    if risk_model_version is not None and risk_model_version not in _SUPPORTED_TRUST_RISK_MODEL_VERSIONS:
        raise ValueError(f"unsupported Trust risk model version: {risk_model_version}")
    if risk_model_version is None and workflow_evidence is not None:
        raise ValueError("legacy unversioned risk model cannot consume workflow evidence")
    if risk_model_version is None and r4_semantic_evidence is not None:
        raise ValueError("legacy unversioned risk model cannot consume R4 semantic evidence")
    if risk_model_version is None and signing_trust_root_evidence is not None:
        raise ValueError("legacy unversioned risk model cannot consume signing trust-root evidence")
    if (
        r4_semantic_evidence is not None
        and risk_model_version not in {
            TRUST_RISK_MODEL_V1_3,
            TRUST_RISK_MODEL_V1_4,
            TRUST_RISK_MODEL_VERSION,
        }
    ):
        raise ValueError("R4 semantic evidence requires Trust risk model v1.3, v1.4 or v1.5")
    if signing_trust_root_evidence is not None and risk_model_version != TRUST_RISK_MODEL_VERSION:
        raise ValueError("signing trust-root evidence requires Trust risk model v1.5")

    workflow_by_path: dict[str, dict[str, Any]] = {}
    if workflow_evidence is not None:
        normalized_workflow = normalize_trust_workflow_evidence(
            workflow_evidence,
            source_revision=request["source_revision"],
            changed_files=request["changed_files"],
        )
        workflow_by_path = {
            item["path"]: item
            for item in normalized_workflow["semantics"]["workflows"]
        }

    r4_by_path: dict[str, dict[str, Any]] = {}
    if r4_semantic_evidence is not None:
        normalized_r4 = normalize_trust_r4_semantic_evidence(
            r4_semantic_evidence,
            source_revision=request["source_revision"],
            changed_files=request["changed_files"],
            risk_model_version=risk_model_version,
        )
        r4_by_path = {
            item["path"]: item
            for item in normalized_r4["semantics"]["files"]
        }

    signing_by_path: dict[str, dict[str, Any]] = {}
    if signing_trust_root_evidence is not None:
        normalized_signing = normalize_trust_signing_trust_root_evidence(
            signing_trust_root_evidence,
            source_revision=request["source_revision"],
            changed_files=request["changed_files"],
        )
        signing_by_path = {
            item["path"]: item
            for item in normalized_signing["semantics"]["files"]
        }

    path_classifier = (
        _path_classification
        if risk_model_version is None
        else _authoritative_path_classification
    )
    base_band = TASK_CLASS_BANDS[request["task_class"]]
    grouped: dict[tuple[str, str], set[str]] = {}
    path_bands: list[str] = []
    for path in request["changed_files"]:
        r4_semantic = r4_by_path.get(path)
        if r4_semantic is not None and r4_semantic["is_r4_authority"]:
            band, reason_id = "R4", "SEMANTIC_R4_AUTHORITY"
        elif (
            signing_by_path.get(path) is not None
            and signing_by_path[path]["is_signing_trust_root_authority"]
        ):
            band, reason_id = "R3", "SEMANTIC_R3_SIGNING_TRUST_ROOT_AUTHORITY"
        else:
            semantic = workflow_by_path.get(path)
            if semantic is None:
                band, reason_id = path_classifier(path)
            else:
                band, reason_id = _WORKFLOW_RISK[semantic["classification"]]
        path_bands.append(band)
        grouped.setdefault((reason_id, band), set()).add(path)
    protected = sorted(
        path
        for path in request["changed_files"]
        if any(_matches_pattern(path, pattern) for pattern in profile["protected_paths"])
    )
    if protected:
        path_bands.append("R3")
        grouped.setdefault(("PROFILE_PROTECTED_PATH", "R3"), set()).update(protected)
    path_floor = _band_max(*path_bands)
    reasons = [
        {
            "reason_id": f"TASK_CLASS:{request['task_class']}",
            "band": base_band,
            "paths": [],
        },
        *[
            {"reason_id": reason_id, "band": band, "paths": sorted(paths)}
            for (reason_id, band), paths in sorted(
                grouped.items(),
                key=lambda item: (BAND_ORDER[item[0][1]], item[0][0]),
            )
        ],
    ]
    output = {
        "base_band": base_band,
        "path_floor_band": path_floor,
        "effective_band": _band_max(base_band, path_floor),
        "protected_files": protected,
        "reasons": reasons,
    }
    corroboration = _review_pack_corroboration(
        profile,
        request["changed_files"],
        risk_model_version=risk_model_version,
    )
    if corroboration is None:
        return output

    corroborated_floor = corroboration["floor_band"]
    semantic_floor = _band_max(path_floor, corroborated_floor)
    underdeclared = BAND_ORDER[base_band] < BAND_ORDER[semantic_floor]
    reasons.extend(corroboration["reasons"])
    if underdeclared:
        reasons.append(
            {
                "reason_id": "TASK_CLASS_UNDERDECLARED",
                "band": semantic_floor,
                "paths": [],
            }
        )
    output.update(
        {
            "corroborated_semantic_floor_band": corroborated_floor,
            "selected_review_packs": corroboration["selected_review_packs"],
            "task_class_underdeclared": underdeclared,
            "effective_band": _band_max(base_band, path_floor, corroborated_floor),
            "reasons": reasons,
        }
    )
    return output


def _load_workflow_evidence_sources(
    *,
    request: dict[str, Any],
    github_source: str | Path | None,
    workflow_diff: str | Path | None,
) -> dict[str, Any] | None:
    if github_source is None and workflow_diff is None:
        return None
    if github_source is None or workflow_diff is None:
        raise TrustError("workflow semantics require both GitHub source and workflow diff")

    source_path = _safe_input_file(github_source, "GitHub source")
    diff_path = _safe_input_file(workflow_diff, "Workflow diff")
    source_data = load_data(source_path)
    if not isinstance(source_data, dict):
        raise TrustError("GitHub source must contain an object")
    try:
        diff_text = diff_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise TrustError("Workflow diff must be UTF-8 text") from exc
    try:
        return build_trust_workflow_evidence(
            github_source=source_data,
            diff_text=diff_text,
            source_revision=request["source_revision"],
            changed_files=request["changed_files"],
        )
    except (TypeError, ValueError) as exc:
        raise TrustError(f"invalid workflow authority evidence: {exc}") from exc


def _load_r4_semantic_evidence_sources(
    *,
    request: dict[str, Any],
    github_source: str | Path | None,
    workflow_diff: str | Path | None,
    risk_model_version: str,
) -> dict[str, Any] | None:
    if github_source is None and workflow_diff is None:
        return None
    if github_source is None or workflow_diff is None:
        raise TrustError("R4 semantics require both GitHub source and workflow diff")

    source_path = _safe_input_file(github_source, "GitHub source")
    diff_path = _safe_input_file(workflow_diff, "Workflow diff")
    source_data = load_data(source_path)
    if not isinstance(source_data, dict):
        raise TrustError("GitHub source must contain an object")
    try:
        diff_text = diff_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise TrustError("Workflow diff must be UTF-8 text") from exc
    try:
        return build_trust_r4_semantic_evidence(
            github_source=source_data,
            diff_text=diff_text,
            source_revision=request["source_revision"],
            changed_files=request["changed_files"],
            risk_model_version=risk_model_version,
        )
    except (TypeError, ValueError) as exc:
        raise TrustError(f"invalid R4 semantic authority evidence: {exc}") from exc


def _load_signing_trust_root_evidence_sources(
    *,
    request: dict[str, Any],
    github_source: str | Path | None,
    workflow_diff: str | Path | None,
) -> dict[str, Any] | None:
    if github_source is None and workflow_diff is None:
        return None
    if github_source is None or workflow_diff is None:
        raise TrustError("signing trust-root semantics require both GitHub source and workflow diff")

    source_path = _safe_input_file(github_source, "GitHub source")
    diff_path = _safe_input_file(workflow_diff, "Workflow diff")
    source_data = load_data(source_path)
    if not isinstance(source_data, dict):
        raise TrustError("GitHub source must contain an object")
    try:
        diff_text = diff_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise TrustError("Workflow diff must be UTF-8 text") from exc
    try:
        return build_trust_signing_trust_root_evidence(
            github_source=source_data,
            diff_text=diff_text,
            source_revision=request["source_revision"],
            changed_files=request["changed_files"],
        )
    except (TypeError, ValueError) as exc:
        raise TrustError(f"invalid signing trust-root authority evidence: {exc}") from exc


def _empty_ledger_evidence() -> dict[str, Any]:
    return {
        "available": False,
        "source": None,
        "sha256": None,
        "schema_version": None,
        "run_count": 0,
        "artifact_count": 0,
        "claim_count": 0,
        "evidence_count": 0,
        "finding_count": 0,
        "decision_count": 0,
    }


def _empty_defect_evidence() -> dict[str, Any]:
    return {
        "available": False,
        "registry_source_present": False,
        "total": 0,
        "by_status": {status: 0 for status in DEFECT_STATUSES},
        "closed_with_resolution_evidence": 0,
        "reopened_transitions": 0,
    }


def _open_sqlite_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _count(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...]) -> int:
    row = connection.execute(query, parameters).fetchone()
    return int(row[0]) if row is not None else 0


def _ledger_evidence(path: str | Path | None, project_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if path is None:
        return _empty_ledger_evidence(), _empty_defect_evidence()
    source = _safe_input_file(path, "Evidence Ledger")
    verification = verify_ledger(source)
    if not verification.get("valid"):
        raise TrustError("invalid Evidence Ledger: " + "; ".join(verification.get("errors", [])))
    ledger = _empty_ledger_evidence()
    defects = _empty_defect_evidence()
    try:
        with _open_sqlite_read_only(source) as connection:
            ledger.update(
                {
                    "available": True,
                    "source": source.name,
                    "sha256": file_sha256(source),
                    "schema_version": LEDGER_SCHEMA_VERSION,
                    "run_count": _count(connection, "SELECT COUNT(*) FROM runs WHERE project_id = ?", (project_id,)),
                    "artifact_count": _count(
                        connection,
                        "SELECT COUNT(*) FROM artifacts a JOIN runs r ON r.run_id = a.run_id WHERE r.project_id = ?",
                        (project_id,),
                    ),
                    "claim_count": _count(
                        connection,
                        "SELECT COUNT(*) FROM claims c JOIN runs r ON r.run_id = c.run_id WHERE r.project_id = ?",
                        (project_id,),
                    ),
                    "evidence_count": _count(
                        connection,
                        "SELECT COUNT(*) FROM evidence e JOIN runs r ON r.run_id = e.run_id WHERE r.project_id = ?",
                        (project_id,),
                    ),
                    "finding_count": _count(
                        connection,
                        "SELECT COUNT(*) FROM findings f JOIN runs r ON r.run_id = f.run_id WHERE r.project_id = ?",
                        (project_id,),
                    ),
                    "decision_count": _count(
                        connection,
                        "SELECT COUNT(*) FROM decisions d JOIN runs r ON r.run_id = d.run_id WHERE r.project_id = ?",
                        (project_id,),
                    ),
                }
            )
            by_status = {
                status: _count(
                    connection,
                    "SELECT COUNT(*) FROM defects WHERE project_id = ? AND lifecycle_status = ?",
                    (project_id, status),
                )
                for status in DEFECT_STATUSES
            }
            registry_source_present = (
                connection.execute(
                    "SELECT 1 FROM registry_sources WHERE project_id = ? LIMIT 1",
                    (project_id,),
                ).fetchone()
                is not None
            )
            defects.update(
                {
                    "available": registry_source_present,
                    "registry_source_present": registry_source_present,
                    "total": sum(by_status.values()),
                    "by_status": by_status,
                    "closed_with_resolution_evidence": _count(
                        connection,
                        """
                        SELECT COUNT(DISTINCT d.defect_id)
                        FROM defects d
                        JOIN defect_artifacts da ON da.defect_id = d.defect_id
                        WHERE d.project_id = ?
                          AND d.lifecycle_status = 'CLOSED'
                          AND da.relation = 'resolution_evidence'
                        """,
                        (project_id,),
                    ),
                    "reopened_transitions": _count(
                        connection,
                        """
                        SELECT COUNT(DISTINCT de.defect_id)
                        FROM defect_events de
                        JOIN defects d ON d.defect_id = de.defect_id
                        WHERE d.project_id = ?
                          AND de.event_type = 'TRANSITIONED'
                          AND de.status_to = 'REOPENED'
                        """,
                        (project_id,),
                    ),
                }
            )
    except sqlite3.DatabaseError as exc:
        raise TrustError(f"Evidence Ledger query failed: {exc}") from exc
    return ledger, defects


def _empty_policy_evidence() -> dict[str, Any]:
    return {
        "registry_available": False,
        "registry_source": None,
        "registry_id": None,
        "registry_sha256": None,
        "active_policy_id": None,
        "active_policy_version": None,
        "active_ruleset_sha256": None,
        "evaluation_available": False,
        "evaluation_source": None,
        "evaluation_id": None,
        "evaluation_report_sha256": None,
        "evaluation_decision": None,
        "holdout_cases": 0,
        "repeatability": False,
        "protected_negative_regressions": 0,
        "active_evaluation_match": False,
        "policy_evaluation_ready": False,
    }


def _policy_evidence(
    registry_path: str | Path | None,
    evaluation_path: str | Path | None,
    project_id: str,
) -> dict[str, Any]:
    output = _empty_policy_evidence()
    registry: dict[str, Any] | None = None
    active: dict[str, Any] | None = None
    if registry_path is not None:
        source, registry = load_policy_registry(_safe_input_file(registry_path, "Policy Registry"))
        if registry["project_id"] != project_id:
            raise TrustError(
                f"Policy Registry project_id mismatch: expected={project_id} actual={registry['project_id']}"
            )
        output.update(
            {
                "registry_available": True,
                "registry_source": source.name,
                "registry_id": registry["registry_id"],
                "registry_sha256": registry["registry_sha256"],
            }
        )
        active_id = registry.get("active_policy_id")
        if isinstance(active_id, str):
            active = next(
                (item for item in registry.get("policies", []) if item.get("policy_id") == active_id),
                None,
            )
            if active is None:
                raise TrustError("Policy Registry active_policy_id is not present in policies")
            output.update(
                {
                    "active_policy_id": active["policy_id"],
                    "active_policy_version": active["version"],
                    "active_ruleset_sha256": active["ruleset"]["sha256"],
                }
            )
    evaluation: dict[str, Any] | None = None
    if evaluation_path is not None:
        source, evaluation = load_evaluation_report(
            _safe_input_file(evaluation_path, "Evaluation report")
        )
        output.update(
            {
                "evaluation_available": True,
                "evaluation_source": source.name,
                "evaluation_id": evaluation["evaluation_id"],
                "evaluation_report_sha256": evaluation["report_sha256"],
                "evaluation_decision": evaluation["gate"]["decision"],
                "holdout_cases": int(evaluation["dataset"]["split_counts"].get("holdout", 0)),
                "repeatability": bool(
                    evaluation["repeatability"]["baseline"]
                    and evaluation["repeatability"]["challenger"]
                ),
                "protected_negative_regressions": len(
                    evaluation["comparison"]["protected_negative_regressions"]
                ),
            }
        )
    if active is not None and evaluation is not None:
        reference = active["evaluation"]
        match = (
            reference.get("evaluation_id") == evaluation["evaluation_id"]
            and reference.get("report_sha256") == evaluation["report_sha256"]
            and reference.get("challenger_policy_sha256")
            == evaluation["challenger_policy"]["sha256"]
            and active["ruleset"]["sha256"] == evaluation["challenger_policy"]["sha256"]
        )
        output["active_evaluation_match"] = match
        output["policy_evaluation_ready"] = bool(
            match and evaluation["gate"]["decision"] == "PASS"
        )
    return output


def _empty_reground_evidence() -> dict[str, Any]:
    return {
        "report_available": False,
        "report_source": None,
        "report_id": None,
        "report_sha256": None,
        "status": None,
        "relation_count": 0,
        "stale_relations": 0,
        "impacted_rechecks": 0,
        "observations_available": False,
        "observation_source": None,
        "dataset_id": None,
        "dataset_sha256": None,
        "observation_count": 0,
        "coverage": None,
        "tp": 0,
        "fp": 0,
        "tn": 0,
        "fn": 0,
        "precision": None,
        "recall": None,
        "false_positive_rate": None,
        "exact_rate": None,
    }


def _classification_metrics(
    report: dict[str, Any],
    observations: dict[str, Any],
) -> dict[str, Any]:
    relations = {
        item["relation_id"]: item["status"]
        for item in report.get("relations", [])
        if isinstance(item, dict)
    }
    tp = fp = tn = fn = 0
    for item in observations["observations"]:
        relation_id = item["relation_id"]
        if relation_id not in relations:
            raise TrustError(f"Reground observation references unknown relation: {relation_id}")
        predicted = relations[relation_id]
        expected = item["expected_status"]
        if predicted == "STALE" and expected == "STALE":
            tp += 1
        elif predicted == "STALE" and expected == "CURRENT":
            fp += 1
        elif predicted == "CURRENT" and expected == "CURRENT":
            tn += 1
        else:
            fn += 1
    count = len(observations["observations"])
    relation_count = len(relations)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    false_positive_rate = fp / (fp + tn) if fp + tn else None
    exact_rate = (tp + tn) / count if count else None
    coverage = count / relation_count if relation_count else 0.0
    return {
        "observation_count": count,
        "coverage": round(coverage, 6),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 6) if precision is not None else None,
        "recall": round(recall, 6) if recall is not None else None,
        "false_positive_rate": (
            round(false_positive_rate, 6)
            if false_positive_rate is not None
            else None
        ),
        "exact_rate": round(exact_rate, 6) if exact_rate is not None else None,
    }


def _reground_evidence(
    report_path: str | Path | None,
    observation_path: str | Path | None,
    project_id: str,
) -> dict[str, Any]:
    output = _empty_reground_evidence()
    report: dict[str, Any] | None = None
    if report_path is not None:
        source, report = load_reground_report(
            _safe_input_file(report_path, "Reground report")
        )
        if report["project_id"] != project_id:
            raise TrustError(
                f"Reground report project_id mismatch: expected={project_id} actual={report['project_id']}"
            )
        output.update(
            {
                "report_available": True,
                "report_source": source.name,
                "report_id": report["report_id"],
                "report_sha256": report["report_sha256"],
                "status": report["summary"]["status"],
                "relation_count": int(report["summary"]["relations_checked"]),
                "stale_relations": int(report["summary"]["stale_relations"]),
                "impacted_rechecks": int(report["summary"]["impacted_rechecks"]),
            }
        )
    if observation_path is not None:
        if report is None:
            raise TrustError("Reground observations require a Reground report")
        source, observations = load_reground_observations(observation_path)
        if observations["project_id"] != project_id:
            raise TrustError(
                "Reground observations project_id does not match the Project Profile"
            )
        if observations["reground_report_id"] != report["report_id"]:
            raise TrustError(
                "Reground observations reground_report_id does not match the Reground report"
            )
        metrics = _classification_metrics(report, observations)
        output.update(
            {
                "observations_available": True,
                "observation_source": source.name,
                "dataset_id": observations["dataset_id"],
                "dataset_sha256": canonical_json_sha256(observations),
                **metrics,
            }
        )
    return output


def _evidence_projection(
    *,
    ledger: str | Path | None,
    policy_registry: str | Path | None,
    evaluation_report: str | Path | None,
    reground_report: str | Path | None,
    reground_observations: str | Path | None,
    project_id: str,
    workflow_evidence: dict[str, Any] | None = None,
    r4_semantic_evidence: dict[str, Any] | None = None,
    signing_trust_root_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ledger_data, defect_data = _ledger_evidence(ledger, project_id)
    policy_data = _policy_evidence(policy_registry, evaluation_report, project_id)
    reground_data = _reground_evidence(
        reground_report,
        reground_observations,
        project_id,
    )
    projection = {
        "ledger": ledger_data,
        "defects": defect_data,
        "policy": policy_data,
        "reground": reground_data,
    }
    if workflow_evidence is not None:
        projection["workflow_diff"] = deepcopy(workflow_evidence)
    if r4_semantic_evidence is not None:
        projection["r4_semantics"] = deepcopy(r4_semantic_evidence)
    if signing_trust_root_evidence is not None:
        projection["signing_trust_root"] = deepcopy(signing_trust_root_evidence)
    return {
        "fingerprint_sha256": canonical_json_sha256(projection),
        **projection,
    }


def _hard_gate_projection(
    request: dict[str, Any],
    risk: dict[str, Any],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    missing_scenarios = sorted(
        set(request["required_scenarios"]) - set(request["completed_scenarios"])
    )
    risk_reason_ids = {item["reason_id"] for item in risk["reasons"]}
    high_risk_task = request["task_class"] in {
        "authentication",
        "authorization",
        "database_migration",
        "deployment",
        "security",
    }
    high_risk_reason_ids = {"HIGH_RISK_PATH", *_WORKFLOW_HIGH_RISK_REASON_IDS}
    high_risk_path = bool(risk_reason_ids & high_risk_reason_ids)
    corroborated_high_risk = any(
        reason_id.startswith("REVIEW_PACK_CORROBORATION:")
        for reason_id in risk_reason_ids
    )
    verifier_changed = (
        request["task_class"] == "verifier"
        or "VERIFIER_OR_POLICY_PATH" in risk_reason_ids
    )
    rollback_details: list[str] = []
    migration_change = (
        request["task_class"] == "database_migration"
        or any("migration" in path.lower() for path in request["changed_files"])
    )
    deployment_change = (
        request["task_class"] == "deployment"
        or any(
            path.lower().startswith(".github/workflows/")
            or "deploy" in path.lower()
            or "terraform" in path.lower()
            for path in request["changed_files"]
        )
    )
    if migration_change:
        if not request["rollback_evidence"]:
            rollback_details.append("ROLLBACK_EVIDENCE")
        if not request["replay_evidence"]:
            rollback_details.append("REPLAY_EVIDENCE")
    elif deployment_change and not request["rollback_evidence"]:
        rollback_details.append("ROLLBACK_EVIDENCE")
    values = {
        "PROTECTED_PATH_CHANGED": (
            bool(risk["protected_files"]),
            "PROFILE",
            risk["protected_files"],
        ),
        "REQUIRED_SCENARIO_MISSING": (
            bool(missing_scenarios),
            "TASK",
            missing_scenarios,
        ),
        "REPOSITORY_MISMATCH": (
            not request["repository_match"],
            "TASK",
            ["repository_match=false"] if not request["repository_match"] else [],
        ),
        "HEAD_MISMATCH": (
            not request["head_match"],
            "TASK",
            ["head_match=false"] if not request["head_match"] else [],
        ),
        "AUTHORIZATION_OR_MIGRATION_CHANGE": (
            high_risk_task or high_risk_path or corroborated_high_risk,
            "TASK",
            sorted(
                {
                    request["task_class"],
                    *[
                        path
                        for item in risk["reasons"]
                        if (
                            item["reason_id"] in high_risk_reason_ids
                            or item["reason_id"].startswith("REVIEW_PACK_CORROBORATION:")
                        )
                        for path in item["paths"]
                    ],
                }
            )
            if high_risk_task or high_risk_path or corroborated_high_risk
            else [],
        ),
        "VERIFIER_CHANGED": (
            verifier_changed,
            "TASK",
            sorted(
                {
                    request["task_class"],
                    *[
                        path
                        for item in risk["reasons"]
                        if item["reason_id"] == "VERIFIER_OR_POLICY_PATH"
                        for path in item["paths"]
                    ],
                }
            )
            if verifier_changed
            else [],
        ),
        "POLICY_EVALUATION_MISSING": (
            not evidence["policy"]["policy_evaluation_ready"],
            "EVIDENCE",
            ["active PASS evaluation not proven"]
            if not evidence["policy"]["policy_evaluation_ready"]
            else [],
        ),
        "ROLLBACK_OR_REPLAY_EVIDENCE_MISSING": (
            bool(rollback_details),
            "TASK",
            sorted(rollback_details),
        ),
    }
    return [
        {
            "gate_id": gate_id,
            "triggered": values[gate_id][0],
            "source": values[gate_id][1],
            "details": values[gate_id][2],
        }
        for gate_id in _HARD_GATE_ORDER
    ]


def _readiness_projection(
    request: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    policy = request["readiness_policy"]
    ledger = evidence["ledger"]
    defects = evidence["defects"]
    policy_evidence = evidence["policy"]
    reground = evidence["reground"]
    conditions = {
        "ledger_available": ledger["available"],
        "ledger_run_threshold": ledger["run_count"] >= policy["min_ledger_runs"],
        "ledger_decision_threshold": (
            ledger["decision_count"] >= policy["min_ledger_decisions"]
        ),
        "defect_registry_present": defects["registry_source_present"],
        "defect_threshold": defects["total"] >= policy["min_defects"],
        "closed_defect_threshold": (
            defects["closed_with_resolution_evidence"]
            >= policy["min_closed_defects"]
        ),
        "active_policy_present": policy_evidence["active_policy_id"] is not None,
        "pass_evaluation_present": (
            policy_evidence["evaluation_decision"] == "PASS"
        ),
        "active_evaluation_match": policy_evidence["active_evaluation_match"],
        "holdout_present": policy_evidence["holdout_cases"] > 0,
        "repeatability_proven": policy_evidence["repeatability"],
        "protected_negative_regressions_zero": (
            policy_evidence["protected_negative_regressions"] == 0
        ),
        "reground_report_present": reground["report_available"],
        "reground_observations_present": reground["observations_available"],
        "reground_observation_threshold": (
            reground["observation_count"] >= policy["min_reground_observations"]
        ),
        "reground_coverage_threshold": (
            reground["coverage"] is not None
            and reground["coverage"] >= policy["min_reground_coverage"]
        ),
        "reground_precision_threshold": (
            reground["precision"] is not None
            and reground["precision"] >= policy["min_reground_precision"]
        ),
        "reground_recall_threshold": (
            reground["recall"] is not None
            and reground["recall"] >= policy["min_reground_recall"]
        ),
        "reground_false_positive_rate_threshold": (
            reground["false_positive_rate"] is not None
            and reground["false_positive_rate"]
            <= policy["max_reground_false_positive_rate"]
        ),
    }
    failed = sorted(name for name, passed in conditions.items() if not passed)
    ready = not failed
    return {
        "status": "READY_FOR_HUMAN_COMPARISON" if ready else "NOT_READY",
        "conditions": conditions,
        "failed_conditions": failed,
        "next_step": (
            "HUMAN_CONFIRMED_DECISION_COMPARISON"
            if ready
            else "COLLECT_READINESS_EVIDENCE"
        ),
    }


def _task_advisory(
    risk: dict[str, Any],
    hard_gates: list[dict[str, Any]],
) -> dict[str, Any]:
    band = risk["effective_band"]
    return {
        "risk_band": band,
        "review_requirement": _REVIEW_REQUIREMENT[band],
        "human_action_required": True,
        "auto_pass_candidate": False,
        "triggered_hard_gates": sorted(
            item["gate_id"] for item in hard_gates if item["triggered"]
        ),
    }


def _snapshot_payload(report: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "mode": report.get("mode"),
        "automation_authorized": report.get("automation_authorized"),
        "maximum_automation_band": report.get("maximum_automation_band"),
        "request": deepcopy(report.get("request")),
        "profile": deepcopy(report.get("profile")),
        "risk": deepcopy(report.get("risk")),
        "hard_gates": deepcopy(report.get("hard_gates")),
        "evidence": deepcopy(report.get("evidence")),
        "readiness": deepcopy(report.get("readiness")),
        "task_advisory": deepcopy(report.get("task_advisory")),
    }
    if "risk_model_version" in report:
        payload["risk_model_version"] = report.get("risk_model_version")
    return payload


def _report_payload(report: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(report)
    payload.pop("report_sha256", None)
    return payload


def _expected_report_id(report: dict[str, Any], snapshot_sha256: str) -> str:
    request = report.get("request") if isinstance(report.get("request"), dict) else {}
    key = {
        "project_id": report.get("project_id"),
        "task_id": request.get("task_id"),
        "source_revision": request.get("source_revision"),
        "snapshot_sha256": snapshot_sha256,
    }
    return f"trust-{canonical_json_sha256(key)[:32]}"


def assess_trust(
    request: str | Path,
    profile: str | Path,
    *,
    ledger: str | Path | None = None,
    policy_registry: str | Path | None = None,
    evaluation_report: str | Path | None = None,
    reground_report: str | Path | None = None,
    reground_observations: str | Path | None = None,
    github_source: str | Path | None = None,
    workflow_diff: str | Path | None = None,
    generated_at: str | None = None,
    _include_corroboration: bool = True,
    _risk_model_version: str | None = TRUST_RISK_MODEL_VERSION,
) -> dict[str, Any]:
    if _risk_model_version is not None and _risk_model_version not in _SUPPORTED_TRUST_RISK_MODEL_VERSIONS:
        raise TrustError(f"unsupported Trust risk model version: {_risk_model_version}")
    if _risk_model_version is None and (github_source is not None or workflow_diff is not None):
        raise TrustError("legacy unversioned risk model cannot consume workflow evidence")

    _, request_data = load_trust_request(request)
    _, profile_data = _profile_descriptor(
        profile, include_corroboration=_include_corroboration
    )
    workflow_evidence = _load_workflow_evidence_sources(
        request=request_data,
        github_source=github_source,
        workflow_diff=workflow_diff,
    ) if _risk_model_version is not None else None
    r4_semantic_evidence = _load_r4_semantic_evidence_sources(
        request=request_data,
        github_source=github_source,
        workflow_diff=workflow_diff,
        risk_model_version=_risk_model_version,
    ) if _risk_model_version in {
        TRUST_RISK_MODEL_V1_3,
        TRUST_RISK_MODEL_V1_4,
        TRUST_RISK_MODEL_VERSION,
    } else None
    signing_trust_root_evidence = _load_signing_trust_root_evidence_sources(
        request=request_data,
        github_source=github_source,
        workflow_diff=workflow_diff,
    ) if _risk_model_version == TRUST_RISK_MODEL_VERSION else None
    evidence = _evidence_projection(
        ledger=ledger,
        policy_registry=policy_registry,
        evaluation_report=evaluation_report,
        reground_report=reground_report,
        reground_observations=reground_observations,
        project_id=profile_data["project_id"],
        workflow_evidence=workflow_evidence,
        r4_semantic_evidence=r4_semantic_evidence,
        signing_trust_root_evidence=signing_trust_root_evidence,
    )
    risk = _risk_projection(
        request_data,
        profile_data,
        workflow_evidence,
        r4_semantic_evidence,
        signing_trust_root_evidence,
        risk_model_version=_risk_model_version,
    )
    hard_gates = _hard_gate_projection(request_data, risk, evidence)
    readiness = _readiness_projection(request_data, evidence)
    advisory = _task_advisory(risk, hard_gates)
    report: dict[str, Any] = {
        "schema_version": TRUST_SCHEMA_VERSION,
        "report_id": "",
        "project_id": profile_data["project_id"],
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "mode": TRUST_MODE,
        "automation_authorized": False,
        "maximum_automation_band": "NONE",
        "request": request_data,
        "profile": profile_data,
        "risk": risk,
        "hard_gates": hard_gates,
        "evidence": evidence,
        "readiness": readiness,
        "task_advisory": advisory,
        "snapshot_sha256": "",
        "report_sha256": "",
    }
    if _risk_model_version is not None:
        report["risk_model_version"] = _risk_model_version
    report["snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(report))
    report["report_id"] = _expected_report_id(report, report["snapshot_sha256"])
    report["report_sha256"] = canonical_json_sha256(_report_payload(report))
    errors = verify_trust_report_data(report)
    if errors:
        raise TrustVerificationError(errors)
    return report


def verify_trust_report_data(report: Any) -> list[str]:
    errors = _schema_errors("trust-report.schema.json", report)
    if not isinstance(report, dict):
        return sorted(set(errors))
    try:
        risk_model_version = report.get("risk_model_version")
        if risk_model_version is not None and risk_model_version not in _SUPPORTED_TRUST_RISK_MODEL_VERSIONS:
            errors.append("risk_model_version is unsupported")
        normalized_request = _normalize_request_data(report.get("request"))
        if report.get("request") != normalized_request:
            errors.append("request canonical projection mismatch")
        profile = report.get("profile")
        if not isinstance(profile, dict):
            errors.append("profile must be an object")
            profile = {
                "source": "",
                "project_id": "",
                "profile_sha256": "",
                "protected_paths": [],
            }
        else:
            normalized_patterns = sorted(
                {
                    _normalize_glob(value, f"profile.protected_paths[{index}]")
                    for index, value in enumerate(profile.get("protected_paths", []))
                }
            )
            if profile.get("protected_paths") != normalized_patterns:
                errors.append("profile.protected_paths canonical projection mismatch")
            if "configured_review_packs" in profile:
                configured_packs = profile.get("configured_review_packs")
                if not isinstance(configured_packs, list):
                    errors.append("profile.configured_review_packs must be an array")
                else:
                    normalized_packs = sorted(
                        {
                            value.strip()
                            for value in configured_packs
                            if isinstance(value, str) and value.strip()
                        }
                    )
                    if configured_packs != normalized_packs:
                        errors.append(
                            "profile.configured_review_packs canonical projection mismatch"
                        )
        if report.get("project_id") != profile.get("project_id"):
            errors.append("project_id does not match profile.project_id")
        evidence = report.get("evidence")
        if not isinstance(evidence, dict):
            errors.append("evidence must be an object")
            evidence = {}

        workflow_evidence = evidence.get("workflow_diff")
        normalized_workflow: dict[str, Any] | None = None
        if workflow_evidence is not None:
            if risk_model_version is None:
                errors.append("legacy unversioned report must not contain workflow evidence")
            normalized_workflow = normalize_trust_workflow_evidence(
                workflow_evidence,
                source_revision=normalized_request["source_revision"],
                changed_files=normalized_request["changed_files"],
            )
            if workflow_evidence != normalized_workflow:
                errors.append("evidence.workflow_diff canonical projection mismatch")

        r4_semantic_evidence = evidence.get("r4_semantics")
        normalized_r4: dict[str, Any] | None = None
        if r4_semantic_evidence is not None:
            if risk_model_version not in {
                TRUST_RISK_MODEL_V1_3,
                TRUST_RISK_MODEL_V1_4,
                TRUST_RISK_MODEL_VERSION,
            }:
                errors.append("R4 semantic evidence requires Trust risk model v1.3, v1.4 or v1.5")
            normalized_r4 = normalize_trust_r4_semantic_evidence(
                r4_semantic_evidence,
                source_revision=normalized_request["source_revision"],
                changed_files=normalized_request["changed_files"],
                risk_model_version=risk_model_version,
            )
            if r4_semantic_evidence != normalized_r4:
                errors.append("evidence.r4_semantics canonical projection mismatch")

        signing_trust_root_evidence = evidence.get("signing_trust_root")
        normalized_signing: dict[str, Any] | None = None
        if signing_trust_root_evidence is not None:
            if risk_model_version != TRUST_RISK_MODEL_VERSION:
                errors.append("signing trust-root evidence requires Trust risk model v1.5")
            normalized_signing = normalize_trust_signing_trust_root_evidence(
                signing_trust_root_evidence,
                source_revision=normalized_request["source_revision"],
                changed_files=normalized_request["changed_files"],
            )
            if signing_trust_root_evidence != normalized_signing:
                errors.append("evidence.signing_trust_root canonical projection mismatch")

        fingerprint_payload = {
            key: deepcopy(evidence.get(key))
            for key in ("ledger", "defects", "policy", "reground")
        }
        if normalized_workflow is not None:
            fingerprint_payload["workflow_diff"] = deepcopy(normalized_workflow)
        if normalized_r4 is not None:
            fingerprint_payload["r4_semantics"] = deepcopy(normalized_r4)
        if normalized_signing is not None:
            fingerprint_payload["signing_trust_root"] = deepcopy(normalized_signing)
        expected_fingerprint = canonical_json_sha256(fingerprint_payload)
        if evidence.get("fingerprint_sha256") != expected_fingerprint:
            errors.append("evidence.fingerprint_sha256 mismatch")
        expected_risk = _risk_projection(
            normalized_request,
            profile,
            normalized_workflow,
            normalized_r4,
            normalized_signing,
            risk_model_version=risk_model_version,
        )
        if report.get("risk") != expected_risk:
            errors.append("risk projection mismatch")
        expected_hard_gates = _hard_gate_projection(
            normalized_request,
            expected_risk,
            evidence,
        )
        if report.get("hard_gates") != expected_hard_gates:
            errors.append("hard_gates projection mismatch")
        expected_readiness = _readiness_projection(normalized_request, evidence)
        if report.get("readiness") != expected_readiness:
            errors.append("readiness projection mismatch")
        expected_advisory = _task_advisory(expected_risk, expected_hard_gates)
        if report.get("task_advisory") != expected_advisory:
            errors.append("task_advisory projection mismatch")
        snapshot = canonical_json_sha256(_snapshot_payload(report))
        if report.get("snapshot_sha256") != snapshot:
            errors.append("snapshot_sha256 mismatch")
        expected_id = _expected_report_id(report, snapshot)
        if report.get("report_id") != expected_id:
            errors.append("report_id mismatch")
        report_hash = canonical_json_sha256(_report_payload(report))
        if report.get("report_sha256") != report_hash:
            errors.append("report_sha256 mismatch")
    except (KeyError, TypeError, ValueError, TrustError) as exc:
        errors.append(f"report structure invalid: {exc}")
    return sorted(set(errors))


def load_trust_report(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input_file(path, "Trust readiness report")
    data = load_data(source)
    errors = verify_trust_report_data(data)
    if errors:
        raise TrustVerificationError(errors)
    return source, data


def verify_trust_report_sources(
    report: dict[str, Any],
    *,
    request: str | Path,
    profile: str | Path,
    ledger: str | Path | None = None,
    policy_registry: str | Path | None = None,
    evaluation_report: str | Path | None = None,
    reground_report: str | Path | None = None,
    reground_observations: str | Path | None = None,
    github_source: str | Path | None = None,
    workflow_diff: str | Path | None = None,
) -> list[str]:
    errors = verify_trust_report_data(report)
    if errors:
        return errors

    risk_model_version = report.get("risk_model_version")
    report_has_workflow = isinstance(report.get("evidence"), dict) and (
        report["evidence"].get("workflow_diff") is not None
    )
    supplied_workflow = github_source is not None or workflow_diff is not None
    if report_has_workflow and (github_source is None or workflow_diff is None):
        return ["source replay requires both GitHub source and workflow diff"]
    if not report_has_workflow and supplied_workflow:
        return ["source replay workflow sources were not part of the report"]

    try:
        replay = assess_trust(
            request,
            profile,
            ledger=ledger,
            policy_registry=policy_registry,
            evaluation_report=evaluation_report,
            reground_report=reground_report,
            reground_observations=reground_observations,
            github_source=github_source,
            workflow_diff=workflow_diff,
            generated_at=report["generated_at"],
            _include_corroboration=(
                "configured_review_packs" in report.get("profile", {})
            ),
            _risk_model_version=risk_model_version,
        )
    except (TrustError, OSError, ValueError) as exc:
        return [f"source replay failed: {exc}"]
    output: list[str] = []
    for field in ("snapshot_sha256", "report_id", "report_sha256"):
        if replay.get(field) != report.get(field):
            output.append(f"source replay {field} mismatch")
    return output


def write_trust_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_trust_report_data(report)
    if errors:
        raise TrustVerificationError(errors)
    target = _safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target
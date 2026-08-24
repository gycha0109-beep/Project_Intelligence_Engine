from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable
from urllib.parse import quote

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from .github_connector import GitHubCLI
from .github_prospective_capture import (
    EXACT_BLOCKERS,
    load_github_prospective_capture_candidate,
)
from .identity import canonical_json_sha256, normalize_source_revision
from .io import load_data
from .operational_policy import (
    POLICY_AUTHORITY,
    OperationalPolicyError,
    normalize_operational_policy_data,
)
from .path_globs import expand_trailing_recursive_glob
from .paths import asset
from .trust import load_trust_request


SCHEMA_VERSION = "1.0"
BINDING_CONTRACT_VERSION = "PIE_OPERATIONAL_POLICY_BINDING_V1"
FACTS_CONTRACT_VERSION = "PIE_OPERATIONAL_TRUST_FACTS_V1"
POLICY_PATH_DEFAULT = ".review/operational/policy.yml"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


class OperationalPolicyBindingError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class OperationalPolicyBindingVerificationError(OperationalPolicyBindingError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("BINDING_INVALID", "invalid operational policy binding: " + "; ".join(self.errors))


def _schema(name: str) -> dict[str, Any]:
    value = load_data(asset(f"schemas/{name}"))
    if not isinstance(value, dict):
        raise OperationalPolicyBindingError("CONTRACT_INVALID", f"schema must contain an object: {name}")
    return value


def _schema_errors(name: str, value: Any) -> list[str]:
    validator = Draft202012Validator(_schema(name), format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperationalPolicyBindingError("TRUST_FACTS_INVALID", f"{field} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperationalPolicyBindingError("TRUST_FACTS_INVALID", f"{field} is invalid: {value}") from exc
    if parsed.tzinfo is None:
        raise OperationalPolicyBindingError("TRUST_FACTS_INVALID", f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_relative_path(value: str) -> str:
    raw = value.strip().replace("\\", "/")
    candidate = PurePosixPath(raw)
    if not raw or candidate.is_absolute() or ".." in candidate.parts:
        raise OperationalPolicyBindingError(
            "INVALID_INPUT",
            f"operational policy path must remain project-relative: {value!r}",
        )
    return candidate.as_posix()


def _safe_output(path: str | Path, field: str) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise OperationalPolicyBindingError("INVALID_INPUT", f"{field} must not contain symlinks: {target}")
    return target.resolve()


def _exact_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA40.fullmatch(value.lower()) is None:
        raise OperationalPolicyBindingError("SOURCE_MISMATCH", f"{field} must be an exact 40-character Git SHA")
    return value.lower()


def _normalize_unique(values: list[str], field: str) -> list[str]:
    normalized = [value.strip() for value in values]
    if any(not value for value in normalized):
        raise OperationalPolicyBindingError("TRUST_FACTS_INVALID", f"{field} must not contain empty values")
    if len(set(normalized)) != len(normalized):
        raise OperationalPolicyBindingError("TRUST_FACTS_INVALID", f"{field} must not contain duplicates")
    return sorted(normalized)


def normalize_operational_trust_facts_data(data: Any) -> dict[str, Any]:
    errors = _schema_errors("operational-trust-facts.schema.json", data)
    if errors:
        raise OperationalPolicyBindingVerificationError(errors)
    if not isinstance(data, dict):
        raise OperationalPolicyBindingVerificationError(["facts must contain an object"])
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": FACTS_CONTRACT_VERSION,
        "project_id": data["project_id"].strip(),
        "source_revision": normalize_source_revision(data["source_revision"]),
        "completed_scenarios": _normalize_unique(data["completed_scenarios"], "completed_scenarios"),
        "verified_evidence": _normalize_unique(data["verified_evidence"], "verified_evidence"),
        "rollback_evidence": bool(data["rollback_evidence"]),
        "replay_evidence": bool(data["replay_evidence"]),
        "provided_by": data["provided_by"].strip(),
        "provided_at": _timestamp(data["provided_at"], "provided_at"),
    }
    normalized["facts_sha256"] = canonical_json_sha256(normalized)
    return normalized


def load_operational_trust_facts(path: str | Path) -> tuple[Path, dict[str, Any]]:
    raw = Path(path).expanduser()
    if _path_has_symlink(raw):
        raise OperationalPolicyBindingError("TRUST_FACTS_INVALID", f"Trust facts path must not contain symlinks: {raw}")
    try:
        source = raw.resolve(strict=True)
    except OSError as exc:
        raise OperationalPolicyBindingError("TRUST_FACTS_INVALID", f"Trust facts not found: {raw}") from exc
    if not source.is_file():
        raise OperationalPolicyBindingError("TRUST_FACTS_INVALID", f"Trust facts must be a regular file: {source}")
    return source, normalize_operational_trust_facts_data(load_data(source))


def _glob_variants(pattern: str) -> tuple[str, ...]:
    variants: set[str] = set()
    frontier = list(expand_trailing_recursive_glob(pattern))
    while frontier:
        current = frontier.pop()
        if current in variants:
            continue
        variants.add(current)
        marker = "**/"
        index = current.find(marker)
        if index >= 0:
            frontier.append(current[:index] + current[index + len(marker):])
    return tuple(sorted(variants))


def _matches_path(path: str, pattern: str) -> bool:
    normalized = PurePosixPath(path.replace("\\", "/"))
    return any(normalized.match(variant) for variant in _glob_variants(pattern))


def _matched_classes(policy: dict[str, Any], changed_files: list[str]) -> list[str]:
    matches: list[str] = []
    for name, item in policy["operational_classes"].items():
        if any(_matches_path(path, pattern) for path in changed_files for pattern in item["paths"]):
            matches.append(name)
    return sorted(matches)


def _github_api_json(
    github_cli: GitHubCLI,
    endpoint: str,
    *,
    cwd: str | Path | None = None,
    allow_not_found: bool = False,
) -> dict[str, Any] | None:
    result = github_cli.run(["api", endpoint], cwd=cwd, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        lowered = detail.lower()
        if allow_not_found and ("404" in lowered or "not found" in lowered):
            return None
        raise OperationalPolicyBindingError("GITHUB_READBACK_FAILED", detail or f"GitHub API request failed: {endpoint}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OperationalPolicyBindingError("GITHUB_READBACK_FAILED", f"GitHub API returned invalid JSON: {endpoint}") from exc
    if not isinstance(value, dict):
        raise OperationalPolicyBindingError("GITHUB_READBACK_FAILED", f"GitHub API result must be an object: {endpoint}")
    return value


def fetch_base_operational_policy(
    github_cli: GitHubCLI,
    *,
    repository: str,
    base_revision: str,
    project_id: str,
    policy_path: str = POLICY_PATH_DEFAULT,
    cwd: str | Path | None = None,
    snapshot_output: str | Path | None = None,
) -> dict[str, Any] | None:
    base_sha = _exact_sha(base_revision, "pull_request.base_oid")
    relative = _safe_relative_path(policy_path)
    endpoint = f"repos/{repository}/contents/{quote(relative, safe='/')}?ref={base_sha}"
    response = _github_api_json(github_cli, endpoint, cwd=cwd, allow_not_found=True)
    if response is None:
        return None
    if response.get("type") != "file":
        raise OperationalPolicyBindingError("POLICY_SOURCE_INVALID", f"base operational policy is not a file: {relative}")
    blob_sha = _exact_sha(response.get("sha"), "policy_blob_sha")
    if response.get("encoding") != "base64" or not isinstance(response.get("content"), str):
        raise OperationalPolicyBindingError("POLICY_SOURCE_INVALID", "base operational policy must be returned as base64 file content")
    try:
        encoded = "".join(response["content"].split())
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
        text = raw.decode("utf-8")
        parsed = yaml.safe_load(text)
    except (ValueError, UnicodeError, yaml.YAMLError) as exc:
        raise OperationalPolicyBindingError("POLICY_SOURCE_INVALID", f"cannot decode base operational policy: {exc}") from exc
    try:
        policy = normalize_operational_policy_data(parsed)
    except OperationalPolicyError as exc:
        raise OperationalPolicyBindingError("POLICY_SOURCE_INVALID", str(exc)) from exc
    if policy["project_id"] != project_id:
        raise OperationalPolicyBindingError(
            "PROJECT_SCOPE_MISMATCH",
            f"operational policy project_id {policy['project_id']!r} does not match candidate {project_id!r}",
        )
    if policy["policy_authority"] != POLICY_AUTHORITY:
        raise OperationalPolicyBindingError("POLICY_SOURCE_INVALID", "operational policy authority is not PR_BASE_REVISION")
    if snapshot_output is not None:
        target = _safe_output(snapshot_output, "operational policy snapshot output")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return {
        "path": relative,
        "authority": POLICY_AUTHORITY,
        "policy_revision": f"git:{base_sha}",
        "policy_blob_sha": blob_sha,
        "policy_content_sha256": hashlib.sha256(raw).hexdigest(),
        "policy_sha256": policy["policy_sha256"],
        "policy": policy,
    }


def _binding_hash(value: dict[str, Any]) -> str:
    payload = deepcopy(value)
    payload.pop("binding_sha256", None)
    trust_request = payload.get("trust_request")
    if isinstance(trust_request, dict):
        # Output filename is transport metadata, not binding semantics.
        trust_request["artifact_name"] = None
    return canonical_json_sha256(payload)


def verify_operational_policy_binding_data(value: Any) -> list[str]:
    errors = _schema_errors("operational-policy-binding.schema.json", value)
    if not isinstance(value, dict):
        return sorted(set(errors or ["binding must contain an object"]))
    if value.get("contract_version") != BINDING_CONTRACT_VERSION:
        errors.append("binding contract_version mismatch")
    for field in (
        "human_review_recorded",
        "outcome_recorded",
        "automation_authorized",
        "pilot_authorized",
        "merge_authorized",
        "deploy_authorized",
        "production_effect_authorized",
    ):
        if value.get(field) is not False:
            errors.append(f"{field} must remain false")
    if value.get("binding_sha256") != _binding_hash(value):
        errors.append("binding_sha256 mismatch")
    return sorted(set(errors))


def write_operational_policy_binding(path: str | Path, value: dict[str, Any]) -> Path:
    errors = verify_operational_policy_binding_data(value)
    if errors:
        raise OperationalPolicyBindingVerificationError(errors)
    target = _safe_output(path, "operational policy binding output")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def _base_binding(candidate: dict[str, Any], *, policy_path: str) -> dict[str, Any]:
    head = _exact_sha(candidate["pull_request"].get("head_oid"), "pull_request.head_oid")
    base = _exact_sha(candidate["pull_request"].get("base_oid"), "pull_request.base_oid")
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": BINDING_CONTRACT_VERSION,
        "project_id": candidate["project_id"],
        "candidate_id": candidate["candidate_id"],
        "repository": deepcopy(candidate["repository"]),
        "pull_request": {
            "number": candidate["pull_request"]["number"],
            "base_oid": base,
            "head_oid": head,
        },
        "task_id": candidate["task_id"],
        "source_revision": normalize_source_revision(head),
        "changed_files": list(candidate["changed_files"]),
        "policy": {
            "path": _safe_relative_path(policy_path),
            "available": False,
            "authority": POLICY_AUTHORITY,
            "policy_revision": f"git:{base}",
            "policy_blob_sha": None,
            "policy_content_sha256": None,
            "policy_sha256": None,
        },
        "match_status": "NO_POLICY_MATCH",
        "matched_operational_classes": [],
        "selected_operational_class": None,
        "requirements": {
            "trust_task_class": None,
            "required_scenarios": [],
            "required_evidence": [],
            "readiness_policy": None,
        },
        "facts": {
            "supplied": False,
            "facts_sha256": None,
            "completed_scenarios": [],
            "verified_evidence": [],
            "rollback_evidence": None,
            "replay_evidence": None,
        },
        "missing_inputs": [],
        "trust_request": {
            "materialized": False,
            "artifact_name": None,
            "request_sha256": None,
        },
        "status": "NO_POLICY_MATCH",
        "next_step": "PROVIDE_EXPLICIT_TRUST_INPUT",
        "human_review_recorded": False,
        "outcome_recorded": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
        "binding_sha256": "",
    }


def _finalize_binding(value: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(value)
    output["missing_inputs"] = sorted(set(output["missing_inputs"]))
    output["binding_sha256"] = _binding_hash(output)
    errors = verify_operational_policy_binding_data(output)
    if errors:
        raise OperationalPolicyBindingVerificationError(errors)
    return output


def bind_operational_policy(
    candidate_path: str | Path,
    *,
    github_cli: GitHubCLI,
    repository_root: str | Path,
    policy_path: str = POLICY_PATH_DEFAULT,
    trust_facts: str | Path | None = None,
    trust_request_output: str | Path | None = None,
    policy_snapshot_output: str | Path | None = None,
) -> dict[str, Any]:
    _candidate_source, candidate = load_github_prospective_capture_candidate(candidate_path)
    exact_blockers = sorted(set(candidate["blockers"]).intersection(EXACT_BLOCKERS))
    if exact_blockers:
        raise OperationalPolicyBindingError(
            "STALE_SOURCE_REVISION",
            "operational binding requires an exact clean candidate: " + ", ".join(exact_blockers),
        )
    root = Path(repository_root).expanduser().resolve()
    if not root.is_dir():
        raise OperationalPolicyBindingError("INVALID_INPUT", f"repository root does not exist: {root}")

    binding = _base_binding(candidate, policy_path=policy_path)
    descriptor = fetch_base_operational_policy(
        github_cli,
        repository=candidate["repository"]["name_with_owner"],
        base_revision=candidate["pull_request"]["base_oid"],
        project_id=candidate["project_id"],
        policy_path=policy_path,
        cwd=root,
        snapshot_output=policy_snapshot_output,
    )
    if descriptor is None:
        binding["missing_inputs"].append("OPERATIONAL_POLICY_NOT_FOUND_AT_BASE")
        return _finalize_binding(binding)

    binding["policy"].update({
        "available": True,
        "policy_revision": descriptor["policy_revision"],
        "policy_blob_sha": descriptor["policy_blob_sha"],
        "policy_content_sha256": descriptor["policy_content_sha256"],
        "policy_sha256": descriptor["policy_sha256"],
    })
    policy = descriptor["policy"]
    matched = _matched_classes(policy, candidate["changed_files"])
    binding["matched_operational_classes"] = matched
    if not matched:
        binding["missing_inputs"].append("NO_OPERATIONAL_CLASS_MATCH")
        return _finalize_binding(binding)
    if len(matched) > 1:
        binding["match_status"] = "AMBIGUOUS_POLICY_MATCH"
        binding["status"] = "AMBIGUOUS_POLICY_MATCH"
        binding["missing_inputs"].append("AMBIGUOUS_OPERATIONAL_CLASS_MATCH")
        return _finalize_binding(binding)

    selected = matched[0]
    rule = policy["operational_classes"][selected]
    binding["match_status"] = "UNIQUE_POLICY_MATCH"
    binding["selected_operational_class"] = selected
    binding["requirements"] = {
        "trust_task_class": rule["trust_task_class"],
        "required_scenarios": list(rule["required_scenarios"]),
        "required_evidence": list(rule["required_evidence"]),
        "readiness_policy": deepcopy(rule["readiness_policy"]),
    }

    if trust_facts is None:
        binding["status"] = "MISSING_TRUST_FIELDS"
        binding["missing_inputs"].extend([
            "completed_scenarios",
            "rollback_evidence",
            "replay_evidence",
        ])
        binding["missing_inputs"].extend(f"required_evidence:{item}" for item in rule["required_evidence"])
        return _finalize_binding(binding)

    _facts_source, facts = load_operational_trust_facts(trust_facts)
    if facts["project_id"] != candidate["project_id"]:
        raise OperationalPolicyBindingError("PROJECT_SCOPE_MISMATCH", "Trust facts project_id does not match candidate")
    expected_revision = normalize_source_revision(candidate["pull_request"]["head_oid"])
    if facts["source_revision"] != expected_revision:
        raise OperationalPolicyBindingError("STALE_TRUST_FACTS", "Trust facts source_revision does not match candidate PR head")
    unexpected_scenarios = sorted(set(facts["completed_scenarios"]) - set(rule["required_scenarios"]))
    if unexpected_scenarios:
        raise OperationalPolicyBindingError(
            "TRUST_FACTS_INVALID",
            "completed_scenarios are not declared by the matched operational class: " + ", ".join(unexpected_scenarios),
        )
    binding["facts"] = {
        "supplied": True,
        "facts_sha256": facts["facts_sha256"],
        "completed_scenarios": list(facts["completed_scenarios"]),
        "verified_evidence": list(facts["verified_evidence"]),
        "rollback_evidence": facts["rollback_evidence"],
        "replay_evidence": facts["replay_evidence"],
    }
    missing_evidence = sorted(set(rule["required_evidence"]) - set(facts["verified_evidence"]))
    if missing_evidence:
        binding["status"] = "MISSING_TRUST_FIELDS"
        binding["missing_inputs"].extend(f"required_evidence:{item}" for item in missing_evidence)
        return _finalize_binding(binding)

    scaffold = candidate["request_scaffold"]
    raw_request = {
        "schema_version": "1.0",
        "task_id": candidate["task_id"],
        "source_revision": expected_revision,
        "task_class": rule["trust_task_class"],
        "changed_files": list(candidate["changed_files"]),
        "required_scenarios": list(rule["required_scenarios"]),
        "completed_scenarios": list(facts["completed_scenarios"]),
        "repository_match": scaffold["repository_match"],
        "head_match": scaffold["head_match"],
        "rollback_evidence": facts["rollback_evidence"],
        "replay_evidence": facts["replay_evidence"],
        "readiness_policy": deepcopy(rule["readiness_policy"]),
    }
    target = _safe_output(
        trust_request_output or (Path(candidate_path).resolve().parent / "operational-trust-request.json"),
        "operational Trust request output",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(raw_request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        _source, normalized_request = load_trust_request(target)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise OperationalPolicyBindingError("TRUST_REQUEST_INVALID", str(exc)) from exc
    binding["trust_request"] = {
        "materialized": True,
        "artifact_name": target.name,
        "request_sha256": normalized_request["request_sha256"],
    }
    binding["status"] = "TRUST_REQUEST_MATERIALIZED"
    binding["next_step"] = "MATERIALIZE_WITH_EXISTING_AUTO2_PATH"
    return _finalize_binding(binding)

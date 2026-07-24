from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any, Iterable

import yaml

from .evaluation import load_evaluation_report
from .identity import canonical_json_sha256
from .intelligence_config import load_rules, validate_rules
from .io import load_data


POLICY_REGISTRY_SCHEMA_VERSION = "1.0"
POLICY_STATUSES = {"DRAFT", "ACTIVE", "SUPERSEDED", "RETIRED"}
_EVENT_TYPES = {"BUILT", "APPROVED", "ACTIVATED", "SUPERSEDED", "RETIRED"}
_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class PolicyRegistryError(RuntimeError):
    pass


class PolicyRegistryVerificationError(PolicyRegistryError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        super().__init__("invalid Policy Registry: " + "; ".join(self.errors))


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyRegistryError(f"{field} is required")
    return value.strip()


def _timestamp(value: str | None, field: str) -> str:
    text = _required_text(value, field)
    if not _TIMESTAMP_RE.fullmatch(text):
        raise PolicyRegistryError(f"{field} must use UTC format YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PolicyRegistryError(f"{field} is invalid: {text}") from exc
    return text


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _semver(value: str) -> str:
    text = _required_text(value, "version")
    if not _SEMVER_RE.fullmatch(text):
        raise PolicyRegistryError("version must be semantic version X.Y.Z")
    return text


def _semver_tuple(value: str) -> tuple[int, int, int]:
    text = _semver(value)
    major, minor, patch = text.split(".")
    return int(major), int(minor), int(patch)


def _expected_registry_id(project_id: str) -> str:
    return f"policy-registry-{canonical_json_sha256({'project_id': project_id})[:24]}"


def _expected_policy_id(
    *,
    project_id: str,
    version: str,
    parent_policy_id: str | None,
    ruleset_sha256: str,
    evaluation_id: str,
) -> str:
    key = {
        "project_id": project_id,
        "version": version,
        "parent_policy_id": parent_policy_id,
        "ruleset_sha256": ruleset_sha256,
        "evaluation_id": evaluation_id,
    }
    return f"policy-{canonical_json_sha256(key)[:32]}"


def _safe_reference(value: Any, field: str) -> str:
    raw = _required_text(value, field).replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise PolicyRegistryError(f"{field} must be relative")
    parts = [part for part in PurePosixPath(raw).parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise PolicyRegistryError(f"{field} contains an unsafe relative path")
    return PurePosixPath(*parts).as_posix()


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.exists() and current.is_symlink():
            return True
    return False


def _safe_source(path: str | Path, field: str) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise PolicyRegistryError(f"{field} must not contain symlinks: {source}")
    resolved = source.resolve()
    if not resolved.is_file():
        raise PolicyRegistryError(f"{field} not found: {resolved}")
    return resolved


def _safe_target(path: str | Path, field: str) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise PolicyRegistryError(f"{field} must not contain symlinks: {target}")
    return target.resolve()


def _relative_reference(registry_path: Path, source: Path, field: str) -> str:
    try:
        relative = source.relative_to(registry_path.parent)
    except ValueError as exc:
        raise PolicyRegistryError(
            f"{field} must be stored under the Policy Registry directory: {source}"
        ) from exc
    return _safe_reference(PurePosixPath(relative).as_posix(), field)


def _policy_payload(policy: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(policy)
    payload.pop("policy_sha256", None)
    return payload


def _registry_payload(registry: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(registry)
    payload.pop("registry_sha256", None)
    return payload


def _event_base(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in event.items()
        if key not in {"event_id", "event_sha256"}
    }


def _event_hash_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in event.items() if key != "event_sha256"}


def _append_event(
    policy: dict[str, Any],
    event_type: str,
    *,
    actor: str,
    at: str,
    details: dict[str, Any] | None = None,
) -> None:
    if event_type not in _EVENT_TYPES:
        raise PolicyRegistryError(f"unsupported Policy event: {event_type}")
    timestamp = _timestamp(at, "event timestamp")
    events = policy.setdefault("events", [])
    if events and timestamp < events[-1]["at"]:
        raise PolicyRegistryError("Policy event timestamp cannot precede the previous event")
    event = {
        "sequence": len(events) + 1,
        "type": event_type,
        "actor": _required_text(actor, "event actor"),
        "at": timestamp,
        "details": deepcopy(details or {}),
        "previous_event_sha256": events[-1]["event_sha256"] if events else None,
    }
    event["event_id"] = f"policy-event-{canonical_json_sha256(event)[:24]}"
    event["event_sha256"] = canonical_json_sha256(event)
    events.append(event)


def _rehash_policy(policy: dict[str, Any]) -> None:
    policy["policy_sha256"] = canonical_json_sha256(_policy_payload(policy))


def _rehash_registry(registry: dict[str, Any]) -> None:
    registry["registry_sha256"] = canonical_json_sha256(_registry_payload(registry))


def _serialize_registry(registry: dict[str, Any]) -> bytes:
    return (json.dumps(registry, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _serialize_rules(rules: dict[str, Any]) -> bytes:
    return yaml.safe_dump(rules, sort_keys=False, allow_unicode=True).encode("utf-8")


def _atomic_write(payloads: list[tuple[Path, bytes]]) -> None:
    if not payloads:
        return
    targets = [target for target, _ in payloads]
    if len(set(targets)) != len(targets):
        raise PolicyRegistryError("atomic write targets must be unique")
    for target in targets:
        if _path_has_symlink(target):
            raise PolicyRegistryError(f"refusing to write through symlink: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
    originals = {target: target.read_bytes() if target.exists() else None for target in targets}
    temporary_paths: list[Path] = []
    replaced: list[Path] = []
    try:
        for target, payload in payloads:
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
                temporary_paths.append(Path(handle.name))
        for (target, _), temporary in zip(payloads, temporary_paths):
            os.replace(temporary, target)
            replaced.append(target)
    except Exception:
        for target in reversed(replaced):
            original = originals[target]
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(original)
        raise
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)


def _empty_registry(project_id: str) -> dict[str, Any]:
    project = _required_text(project_id, "project_id")
    registry = {
        "schema_version": POLICY_REGISTRY_SCHEMA_VERSION,
        "registry_id": _expected_registry_id(project),
        "project_id": project,
        "active_policy_id": None,
        "policies": [],
    }
    _rehash_registry(registry)
    return registry


def verify_policy_registry_data(registry: Any) -> list[str]:
    if not isinstance(registry, dict):
        return ["registry must contain an object"]
    errors: list[str] = []
    if registry.get("schema_version") != POLICY_REGISTRY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {POLICY_REGISTRY_SCHEMA_VERSION!r}")
    project_id = registry.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        errors.append("project_id is required")
    if not isinstance(registry.get("registry_id"), str) or not registry["registry_id"].strip():
        errors.append("registry_id is required")
    elif isinstance(project_id, str) and registry["registry_id"] != _expected_registry_id(project_id):
        errors.append("registry_id mismatch")
    if registry.get("registry_sha256") != canonical_json_sha256(_registry_payload(registry)):
        errors.append("registry_sha256 mismatch")

    policies = registry.get("policies")
    if not isinstance(policies, list):
        errors.append("policies must be an array")
        policies = []
    ids: set[str] = set()
    versions: set[str] = set()
    policy_map: dict[str, dict[str, Any]] = {}
    active_status_ids: list[str] = []

    for index, policy in enumerate(policies):
        prefix = f"policies[{index}]"
        if not isinstance(policy, dict):
            errors.append(f"{prefix} must be an object")
            continue
        policy_id = policy.get("policy_id")
        version = policy.get("version")
        if not isinstance(policy_id, str) or not policy_id:
            errors.append(f"{prefix}.policy_id is required")
        elif policy_id in ids:
            errors.append(f"duplicate policy_id: {policy_id}")
        else:
            ids.add(policy_id)
            policy_map[policy_id] = policy
        if not isinstance(version, str) or not _SEMVER_RE.fullmatch(version):
            errors.append(f"{prefix}.version is invalid")
        elif version in versions:
            errors.append(f"duplicate policy version: {version}")
        else:
            versions.add(version)
        if policy.get("project_id") != project_id:
            errors.append(f"{prefix}.project_id does not match registry")
        try:
            _required_text(policy.get("created_by"), f"{prefix}.created_by")
            _timestamp(policy.get("created_at"), f"{prefix}.created_at")
        except PolicyRegistryError as exc:
            errors.append(str(exc))
        status = policy.get("status")
        if status not in POLICY_STATUSES:
            errors.append(f"{prefix}.status is invalid")
        if status == "ACTIVE" and isinstance(policy_id, str):
            active_status_ids.append(policy_id)

        ruleset = policy.get("ruleset")
        if not isinstance(ruleset, dict):
            errors.append(f"{prefix}.ruleset must be an object")
            ruleset = {}
        rules = ruleset.get("rules")
        rule_errors = (
            validate_rules(rules, required_status="approved")
            if isinstance(rules, dict)
            else ["rules must be an object"]
        )
        errors.extend(f"{prefix}.ruleset.{error}" for error in rule_errors)
        expected_rules_hash = canonical_json_sha256(rules) if isinstance(rules, dict) else None
        if ruleset.get("sha256") != expected_rules_hash:
            errors.append(f"{prefix}.ruleset.sha256 mismatch")

        evaluation = policy.get("evaluation")
        if not isinstance(evaluation, dict):
            errors.append(f"{prefix}.evaluation must be an object")
            evaluation = {}
        if evaluation.get("decision") != "PASS":
            errors.append(f"{prefix}.evaluation.decision must be PASS")
        if evaluation.get("challenger_policy_sha256") != ruleset.get("sha256"):
            errors.append(f"{prefix}.evaluation challenger hash does not match ruleset")
        for field in ("evaluation_id", "report", "report_sha256"):
            if not isinstance(evaluation.get(field), str) or not evaluation[field]:
                errors.append(f"{prefix}.evaluation.{field} is required")
        try:
            _safe_reference(evaluation.get("report"), f"{prefix}.evaluation.report")
        except PolicyRegistryError as exc:
            errors.append(str(exc))
        if all(
            isinstance(value, str) and value
            for value in (
                policy.get("project_id"),
                version,
                ruleset.get("sha256"),
                evaluation.get("evaluation_id"),
            )
        ):
            expected_id = _expected_policy_id(
                project_id=policy["project_id"],
                version=version,
                parent_policy_id=policy.get("parent_policy_id"),
                ruleset_sha256=ruleset["sha256"],
                evaluation_id=evaluation["evaluation_id"],
            )
            if policy_id != expected_id:
                errors.append(f"{prefix}.policy_id mismatch")

        events = policy.get("events")
        if not isinstance(events, list) or not events:
            errors.append(f"{prefix}.events must be a non-empty array")
            events = []
        previous_hash: str | None = None
        previous_at: str | None = None
        projected_status = "DRAFT"
        for event_index, event in enumerate(events):
            event_prefix = f"{prefix}.events[{event_index}]"
            if not isinstance(event, dict):
                errors.append(f"{event_prefix} must be an object")
                continue
            if event.get("sequence") != event_index + 1:
                errors.append(f"{event_prefix}.sequence mismatch")
            if event.get("previous_event_sha256") != previous_hash:
                errors.append(f"{event_prefix}.previous_event_sha256 mismatch")
            expected_event_id = f"policy-event-{canonical_json_sha256(_event_base(event))[:24]}"
            if event.get("event_id") != expected_event_id:
                errors.append(f"{event_prefix}.event_id mismatch")
            expected_event_hash = canonical_json_sha256(_event_hash_payload(event))
            if event.get("event_sha256") != expected_event_hash:
                errors.append(f"{event_prefix}.event_sha256 mismatch")
            previous_hash = event.get("event_sha256") if isinstance(event.get("event_sha256"), str) else None
            event_type = event.get("type")
            if event_type not in _EVENT_TYPES:
                errors.append(f"{event_prefix}.type is invalid")
                continue
            try:
                event_at = _timestamp(event.get("at"), f"{event_prefix}.at")
                _required_text(event.get("actor"), f"{event_prefix}.actor")
                if previous_at is not None and event_at < previous_at:
                    errors.append(f"{event_prefix}.at precedes the previous event")
                previous_at = event_at
            except PolicyRegistryError as exc:
                errors.append(str(exc))
            if event_index == 0 and event_type != "BUILT":
                errors.append(f"{event_prefix} first event must be BUILT")
            if event_type == "BUILT":
                if event_index != 0:
                    errors.append(f"{event_prefix} BUILT may only be the first event")
            elif event_type == "APPROVED":
                if projected_status != "DRAFT":
                    errors.append(f"{event_prefix} APPROVED transition is invalid")
                projected_status = "APPROVED"
            elif event_type == "ACTIVATED":
                if projected_status != "APPROVED":
                    errors.append(f"{event_prefix} ACTIVATED transition is invalid")
                projected_status = "ACTIVE"
            elif event_type == "SUPERSEDED":
                if projected_status != "ACTIVE":
                    errors.append(f"{event_prefix} SUPERSEDED transition is invalid")
                projected_status = "SUPERSEDED"
            elif event_type == "RETIRED":
                if projected_status not in {"ACTIVE", "SUPERSEDED"}:
                    errors.append(f"{event_prefix} RETIRED transition is invalid")
                projected_status = "RETIRED"
        if projected_status == "APPROVED":
            errors.append(f"{prefix} has incomplete approval without activation")
        elif projected_status != status:
            errors.append(f"{prefix}.status does not match lifecycle events")

        if status == "DRAFT":
            if any(policy.get(field) is not None for field in ("approval", "effective_at", "superseded_by", "retirement")):
                errors.append(f"{prefix} DRAFT lifecycle projection contains terminal metadata")
        if status in {"ACTIVE", "SUPERSEDED", "RETIRED"}:
            approval = policy.get("approval")
            approved_events = [event for event in events if isinstance(event, dict) and event.get("type") == "APPROVED"]
            if not isinstance(approval, dict):
                errors.append(f"{prefix}.approval is required")
            elif len(approved_events) != 1:
                errors.append(f"{prefix} must contain exactly one APPROVED event")
            elif (
                approval.get("approved_by") != approved_events[0].get("actor")
                or approval.get("approved_at") != approved_events[0].get("at")
            ):
                errors.append(f"{prefix}.approval does not match APPROVED event")
            activated_events = [event for event in events if isinstance(event, dict) and event.get("type") == "ACTIVATED"]
            if len(activated_events) != 1 or policy.get("effective_at") != activated_events[0].get("at"):
                errors.append(f"{prefix}.effective_at does not match ACTIVATED event")
        if status == "SUPERSEDED":
            superseded_events = [event for event in events if isinstance(event, dict) and event.get("type") == "SUPERSEDED"]
            if not isinstance(policy.get("superseded_by"), str):
                errors.append(f"{prefix}.superseded_by is required")
            elif len(superseded_events) != 1 or superseded_events[0].get("details", {}).get("superseded_by") != policy.get("superseded_by"):
                errors.append(f"{prefix}.superseded_by does not match SUPERSEDED event")
        if status == "RETIRED":
            retirement = policy.get("retirement")
            retired_events = [event for event in events if isinstance(event, dict) and event.get("type") == "RETIRED"]
            if not isinstance(retirement, dict):
                errors.append(f"{prefix}.retirement is required")
            elif not all(isinstance(retirement.get(field), str) and retirement[field] for field in ("retired_by", "retired_at", "reason")):
                errors.append(f"{prefix}.retirement is incomplete")
            elif len(retired_events) != 1:
                errors.append(f"{prefix} must contain exactly one RETIRED event")
            elif (
                retirement["retired_by"] != retired_events[0].get("actor")
                or retirement["retired_at"] != retired_events[0].get("at")
                or retirement["reason"] != retired_events[0].get("details", {}).get("reason")
            ):
                errors.append(f"{prefix}.retirement does not match RETIRED event")

        if policy.get("policy_sha256") != canonical_json_sha256(_policy_payload(policy)):
            errors.append(f"{prefix}.policy_sha256 mismatch")

    active_id = registry.get("active_policy_id")
    if active_id is not None and not isinstance(active_id, str):
        errors.append("active_policy_id must be a string or null")
    if len(active_status_ids) > 1:
        errors.append("multiple ACTIVE policies are not allowed")
    if active_id is None and active_status_ids:
        errors.append("active_policy_id is null while an ACTIVE policy exists")
    if isinstance(active_id, str):
        if active_id not in policy_map:
            errors.append("active_policy_id references missing Policy")
        elif active_status_ids != [active_id]:
            errors.append("active_policy_id does not match ACTIVE Policy projection")

    for policy_id, policy in policy_map.items():
        parent = policy.get("parent_policy_id")
        if parent is not None and not isinstance(parent, str):
            errors.append(f"Policy {policy_id} parent_policy_id must be string or null")
        elif isinstance(parent, str) and parent not in policy_map:
            errors.append(f"Policy {policy_id} references missing parent {parent}")
        elif parent == policy_id:
            errors.append(f"Policy {policy_id} cannot parent itself")
        elif isinstance(parent, str) and parent in policy_map:
            try:
                if _semver_tuple(policy["version"]) <= _semver_tuple(policy_map[parent]["version"]):
                    errors.append(f"Policy {policy_id} version must be greater than its parent")
            except (KeyError, PolicyRegistryError):
                pass
        superseded_by = policy.get("superseded_by")
        if isinstance(superseded_by, str):
            child = policy_map.get(superseded_by)
            if child is None:
                errors.append(f"Policy {policy_id} superseded_by references missing Policy")
            elif child.get("parent_policy_id") != policy_id:
                errors.append(f"Policy {policy_id} superseded_by is not its child")

    for policy_id in policy_map:
        seen: set[str] = set()
        cursor: str | None = policy_id
        while cursor is not None:
            if cursor in seen:
                errors.append(f"Policy parent cycle detected at {policy_id}")
                break
            seen.add(cursor)
            parent = policy_map.get(cursor, {}).get("parent_policy_id")
            cursor = parent if isinstance(parent, str) else None

    return sorted(set(errors))


def load_policy_registry(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_source(path, "Policy Registry")
    data = load_data(source)
    errors = verify_policy_registry_data(data)
    if errors:
        raise PolicyRegistryVerificationError(errors)
    return source, data


def _write_registry(path: Path, registry: dict[str, Any]) -> None:
    errors = verify_policy_registry_data(registry)
    if errors:
        raise PolicyRegistryVerificationError(errors)
    _atomic_write([(path, _serialize_registry(registry))])


def build_policy(
    registry: str | Path,
    *,
    project_id: str,
    version: str,
    rules: str | Path,
    evaluation_report: str | Path,
    created_by: str,
    created_at: str | None = None,
    parent_policy_id: str | None = None,
) -> dict[str, Any]:
    registry_path = _safe_target(registry, "Policy Registry")
    project = _required_text(project_id, "project_id")
    semantic_version = _semver(version)
    actor = _required_text(created_by, "created_by")
    timestamp = _timestamp(created_at or utc_now(), "created_at")

    if registry_path.exists():
        _, current = load_policy_registry(registry_path)
        if current["project_id"] != project:
            raise PolicyRegistryError("project_id does not match existing Registry")
        updated = deepcopy(current)
    else:
        updated = _empty_registry(project)

    policy_map = {item["policy_id"]: item for item in updated["policies"]}
    if parent_policy_id is not None and parent_policy_id not in policy_map:
        raise PolicyRegistryError(f"parent Policy not found: {parent_policy_id}")
    if parent_policy_id is not None and _semver_tuple(semantic_version) <= _semver_tuple(policy_map[parent_policy_id]["version"]):
        raise PolicyRegistryError("Policy version must be greater than its parent version")
    if any(item["version"] == semantic_version for item in updated["policies"]):
        raise PolicyRegistryError(f"Policy version already exists: {semantic_version}")

    rules_path = _safe_source(rules, "approved Rule file")
    try:
        rules_data = load_rules(rules_path, required_status="approved")
    except ValueError as exc:
        raise PolicyRegistryError(str(exc)) from exc
    ruleset_hash = canonical_json_sha256(rules_data)

    report_input = Path(evaluation_report).expanduser()
    if _path_has_symlink(report_input):
        raise PolicyRegistryError(f"evaluation report must not contain symlinks: {report_input}")
    report_path, report = load_evaluation_report(report_input)
    if report["gate"]["decision"] != "PASS":
        raise PolicyRegistryError("Policy build requires a PASS evaluation report")
    if report["challenger_policy"]["sha256"] != ruleset_hash:
        raise PolicyRegistryError("evaluation challenger Policy hash does not match approved Rule set")
    report_reference = _relative_reference(registry_path, report_path, "evaluation report")

    policy_id = _expected_policy_id(
        project_id=project,
        version=semantic_version,
        parent_policy_id=parent_policy_id,
        ruleset_sha256=ruleset_hash,
        evaluation_id=report["evaluation_id"],
    )
    if policy_id in policy_map:
        raise PolicyRegistryError(f"Policy already exists: {policy_id}")

    policy = {
        "policy_id": policy_id,
        "project_id": project,
        "version": semantic_version,
        "parent_policy_id": parent_policy_id,
        "status": "DRAFT",
        "ruleset": {
            "sha256": ruleset_hash,
            "source": rules_path.name,
            "rules": rules_data,
        },
        "evaluation": {
            "evaluation_id": report["evaluation_id"],
            "report": report_reference,
            "report_sha256": report["report_sha256"],
            "decision": report["gate"]["decision"],
            "dataset_sha256": report["dataset"]["sha256"],
            "baseline_policy_sha256": report["baseline_policy"]["sha256"],
            "challenger_policy_sha256": report["challenger_policy"]["sha256"],
            "evaluator": deepcopy(report["evaluator"]),
        },
        "created_by": actor,
        "created_at": timestamp,
        "approval": None,
        "effective_at": None,
        "superseded_by": None,
        "retirement": None,
        "events": [],
    }
    _append_event(policy, "BUILT", actor=actor, at=timestamp, details={"version": semantic_version})
    _rehash_policy(policy)
    updated["policies"].append(policy)
    updated["policies"] = sorted(updated["policies"], key=lambda item: (_semver_tuple(item["version"]), item["policy_id"]))
    _rehash_registry(updated)
    _write_registry(registry_path, updated)
    return deepcopy(policy)


def approve_policy(
    registry: str | Path,
    policy_id: str,
    *,
    approved_by: str,
    materialized_rules: str | Path,
    approved_at: str | None = None,
    effective_at: str | None = None,
    rationale: str | None = None,
) -> dict[str, Any]:
    registry_path, current = load_policy_registry(registry)
    materialized_path = _safe_target(materialized_rules, "materialized approved Rule file")
    actor = _required_text(approved_by, "approved_by")
    approval_time = _timestamp(approved_at or utc_now(), "approved_at")
    effective_time = _timestamp(effective_at or approval_time, "effective_at")
    if effective_time > approval_time:
        raise PolicyRegistryError("future effective_at is not supported in Stage 7")
    if effective_time != approval_time:
        raise PolicyRegistryError("effective_at must equal approved_at for immediate activation")

    updated = deepcopy(current)
    policy_map = {item["policy_id"]: item for item in updated["policies"]}
    selected = policy_map.get(policy_id)
    if selected is None:
        raise PolicyRegistryError(f"Policy not found: {policy_id}")
    if selected["status"] != "DRAFT":
        raise PolicyRegistryError(f"Policy is not DRAFT: {policy_id}")
    if approval_time < selected["events"][-1]["at"]:
        raise PolicyRegistryError("approved_at cannot precede Policy creation")

    active_id = updated.get("active_policy_id")
    if active_id is None:
        if selected.get("parent_policy_id") is not None:
            raise PolicyRegistryError("first active Policy must not have a parent")
    else:
        if selected.get("parent_policy_id") != active_id:
            raise PolicyRegistryError("Policy parent must be the current active Policy")
        active = policy_map[active_id]
        if active["status"] != "ACTIVE":
            raise PolicyRegistryError("active Policy projection is invalid")
        if approval_time < active["events"][-1]["at"]:
            raise PolicyRegistryError("approved_at cannot precede active Policy history")
        active["status"] = "SUPERSEDED"
        active["superseded_by"] = policy_id
        _append_event(active, "SUPERSEDED", actor=actor, at=approval_time, details={"superseded_by": policy_id})
        _rehash_policy(active)

    selected["approval"] = {
        "approved_by": actor,
        "approved_at": approval_time,
        **({"rationale": rationale.strip()} if isinstance(rationale, str) and rationale.strip() else {}),
    }
    selected["effective_at"] = effective_time
    _append_event(selected, "APPROVED", actor=actor, at=approval_time, details={})
    _append_event(selected, "ACTIVATED", actor=actor, at=effective_time, details={"effective_at": effective_time})
    selected["status"] = "ACTIVE"
    _rehash_policy(selected)
    updated["active_policy_id"] = policy_id
    _rehash_registry(updated)

    errors = verify_policy_registry_data(updated)
    if errors:
        raise PolicyRegistryVerificationError(errors)
    _atomic_write([
        (registry_path, _serialize_registry(updated)),
        (materialized_path, _serialize_rules(selected["ruleset"]["rules"])),
    ])
    return deepcopy(selected)


def retire_policy(
    registry: str | Path,
    policy_id: str,
    *,
    retired_by: str,
    reason: str,
    retired_at: str | None = None,
    materialized_rules: str | Path | None = None,
) -> dict[str, Any]:
    registry_path, current = load_policy_registry(registry)
    actor = _required_text(retired_by, "retired_by")
    retirement_reason = _required_text(reason, "reason")
    timestamp = _timestamp(retired_at or utc_now(), "retired_at")
    updated = deepcopy(current)
    policy_map = {item["policy_id"]: item for item in updated["policies"]}
    selected = policy_map.get(policy_id)
    if selected is None:
        raise PolicyRegistryError(f"Policy not found: {policy_id}")
    if selected["status"] not in {"ACTIVE", "SUPERSEDED"}:
        raise PolicyRegistryError(f"Policy cannot be retired from {selected['status']}")
    if timestamp < selected["events"][-1]["at"]:
        raise PolicyRegistryError("retired_at cannot precede Policy history")
    was_active = updated.get("active_policy_id") == policy_id
    if was_active and materialized_rules is None:
        raise PolicyRegistryError("retiring the active Policy requires materialized_rules")

    selected["status"] = "RETIRED"
    selected["retirement"] = {
        "retired_by": actor,
        "retired_at": timestamp,
        "reason": retirement_reason,
    }
    _append_event(selected, "RETIRED", actor=actor, at=timestamp, details={"reason": retirement_reason})
    _rehash_policy(selected)
    if was_active:
        updated["active_policy_id"] = None
    _rehash_registry(updated)
    errors = verify_policy_registry_data(updated)
    if errors:
        raise PolicyRegistryVerificationError(errors)

    payloads = [(registry_path, _serialize_registry(updated))]
    if was_active and materialized_rules is not None:
        materialized_path = _safe_target(materialized_rules, "materialized approved Rule file")
        payloads.append((materialized_path, _serialize_rules({"schema_version": "1.0", "rules": []})))
    _atomic_write(payloads)
    return deepcopy(selected)


def materialize_active_policy(registry: str | Path, output: str | Path) -> Path:
    _, data = load_policy_registry(registry)
    active_id = data.get("active_policy_id")
    if not isinstance(active_id, str):
        raise PolicyRegistryError("Registry has no active Policy")
    active = next(item for item in data["policies"] if item["policy_id"] == active_id)
    target = _safe_target(output, "materialized approved Rule file")
    _atomic_write([(target, _serialize_rules(active["ruleset"]["rules"]))])
    return target


def compare_policies(registry: str | Path, left_policy_id: str, right_policy_id: str) -> dict[str, Any]:
    _, data = load_policy_registry(registry)
    policy_map = {item["policy_id"]: item for item in data["policies"]}
    left = policy_map.get(left_policy_id)
    right = policy_map.get(right_policy_id)
    if left is None:
        raise PolicyRegistryError(f"Policy not found: {left_policy_id}")
    if right is None:
        raise PolicyRegistryError(f"Policy not found: {right_policy_id}")
    left_rules = {item["id"]: item for item in left["ruleset"]["rules"].get("rules", [])}
    right_rules = {item["id"]: item for item in right["ruleset"]["rules"].get("rules", [])}
    return {
        "schema_version": "1.0",
        "left_policy_id": left_policy_id,
        "right_policy_id": right_policy_id,
        "left_version": left["version"],
        "right_version": right["version"],
        "added_rule_ids": sorted(set(right_rules) - set(left_rules)),
        "removed_rule_ids": sorted(set(left_rules) - set(right_rules)),
        "changed_rule_ids": sorted(
            rule_id
            for rule_id in set(left_rules) & set(right_rules)
            if canonical_json_sha256(left_rules[rule_id]) != canonical_json_sha256(right_rules[rule_id])
        ),
        "same_ruleset": left["ruleset"]["sha256"] == right["ruleset"]["sha256"],
    }


def verify_policy_registry_file(
    registry: str | Path,
    *,
    materialized_rules: str | Path | None = None,
    verify_evaluation_reports: bool = True,
) -> list[str]:
    try:
        registry_path = _safe_source(registry, "Policy Registry")
        data = load_data(registry_path)
    except Exception as exc:
        return [str(exc)]
    errors = verify_policy_registry_data(data)
    if errors:
        return errors

    if verify_evaluation_reports:
        for policy in data["policies"]:
            try:
                reference = _safe_reference(policy["evaluation"]["report"], "evaluation report")
                report_path = _safe_source(registry_path.parent / reference, "evaluation report")
                _, report = load_evaluation_report(report_path)
                if report["report_sha256"] != policy["evaluation"]["report_sha256"]:
                    errors.append(f"Policy {policy['policy_id']} evaluation report hash mismatch")
                if report["evaluation_id"] != policy["evaluation"]["evaluation_id"]:
                    errors.append(f"Policy {policy['policy_id']} evaluation ID mismatch")
                if report["challenger_policy"]["sha256"] != policy["ruleset"]["sha256"]:
                    errors.append(f"Policy {policy['policy_id']} evaluation challenger mismatch")
                if report["gate"]["decision"] != "PASS":
                    errors.append(f"Policy {policy['policy_id']} evaluation is not PASS")
            except Exception as exc:
                errors.append(f"Policy {policy['policy_id']} evaluation verification failed: {exc}")

    if materialized_rules is not None:
        try:
            materialized_path = _safe_source(materialized_rules, "materialized approved Rule file")
            materialized = load_rules(materialized_path, required_status="approved")
            active_id = data.get("active_policy_id")
            expected = (
                next(item for item in data["policies"] if item["policy_id"] == active_id)["ruleset"]["rules"]
                if isinstance(active_id, str)
                else {"schema_version": "1.0", "rules": []}
            )
            if canonical_json_sha256(materialized) != canonical_json_sha256(expected):
                errors.append("materialized approved Rule file does not match active Policy")
        except Exception as exc:
            errors.append(str(exc))
    return sorted(set(errors))


def list_policies(registry: str | Path) -> list[dict[str, Any]]:
    _, data = load_policy_registry(registry)
    return [
        {
            "policy_id": item["policy_id"],
            "version": item["version"],
            "status": item["status"],
            "parent_policy_id": item.get("parent_policy_id"),
            "ruleset_sha256": item["ruleset"]["sha256"],
            "evaluation_id": item["evaluation"]["evaluation_id"],
            "effective_at": item.get("effective_at"),
        }
        for item in sorted(data["policies"], key=lambda policy: (_semver_tuple(policy["version"]), policy["policy_id"]))
    ]


def show_policy(registry: str | Path, policy_id: str) -> dict[str, Any]:
    _, data = load_policy_registry(registry)
    selected = next((item for item in data["policies"] if item["policy_id"] == policy_id), None)
    if selected is None:
        raise PolicyRegistryError(f"Policy not found: {policy_id}")
    return deepcopy(selected)

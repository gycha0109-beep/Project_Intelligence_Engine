from __future__ import annotations

from copy import deepcopy
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .io import load_data
from .paths import asset


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_OPERATIONAL_POLICY_V1"
POLICY_AUTHORITY = "PR_BASE_REVISION"
_WINDOW_DRIVE = re.compile(r"^[A-Za-z]:/")


class OperationalPolicyError(RuntimeError):
    pass


class OperationalPolicyVerificationError(OperationalPolicyError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid operational policy: " + "; ".join(self.errors))


def _schema(name: str) -> dict[str, Any]:
    value = load_data(asset(f"schemas/{name}"))
    if not isinstance(value, dict):
        raise OperationalPolicyError(f"schema must contain an object: {name}")
    return value


def _schema_errors(value: Any) -> list[str]:
    validator = Draft202012Validator(
        _schema("operational-policy.schema.json"),
        format_checker=FormatChecker(),
    )
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _contract_alignment_errors() -> list[str]:
    operational = _schema("operational-policy.schema.json")
    trust = _schema("trust-request.schema.json")
    errors: list[str] = []
    try:
        operational_tasks = operational["$defs"]["operationalClass"]["properties"]["trust_task_class"]["enum"]
        trust_tasks = trust["properties"]["task_class"]["enum"]
        if operational_tasks != trust_tasks:
            errors.append("Trust task_class vocabulary drifted from trust-request.schema.json")
        if operational["$defs"]["readinessPolicy"] != trust["$defs"]["readinessPolicy"]:
            errors.append("readiness_policy contract drifted from trust-request.schema.json")
    except (KeyError, TypeError) as exc:
        errors.append(f"Trust contract alignment cannot be evaluated: {exc}")
    return errors


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_input_file(path: str | Path) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise OperationalPolicyError(f"operational policy path must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise OperationalPolicyError(f"operational policy not found: {source}") from exc
    if not resolved.is_file():
        raise OperationalPolicyError(f"operational policy must be a regular file: {resolved}")
    return resolved


def _normalize_glob(value: str, field: str) -> str:
    raw = value.strip().replace("\\", "/")
    if not raw:
        raise OperationalPolicyError(f"{field} must be non-empty")
    if any(ord(character) < 32 for character in raw):
        raise OperationalPolicyError(f"{field} must not contain control characters")
    if raw.startswith("/") or _WINDOW_DRIVE.match(raw):
        raise OperationalPolicyError(f"{field} must remain project-relative: {value!r}")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise OperationalPolicyError(f"{field} contains an unsafe path pattern: {value!r}")
    normalized = candidate.as_posix()
    if normalized in {"", "."}:
        raise OperationalPolicyError(f"{field} must not be empty")
    return normalized


def _normalized_unique(values: list[str], field: str, *, paths: bool = False) -> list[str]:
    normalized = [
        _normalize_glob(value, f"{field}[{index}]") if paths else value.strip()
        for index, value in enumerate(values)
    ]
    if len(set(normalized)) != len(normalized):
        raise OperationalPolicyError(f"{field} must not contain normalized duplicates")
    return sorted(normalized)


def normalize_operational_policy_data(data: Any) -> dict[str, Any]:
    alignment_errors = _contract_alignment_errors()
    if alignment_errors:
        raise OperationalPolicyVerificationError(alignment_errors)
    errors = _schema_errors(data)
    if errors:
        raise OperationalPolicyVerificationError(errors)
    if not isinstance(data, dict):
        raise OperationalPolicyVerificationError(["policy must contain an object"])

    classes: dict[str, Any] = {}
    for name in sorted(data["operational_classes"]):
        item = data["operational_classes"][name]
        classes[name] = {
            "paths": _normalized_unique(item["paths"], f"operational_classes.{name}.paths", paths=True),
            "trust_task_class": item["trust_task_class"],
            "required_scenarios": _normalized_unique(
                item["required_scenarios"],
                f"operational_classes.{name}.required_scenarios",
            ),
            "required_evidence": _normalized_unique(
                item["required_evidence"],
                f"operational_classes.{name}.required_evidence",
            ),
            "readiness_policy": deepcopy(item["readiness_policy"]),
        }

    normalized: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "project_id": data["project_id"].strip(),
        "policy_authority": POLICY_AUTHORITY,
        "operational_classes": classes,
    }
    normalized["policy_sha256"] = canonical_json_sha256(normalized)
    return normalized


def load_operational_policy(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input_file(path)
    return source, normalize_operational_policy_data(load_data(source))


def verify_operational_policy_file(path: str | Path) -> list[str]:
    try:
        load_operational_policy(path)
    except OperationalPolicyError as exc:
        return [str(exc)]
    except (OSError, ValueError, TypeError) as exc:
        return [f"cannot verify operational policy: {exc}"]
    return []

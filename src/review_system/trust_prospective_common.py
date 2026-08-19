from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable

from .identity import file_sha256
from .trust_comparison import TrustComparisonVerificationError, load_registry, verify_registry_data
from .trust_observation import load_policy
from .trust_reconciliation_authority import load_source_manifest, reconcile_sources

SCHEMA_VERSION = "1.0"
MODE = "REPORT_ONLY"
TARGET_BAND = "R0"
CAMPAIGN_CONTRACT = "PROSPECTIVE_R0_EVIDENCE_CAMPAIGN_V1"
SUPPORTED_OUTCOME_AUTHORITIES = {"PRODUCTION_DEFECT", "CONTROLLED_EVALUATION", "INDEPENDENT_AUDIT"}
SOURCE_FIELDS = ("ledger", "policy_registry", "evaluation_report", "reground_report", "reground_observations")
SHA40 = re.compile(r"^(?:git:)?[0-9a-f]{40}$")
CHECK_SPECS = (
    ("MINIMUM_R0_ASSESSMENT_COUNT", "r0_assessment_count", "minimum_r0_assessment_count", ">="),
    ("MINIMUM_R0_REVIEWED_COUNT", "r0_reviewed_count", "minimum_r0_reviewed_count", ">="),
    ("MINIMUM_R0_CONCLUSIVE_OUTCOME_COUNT", "r0_conclusive_outcome_count", "minimum_r0_conclusive_outcome_count", ">="),
    ("MINIMUM_R0_CONFIRMED_SAFE_COUNT", "r0_confirmed_safe_count", "minimum_r0_confirmed_safe_count", ">="),
    ("MINIMUM_CONFIRMED_UNSAFE_CHALLENGE_COUNT", "confirmed_unsafe_challenge_count", "minimum_confirmed_unsafe_challenge_count", ">="),
    ("MINIMUM_R0_INDEPENDENT_AUDIT_COUNT", "r0_independent_audit_count", "minimum_r0_independent_audit_count", ">="),
    ("MINIMUM_R0_OUTCOME_COVERAGE", "r0_outcome_coverage", "minimum_r0_outcome_coverage", ">="),
    ("MINIMUM_R0_EVIDENCE_SPAN_DAYS", "r0_evidence_span_days", "minimum_r0_evidence_span_days", ">="),
    ("MAXIMUM_R0_FALSE_NEGATIVES", "r0_false_negative", "maximum_r0_false_negatives", "<="),
    ("MAXIMUM_R0_FALSE_NEGATIVE_RATE", "r0_false_negative_rate", "maximum_r0_false_negative_rate", "<="),
)
SAFETY_CHECK_IDS = {"MAXIMUM_R0_FALSE_NEGATIVES", "MAXIMUM_R0_FALSE_NEGATIVE_RATE"}


class ProspectiveEvidenceError(RuntimeError):
    pass


class ProspectiveEvidenceVerificationError(ProspectiveEvidenceError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid prospective R0 evidence campaign report: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProspectiveEvidenceError(f"{field} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProspectiveEvidenceError(f"{field} is invalid: {value}") from exc
    if parsed.tzinfo is None:
        raise ProspectiveEvidenceError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_root(path: str | Path) -> Path:
    root = Path(path).expanduser()
    if _path_has_symlink(root):
        raise ProspectiveEvidenceError(f"campaign workspace must not contain symlinks: {root}")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ProspectiveEvidenceError(f"campaign workspace not found: {root}") from exc
    if not resolved.is_dir():
        raise ProspectiveEvidenceError(f"campaign workspace must be a directory: {resolved}")
    return resolved


def _safe_input(path: str | Path, field: str) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise ProspectiveEvidenceError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise ProspectiveEvidenceError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise ProspectiveEvidenceError(f"{field} must be a regular file: {resolved}")
    return resolved


def _required_workspace(root: Path) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry_path = root / "comparison-registry.json"
    manifest_path = root / "reconciliation-sources.json"
    policy_path = root / "observation-policy.json"
    for path, field in (
        (registry_path, "comparison registry"),
        (manifest_path, "reconciliation source manifest"),
        (policy_path, "observation policy"),
    ):
        if not path.is_file() or path.is_symlink():
            raise ProspectiveEvidenceError(f"campaign workspace missing {field}: {path}")
    _, registry = load_registry(registry_path)
    _, manifest = load_source_manifest(manifest_path)
    _, policy = load_policy(policy_path)
    if registry["project_id"] != manifest["project_id"]:
        raise ProspectiveEvidenceError("registry and reconciliation manifest project_id mismatch")
    return registry_path, manifest_path, policy_path, registry, manifest, policy


def _copy_exact(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_symlink() or not target.is_file():
            raise ProspectiveEvidenceError(f"campaign source target is not a regular file: {target}")
        if file_sha256(target) != file_sha256(source):
            raise ProspectiveEvidenceError(f"campaign source target already exists with different bytes: {target}")
        return
    with source.open("rb") as reader, target.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_temp(path: Path, payload: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _restore(path: Path, payload: bytes) -> None:
    temporary = _write_temp(path, payload)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_one(path: Path, payload: bytes) -> None:
    temporary = _write_temp(path, payload)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_registry_manifest(
    registry_path: Path,
    manifest_path: Path,
    registry: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    registry_errors = verify_registry_data(registry)
    if registry_errors:
        raise TrustComparisonVerificationError(registry_errors)
    original_registry = registry_path.read_bytes()
    original_manifest = manifest_path.read_bytes()
    registry_temp = _write_temp(registry_path, _json_bytes(registry))
    manifest_temp = _write_temp(manifest_path, _json_bytes(manifest))
    try:
        os.replace(registry_temp, registry_path)
        try:
            os.replace(manifest_temp, manifest_path)
        except Exception:
            _restore(registry_path, original_registry)
            raise
    finally:
        registry_temp.unlink(missing_ok=True)
        manifest_temp.unlink(missing_ok=True)
    try:
        load_registry(registry_path)
        load_source_manifest(manifest_path)
    except Exception:
        _restore(registry_path, original_registry)
        _restore(manifest_path, original_manifest)
        raise


def _validate_manifest_candidate(root: Path, manifest: dict[str, Any]) -> None:
    temp = _write_temp(root / "reconciliation-sources.json", _json_bytes(manifest))
    try:
        load_source_manifest(temp)
    finally:
        temp.unlink(missing_ok=True)


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ProspectiveEvidenceError(f"campaign source escaped workspace: {path}") from exc


def _assessment_source_entry(assessment_id: str, root: Path, stored: dict[str, Path | None]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "assessment_id": assessment_id,
        "trust_report": _relative(root, stored["trust_report"]),
        "request": _relative(root, stored["request"]),
        "profile": _relative(root, stored["profile"]),
    }
    for field in SOURCE_FIELDS:
        path = stored.get(field)
        entry[field] = None if path is None else _relative(root, path)
    return entry


def _candidate_paths(root: Path, registry: dict[str, Any], manifest: dict[str, Any]) -> tuple[Path, Path]:
    registry_temp = _write_temp(root / "comparison-registry.json", _json_bytes(registry))
    manifest_temp = _write_temp(root / "reconciliation-sources.json", _json_bytes(manifest))
    return registry_temp, manifest_temp


def _replay_candidate(root: Path, registry: dict[str, Any], manifest: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    registry_temp, manifest_temp = _candidate_paths(root, registry, manifest)
    try:
        return reconcile_sources(registry_temp, manifest_temp, generated_at=generated_at)
    finally:
        registry_temp.unlink(missing_ok=True)
        manifest_temp.unlink(missing_ok=True)



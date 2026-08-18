from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256, file_sha256
from .io import load_data
from .paths import asset
from .trust_comparison import load_registry
from .trust_observation import assess_observation, load_policy, write_report as write_observation_report
from .trust_pilot_evidence_run import run_r0_pilot_evidence
from .trust_reconciliation_authority import (
    load_source_manifest,
    reconcile_sources,
    write_reconciliation_report,
)


SCHEMA_VERSION = "1.0"
MODE = "REPORT_ONLY"
TARGET_BAND = "R0"
WORKSPACE_CONTRACT = "R0_EVIDENCE_ACQUISITION_WORKSPACE_V1"
ELIGIBLE_STATUS = "ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW"
REQUIRED_INPUTS = (
    ("attestation", "acquisition-attestation.json"),
    ("comparison_registry", "comparison-registry.json"),
    ("reconciliation_sources", "reconciliation-sources.json"),
    ("observation_policy", "observation-policy.json"),
)
RESERVED_PACKAGE_PATHS = {
    "acquisition-attestation.json",
    "comparison-registry.json",
    "reconciliation-sources.json",
    "observation-policy.json",
    "reconciliation-report.json",
    "observation-report.json",
}


class EvidenceAcquisitionError(RuntimeError):
    pass


class EvidenceAcquisitionVerificationError(EvidenceAcquisitionError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid R0 evidence acquisition report: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceAcquisitionError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceAcquisitionError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise EvidenceAcquisitionError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_root(path: str | Path, field: str, *, must_exist: bool) -> Path:
    root = Path(path).expanduser()
    if _path_has_symlink(root):
        raise EvidenceAcquisitionError(f"{field} must not contain symlinks: {root}")
    if must_exist:
        try:
            resolved = root.resolve(strict=True)
        except OSError as exc:
            raise EvidenceAcquisitionError(f"{field} not found: {root}") from exc
        if not resolved.is_dir():
            raise EvidenceAcquisitionError(f"{field} must be a directory: {resolved}")
        return resolved
    return root.resolve()


def _safe_file(root: Path, relative: str) -> Path | None:
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise EvidenceAcquisitionError(f"unsafe workspace reference: {relative}")
    candidate = root.joinpath(*path.parts)
    if _path_has_symlink(candidate):
        raise EvidenceAcquisitionError(f"workspace reference must not traverse symlinks: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _schema_errors(name: str, value: Any) -> list[str]:
    schema = load_data(asset(f"schemas/{name}"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _required_inventory(root: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for key, filename in REQUIRED_INPUTS:
        source = _safe_file(root, filename)
        output.append({
            "key": key,
            "filename": filename,
            "present": source is not None,
            "sha256": file_sha256(source) if source is not None else None,
        })
    return output


def _load_attestation(path: Path) -> dict[str, Any]:
    try:
        value = load_data(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise EvidenceAcquisitionError(f"cannot load acquisition attestation: {type(exc).__name__}") from exc
    errors = _schema_errors("r0-evidence-acquisition-attestation.schema.json", value)
    if errors:
        raise EvidenceAcquisitionVerificationError([f"attestation: {item}" for item in errors])
    assert isinstance(value, dict)
    return value


def _closure_references(manifest: dict[str, Any]) -> list[str]:
    refs: set[str] = set()
    for item in manifest["assessment_sources"]:
        for field in (
            "trust_report", "request", "profile", "ledger", "policy_registry",
            "evaluation_report", "reground_report", "reground_observations",
        ):
            value = item.get(field)
            if value:
                refs.add(str(value))
    for item in manifest["outcome_sources"]:
        for field, value in item.items():
            if field not in {"event_id", "authority_type"} and value:
                refs.add(str(value))
    collisions = sorted(ref for ref in refs if ref in RESERVED_PACKAGE_PATHS)
    if collisions:
        raise EvidenceAcquisitionError("source closure collides with reserved package paths: " + ", ".join(collisions))
    return sorted(refs)


def _closure_inventory(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for reference in _closure_references(manifest):
        source = _safe_file(root, reference)
        output.append({
            "reference": reference,
            "present": source is not None,
            "sha256": file_sha256(source) if source is not None else None,
        })
    return output


def _empty_generated() -> dict[str, Any]:
    return {
        "reconciliation_report_id": None,
        "observation_report_id": None,
        "pilot_evidence_run_id": None,
        "pilot_evidence_status": None,
        "source_replay_verified": False,
    }


def _snapshot_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "mode": report.get("mode"),
        "target_band": report.get("target_band"),
        "automation_authorized": report.get("automation_authorized"),
        "pilot_authorized": report.get("pilot_authorized"),
        "workspace_contract": report.get("workspace_contract"),
        "required_inputs": deepcopy(report.get("required_inputs")),
        "source_closure": deepcopy(report.get("source_closure")),
        "workspace_complete": report.get("workspace_complete"),
        "package": deepcopy(report.get("package")),
        "generated": deepcopy(report.get("generated")),
        "blockers": deepcopy(report.get("blockers")),
        "status": report.get("status"),
        "next_step": report.get("next_step"),
    }


def _report_payload(report: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(report)
    value.pop("report_sha256", None)
    return value


def _report_id(project_id: str | None, snapshot_sha256: str) -> str:
    key = {"project_id": project_id, "workspace_contract": WORKSPACE_CONTRACT, "evidence_snapshot_sha256": snapshot_sha256}
    return f"r0-evidence-acquisition-{canonical_json_sha256(key)[:32]}"


def _finalize(report: dict[str, Any]) -> dict[str, Any]:
    report["evidence_snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(report))
    report["report_id"] = _report_id(report.get("project_id"), report["evidence_snapshot_sha256"])
    report["report_sha256"] = canonical_json_sha256(_report_payload(report))
    errors = verify_acquisition_report_data(report)
    if errors:
        raise EvidenceAcquisitionVerificationError(errors)
    return report


def _base_report(*, generated_at: str | None, required_inputs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": "r0-evidence-acquisition-" + "0" * 32,
        "project_id": None,
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "mode": MODE,
        "target_band": TARGET_BAND,
        "automation_authorized": False,
        "pilot_authorized": False,
        "workspace_contract": WORKSPACE_CONTRACT,
        "required_inputs": required_inputs,
        "source_closure": [],
        "workspace_complete": False,
        "package": {"attempted": False, "published": False, "file_count": 0},
        "generated": _empty_generated(),
        "blockers": [],
        "status": "BLOCKED_MISSING_INPUT",
        "next_step": "PROVIDE_REQUIRED_ACQUISITION_INPUTS",
        "evidence_snapshot_sha256": "0" * 64,
        "report_sha256": "0" * 64,
    }


def inspect_acquisition_workspace(workspace_root: str | Path, *, generated_at: str | None = None) -> dict[str, Any]:
    root = _safe_root(workspace_root, "acquisition workspace", must_exist=True)
    required = _required_inventory(root)
    report = _base_report(generated_at=generated_at, required_inputs=required)
    missing = [item["key"] for item in required if not item["present"]]
    if missing:
        report["blockers"] = [f"MISSING_REQUIRED_INPUT:{key.upper()}" for key in missing]
        return _finalize(report)

    attestation_path = _safe_file(root, "acquisition-attestation.json")
    registry_path = _safe_file(root, "comparison-registry.json")
    manifest_path = _safe_file(root, "reconciliation-sources.json")
    policy_path = _safe_file(root, "observation-policy.json")
    assert attestation_path and registry_path and manifest_path and policy_path
    attestation = _load_attestation(attestation_path)
    _, registry = load_registry(registry_path)
    _, manifest = load_source_manifest(manifest_path)
    _, _policy = load_policy(policy_path)
    project_ids = {attestation["project_id"], registry["project_id"], manifest["project_id"]}
    if len(project_ids) != 1:
        raise EvidenceAcquisitionError("project_id mismatch across attestation, comparison registry, and reconciliation sources")
    report["project_id"] = registry["project_id"]
    closure = _closure_inventory(root, manifest)
    report["source_closure"] = closure
    missing_closure = [item["reference"] for item in closure if not item["present"]]
    if missing_closure:
        report["blockers"] = [f"MISSING_SOURCE_CLOSURE:{item}" for item in missing_closure]
        report["status"] = "BLOCKED_MISSING_SOURCE_CLOSURE"
        report["next_step"] = "PROVIDE_MISSING_SOURCE_EVIDENCE"
        return _finalize(report)
    report["workspace_complete"] = True
    report["status"] = "READY_TO_POPULATE"
    report["next_step"] = "POPULATE_R0_EVIDENCE_PACKAGE"
    return _finalize(report)


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, target.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())


def _count_files(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_file())


def populate_r0_evidence_package(
    workspace_root: str | Path,
    package_root: str | Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = _safe_root(workspace_root, "acquisition workspace", must_exist=True)
    report = inspect_acquisition_workspace(root, generated_at=generated_at)
    if report["status"] != "READY_TO_POPULATE":
        return report
    target = _safe_root(package_root, "R0 evidence package", must_exist=False)
    if target.exists():
        raise EvidenceAcquisitionError(f"R0 evidence package target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if _path_has_symlink(target.parent):
        raise EvidenceAcquisitionError(f"R0 evidence package parent must not contain symlinks: {target.parent}")

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent))
    report["package"]["attempted"] = True
    try:
        for _key, filename in REQUIRED_INPUTS:
            source = _safe_file(root, filename)
            assert source is not None
            _copy_file(source, staging / filename)
        for item in report["source_closure"]:
            source = _safe_file(root, item["reference"])
            assert source is not None
            _copy_file(source, staging.joinpath(*PurePosixPath(item["reference"]).parts))

        reconciliation = reconcile_sources(
            staging / "comparison-registry.json",
            staging / "reconciliation-sources.json",
            generated_at=report["generated_at"],
        )
        write_reconciliation_report(staging / "reconciliation-report.json", reconciliation)
        observation = assess_observation(
            staging / "comparison-registry.json",
            staging / "observation-policy.json",
            generated_at=report["generated_at"],
        )
        write_observation_report(staging / "observation-report.json", observation)
        pilot_run = run_r0_pilot_evidence(staging, generated_at=report["generated_at"])
        report["generated"] = {
            "reconciliation_report_id": reconciliation["report_id"],
            "observation_report_id": observation["report_id"],
            "pilot_evidence_run_id": pilot_run["run_id"],
            "pilot_evidence_status": pilot_run["status"],
            "source_replay_verified": bool(pilot_run["source_replay"]["verified"]),
        }
        if not pilot_run["source_replay"]["verified"]:
            report["blockers"] = sorted(set(["SOURCE_REPLAY_FAILED", *pilot_run["blockers"]]))
            report["status"] = "BLOCKED_SOURCE_REPLAY"
            report["next_step"] = "REPAIR_AND_REPLAY_SOURCE_EVIDENCE"
            return _finalize(report)

        file_count = _count_files(staging)
        os.replace(staging, target)
        report["package"] = {"attempted": True, "published": True, "file_count": file_count}
        report["blockers"] = list(pilot_run["blockers"])
        if pilot_run["status"] == ELIGIBLE_STATUS:
            report["status"] = "PACKAGE_POPULATED_ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW"
        else:
            report["status"] = "PACKAGE_POPULATED_NOT_ELIGIBLE"
        report["next_step"] = pilot_run["next_step"]
        return _finalize(report)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _expected_status(report: dict[str, Any]) -> tuple[str, list[str], str]:
    required = report.get("required_inputs") if isinstance(report.get("required_inputs"), list) else []
    missing_required = [item.get("key") for item in required if isinstance(item, dict) and item.get("present") is False]
    closure = report.get("source_closure") if isinstance(report.get("source_closure"), list) else []
    missing_closure = [item.get("reference") for item in closure if isinstance(item, dict) and item.get("present") is False]
    package = report.get("package") if isinstance(report.get("package"), dict) else {}
    generated = report.get("generated") if isinstance(report.get("generated"), dict) else {}
    if missing_required:
        return (
            "BLOCKED_MISSING_INPUT",
            [f"MISSING_REQUIRED_INPUT:{str(key).upper()}" for key in missing_required],
            "PROVIDE_REQUIRED_ACQUISITION_INPUTS",
        )
    if missing_closure:
        return (
            "BLOCKED_MISSING_SOURCE_CLOSURE",
            [f"MISSING_SOURCE_CLOSURE:{ref}" for ref in missing_closure],
            "PROVIDE_MISSING_SOURCE_EVIDENCE",
        )
    if not package.get("attempted"):
        return "READY_TO_POPULATE", [], "POPULATE_R0_EVIDENCE_PACKAGE"
    if not package.get("published"):
        blockers = list(report.get("blockers") or [])
        if "SOURCE_REPLAY_FAILED" not in blockers:
            blockers.append("SOURCE_REPLAY_FAILED")
        return "BLOCKED_SOURCE_REPLAY", sorted(set(blockers)), "REPAIR_AND_REPLAY_SOURCE_EVIDENCE"
    if generated.get("pilot_evidence_status") == ELIGIBLE_STATUS:
        return (
            "PACKAGE_POPULATED_ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW",
            list(report.get("blockers") or []),
            report.get("next_step") or "REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION",
        )
    return (
        "PACKAGE_POPULATED_NOT_ELIGIBLE",
        list(report.get("blockers") or []),
        report.get("next_step") or "RESOLVE_PILOT_SAFETY_BLOCKERS",
    )


def verify_acquisition_report_data(report: Any) -> list[str]:
    errors = _schema_errors("r0-evidence-acquisition-report.schema.json", report)
    if not isinstance(report, dict):
        return sorted(set(errors or ["report must contain an object"]))
    if report.get("mode") != MODE:
        errors.append("mode must remain REPORT_ONLY")
    if report.get("target_band") != TARGET_BAND:
        errors.append("target_band must remain R0")
    if report.get("automation_authorized") is not False:
        errors.append("automation_authorized must remain false")
    if report.get("pilot_authorized") is not False:
        errors.append("pilot_authorized must remain false")
    if report.get("workspace_contract") != WORKSPACE_CONTRACT:
        errors.append("workspace contract mismatch")
    required = report.get("required_inputs") if isinstance(report.get("required_inputs"), list) else []
    expected_required = list(REQUIRED_INPUTS)
    if len(required) == len(expected_required):
        for index, (item, (key, filename)) in enumerate(zip(required, expected_required)):
            if isinstance(item, dict) and (item.get("key") != key or item.get("filename") != filename):
                errors.append(f"required_inputs[{index}] canonical projection mismatch")
    workspace_complete = (
        len(required) == len(expected_required)
        and all(isinstance(item, dict) and item.get("present") is True and isinstance(item.get("sha256"), str) for item in required)
        and all(isinstance(item, dict) and item.get("present") is True and isinstance(item.get("sha256"), str) for item in report.get("source_closure", []))
    )
    if report.get("workspace_complete") is not workspace_complete:
        errors.append("workspace_complete projection mismatch")
    package = report.get("package") if isinstance(report.get("package"), dict) else {}
    generated = report.get("generated") if isinstance(report.get("generated"), dict) else {}
    if package.get("published") and not package.get("attempted"):
        errors.append("published package requires attempted=true")
    if package.get("published") and generated.get("source_replay_verified") is not True:
        errors.append("published package requires verified source replay")
    if generated.get("source_replay_verified") is True and not package.get("attempted"):
        errors.append("verified source replay requires package attempt")
    expected_status, expected_blockers, expected_next = _expected_status(report)
    if report.get("status") != expected_status:
        errors.append("status projection mismatch")
    if report.get("blockers") != expected_blockers:
        errors.append("blockers projection mismatch")
    if report.get("next_step") != expected_next:
        errors.append("next_step projection mismatch")
    snapshot = canonical_json_sha256(_snapshot_payload(report))
    if report.get("evidence_snapshot_sha256") != snapshot:
        errors.append("evidence_snapshot_sha256 mismatch")
    if report.get("report_id") != _report_id(report.get("project_id"), snapshot):
        errors.append("report_id mismatch")
    if report.get("report_sha256") != canonical_json_sha256(_report_payload(report)):
        errors.append("report_sha256 mismatch")
    return sorted(set(errors))


def load_acquisition_report(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise EvidenceAcquisitionError(f"report path must not contain symlinks: {source}")
    try:
        source = source.resolve(strict=True)
    except OSError as exc:
        raise EvidenceAcquisitionError(f"report not found: {source}") from exc
    if not source.is_file():
        raise EvidenceAcquisitionError(f"report must be a regular file: {source}")
    value = load_data(source)
    errors = verify_acquisition_report_data(value)
    if errors:
        raise EvidenceAcquisitionVerificationError(errors)
    return source, value


def verify_acquisition_report_sources(
    report: dict[str, Any],
    *,
    workspace_root: str | Path | None = None,
    package_root: str | Path | None = None,
) -> list[str]:
    errors = verify_acquisition_report_data(report)
    if errors:
        return errors
    if workspace_root is not None:
        try:
            inspected = inspect_acquisition_workspace(workspace_root, generated_at=report["generated_at"])
        except (EvidenceAcquisitionError, EvidenceAcquisitionVerificationError, OSError, ValueError) as exc:
            return [f"workspace replay failed: {type(exc).__name__}"]
        for field in ("project_id", "required_inputs", "source_closure", "workspace_complete"):
            if inspected.get(field) != report.get(field):
                errors.append(f"workspace replay {field} mismatch")
    if report.get("package", {}).get("published"):
        if package_root is None:
            errors.append("published acquisition report requires package_root source replay")
        else:
            try:
                replay = run_r0_pilot_evidence(package_root, generated_at=report["generated_at"])
            except (OSError, ValueError, RuntimeError) as exc:
                errors.append(f"package replay failed: {type(exc).__name__}")
            else:
                generated = report["generated"]
                expected = {
                    "pilot_evidence_run_id": replay["run_id"],
                    "pilot_evidence_status": replay["status"],
                    "source_replay_verified": bool(replay["source_replay"]["verified"]),
                }
                for field, value in expected.items():
                    if generated.get(field) != value:
                        errors.append(f"package replay {field} mismatch")
    return sorted(set(errors))


def write_acquisition_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_acquisition_report_data(report)
    if errors:
        raise EvidenceAcquisitionVerificationError(errors)
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise EvidenceAcquisitionError(f"output path must not contain symlinks: {target}")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target

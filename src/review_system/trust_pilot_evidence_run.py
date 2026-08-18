from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256, file_sha256
from .io import load_data
from .paths import asset
from .trust_pilot_review import (
    ELIGIBLE_STATUS,
    NOT_ELIGIBLE_STATUS,
    PilotSafetyReviewError,
    PilotSafetyReviewVerificationError,
)
from .trust_pilot_review_authority import review_r0_pilot


SCHEMA_VERSION = "1.0"
MODE = "REPORT_ONLY"
TARGET_BAND = "R0"
PACKAGE_CONTRACT = "R0_PILOT_EVIDENCE_PACKAGE_V1"
EXPECTED_FILES = (
    ("comparison_registry", "comparison-registry.json"),
    ("reconciliation_sources", "reconciliation-sources.json"),
    ("reconciliation_report", "reconciliation-report.json"),
    ("observation_policy", "observation-policy.json"),
    ("observation_report", "observation-report.json"),
)


class PilotEvidenceRunError(RuntimeError):
    pass


class PilotEvidenceRunVerificationError(PilotEvidenceRunError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid R0 pilot eligibility evidence run report: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PilotEvidenceRunError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PilotEvidenceRunError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise PilotEvidenceRunError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise PilotEvidenceRunError(f"output path must not contain symlinks: {target}")
    return target.resolve()


def _schema_errors(value: Any) -> list[str]:
    schema = load_data(asset("schemas/r0-pilot-eligibility-evidence-run-report.schema.json"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    output: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        output.append(f"{location}: {error.message}")
    return output


def _inventory(evidence_root: str | Path) -> tuple[Path, list[dict[str, Any]], list[str]]:
    root = Path(evidence_root).expanduser()
    if _path_has_symlink(root):
        raise PilotEvidenceRunError("evidence root must not contain symlinks")
    root = root.resolve()
    inventory: list[dict[str, Any]] = []
    blockers: list[str] = []
    for key, filename in EXPECTED_FILES:
        source = root / filename
        present = False
        digest: str | None = None
        if not _path_has_symlink(source) and source.exists() and source.is_file():
            present = True
            digest = file_sha256(source)
        else:
            blockers.append(f"EVIDENCE_FILE_MISSING:{key.upper()}")
        inventory.append({"key": key, "filename": filename, "present": present, "sha256": digest})
    return root, inventory, sorted(set(blockers))


def _report_payload(report: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(report)
    value.pop("report_sha256", None)
    return value


def _snapshot_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "mode": report.get("mode"),
        "target_band": report.get("target_band"),
        "automation_authorized": report.get("automation_authorized"),
        "pilot_authorized": report.get("pilot_authorized"),
        "package_contract": deepcopy(report.get("package_contract")),
        "inventory": deepcopy(report.get("inventory")),
        "package_complete": report.get("package_complete"),
        "source_replay": deepcopy(report.get("source_replay")),
        "pilot_review": deepcopy(report.get("pilot_review")),
        "blockers": deepcopy(report.get("blockers")),
        "status": report.get("status"),
        "next_step": report.get("next_step"),
    }


def _run_id(report: dict[str, Any], snapshot_sha256: str) -> str:
    key = {
        "project_id": report.get("project_id"),
        "package_contract": report.get("package_contract"),
        "evidence_snapshot_sha256": snapshot_sha256,
    }
    return f"r0-pilot-evidence-run-{canonical_json_sha256(key)[:32]}"


def _project(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "attempted": False,
            "review_id": None,
            "report_sha256": None,
            "status": None,
            "next_step": None,
            "blockers": [],
        }
    return {
        "attempted": True,
        "review_id": report["review_id"],
        "report_sha256": report["report_sha256"],
        "status": report["status"],
        "next_step": report["next_step"],
        "blockers": sorted(set(report["blockers"])),
    }


def _decision(
    *,
    package_complete: bool,
    inventory_blockers: list[str],
    source_replay: dict[str, Any],
    pilot_review: dict[str, Any],
) -> tuple[str, list[str], str]:
    blockers = list(inventory_blockers)
    if package_complete and not source_replay["verified"]:
        blockers.append("SOURCE_REPLAY_FAILED")
    blockers.extend(pilot_review["blockers"])
    blockers = sorted(set(blockers))
    eligible = (
        package_complete
        and source_replay["attempted"]
        and source_replay["verified"]
        and pilot_review["attempted"]
        and pilot_review["status"] == ELIGIBLE_STATUS
        and not blockers
    )
    if eligible:
        return ELIGIBLE_STATUS, [], "REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION"
    if not package_complete:
        return NOT_ELIGIBLE_STATUS, blockers, "PROVIDE_COMPLETE_R0_EVIDENCE_PACKAGE"
    if not source_replay["verified"]:
        return NOT_ELIGIBLE_STATUS, blockers, "REPAIR_AND_REPLAY_SOURCE_EVIDENCE"
    return NOT_ELIGIBLE_STATUS, blockers, pilot_review["next_step"] or "RESOLVE_PILOT_SAFETY_BLOCKERS"


def run_r0_pilot_evidence(
    evidence_root: str | Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root, inventory, inventory_blockers = _inventory(evidence_root)
    package_complete = all(item["present"] and item["sha256"] for item in inventory) and not inventory_blockers
    source_replay = {"attempted": False, "verified": False, "error_codes": []}
    pilot_report: dict[str, Any] | None = None
    project_id: str | None = None

    if package_complete:
        paths = {key: root / filename for key, filename in EXPECTED_FILES}
        source_replay["attempted"] = True
        try:
            pilot_report = review_r0_pilot(
                registry_path=paths["comparison_registry"],
                reconciliation_report_path=paths["reconciliation_report"],
                reconciliation_sources_path=paths["reconciliation_sources"],
                observation_report_path=paths["observation_report"],
                observation_policy_path=paths["observation_policy"],
                generated_at=generated_at,
            )
            project_id = pilot_report["project_id"]
            replay = pilot_report["source_replay"]
            error_codes: list[str] = []
            if not replay["reconciliation_verified"]:
                error_codes.append("RECONCILIATION_SOURCE_REPLAY_FAILED")
            if not replay["observation_verified"]:
                error_codes.append("OBSERVATION_SOURCE_REPLAY_FAILED")
            source_replay["error_codes"] = error_codes
            source_replay["verified"] = not error_codes
        except (
            PilotSafetyReviewError,
            PilotSafetyReviewVerificationError,
            OSError,
            ValueError,
        ) as exc:
            source_replay["error_codes"] = [f"PILOT_REVIEW_FAILED:{type(exc).__name__}"]

    pilot_projection = _project(pilot_report)
    status, blockers, next_step = _decision(
        package_complete=bool(package_complete),
        inventory_blockers=inventory_blockers,
        source_replay=source_replay,
        pilot_review=pilot_projection,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": "",
        "project_id": project_id,
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "mode": MODE,
        "target_band": TARGET_BAND,
        "automation_authorized": False,
        "pilot_authorized": False,
        "package_contract": {
            "name": PACKAGE_CONTRACT,
            "root_name": root.name or ".",
            "expected_files": [filename for _, filename in EXPECTED_FILES],
        },
        "inventory": inventory,
        "package_complete": bool(package_complete),
        "source_replay": source_replay,
        "pilot_review": pilot_projection,
        "blockers": blockers,
        "status": status,
        "next_step": next_step,
        "evidence_snapshot_sha256": "",
        "report_sha256": "",
    }
    snapshot = canonical_json_sha256(_snapshot_payload(report))
    report["evidence_snapshot_sha256"] = snapshot
    report["run_id"] = _run_id(report, snapshot)
    report["report_sha256"] = canonical_json_sha256(_report_payload(report))
    errors = verify_pilot_evidence_run_report_data(report)
    if errors:
        raise PilotEvidenceRunVerificationError(errors)
    return report


def verify_pilot_evidence_run_report_data(report: Any) -> list[str]:
    errors = _schema_errors(report)
    if not isinstance(report, dict):
        return sorted(set(errors or ["report must contain an object"]))
    try:
        if report.get("mode") != MODE:
            errors.append("mode must remain REPORT_ONLY")
        if report.get("target_band") != TARGET_BAND:
            errors.append("target_band must remain R0")
        if report.get("automation_authorized") is not False:
            errors.append("automation_authorized must remain false")
        if report.get("pilot_authorized") is not False:
            errors.append("pilot_authorized must remain false")

        contract = report.get("package_contract") if isinstance(report.get("package_contract"), dict) else {}
        if contract.get("name") != PACKAGE_CONTRACT:
            errors.append("package contract name mismatch")
        expected_files = [filename for _, filename in EXPECTED_FILES]
        if contract.get("expected_files") != expected_files:
            errors.append("package expected_files projection mismatch")

        inventory = report.get("inventory") if isinstance(report.get("inventory"), list) else []
        expected_pairs = list(EXPECTED_FILES)
        if len(inventory) == len(expected_pairs):
            for index, (item, (key, filename)) in enumerate(zip(inventory, expected_pairs)):
                if not isinstance(item, dict):
                    continue
                if item.get("key") != key or item.get("filename") != filename:
                    errors.append(f"inventory[{index}] canonical projection mismatch")
                if item.get("present") is False and item.get("sha256") is not None:
                    errors.append(f"inventory[{index}] missing file must not carry sha256")
                if item.get("present") is True and not isinstance(item.get("sha256"), str):
                    errors.append(f"inventory[{index}] present file must carry sha256")

        package_complete = bool(inventory) and all(
            isinstance(item, dict) and item.get("present") is True and isinstance(item.get("sha256"), str)
            for item in inventory
        )
        inventory_blockers = [
            f"EVIDENCE_FILE_MISSING:{key.upper()}"
            for item, (key, _) in zip(inventory, EXPECTED_FILES)
            if isinstance(item, dict) and item.get("present") is False
        ]
        recorded_complete = report.get("package_complete") is True
        if recorded_complete != package_complete:
            errors.append("package_complete projection mismatch")

        source_replay = report.get("source_replay") if isinstance(report.get("source_replay"), dict) else {}
        pilot_review = report.get("pilot_review") if isinstance(report.get("pilot_review"), dict) else {}
        if recorded_complete and source_replay.get("attempted") is not True:
            errors.append("complete package must attempt source replay")
        if not recorded_complete and source_replay.get("attempted") is not False:
            errors.append("incomplete package must not attempt source replay")
        if source_replay.get("verified") is True and source_replay.get("error_codes"):
            errors.append("verified source replay must not carry errors")
        if source_replay.get("verified") is True and pilot_review.get("attempted") is not True:
            errors.append("verified source replay requires pilot review")

        expected_status, expected_blockers, expected_next = _decision(
            package_complete=recorded_complete,
            inventory_blockers=inventory_blockers,
            source_replay=source_replay,
            pilot_review=pilot_review,
        )
        if report.get("status") != expected_status:
            errors.append("status projection mismatch")
        if report.get("blockers") != expected_blockers:
            errors.append("blockers projection mismatch")
        if report.get("next_step") != expected_next:
            errors.append("next_step projection mismatch")
        if report.get("status") == ELIGIBLE_STATUS and report.get("pilot_authorized") is not False:
            errors.append("eligibility must not authorize pilot")

        snapshot = canonical_json_sha256(_snapshot_payload(report))
        if report.get("evidence_snapshot_sha256") != snapshot:
            errors.append("evidence_snapshot_sha256 mismatch")
        if report.get("run_id") != _run_id(report, snapshot):
            errors.append("run_id mismatch")
        if report.get("report_sha256") != canonical_json_sha256(_report_payload(report)):
            errors.append("report_sha256 mismatch")
    except (KeyError, TypeError, ValueError, PilotEvidenceRunError) as exc:
        errors.append(f"report structure invalid: {exc}")
    return sorted(set(errors))


def verify_pilot_evidence_run_report_sources(
    report: dict[str, Any],
    *,
    evidence_root: str | Path,
) -> list[str]:
    errors = verify_pilot_evidence_run_report_data(report)
    if errors:
        return errors
    try:
        replay = run_r0_pilot_evidence(evidence_root, generated_at=report["generated_at"])
    except (PilotEvidenceRunError, PilotEvidenceRunVerificationError, OSError, ValueError) as exc:
        return [f"source replay failed: {type(exc).__name__}"]
    fields = (
        "project_id",
        "package_contract",
        "inventory",
        "package_complete",
        "source_replay",
        "pilot_review",
        "blockers",
        "status",
        "next_step",
        "evidence_snapshot_sha256",
        "run_id",
        "report_sha256",
    )
    return [f"source replay {field} mismatch" for field in fields if replay.get(field) != report.get(field)]


def load_pilot_evidence_run_report(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise PilotEvidenceRunError(f"report path must not contain symlinks: {source}")
    try:
        source = source.resolve(strict=True)
    except OSError as exc:
        raise PilotEvidenceRunError(f"report not found: {source}") from exc
    if not source.is_file():
        raise PilotEvidenceRunError(f"report must be a regular file: {source}")
    try:
        value = load_data(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PilotEvidenceRunError(f"cannot load evidence run report: {type(exc).__name__}") from exc
    errors = verify_pilot_evidence_run_report_data(value)
    if errors:
        raise PilotEvidenceRunVerificationError(errors)
    return source, value


def write_pilot_evidence_run_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_pilot_evidence_run_report_data(report)
    if errors:
        raise PilotEvidenceRunVerificationError(errors)
    target = _safe_output(path)
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

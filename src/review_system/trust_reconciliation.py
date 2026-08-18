from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .defects import DefectRegistryError, load_defect_registry, verify_defect_registry
from .evaluation import EvaluationError, load_evaluation_report
from .identity import canonical_json_sha256, file_sha256
from .io import load_data
from .ledger import verify_ledger
from .paths import asset
from .trust import TrustError, TrustVerificationError, load_trust_report, verify_trust_report_sources
from .trust_comparison import TrustComparisonError, TrustComparisonVerificationError, load_registry


SCHEMA_VERSION = "1.0"
MODE = "REPORT_ONLY"
CONCLUSIVE_VERDICTS = {"SAFE", "UNSAFE"}
UNSUPPORTED_AUTHORITIES = {"REGRESSION", "SECURITY_INCIDENT", "FALSE_POSITIVE_REVIEW"}
DEFECT_UNSAFE_STATUSES = {
    "REPRODUCED", "CLASSIFIED", "RULE_CANDIDATE", "MITIGATED",
    "VERIFIED", "CLOSED", "REOPENED",
}


class TrustReconciliationError(RuntimeError):
    pass


class TrustReconciliationVerificationError(TrustReconciliationError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid Trust reconciliation report: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustReconciliationError(f"{field} must be a non-empty timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustReconciliationError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise TrustReconciliationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _before_or_equal(value: Any, limit: str) -> bool:
    left = _as_datetime(value)
    right = _as_datetime(limit)
    return left is not None and right is not None and left <= right


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_input(path: str | Path, field: str) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise TrustReconciliationError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise TrustReconciliationError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise TrustReconciliationError(f"{field} must be a regular file: {resolved}")
    return resolved


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise TrustReconciliationError(f"output path must not contain symlinks: {target}")
    return target.resolve()


def _schema_errors(schema_name: str, value: Any) -> list[str]:
    schema = load_data(asset(f"schemas/{schema_name}"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _relative_ref(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustReconciliationError(f"{field} must be a non-empty relative path")
    raw = value.strip().replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise TrustReconciliationError(f"{field} must be relative to the source manifest")
    path = PurePosixPath(raw)
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise TrustReconciliationError(f"{field} contains unsafe traversal")
    return PurePosixPath(*parts).as_posix()


def _resolve_ref(root: Path, value: str, field: str) -> Path | None:
    relative = _relative_ref(value, field)
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    if _path_has_symlink(candidate):
        raise TrustReconciliationError(f"{field} must not traverse symlinks: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    if not resolved.is_file():
        return None
    return resolved


def _normalize_manifest(data: Any) -> dict[str, Any]:
    errors = _schema_errors("trust-reconciliation-sources.schema.json", data)
    if errors:
        raise TrustReconciliationError("invalid Trust reconciliation source manifest: " + "; ".join(errors))
    assert isinstance(data, dict)
    assessment_ids: set[str] = set()
    assessments: list[dict[str, Any]] = []
    for index, item in enumerate(data["assessment_sources"]):
        assessment_id = str(item["assessment_id"]).strip()
        if assessment_id in assessment_ids:
            raise TrustReconciliationError(f"duplicate assessment source: {assessment_id}")
        assessment_ids.add(assessment_id)
        normalized = {
            "assessment_id": assessment_id,
            "trust_report": _relative_ref(item["trust_report"], f"assessment_sources[{index}].trust_report"),
            "request": _relative_ref(item["request"], f"assessment_sources[{index}].request"),
            "profile": _relative_ref(item["profile"], f"assessment_sources[{index}].profile"),
        }
        for field in ("ledger", "policy_registry", "evaluation_report", "reground_report", "reground_observations"):
            value = item.get(field)
            normalized[field] = None if value is None else _relative_ref(value, f"assessment_sources[{index}].{field}")
        assessments.append(normalized)
    event_ids: set[str] = set()
    outcomes: list[dict[str, Any]] = []
    for index, item in enumerate(data["outcome_sources"]):
        event_id = str(item["event_id"]).strip()
        if event_id in event_ids:
            raise TrustReconciliationError(f"duplicate Outcome source: {event_id}")
        event_ids.add(event_id)
        authority_type = item["authority_type"]
        normalized = {"event_id": event_id, "authority_type": authority_type}
        if authority_type == "PRODUCTION_DEFECT":
            normalized["defect_registry"] = _relative_ref(item["defect_registry"], f"outcome_sources[{index}].defect_registry")
            normalized["ledger"] = _relative_ref(item["ledger"], f"outcome_sources[{index}].ledger")
        else:
            normalized["evaluation_report"] = _relative_ref(item["evaluation_report"], f"outcome_sources[{index}].evaluation_report")
        outcomes.append(normalized)
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": str(data["project_id"]).strip(),
        "assessment_sources": sorted(assessments, key=lambda item: item["assessment_id"]),
        "outcome_sources": sorted(outcomes, key=lambda item: item["event_id"]),
    }


def load_source_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "Trust reconciliation source manifest")
    try:
        data = load_data(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TrustReconciliationError(f"cannot load Trust reconciliation source manifest: {exc}") from exc
    return source, _normalize_manifest(data)


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return canonical_json_sha256(_normalize_manifest(manifest))


def _source_descriptor(path: Path | None, reference: str | None) -> dict[str, Any] | None:
    if reference is None:
        return None
    return {"source": reference, "file_sha256": file_sha256(path) if path is not None else None}


def _assessment_status(checks: dict[str, bool]) -> str:
    if not checks.get("source_present", False):
        return "SOURCE_MISSING"
    if not checks.get("semantic_valid", False):
        return "SOURCE_VERIFICATION_FAILED"
    if not checks.get("report_id_match", False):
        return "REPORT_ID_MISMATCH"
    if not checks.get("report_hash_match", False):
        return "SOURCE_HASH_MISMATCH"
    if not checks.get("project_match", False):
        return "PROJECT_MISMATCH"
    if not checks.get("task_match", False):
        return "TASK_MISMATCH"
    if not checks.get("revision_match", False):
        return "REVISION_MISMATCH"
    if not all(checks.get(field, False) for field in ("risk_match", "hard_gates_match", "readiness_match")):
        return "PROJECTION_MISMATCH"
    if not checks.get("source_replay_match", False):
        return "SOURCE_REPLAY_FAILED"
    return "RECONCILED"


def _assessment_reconciliation(
    assessment: dict[str, Any], source_entry: dict[str, Any] | None, root: Path, project_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    checks = {
        "source_present": False,
        "semantic_valid": False,
        "report_id_match": False,
        "report_hash_match": False,
        "project_match": False,
        "task_match": False,
        "revision_match": False,
        "risk_match": False,
        "hard_gates_match": False,
        "readiness_match": False,
        "source_replay_match": False,
    }
    reasons: list[str] = []
    report: dict[str, Any] | None = None
    descriptor = None
    if source_entry is not None:
        trust_path = _resolve_ref(root, source_entry["trust_report"], "assessment trust_report")
        descriptor = _source_descriptor(trust_path, source_entry["trust_report"])
        checks["source_present"] = trust_path is not None
        if trust_path is not None:
            try:
                _, report = load_trust_report(trust_path)
                checks["semantic_valid"] = True
            except (TrustError, TrustVerificationError, OSError, ValueError) as exc:
                reasons.append(f"TRUST_REPORT_INVALID:{type(exc).__name__}")
    if report is not None:
        request = report.get("request") if isinstance(report.get("request"), dict) else {}
        risk = report.get("risk") if isinstance(report.get("risk"), dict) else {}
        advisory = report.get("task_advisory") if isinstance(report.get("task_advisory"), dict) else {}
        readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
        checks.update({
            "report_id_match": report.get("report_id") == assessment.get("trust_report_id"),
            "report_hash_match": report.get("report_sha256") == assessment.get("trust_report_sha256"),
            "project_match": report.get("project_id") == project_id,
            "task_match": request.get("task_id") == assessment.get("task_id"),
            "revision_match": request.get("source_revision") == assessment.get("source_revision"),
            "risk_match": risk.get("effective_band") == assessment.get("predicted_risk_band"),
            "hard_gates_match": sorted(advisory.get("triggered_hard_gates", [])) == sorted(assessment.get("triggered_hard_gates", [])),
            "readiness_match": readiness.get("status") == assessment.get("readiness_status"),
        })
        assert source_entry is not None
        paths: dict[str, Path | None] = {}
        for field in ("request", "profile", "ledger", "policy_registry", "evaluation_report", "reground_report", "reground_observations"):
            reference = source_entry.get(field)
            paths[field] = None if reference is None else _resolve_ref(root, reference, f"assessment {field}")
        missing = [field for field in ("request", "profile") if paths[field] is None]
        missing += [
            field for field in ("ledger", "policy_registry", "evaluation_report", "reground_report", "reground_observations")
            if source_entry.get(field) is not None and paths[field] is None
        ]
        if missing:
            reasons.extend(f"SOURCE_MISSING:{field}" for field in missing)
        else:
            replay_errors = verify_trust_report_sources(
                report,
                request=paths["request"],
                profile=paths["profile"],
                ledger=paths["ledger"],
                policy_registry=paths["policy_registry"],
                evaluation_report=paths["evaluation_report"],
                reground_report=paths["reground_report"],
                reground_observations=paths["reground_observations"],
            )
            checks["source_replay_match"] = not replay_errors
            reasons.extend(f"SOURCE_REPLAY:{error}" for error in replay_errors)
    status = _assessment_status(checks)
    return ({
        "assessment_id": assessment["assessment_id"],
        "trust_report_id": assessment["trust_report_id"],
        "trust_report_sha256": assessment["trust_report_sha256"],
        "status": status,
        "reconciled": status == "RECONCILED",
        "checks": checks,
        "reason_codes": sorted(set(reasons)),
        "source": descriptor,
    }, report)


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _defect_status_as_of(registry: dict[str, Any], defect_id: str, occurred_at: str) -> str | None:
    status = None
    for item in sorted(registry.get("events", []), key=lambda value: (value.get("occurred_at", ""), value.get("event_id", ""))):
        if item.get("defect_id") != defect_id or not _before_or_equal(item.get("occurred_at"), occurred_at):
            continue
        status_to = item.get("status_to")
        if isinstance(status_to, str) and status_to:
            status = status_to
    return status


def _defect_outcome(
    event: dict[str, Any], assessment: dict[str, Any], source_entry: dict[str, Any], root: Path, project_id: str,
) -> tuple[str, dict[str, bool], list[str], str | None, dict[str, Any] | None]:
    checks = {
        "source_present": False,
        "registry_valid": False,
        "ledger_valid": False,
        "project_match": False,
        "registry_ledger_match": False,
        "defect_present": False,
        "defect_projection_match": False,
        "revision_relation_match": False,
        "lifecycle_sufficient": False,
        "supporting_artifact_present": False,
        "supporting_evidence_precedes_outcome": False,
        "verdict_supported": False,
    }
    reasons: list[str] = []
    registry_path = _resolve_ref(root, source_entry["defect_registry"], "Outcome defect_registry")
    ledger_path = _resolve_ref(root, source_entry["ledger"], "Outcome ledger")
    checks["source_present"] = registry_path is not None and ledger_path is not None
    if not checks["source_present"]:
        return "SOURCE_MISSING", checks, reasons, None, None
    assert registry_path is not None and ledger_path is not None
    try:
        _, registry = load_defect_registry(registry_path)
        checks["registry_valid"] = True
    except (DefectRegistryError, OSError, ValueError) as exc:
        reasons.append(f"DEFECT_REGISTRY_INVALID:{type(exc).__name__}")
        return "SOURCE_VERIFICATION_FAILED", checks, reasons, None, None
    ledger_result = verify_ledger(ledger_path)
    checks["ledger_valid"] = bool(ledger_result.get("valid"))
    if not checks["ledger_valid"]:
        reasons.extend(f"LEDGER:{error}" for error in ledger_result.get("errors", []))
        return "SOURCE_VERIFICATION_FAILED", checks, reasons, None, None
    checks["project_match"] = registry.get("project_id") == project_id
    if not checks["project_match"]:
        return "PROJECT_MISMATCH", checks, reasons, None, None
    registry_verification = verify_defect_registry(ledger_path, registry_path)
    checks["registry_ledger_match"] = bool(registry_verification.get("valid"))
    if not checks["registry_ledger_match"]:
        reasons.extend(f"DEFECT_LEDGER:{error}" for error in registry_verification.get("errors", []))
        return "SOURCE_HASH_MISMATCH", checks, reasons, None, None
    defect_id = event.get("payload", {}).get("defect_id")
    if not isinstance(defect_id, str) or not defect_id.strip():
        reasons.append("DEFECT_ID_MISSING")
        return "OUTCOME_REFERENCE_MISMATCH", checks, reasons, None, None
    defect = next((item for item in registry.get("defects", []) if item.get("defect_id") == defect_id), None)
    checks["defect_present"] = defect is not None
    if defect is None:
        return "OUTCOME_REFERENCE_MISMATCH", checks, reasons, None, None
    occurred_at = event["occurred_at"]
    status_as_of = _defect_status_as_of(registry, defect_id, occurred_at)
    eligible_finding_ids = {
        item["finding_id"] for item in registry.get("finding_links", [])
        if item.get("defect_id") == defect_id and _before_or_equal(item.get("linked_at"), occurred_at)
    }
    eligible_artifact_links = [
        item for item in registry.get("artifact_links", [])
        if item.get("defect_id") == defect_id
        and item.get("relation") in {"reproducer", "diagnostic"}
        and _before_or_equal(item.get("linked_at"), occurred_at)
    ]
    same_revision_findings: list[str] = []
    same_revision_artifacts: list[str] = []
    stored_defect = None
    try:
        with _read_only_connection(ledger_path) as connection:
            stored = connection.execute("SELECT * FROM defects WHERE defect_id = ?", (defect_id,)).fetchone()
            stored_defect = dict(stored) if stored is not None else None
            if eligible_finding_ids:
                placeholders = ",".join("?" for _ in eligible_finding_ids)
                rows = connection.execute(
                    f"""
                    SELECT DISTINCT f.finding_id
                    FROM findings f JOIN runs r ON r.run_id = f.run_id
                    WHERE f.finding_id IN ({placeholders})
                      AND r.project_id = ? AND r.source_revision = ?
                    """,
                    (*sorted(eligible_finding_ids), project_id, assessment["source_revision"]),
                ).fetchall()
                same_revision_findings = [str(row["finding_id"]) for row in rows]
            for link in eligible_artifact_links:
                row = connection.execute(
                    """
                    SELECT a.artifact_id
                    FROM artifacts a JOIN runs r ON r.run_id = a.run_id
                    WHERE a.artifact_id = ? AND r.project_id = ? AND r.source_revision = ?
                    """,
                    (link["artifact_id"], project_id, assessment["source_revision"]),
                ).fetchone()
                if row is not None:
                    same_revision_artifacts.append(str(row["artifact_id"]))
    except sqlite3.DatabaseError as exc:
        reasons.append(f"LEDGER_QUERY:{exc}")
        return "SOURCE_VERIFICATION_FAILED", checks, reasons, None, None
    if stored_defect is not None:
        compared_fields = (
            "defect_id", "defect_key_sha256", "signature", "title", "category", "root_cause",
            "lifecycle_status", "first_seen_run_id", "last_seen_run_id", "owner", "resolution",
            "created_at", "updated_at",
        )
        checks["defect_projection_match"] = all(stored_defect.get(field) == defect.get(field) for field in compared_fields)
        checks["defect_projection_match"] = checks["defect_projection_match"] and stored_defect.get("project_id") == project_id
    checks["revision_relation_match"] = bool(same_revision_findings)
    checks["lifecycle_sufficient"] = status_as_of in DEFECT_UNSAFE_STATUSES
    checks["supporting_artifact_present"] = bool(same_revision_artifacts)
    checks["supporting_evidence_precedes_outcome"] = bool(same_revision_artifacts)
    verdict = event["payload"]["verdict"]
    if verdict == "UNSAFE":
        checks["verdict_supported"] = all([
            checks["defect_projection_match"], checks["revision_relation_match"], checks["lifecycle_sufficient"],
            checks["supporting_artifact_present"], checks["supporting_evidence_precedes_outcome"],
        ])
    elif verdict == "INCONCLUSIVE":
        checks["verdict_supported"] = checks["defect_projection_match"] and checks["revision_relation_match"]
    else:
        reasons.append("PRODUCTION_DEFECT_CANNOT_PROVE_SAFE")
    authority_key = f"defect:{registry['registry_sha256']}:{defect_id}"
    authority = {
        "authority_type": "PRODUCTION_DEFECT",
        "defect_id": defect_id,
        "registry_sha256": registry["registry_sha256"],
        "lifecycle_status": status_as_of,
        "revision_run_count": len(same_revision_findings),
        "supporting_artifact_count": len(same_revision_artifacts),
    }
    if verdict == "SAFE":
        return "OUTCOME_VERDICT_MISMATCH", checks, reasons, authority_key, authority
    if not checks["defect_projection_match"]:
        return "SOURCE_HASH_MISMATCH", checks, reasons, authority_key, authority
    if not checks["revision_relation_match"]:
        return "REVISION_MISMATCH", checks, reasons, authority_key, authority
    if not checks["verdict_supported"]:
        return "INSUFFICIENT_EVIDENCE", checks, reasons, authority_key, authority
    return "RECONCILED", checks, reasons, authority_key, authority


def _evaluation_outcome(
    event: dict[str, Any], assessment: dict[str, Any], assessment_report: dict[str, Any] | None,
    source_entry: dict[str, Any], root: Path,
) -> tuple[str, dict[str, bool], list[str], str | None, dict[str, Any] | None]:
    checks = {
        "source_present": False,
        "evaluation_valid": False,
        "outcome_reference_match": False,
        "trust_evaluation_match": False,
        "revision_match": False,
        "unambiguous_case": False,
        "repeatability": False,
        "holdout_match": False,
        "protected_negative_match": False,
        "gate_pass": False,
        "zero_protected_negative_regressions": False,
        "verdict_supported": False,
    }
    reasons: list[str] = []
    path = _resolve_ref(root, source_entry["evaluation_report"], "Outcome evaluation_report")
    checks["source_present"] = path is not None
    if path is None:
        return "SOURCE_MISSING", checks, reasons, None, None
    try:
        _, evaluation = load_evaluation_report(path)
        checks["evaluation_valid"] = True
    except (EvaluationError, OSError, ValueError) as exc:
        reasons.append(f"EVALUATION_INVALID:{type(exc).__name__}")
        return "SOURCE_VERIFICATION_FAILED", checks, reasons, None, None
    refs = set(event.get("payload", {}).get("evidence_refs", []))
    checks["outcome_reference_match"] = evaluation["evaluation_id"] in refs or evaluation["report_sha256"] in refs
    trust_policy: dict[str, Any] = {}
    if isinstance(assessment_report, dict):
        evidence = assessment_report.get("evidence")
        if isinstance(evidence, dict) and isinstance(evidence.get("policy"), dict):
            trust_policy = evidence["policy"]
    checks["trust_evaluation_match"] = bool(
        trust_policy.get("evaluation_available")
        and trust_policy.get("evaluation_id") == evaluation["evaluation_id"]
        and trust_policy.get("evaluation_report_sha256") == evaluation["report_sha256"]
    )
    matching_cases = [case for case in evaluation.get("cases", []) if case.get("source_revision") == assessment["source_revision"]]
    matching_holdout = [case for case in matching_cases if case.get("split") == "holdout"]
    checks["revision_match"] = bool(matching_cases)
    checks["unambiguous_case"] = len(matching_holdout) == 1
    checks["holdout_match"] = len(matching_holdout) == 1
    checks["repeatability"] = bool(evaluation["repeatability"].get("baseline") and evaluation["repeatability"].get("challenger"))
    case = matching_holdout[0] if len(matching_holdout) == 1 else None
    negative_ids = set(evaluation["comparison"].get("protected_negative_regressions", []))
    checks["protected_negative_match"] = bool(case and case.get("case_id") in negative_ids)
    checks["gate_pass"] = evaluation["gate"].get("decision") == "PASS"
    checks["zero_protected_negative_regressions"] = not negative_ids
    verdict = event["payload"]["verdict"]
    if verdict == "SAFE":
        checks["verdict_supported"] = all([
            checks["outcome_reference_match"], checks["trust_evaluation_match"], checks["unambiguous_case"],
            checks["repeatability"], checks["holdout_match"], checks["gate_pass"], checks["zero_protected_negative_regressions"],
        ])
    elif verdict == "UNSAFE":
        checks["verdict_supported"] = all([
            checks["outcome_reference_match"], checks["trust_evaluation_match"], checks["unambiguous_case"],
            checks["repeatability"], checks["holdout_match"], checks["protected_negative_match"],
        ])
    else:
        unique = matching_holdout[0] if len(matching_holdout) == 1 else (matching_cases[0] if len(matching_cases) == 1 else None)
        case = unique
        checks["unambiguous_case"] = unique is not None
        checks["verdict_supported"] = all([
            checks["outcome_reference_match"], checks["trust_evaluation_match"], checks["revision_match"],
            checks["unambiguous_case"], checks["repeatability"],
        ])
    case_id = case.get("case_id") if case else None
    authority_key = f"evaluation:{evaluation['report_sha256']}:{case_id}" if case_id else None
    authority = {
        "authority_type": "CONTROLLED_EVALUATION",
        "evaluation_id": evaluation["evaluation_id"],
        "report_sha256": evaluation["report_sha256"],
        "case_id": case_id,
        "case_split": case.get("split") if case else None,
        "gate_decision": evaluation["gate"]["decision"],
        "protected_negative_match": checks["protected_negative_match"],
    }
    if not checks["outcome_reference_match"]:
        return "OUTCOME_REFERENCE_MISMATCH", checks, reasons, authority_key, authority
    if not checks["trust_evaluation_match"]:
        return "PROJECT_MISMATCH", checks, reasons, authority_key, authority
    if not checks["revision_match"]:
        return "REVISION_MISMATCH", checks, reasons, authority_key, authority
    if not checks["unambiguous_case"]:
        return "AMBIGUOUS_AUTHORITY", checks, reasons, authority_key, authority
    if verdict in CONCLUSIVE_VERDICTS and not checks["holdout_match"]:
        return "INSUFFICIENT_EVIDENCE", checks, reasons, authority_key, authority
    if not checks["verdict_supported"]:
        return "OUTCOME_VERDICT_MISMATCH" if verdict in CONCLUSIVE_VERDICTS else "INSUFFICIENT_EVIDENCE", checks, reasons, authority_key, authority
    return "RECONCILED", checks, reasons, authority_key, authority


def _outcome_reconciliation(
    event: dict[str, Any], assessment: dict[str, Any], assessment_result: dict[str, Any],
    assessment_report: dict[str, Any] | None, source_entry: dict[str, Any] | None, root: Path, project_id: str,
) -> dict[str, Any]:
    outcome_type = event["payload"]["outcome_type"]
    verdict = event["payload"]["verdict"]
    reasons: list[str] = []
    authority_key = None
    authority = None
    if not assessment_result["reconciled"]:
        base_status = "ASSESSMENT_UNRECONCILED"
        checks = {"assessment_reconciled": False}
    elif outcome_type == "INDEPENDENT_AUDIT":
        base_status = "PROVENANCE_UNVERIFIED"
        checks = {"assessment_reconciled": True, "independent_provenance_verified": False}
        reasons.append("NO_INDEPENDENT_AUDIT_AUTHORITY_CONTRACT")
    elif outcome_type in UNSUPPORTED_AUTHORITIES:
        base_status = "UNSUPPORTED_SOURCE"
        checks = {"assessment_reconciled": True, "authority_supported": False}
        reasons.append(f"NO_{outcome_type}_AUTHORITY_CONTRACT")
    elif source_entry is None:
        base_status = "SOURCE_MISSING"
        checks = {"assessment_reconciled": True, "source_present": False}
    elif source_entry.get("authority_type") != outcome_type:
        base_status = "OUTCOME_REFERENCE_MISMATCH"
        checks = {"assessment_reconciled": True, "authority_type_match": False}
    elif outcome_type == "PRODUCTION_DEFECT":
        base_status, checks, reasons, authority_key, authority = _defect_outcome(event, assessment, source_entry, root, project_id)
        checks = {"assessment_reconciled": True, **checks}
    elif outcome_type == "CONTROLLED_EVALUATION":
        base_status, checks, reasons, authority_key, authority = _evaluation_outcome(event, assessment, assessment_report, source_entry, root)
        checks = {"assessment_reconciled": True, **checks}
    else:
        base_status = "UNSUPPORTED_SOURCE"
        checks = {"assessment_reconciled": True, "authority_supported": False}
    return {
        "event_id": event["event_id"],
        "assessment_id": event["assessment_id"],
        "outcome_type": outcome_type,
        "verdict": verdict,
        "conclusive": verdict in CONCLUSIVE_VERDICTS,
        "base_status": base_status,
        "status": base_status,
        "reconciled": base_status == "RECONCILED",
        "checks": checks,
        "reason_codes": sorted(set(reasons)),
        "authority_key": authority_key,
        "authority": authority,
    }


def _expected_outcome_base_status(item: dict[str, Any]) -> str:
    checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
    outcome_type = item.get("outcome_type")
    verdict = item.get("verdict")
    if not checks.get("assessment_reconciled", False):
        return "ASSESSMENT_UNRECONCILED"
    if outcome_type == "INDEPENDENT_AUDIT":
        return "RECONCILED" if checks.get("independent_provenance_verified", False) else "PROVENANCE_UNVERIFIED"
    if outcome_type in UNSUPPORTED_AUTHORITIES:
        return "RECONCILED" if checks.get("authority_supported", False) else "UNSUPPORTED_SOURCE"
    if outcome_type == "PRODUCTION_DEFECT":
        if not checks.get("source_present", False):
            return "SOURCE_MISSING"
        if not checks.get("registry_valid", False) or not checks.get("ledger_valid", False):
            return "SOURCE_VERIFICATION_FAILED"
        if not checks.get("project_match", False):
            return "PROJECT_MISMATCH"
        if not checks.get("registry_ledger_match", False):
            return "SOURCE_HASH_MISMATCH"
        if not checks.get("defect_present", False):
            return "OUTCOME_REFERENCE_MISMATCH"
        if not checks.get("defect_projection_match", False):
            return "SOURCE_HASH_MISMATCH"
        if not checks.get("revision_relation_match", False):
            return "REVISION_MISMATCH"
        if verdict == "SAFE":
            return "OUTCOME_VERDICT_MISMATCH"
        return "RECONCILED" if checks.get("verdict_supported", False) else "INSUFFICIENT_EVIDENCE"
    if outcome_type == "CONTROLLED_EVALUATION":
        if not checks.get("source_present", False):
            return "SOURCE_MISSING"
        if not checks.get("evaluation_valid", False):
            return "SOURCE_VERIFICATION_FAILED"
        if not checks.get("outcome_reference_match", False):
            return "OUTCOME_REFERENCE_MISMATCH"
        if not checks.get("trust_evaluation_match", False):
            return "PROJECT_MISMATCH"
        if not checks.get("revision_match", False):
            return "REVISION_MISMATCH"
        if not checks.get("unambiguous_case", False):
            return "AMBIGUOUS_AUTHORITY"
        if verdict in CONCLUSIVE_VERDICTS and not checks.get("holdout_match", False):
            return "INSUFFICIENT_EVIDENCE"
        if not checks.get("verdict_supported", False):
            return "OUTCOME_VERDICT_MISMATCH" if verdict in CONCLUSIVE_VERDICTS else "INSUFFICIENT_EVIDENCE"
        return "RECONCILED"
    if checks.get("authority_type_match") is False:
        return "OUTCOME_REFERENCE_MISMATCH"
    if checks.get("source_present") is False:
        return "SOURCE_MISSING"
    return "UNSUPPORTED_SOURCE"


def _apply_duplicate_authority(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = deepcopy(results)
    by_key: dict[str, list[dict[str, Any]]] = {}
    for item in output:
        key = item.get("authority_key")
        if item.get("conclusive") and item.get("base_status") == "RECONCILED" and isinstance(key, str):
            by_key.setdefault(key, []).append(item)
    duplicates = {key for key, values in by_key.items() if len(values) > 1}
    for item in output:
        expected = "DUPLICATE_AUTHORITY" if item.get("authority_key") in duplicates and item.get("conclusive") and item.get("base_status") == "RECONCILED" else item.get("base_status")
        item["status"] = expected
        item["reconciled"] = expected == "RECONCILED"
    return output


def _summary(assessments: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    conclusive = [item for item in outcomes if item.get("conclusive")]
    assessment_reconciled = sum(1 for item in assessments if item.get("reconciled"))
    conclusive_reconciled = sum(1 for item in conclusive if item.get("reconciled"))
    return {
        "assessment_count": len(assessments),
        "assessment_reconciled_count": assessment_reconciled,
        "assessment_unreconciled_count": len(assessments) - assessment_reconciled,
        "outcome_count": len(outcomes),
        "conclusive_outcome_count": len(conclusive),
        "conclusive_outcome_reconciled_count": conclusive_reconciled,
        "conclusive_outcome_unreconciled_count": len(conclusive) - conclusive_reconciled,
        "nonconclusive_outcome_count": len(outcomes) - len(conclusive),
        "unsupported_source_count": sum(1 for item in outcomes if item.get("status") == "UNSUPPORTED_SOURCE"),
        "provenance_unverified_count": sum(1 for item in outcomes if item.get("status") == "PROVENANCE_UNVERIFIED"),
        "duplicate_authority_count": sum(1 for item in outcomes if item.get("status") == "DUPLICATE_AUTHORITY"),
        "source_reconciliation_complete": assessment_reconciled == len(assessments) and conclusive_reconciled == len(conclusive),
    }


def _snapshot_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "mode": report.get("mode"),
        "automation_authorized": report.get("automation_authorized"),
        "pilot_authorized": report.get("pilot_authorized"),
        "comparison_registry": deepcopy(report.get("comparison_registry")),
        "source_manifest": deepcopy(report.get("source_manifest")),
        "assessment_reconciliation": deepcopy(report.get("assessment_reconciliation")),
        "outcome_reconciliation": deepcopy(report.get("outcome_reconciliation")),
        "summary": deepcopy(report.get("summary")),
        "status": report.get("status"),
    }


def _report_payload(report: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(report)
    payload.pop("report_sha256", None)
    return payload


def _report_id(report: dict[str, Any], snapshot_sha256: str) -> str:
    key = {
        "project_id": report.get("project_id"),
        "registry_id": report.get("comparison_registry", {}).get("registry_id"),
        "registry_sha256": report.get("comparison_registry", {}).get("registry_sha256"),
        "manifest_sha256": report.get("source_manifest", {}).get("manifest_sha256"),
        "evidence_snapshot_sha256": snapshot_sha256,
    }
    return f"trust-reconciliation-{canonical_json_sha256(key)[:32]}"


def _validate_manifest_registry_bindings(registry: dict[str, Any], manifest: dict[str, Any]) -> None:
    assessment_ids = {item["assessment_id"] for item in registry["assessments"]}
    manifest_assessments = {item["assessment_id"] for item in manifest["assessment_sources"]}
    orphan_assessments = sorted(manifest_assessments - assessment_ids)
    if orphan_assessments:
        raise TrustReconciliationError("source manifest references unknown assessment(s): " + ", ".join(orphan_assessments))
    outcomes = {event["event_id"]: event for event in registry["events"] if event["event_type"] == "OUTCOME"}
    manifest_outcomes = {item["event_id"]: item for item in manifest["outcome_sources"]}
    orphan_events = sorted(set(manifest_outcomes) - set(outcomes))
    if orphan_events:
        raise TrustReconciliationError("source manifest references unknown Outcome event(s): " + ", ".join(orphan_events))
    for event_id, source in manifest_outcomes.items():
        expected = outcomes[event_id]["payload"]["outcome_type"]
        if source["authority_type"] != expected:
            raise TrustReconciliationError(
                f"source manifest authority_type mismatch for {event_id}: expected={expected} actual={source['authority_type']}"
            )


def reconcile_sources(
    registry_path: str | Path, source_manifest_path: str | Path, *, generated_at: str | None = None,
) -> dict[str, Any]:
    registry_source = _safe_input(registry_path, "Trust comparison registry")
    _, registry = load_registry(registry_source)
    manifest_source, manifest = load_source_manifest(source_manifest_path)
    if manifest["project_id"] != registry["project_id"]:
        raise TrustReconciliationError(
            f"source manifest project_id mismatch: expected={registry['project_id']} actual={manifest['project_id']}"
        )
    _validate_manifest_registry_bindings(registry, manifest)
    root = manifest_source.parent
    assessment_entries = {item["assessment_id"]: item for item in manifest["assessment_sources"]}
    assessment_results: list[dict[str, Any]] = []
    assessment_reports: dict[str, dict[str, Any] | None] = {}
    for assessment in registry["assessments"]:
        result, trust_report = _assessment_reconciliation(
            assessment, assessment_entries.get(assessment["assessment_id"]), root, registry["project_id"]
        )
        assessment_results.append(result)
        assessment_reports[assessment["assessment_id"]] = trust_report
    assessment_results.sort(key=lambda item: item["assessment_id"])
    assessment_result_by_id = {item["assessment_id"]: item for item in assessment_results}
    assessment_by_id = {item["assessment_id"]: item for item in registry["assessments"]}
    outcome_entries = {item["event_id"]: item for item in manifest["outcome_sources"]}
    outcome_results: list[dict[str, Any]] = []
    for event in registry["events"]:
        if event["event_type"] != "OUTCOME":
            continue
        assessment = assessment_by_id[event["assessment_id"]]
        outcome_results.append(_outcome_reconciliation(
            event,
            assessment,
            assessment_result_by_id[event["assessment_id"]],
            assessment_reports[event["assessment_id"]],
            outcome_entries.get(event["event_id"]),
            root,
            registry["project_id"],
        ))
    outcome_results.sort(key=lambda item: item["event_id"])
    outcome_results = _apply_duplicate_authority(outcome_results)
    summary = _summary(assessment_results, outcome_results)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "",
        "project_id": registry["project_id"],
        "generated_at": _timestamp(generated_at or utc_now(), "generated_at"),
        "mode": MODE,
        "automation_authorized": False,
        "pilot_authorized": False,
        "comparison_registry": {
            "source": registry_source.name,
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
            "file_sha256": file_sha256(registry_source),
        },
        "source_manifest": {
            "source": manifest_source.name,
            "manifest_sha256": canonical_json_sha256(manifest),
            "assessment_source_count": len(manifest["assessment_sources"]),
            "outcome_source_count": len(manifest["outcome_sources"]),
        },
        "assessment_reconciliation": assessment_results,
        "outcome_reconciliation": outcome_results,
        "summary": summary,
        "status": "RECONCILED" if summary["source_reconciliation_complete"] else "UNRECONCILED",
        "evidence_snapshot_sha256": "",
        "report_sha256": "",
    }
    report["evidence_snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(report))
    report["report_id"] = _report_id(report, report["evidence_snapshot_sha256"])
    report["report_sha256"] = canonical_json_sha256(_report_payload(report))
    errors = verify_reconciliation_report_data(report)
    if errors:
        raise TrustReconciliationVerificationError(errors)
    return report


def verify_reconciliation_report_data(report: Any) -> list[str]:
    errors = _schema_errors("trust-reconciliation-report.schema.json", report)
    if not isinstance(report, dict):
        return sorted(set(errors or ["report must contain an object"]))
    try:
        if report.get("mode") != MODE:
            errors.append("mode must remain REPORT_ONLY")
        if report.get("automation_authorized") is not False:
            errors.append("automation_authorized must remain false")
        if report.get("pilot_authorized") is not False:
            errors.append("pilot_authorized must remain false")
        assessments = report.get("assessment_reconciliation") if isinstance(report.get("assessment_reconciliation"), list) else []
        if assessments != sorted(assessments, key=lambda item: item.get("assessment_id", "")):
            errors.append("assessment_reconciliation canonical order mismatch")
        assessment_ids: set[str] = set()
        for index, item in enumerate(assessments):
            if not isinstance(item, dict):
                continue
            identifier = item.get("assessment_id")
            if identifier in assessment_ids:
                errors.append(f"duplicate assessment reconciliation: {identifier}")
            assessment_ids.add(identifier)
            expected_status = _assessment_status(item.get("checks", {}))
            if item.get("status") != expected_status:
                errors.append(f"assessment_reconciliation[{index}] status projection mismatch")
            if item.get("reconciled") is not (expected_status == "RECONCILED"):
                errors.append(f"assessment_reconciliation[{index}] reconciled projection mismatch")
        outcomes = report.get("outcome_reconciliation") if isinstance(report.get("outcome_reconciliation"), list) else []
        if outcomes != sorted(outcomes, key=lambda item: item.get("event_id", "")):
            errors.append("outcome_reconciliation canonical order mismatch")
        event_ids: set[str] = set()
        projected: list[dict[str, Any]] = []
        for index, item in enumerate(outcomes):
            if not isinstance(item, dict):
                continue
            identifier = item.get("event_id")
            if identifier in event_ids:
                errors.append(f"duplicate Outcome reconciliation: {identifier}")
            event_ids.add(identifier)
            expected_conclusive = item.get("verdict") in CONCLUSIVE_VERDICTS
            if item.get("conclusive") is not expected_conclusive:
                errors.append(f"outcome_reconciliation[{index}] conclusive projection mismatch")
            expected_base = _expected_outcome_base_status(item)
            if item.get("base_status") != expected_base:
                errors.append(f"outcome_reconciliation[{index}] base_status projection mismatch")
            normalized = deepcopy(item)
            normalized["base_status"] = expected_base
            normalized["status"] = expected_base
            normalized["reconciled"] = expected_base == "RECONCILED"
            projected.append(normalized)
        expected_outcomes = _apply_duplicate_authority(projected)
        if len(expected_outcomes) == len(outcomes):
            for index, (recorded, expected) in enumerate(zip(outcomes, expected_outcomes)):
                if recorded.get("status") != expected.get("status"):
                    errors.append(f"outcome_reconciliation[{index}] status projection mismatch")
                if recorded.get("reconciled") is not expected.get("reconciled"):
                    errors.append(f"outcome_reconciliation[{index}] reconciled projection mismatch")
        expected_summary = _summary(assessments, expected_outcomes)
        if report.get("summary") != expected_summary:
            errors.append("summary projection mismatch")
        expected_status = "RECONCILED" if expected_summary["source_reconciliation_complete"] else "UNRECONCILED"
        if report.get("status") != expected_status:
            errors.append("status projection mismatch")
        expected_snapshot = canonical_json_sha256(_snapshot_payload(report))
        if report.get("evidence_snapshot_sha256") != expected_snapshot:
            errors.append("evidence_snapshot_sha256 mismatch")
        expected_id = _report_id(report, expected_snapshot)
        if report.get("report_id") != expected_id:
            errors.append("report_id mismatch")
        expected_hash = canonical_json_sha256(_report_payload(report))
        if report.get("report_sha256") != expected_hash:
            errors.append("report_sha256 mismatch")
    except (KeyError, TypeError, ValueError, TrustReconciliationError) as exc:
        errors.append(f"report structure invalid: {exc}")
    return sorted(set(errors))


def load_reconciliation_report(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input(path, "Trust reconciliation report")
    try:
        value = load_data(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TrustReconciliationError(f"cannot load Trust reconciliation report: {exc}") from exc
    errors = verify_reconciliation_report_data(value)
    if errors:
        raise TrustReconciliationVerificationError(errors)
    return source, value


def verify_reconciliation_report_sources(
    report: dict[str, Any], *, registry_path: str | Path, source_manifest_path: str | Path,
) -> list[str]:
    errors = verify_reconciliation_report_data(report)
    if errors:
        return errors
    try:
        replay = reconcile_sources(registry_path, source_manifest_path, generated_at=report["generated_at"])
    except (TrustReconciliationError, TrustComparisonError, TrustComparisonVerificationError, OSError, ValueError) as exc:
        return [f"source replay failed: {exc}"]
    output: list[str] = []
    for field in (
        "comparison_registry", "source_manifest", "assessment_reconciliation", "outcome_reconciliation",
        "summary", "status", "evidence_snapshot_sha256", "report_id", "report_sha256",
    ):
        if replay.get(field) != report.get(field):
            output.append(f"source replay {field} mismatch")
    return output


def write_reconciliation_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_reconciliation_report_data(report)
    if errors:
        raise TrustReconciliationVerificationError(errors)
    target = _safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target

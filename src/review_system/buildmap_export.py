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
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .intelligence_config import normalize_path
from .io import load_data
from .ledger import verify_ledger
from .paths import asset


BUILDMAP_EXPORT_SCHEMA_VERSION = "1.0"
BUILDMAP_REDACTION_POLICY_ID = "buildmap-default-1"
_ALLOWED_SOURCE_SCHEMES = {"github", "review", "pie"}
_RAW_GITHUB_PATHS = {
    "github-source.json",
    "github-discussions.json",
    "github-discussion.json",
    "issue-comments.json",
    "review-comments.json",
    "reviews.json",
    "comments.json",
}
_SENSITIVE_SUFFIXES = {".patch", ".diff", ".log", ".pem", ".key"}
_SENSITIVE_TOKENS = {"secret", "credential", "credentials", "token"}


class BuildMapExportError(RuntimeError):
    pass


class BuildMapExportVerificationError(BuildMapExportError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        super().__init__("invalid BuildMap export: " + "; ".join(self.errors))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BuildMapExportError(f"{field} must be a non-empty timestamp")
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BuildMapExportError(f"{field} must be an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise BuildMapExportError(f"{field} must include a timezone")
    return parsed.isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    candidate = path.absolute()
    parts = candidate.parts
    if not parts:
        return False
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        if current.exists() and current.is_symlink():
            return True
    return False


def _safe_input_file(path: str | Path, field: str) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise BuildMapExportError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise BuildMapExportError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise BuildMapExportError(f"{field} is not a file: {resolved}")
    return resolved


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise BuildMapExportError(f"output path must not contain symlinks: {target}")
    return target.resolve()


def _open_ledger(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _rows(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def _load_source_rows(database: Path, project_id: str, run_id: str) -> dict[str, Any]:
    verification = verify_ledger(database)
    if not verification.get("valid"):
        errors = verification.get("errors", [])
        raise BuildMapExportError("invalid Evidence Ledger: " + "; ".join(str(item) for item in errors))
    with _open_ledger(database) as connection:
        run_row = connection.execute(
            "SELECT * FROM runs WHERE run_id = ? AND project_id = ?",
            (run_id, project_id),
        ).fetchone()
        if run_row is None:
            raise BuildMapExportError(
                f"Run not found for project: project_id={project_id!r} run_id={run_id!r}"
            )
        artifacts = _rows(
            connection,
            "SELECT * FROM artifacts WHERE run_id = ? ORDER BY relative_path, artifact_id",
            (run_id,),
        )
        claims = _rows(
            connection,
            "SELECT * FROM claims WHERE run_id = ? ORDER BY claim_id",
            (run_id,),
        )
        evidence = _rows(
            connection,
            "SELECT * FROM evidence WHERE run_id = ? ORDER BY evidence_id",
            (run_id,),
        )
        claim_evidence = _rows(
            connection,
            """
            SELECT ce.*
            FROM claim_evidence ce
            JOIN claims c ON c.claim_id = ce.claim_id
            WHERE c.run_id = ?
            ORDER BY ce.claim_id, ce.evidence_id, ce.relation
            """,
            (run_id,),
        )
        findings = _rows(
            connection,
            "SELECT * FROM findings WHERE run_id = ? ORDER BY finding_id",
            (run_id,),
        )
        finding_defects = _rows(
            connection,
            """
            SELECT fd.*
            FROM finding_defects fd
            JOIN findings f ON f.finding_id = fd.finding_id
            WHERE f.run_id = ?
            ORDER BY fd.finding_id, fd.defect_id
            """,
            (run_id,),
        )
        defects = _rows(
            connection,
            """
            SELECT DISTINCT d.*
            FROM defects d
            JOIN finding_defects fd ON fd.defect_id = d.defect_id
            JOIN findings f ON f.finding_id = fd.finding_id
            WHERE f.run_id = ?
            ORDER BY d.defect_id
            """,
            (run_id,),
        )
        defect_artifacts = _rows(
            connection,
            """
            SELECT DISTINCT da.*
            FROM defect_artifacts da
            JOIN finding_defects fd ON fd.defect_id = da.defect_id
            JOIN findings f ON f.finding_id = fd.finding_id
            WHERE f.run_id = ?
            ORDER BY da.defect_id, da.artifact_id, da.relation
            """,
            (run_id,),
        )
        decisions = _rows(
            connection,
            "SELECT * FROM decisions WHERE run_id = ? ORDER BY decision_id",
            (run_id,),
        )
        policy_snapshots = _rows(
            connection,
            "SELECT * FROM policy_snapshots WHERE run_id = ? ORDER BY policy_snapshot_id",
            (run_id,),
        )
    return {
        "run": dict(run_row),
        "artifacts": artifacts,
        "claims": claims,
        "evidence": evidence,
        "claim_evidence": claim_evidence,
        "findings": findings,
        "finding_defects": finding_defects,
        "defects": defects,
        "defect_artifacts": defect_artifacts,
        "decisions": decisions,
        "policy_snapshots": policy_snapshots,
    }


def _stable_source_rows(rows: dict[str, Any]) -> dict[str, Any]:
    run = rows["run"]
    stable_run = {
        key: run.get(key)
        for key in (
            "run_id",
            "run_key_sha256",
            "project_id",
            "run_type",
            "source_revision",
            "source_identifier",
            "legacy_run_id",
            "manifest_sha256",
        )
    }

    def without(items: list[dict[str, Any]], excluded: set[str]) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in item.items() if key not in excluded}
            for item in items
        ]

    return {
        "run": stable_run,
        "artifacts": without(rows["artifacts"], set()),
        "claims": without(rows["claims"], set()),
        "evidence": without(rows["evidence"], set()),
        "claim_evidence": without(rows["claim_evidence"], set()),
        "findings": without(rows["findings"], {"imported_at"}),
        "finding_defects": without(rows["finding_defects"], set()),
        "defects": without(rows["defects"], set()),
        "defect_artifacts": without(rows["defect_artifacts"], set()),
        "decisions": without(rows["decisions"], set()),
        "policy_snapshots": without(rows["policy_snapshots"], {"imported_at"}),
    }


def calculate_source_fingerprint(rows: dict[str, Any]) -> str:
    return canonical_json_sha256(_stable_source_rows(rows))


def _safe_source_identifier(value: str, run_id: str) -> tuple[str, bool]:
    fallback = f"pie://runs/{run_id}"
    if not isinstance(value, str) or not value.strip():
        return fallback, True
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return fallback, True
    if parsed.scheme not in _ALLOWED_SOURCE_SCHEMES:
        return fallback, True
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        return fallback, True
    if any(ord(character) < 32 for character in raw):
        return fallback, True
    return raw, False


def _normalize_patterns(patterns: Iterable[str]) -> list[str]:
    normalized: set[str] = set()
    for value in patterns:
        try:
            pattern = normalize_path(value)
        except ValueError as exc:
            raise BuildMapExportError(f"invalid redaction path pattern {value!r}: {exc}") from exc
        normalized.add(pattern)
    return sorted(normalized)


def _raw_github_artifact(path: str) -> bool:
    lowered = path.lower()
    name = PurePosixPath(lowered).name
    if lowered in _RAW_GITHUB_PATHS or name in _RAW_GITHUB_PATHS:
        return True
    return any(
        token in name
        for token in (
            "discussion",
            "issue-comment",
            "review-comment",
            "conversation",
            "transcript",
        )
    )


def _sensitive_artifact(path: str) -> bool:
    lowered = path.lower()
    name = PurePosixPath(lowered).name
    suffix = PurePosixPath(lowered).suffix
    if name == ".env" or name.startswith(".env."):
        return True
    if suffix in _SENSITIVE_SUFFIXES:
        return True
    return any(token in name for token in _SENSITIVE_TOKENS)


def _artifact_redaction_reason(path: str, custom_patterns: list[str]) -> str | None:
    if _raw_github_artifact(path):
        return "raw_github_discussion"
    if _sensitive_artifact(path):
        return "sensitive_path"
    if any(fnmatch.fnmatchcase(path, pattern) for pattern in custom_patterns):
        return "custom_pattern"
    return None


def _artifact_projection(
    rows: list[dict[str, Any]],
    custom_patterns: list[str],
) -> tuple[list[dict[str, Any]], set[str], dict[str, int]]:
    projected: list[dict[str, Any]] = []
    included: set[str] = set()
    omitted = {
        "raw_github_discussion": 0,
        "sensitive_path": 0,
        "custom_pattern": 0,
    }
    for row in rows:
        try:
            path = normalize_path(str(row["relative_path"]))
        except ValueError as exc:
            raise BuildMapExportError(
                f"Ledger artifact path is unsafe: {row.get('relative_path')!r}: {exc}"
            ) from exc
        reason = _artifact_redaction_reason(path, custom_patterns)
        if reason is not None:
            omitted[reason] += 1
            continue
        item = {
            "artifact_id": str(row["artifact_id"]),
            "artifact_type": str(row["artifact_type"]),
            "relative_path": path,
            "sha256": str(row["sha256"]),
            "media_type": str(row["media_type"]),
            "size_bytes": int(row["size_bytes"]),
        }
        projected.append(item)
        included.add(item["artifact_id"])
    projected.sort(key=lambda item: (item["relative_path"], item["artifact_id"]))
    return projected, included, omitted


def _artifact_reference(value: Any, included: set[str]) -> tuple[str | None, bool]:
    artifact_id = str(value) if isinstance(value, str) and value else None
    return artifact_id, artifact_id is not None and artifact_id not in included


def _result_sha256(value: Any) -> str | None:
    if value is None:
        return None
    return canonical_json_sha256({"result": value})


def _reason_refs(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    data: Any = value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    refs: set[tuple[str, str]] = set()
    for group, items in data.items():
        if not isinstance(group, str) or not group:
            continue
        values = items if isinstance(items, list) else [items]
        for item in values:
            reason_id: str | None = None
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                reason_id = item["id"]
            elif isinstance(item, str):
                reason_id = item
            if reason_id:
                refs.add((group, reason_id))
    return [
        {"group": group, "reason_id": reason_id}
        for group, reason_id in sorted(refs)
    ]


def _project_rows(rows: dict[str, Any], included_artifacts: set[str]) -> dict[str, Any]:
    claims = [
        {
            "claim_id": str(row["claim_id"]),
            "claim_type": str(row["claim_type"]),
            "status": str(row["status"]),
            "policy_version": row.get("policy_version"),
        }
        for row in rows["claims"]
    ]
    evidence = []
    for row in rows["evidence"]:
        artifact_id, redacted = _artifact_reference(row.get("artifact_id"), included_artifacts)
        evidence.append(
            {
                "evidence_id": str(row["evidence_id"]),
                "evidence_level": str(row["evidence_level"]),
                "evidence_type": str(row["evidence_type"]),
                "result_sha256": _result_sha256(row.get("result")),
                "artifact_id": artifact_id,
                "artifact_redacted": redacted,
            }
        )
    claim_evidence = [
        {
            "claim_id": str(row["claim_id"]),
            "evidence_id": str(row["evidence_id"]),
            "relation": str(row["relation"]),
            "strength": row.get("strength"),
        }
        for row in rows["claim_evidence"]
    ]
    defect_ids_by_finding: dict[str, set[str]] = {}
    for link in rows["finding_defects"]:
        finding_id = str(link["finding_id"])
        defect_ids_by_finding.setdefault(finding_id, set()).add(str(link["defect_id"]))
    findings = []
    for row in rows["findings"]:
        artifact_id, redacted = _artifact_reference(row.get("artifact_id"), included_artifacts)
        findings.append(
            {
                "finding_id": str(row["finding_id"]),
                "category": str(row["category"]),
                "severity": str(row["severity"]),
                "confidence": str(row["confidence"]),
                "status": str(row["status"]),
                "defect_ids": sorted(defect_ids_by_finding.get(str(row["finding_id"]), set())),
                "finding_sha256": str(row["finding_sha256"]),
                "artifact_id": artifact_id,
                "artifact_redacted": redacted,
            }
        )
    artifact_refs_by_defect: dict[str, list[dict[str, Any]]] = {}
    for link in rows["defect_artifacts"]:
        artifact_id, redacted = _artifact_reference(link.get("artifact_id"), included_artifacts)
        if artifact_id is None:
            continue
        artifact_refs_by_defect.setdefault(str(link["defect_id"]), []).append(
            {
                "artifact_id": artifact_id,
                "relation": str(link["relation"]),
                "artifact_redacted": redacted,
            }
        )
    for refs in artifact_refs_by_defect.values():
        refs.sort(key=lambda item: (item["artifact_id"], item["relation"]))
    defects = [
        {
            "defect_id": str(row["defect_id"]),
            "category": str(row["category"]),
            "lifecycle_status": str(row["lifecycle_status"]),
            "signature_sha256": canonical_json_sha256({"signature": row.get("signature")}),
            "first_seen_run_id": row.get("first_seen_run_id"),
            "last_seen_run_id": row.get("last_seen_run_id"),
            "artifact_refs": artifact_refs_by_defect.get(str(row["defect_id"]), []),
        }
        for row in rows["defects"]
    ]
    decisions = []
    for row in rows["decisions"]:
        artifact_id, redacted = _artifact_reference(row.get("artifact_id"), included_artifacts)
        decisions.append(
            {
                "decision_id": str(row["decision_id"]),
                "decision_type": str(row["decision_type"]),
                "outcome": str(row["outcome"]),
                "policy_version": row.get("policy_version"),
                "decided_at": row.get("decided_at"),
                "artifact_id": artifact_id,
                "artifact_redacted": redacted,
                "reason_refs": _reason_refs(row.get("reasons_json")),
            }
        )
    policy_snapshots = []
    for row in rows["policy_snapshots"]:
        artifact_id, redacted = _artifact_reference(row.get("artifact_id"), included_artifacts)
        policy_snapshots.append(
            {
                "policy_snapshot_id": str(row["policy_snapshot_id"]),
                "policy_version": row.get("policy_version"),
                "sha256": str(row["sha256"]),
                "artifact_id": artifact_id,
                "artifact_redacted": redacted,
            }
        )
    claims.sort(key=lambda item: item["claim_id"])
    evidence.sort(key=lambda item: item["evidence_id"])
    claim_evidence.sort(key=lambda item: (item["claim_id"], item["evidence_id"], item["relation"]))
    findings.sort(key=lambda item: item["finding_id"])
    defects.sort(key=lambda item: item["defect_id"])
    decisions.sort(key=lambda item: item["decision_id"])
    policy_snapshots.sort(key=lambda item: item["policy_snapshot_id"])
    return {
        "claims": claims,
        "evidence": evidence,
        "claim_evidence": claim_evidence,
        "findings": findings,
        "defects": defects,
        "decisions": decisions,
        "policy_snapshots": policy_snapshots,
    }


def _projection_payload(export: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": export.get("schema_version"),
        "project_id": export.get("project_id"),
        "source": deepcopy(export.get("source")),
        "projection": deepcopy(export.get("projection")),
        "redaction": deepcopy(export.get("redaction")),
        "source_fingerprint_sha256": export.get("source_fingerprint_sha256"),
    }


def _export_payload(export: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(export)
    payload.pop("export_sha256", None)
    return payload


def _expected_export_id(export: dict[str, Any], projection_sha256: str) -> str:
    source = export.get("source") if isinstance(export.get("source"), dict) else {}
    natural_key = {
        "project_id": export.get("project_id"),
        "run_id": source.get("run_id"),
        "run_key_sha256": source.get("run_key_sha256"),
        "projection_sha256": projection_sha256,
    }
    return f"buildmap-{canonical_json_sha256(natural_key)[:32]}"


def build_buildmap_export(
    database: str | Path,
    *,
    project_id: str,
    run_id: str,
    redaction_paths: Iterable[str] = (),
    generated_at: str | None = None,
) -> dict[str, Any]:
    project = project_id.strip() if isinstance(project_id, str) else ""
    selected_run = run_id.strip() if isinstance(run_id, str) else ""
    if not project:
        raise BuildMapExportError("project_id must be a non-empty string")
    if not selected_run:
        raise BuildMapExportError("run_id must be a non-empty string")
    database_path = _safe_input_file(database, "Evidence Ledger")
    custom_patterns = _normalize_patterns(redaction_paths)
    rows = _load_source_rows(database_path, project, selected_run)
    run = rows["run"]
    artifacts, included_artifacts, omitted = _artifact_projection(rows["artifacts"], custom_patterns)
    source_identifier, source_redacted = _safe_source_identifier(
        str(run.get("source_identifier", "")),
        selected_run,
    )
    source = {
        "pie_run_uri": f"pie://runs/{selected_run}",
        "run_id": selected_run,
        "run_key_sha256": str(run["run_key_sha256"]),
        "run_type": str(run["run_type"]),
        "source_revision": str(run["source_revision"]),
        "source_identifier": source_identifier,
        "manifest_sha256": str(run["manifest_sha256"]),
    }
    projection = {"artifacts": artifacts, **_project_rows(rows, included_artifacts)}
    export: dict[str, Any] = {
        "schema_version": BUILDMAP_EXPORT_SCHEMA_VERSION,
        "export_id": "",
        "project_id": project,
        "generated_at": _timestamp(generated_at or _utc_now(), "generated_at"),
        "source": source,
        "projection": projection,
        "redaction": {
            "policy_id": BUILDMAP_REDACTION_POLICY_ID,
            "content_included": False,
            "raw_github_discussion_included": False,
            "source_identifier_redacted": source_redacted,
            "custom_patterns_sha256": canonical_json_sha256(custom_patterns),
            "omitted_artifacts": omitted,
        },
        "source_fingerprint_sha256": calculate_source_fingerprint(rows),
        "projection_sha256": "",
        "export_sha256": "",
    }
    export["projection_sha256"] = canonical_json_sha256(_projection_payload(export))
    export["export_id"] = _expected_export_id(export, export["projection_sha256"])
    export["export_sha256"] = canonical_json_sha256(_export_payload(export))
    errors = verify_buildmap_export_data(export)
    if errors:
        raise BuildMapExportVerificationError(errors)
    return export


def _schema_errors(data: Any) -> list[str]:
    schema = load_data(asset("schemas/buildmap-export.schema.json"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    output: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        output.append(f"{location}: {error.message}")
    return output


def _canonical_projection_errors(export: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    projection = export.get("projection")
    if not isinstance(projection, dict):
        return errors
    artifacts_raw = projection.get("artifacts")
    artifacts = artifacts_raw if isinstance(artifacts_raw, list) else []
    artifact_ids: set[str] = set()
    canonical_artifacts: list[dict[str, Any]] = []
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            continue
        try:
            path = normalize_path(item.get("relative_path", ""))
        except ValueError as exc:
            errors.append(f"projection.artifacts[{index}].relative_path: {exc}")
            continue
        if _artifact_redaction_reason(path, []) is not None:
            errors.append(f"projection.artifacts[{index}] violates default redaction policy")
        artifact_id = item.get("artifact_id")
        if isinstance(artifact_id, str):
            if artifact_id in artifact_ids:
                errors.append(f"duplicate artifact_id: {artifact_id}")
            artifact_ids.add(artifact_id)
        canonical_artifacts.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": item.get("artifact_type"),
                "relative_path": path,
                "sha256": item.get("sha256"),
                "media_type": item.get("media_type"),
                "size_bytes": item.get("size_bytes"),
            }
        )
    canonical_artifacts.sort(key=lambda item: (str(item["relative_path"]), str(item["artifact_id"])))
    if artifacts_raw != canonical_artifacts:
        errors.append("projection.artifacts canonical projection mismatch")

    sort_keys = {
        "claims": lambda item: str(item.get("claim_id")),
        "evidence": lambda item: str(item.get("evidence_id")),
        "claim_evidence": lambda item: (
            str(item.get("claim_id")),
            str(item.get("evidence_id")),
            str(item.get("relation")),
        ),
        "findings": lambda item: str(item.get("finding_id")),
        "defects": lambda item: str(item.get("defect_id")),
        "decisions": lambda item: str(item.get("decision_id")),
        "policy_snapshots": lambda item: str(item.get("policy_snapshot_id")),
    }
    for name, key in sort_keys.items():
        items = projection.get(name)
        if isinstance(items, list) and items != sorted(items, key=key):
            errors.append(f"projection.{name} canonical ordering mismatch")

    for name in ("evidence", "findings", "decisions", "policy_snapshots"):
        items = projection.get(name)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            artifact_id = item.get("artifact_id")
            expected_redacted = isinstance(artifact_id, str) and artifact_id not in artifact_ids
            if item.get("artifact_redacted") is not expected_redacted:
                errors.append(f"projection.{name}[{index}].artifact_redacted mismatch")

    findings = projection.get("findings")
    if isinstance(findings, list):
        for index, item in enumerate(findings):
            if not isinstance(item, dict):
                continue
            defect_ids = item.get("defect_ids")
            if not isinstance(defect_ids, list) or not all(isinstance(value, str) and value for value in defect_ids):
                errors.append(f"projection.findings[{index}].defect_ids canonical mismatch")
            elif defect_ids != sorted(set(defect_ids)):
                errors.append(f"projection.findings[{index}].defect_ids canonical mismatch")

    defects = projection.get("defects")
    if isinstance(defects, list):
        for index, item in enumerate(defects):
            if not isinstance(item, dict):
                continue
            refs = item.get("artifact_refs")
            if not isinstance(refs, list):
                errors.append(f"projection.defects[{index}].artifact_refs canonical mismatch")
                continue
            canonical: list[dict[str, Any]] = []
            seen: set[tuple[str, str]] = set()
            malformed = False
            for ref in refs:
                if not isinstance(ref, dict):
                    malformed = True
                    continue
                artifact_id = ref.get("artifact_id")
                relation = ref.get("relation")
                if not isinstance(artifact_id, str) or not artifact_id or not isinstance(relation, str) or not relation:
                    malformed = True
                    continue
                key = (artifact_id, relation)
                if key in seen:
                    malformed = True
                    continue
                seen.add(key)
                canonical.append(
                    {
                        "artifact_id": artifact_id,
                        "relation": relation,
                        "artifact_redacted": artifact_id not in artifact_ids,
                    }
                )
            canonical.sort(key=lambda ref: (ref["artifact_id"], ref["relation"]))
            if malformed or refs != canonical:
                errors.append(f"projection.defects[{index}].artifact_refs canonical mismatch")

    decisions = projection.get("decisions")
    if isinstance(decisions, list):
        for index, item in enumerate(decisions):
            if not isinstance(item, dict):
                continue
            refs = item.get("reason_refs")
            if isinstance(refs, list):
                keys: list[tuple[str, str]] = []
                malformed = False
                for ref in refs:
                    if not isinstance(ref, dict):
                        malformed = True
                        continue
                    group = ref.get("group")
                    reason_id = ref.get("reason_id")
                    if not isinstance(group, str) or not group or not isinstance(reason_id, str) or not reason_id:
                        malformed = True
                        continue
                    keys.append((group, reason_id))
                canonical = [
                    {"group": group, "reason_id": reason_id}
                    for group, reason_id in sorted(set(keys))
                ]
                if malformed or refs != canonical:
                    errors.append(f"projection.decisions[{index}].reason_refs canonical mismatch")
    return errors


def verify_buildmap_export_data(data: Any) -> list[str]:
    errors = _schema_errors(data)
    if not isinstance(data, dict):
        return sorted(set(errors))
    errors.extend(_canonical_projection_errors(data))
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    run_id = source.get("run_id")
    expected_uri = f"pie://runs/{run_id}" if isinstance(run_id, str) else None
    if source.get("pie_run_uri") != expected_uri:
        errors.append("source.pie_run_uri mismatch")
    redaction = data.get("redaction") if isinstance(data.get("redaction"), dict) else {}
    source_identifier = source.get("source_identifier")
    if redaction.get("source_identifier_redacted") is True:
        if source_identifier != expected_uri:
            errors.append("redacted source identifier must equal pie_run_uri")
    elif isinstance(source_identifier, str) and isinstance(run_id, str):
        safe, was_redacted = _safe_source_identifier(source_identifier, run_id)
        if was_redacted or safe != source_identifier:
            errors.append("source.source_identifier violates safe identifier policy")
    projection_hash = canonical_json_sha256(_projection_payload(data))
    if data.get("projection_sha256") != projection_hash:
        errors.append("projection_sha256 mismatch")
    expected_export_id = _expected_export_id(data, projection_hash)
    if data.get("export_id") != expected_export_id:
        errors.append("export_id mismatch")
    export_hash = canonical_json_sha256(_export_payload(data))
    if data.get("export_sha256") != export_hash:
        errors.append("export_sha256 mismatch")
    return sorted(set(errors))


def verify_buildmap_export_source(data: Any, database: str | Path) -> list[str]:
    errors = verify_buildmap_export_data(data)
    if errors or not isinstance(data, dict):
        return errors
    try:
        database_path = _safe_input_file(database, "Evidence Ledger")
        source = data["source"]
        rows = _load_source_rows(database_path, data["project_id"], source["run_id"])
    except Exception as exc:
        return [f"source verification failed: {exc}"]
    if data.get("source_fingerprint_sha256") != calculate_source_fingerprint(rows):
        errors.append("source_fingerprint_sha256 mismatch")
    run = rows["run"]
    expected_identifier, redacted = _safe_source_identifier(str(run.get("source_identifier", "")), source["run_id"])
    expected_source = {
        "pie_run_uri": f"pie://runs/{source['run_id']}",
        "run_id": source["run_id"],
        "run_key_sha256": str(run["run_key_sha256"]),
        "run_type": str(run["run_type"]),
        "source_revision": str(run["source_revision"]),
        "source_identifier": expected_identifier,
        "manifest_sha256": str(run["manifest_sha256"]),
    }
    if data.get("source") != expected_source:
        errors.append("source projection mismatch")
    if data.get("redaction", {}).get("source_identifier_redacted") is not redacted:
        errors.append("redaction.source_identifier_redacted mismatch")

    projection = data.get("projection", {})
    artifacts = projection.get("artifacts", []) if isinstance(projection, dict) else []
    included_ids = {
        item["artifact_id"]
        for item in artifacts
        if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
    }
    by_id = {str(row["artifact_id"]): row for row in rows["artifacts"]}
    expected_artifacts: list[dict[str, Any]] = []
    for artifact_id in included_ids:
        row = by_id.get(artifact_id)
        if row is None:
            errors.append(f"export references unknown artifact: {artifact_id}")
            continue
        path = normalize_path(str(row["relative_path"]))
        if _artifact_redaction_reason(path, []) is not None:
            errors.append(f"export includes default-redacted artifact: {artifact_id}")
        expected_artifacts.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": str(row["artifact_type"]),
                "relative_path": path,
                "sha256": str(row["sha256"]),
                "media_type": str(row["media_type"]),
                "size_bytes": int(row["size_bytes"]),
            }
        )
    expected_artifacts.sort(key=lambda item: (item["relative_path"], item["artifact_id"]))
    if artifacts != expected_artifacts:
        errors.append("artifact source projection mismatch")
    expected_projection = {"artifacts": expected_artifacts, **_project_rows(rows, included_ids)}
    if projection != expected_projection:
        errors.append("BuildMap source projection mismatch")

    omitted = data.get("redaction", {}).get("omitted_artifacts", {})
    actual_default = {"raw_github_discussion": 0, "sensitive_path": 0}
    custom_count = 0
    for row in rows["artifacts"]:
        artifact_id = str(row["artifact_id"])
        if artifact_id in included_ids:
            continue
        path = normalize_path(str(row["relative_path"]))
        reason = _artifact_redaction_reason(path, [])
        if reason in actual_default:
            actual_default[reason] += 1
        else:
            custom_count += 1
    if omitted.get("raw_github_discussion") != actual_default["raw_github_discussion"]:
        errors.append("redaction raw_github_discussion count mismatch")
    if omitted.get("sensitive_path") != actual_default["sensitive_path"]:
        errors.append("redaction sensitive_path count mismatch")
    if omitted.get("custom_pattern") != custom_count:
        errors.append("redaction custom_pattern count mismatch")
    return sorted(set(errors))


def write_buildmap_export(path: str | Path, data: dict[str, Any]) -> Path:
    errors = verify_buildmap_export_data(data)
    if errors:
        raise BuildMapExportVerificationError(errors)
    target = _safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
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


def load_buildmap_export(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input_file(path, "BuildMap export")
    data = load_data(source)
    errors = verify_buildmap_export_data(data)
    if errors:
        raise BuildMapExportVerificationError(errors)
    return source, data

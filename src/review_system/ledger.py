from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .identity import canonical_json_sha256, validate_identity_manifest
from .io import load_data


LEDGER_SCHEMA_VERSION = "002"


class LedgerError(RuntimeError):
    pass


class LedgerMigrationError(LedgerError):
    pass


class LedgerImportError(LedgerError):
    pass


_INITIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    run_key_sha256 TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    run_type TEXT NOT NULL CHECK (run_type IN ('review', 'pull_request')),
    source_revision TEXT NOT NULL,
    source_identifier TEXT NOT NULL,
    legacy_run_id TEXT,
    artifact_root TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_key_sha256 TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    media_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    UNIQUE (run_id, relative_path)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    claim_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    scope_json TEXT,
    status TEXT NOT NULL,
    policy_version TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    evidence_level TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    result TEXT,
    artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    locator TEXT,
    producer TEXT,
    producer_version TEXT,
    collected_at TEXT
);

CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    strength TEXT,
    PRIMARY KEY (claim_id, evidence_id, relation)
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    decision_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reasons_json TEXT,
    policy_version TEXT,
    decided_at TEXT,
    artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS policy_snapshots (
    policy_snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    policy_version TEXT,
    source TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    UNIQUE (run_id, sha256)
);

CREATE INDEX IF NOT EXISTS idx_runs_project_id ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_source_identifier ON runs(source_identifier);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_claims_run_id ON claims(run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_run_id ON evidence(run_id);
CREATE INDEX IF NOT EXISTS idx_decisions_run_id ON decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_policy_snapshots_run_id ON policy_snapshots(run_id);
"""

_DEFECT_REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    finding_key_sha256 TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    source_finding_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    impact TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    finding_sha256 TEXT NOT NULL,
    artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    imported_at TEXT NOT NULL,
    UNIQUE (run_id, source_finding_id)
);

CREATE TABLE IF NOT EXISTS registry_sources (
    project_id TEXT PRIMARY KEY,
    registry_path TEXT NOT NULL,
    registry_sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS defects (
    defect_id TEXT PRIMARY KEY,
    defect_key_sha256 TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    root_cause TEXT,
    lifecycle_status TEXT NOT NULL CHECK (
        lifecycle_status IN (
            'OBSERVED', 'REPRODUCED', 'CLASSIFIED', 'RULE_CANDIDATE',
            'MITIGATED', 'VERIFIED', 'CLOSED', 'REOPENED'
        )
    ),
    first_seen_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
    last_seen_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
    owner TEXT,
    resolution TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, signature)
);

CREATE TABLE IF NOT EXISTS finding_defects (
    finding_id TEXT NOT NULL REFERENCES findings(finding_id) ON DELETE RESTRICT,
    defect_id TEXT NOT NULL REFERENCES defects(defect_id) ON DELETE CASCADE,
    match_method TEXT NOT NULL CHECK (match_method IN ('manual', 'deterministic_signature')),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    approved_by TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (finding_id, defect_id)
);

CREATE TABLE IF NOT EXISTS defect_events (
    event_id TEXT PRIMARY KEY,
    defect_id TEXT NOT NULL REFERENCES defects(defect_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('CREATED', 'FINDING_LINKED', 'ARTIFACT_LINKED', 'TRANSITIONED')
    ),
    status_from TEXT,
    status_to TEXT,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS defect_artifacts (
    defect_id TEXT NOT NULL REFERENCES defects(defect_id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
    relation TEXT NOT NULL CHECK (
        relation IN ('reproducer', 'diagnostic', 'mitigation', 'verification', 'resolution_evidence')
    ),
    linked_by TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    note TEXT,
    PRIMARY KEY (defect_id, artifact_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_findings_run_id ON findings(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_category ON findings(category);
CREATE INDEX IF NOT EXISTS idx_defects_project_status ON defects(project_id, lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_finding_defects_defect_id ON finding_defects(defect_id);
CREATE INDEX IF NOT EXISTS idx_defect_events_defect_id ON defect_events(defect_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_defect_artifacts_defect_id ON defect_artifacts(defect_id);
"""

_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("001", _INITIAL_SCHEMA),
    (LEDGER_SCHEMA_VERSION, _DEFECT_REGISTRY_SCHEMA),
)


@dataclass(frozen=True)
class LedgerImportResult:
    database: Path
    artifact_root: Path
    run_id: str
    run_type: str
    artifact_count: int
    decision_count: int
    policy_snapshot_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "database": str(self.database),
            "artifact_root": str(self.artifact_root),
            "run_id": self.run_id,
            "run_type": self.run_type,
            "artifact_count": self.artifact_count,
            "decision_count": self.decision_count,
            "policy_snapshot_count": self.policy_snapshot_count,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _migration_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _database_path(database: str | Path, *, create_parent: bool) -> Path:
    path = Path(database).expanduser().resolve()
    if path.exists() and not path.is_file():
        raise LedgerError(f"ledger database path is not a file: {path}")
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5.0)
    else:
        connection = sqlite3.connect(path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_ledger(database: str | Path) -> Path:
    path = _database_path(database, create_parent=True)
    with _connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum_sha256 TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        for version, sql in _MIGRATIONS:
            checksum = _migration_checksum(sql)
            row = connection.execute(
                "SELECT checksum_sha256 FROM schema_migrations WHERE version = ?",
                (version,),
            ).fetchone()
            if row is not None:
                if row["checksum_sha256"] != checksum:
                    raise LedgerMigrationError(
                        f"ledger migration {version} checksum mismatch: "
                        f"database={row['checksum_sha256']} code={checksum}"
                    )
                continue
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, checksum_sha256, applied_at) VALUES (?, ?, ?)",
                (version, checksum, _utc_now()),
            )
    return path


def _ensure_database_outside_root(database: Path, artifact_root: Path) -> None:
    try:
        database.relative_to(artifact_root)
    except ValueError:
        return
    raise LedgerImportError(
        f"ledger database must be outside the artifact root to avoid self-indexing: {database}"
    )


def _load_identity_directory(
    directory: str | Path,
    *,
    expected_run_type: str | None,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise LedgerImportError(f"artifact directory does not exist: {root}")
    errors = validate_identity_manifest(root, require_complete=True)
    if errors:
        raise LedgerImportError("invalid identity directory: " + "; ".join(errors))
    manifest = load_data(root / "identity.json")
    if not isinstance(manifest, dict):
        raise LedgerImportError("identity.json must contain an object")
    run = manifest.get("run")
    artifacts = manifest.get("artifacts")
    if not isinstance(run, dict):
        raise LedgerImportError("identity.json run must be an object")
    if not isinstance(artifacts, list) or not all(isinstance(item, dict) for item in artifacts):
        raise LedgerImportError("identity.json artifacts must be an array of objects")
    run_type = run.get("run_type")
    if expected_run_type is not None and run_type != expected_run_type:
        raise LedgerImportError(
            f"identity run type mismatch: expected {expected_run_type!r}, found {run_type!r}"
        )
    return root, manifest, run, artifacts


def _legacy_run_id(root: Path, run_type: str) -> str | None:
    if run_type == "review" and (root / "run.json").is_file():
        data = load_data(root / "run.json")
        if isinstance(data, dict) and isinstance(data.get("run_id"), str):
            return data["run_id"]
    if run_type == "pull_request" and (root / "github-source.json").is_file():
        data = load_data(root / "github-source.json")
        number = data.get("pull_request", {}).get("number") if isinstance(data, dict) else None
        if isinstance(number, int) and not isinstance(number, bool):
            return f"PR-{number}"
    return None


def _explicit_projections(
    root: Path,
    run: dict[str, Any],
    artifacts: list[dict[str, Any]],
    *,
    imported_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_path = {
        item["relative_path"]: item
        for item in artifacts
        if isinstance(item.get("relative_path"), str)
    }
    run_id = str(run["run_id"])
    decisions: list[dict[str, Any]] = []
    policies: list[dict[str, Any]] = []

    policy_artifact = by_path.get("gate-policy.yml")
    if policy_artifact is not None and (root / "gate-policy.yml").is_file():
        policy = load_data(root / "gate-policy.yml")
        version = str(policy.get("version")) if isinstance(policy, dict) and policy.get("version") is not None else None
        digest = str(policy_artifact["sha256"])
        policies.append(
            {
                "policy_snapshot_id": f"policy-{canonical_json_sha256({'run_id': run_id, 'sha256': digest})[:32]}",
                "run_id": run_id,
                "policy_version": version,
                "source": "gate-policy.yml",
                "sha256": digest,
                "imported_at": imported_at,
                "artifact_id": policy_artifact["artifact_id"],
            }
        )

    gate_artifact = by_path.get("gate-result.json")
    if gate_artifact is not None and (root / "gate-result.json").is_file():
        gate = load_data(root / "gate-result.json")
        if isinstance(gate, dict) and isinstance(gate.get("decision"), str):
            policy_meta = gate.get("policy") if isinstance(gate.get("policy"), dict) else {}
            version = str(policy_meta.get("version")) if policy_meta.get("version") is not None else None
            natural_key = {
                "run_id": run_id,
                "decision_type": "review_gate",
                "outcome": gate["decision"],
                "artifact_id": gate_artifact["artifact_id"],
            }
            decisions.append(
                {
                    "decision_id": f"decision-{canonical_json_sha256(natural_key)[:32]}",
                    "run_id": run_id,
                    "decision_type": "review_gate",
                    "outcome": gate["decision"],
                    "reasons_json": json.dumps(
                        gate.get("triggered", {}),
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "policy_version": version,
                    "decided_at": gate.get("generated_at") if isinstance(gate.get("generated_at"), str) else None,
                    "artifact_id": gate_artifact["artifact_id"],
                }
            )
    return decisions, policies


def _required_run_fields(run: dict[str, Any]) -> None:
    fields = (
        "run_id",
        "run_key_sha256",
        "project_id",
        "run_type",
        "source_revision",
        "source_identifier",
    )
    missing = [field for field in fields if not isinstance(run.get(field), str) or not run.get(field)]
    if missing:
        raise LedgerImportError("identity run is missing fields: " + ", ".join(missing))


def _delete_stale_artifacts(
    connection: sqlite3.Connection,
    run_id: str,
    artifact_ids: list[str],
) -> None:
    if not artifact_ids:
        connection.execute("DELETE FROM artifacts WHERE run_id = ?", (run_id,))
        return
    placeholders = ",".join("?" for _ in artifact_ids)
    connection.execute(
        f"DELETE FROM artifacts WHERE run_id = ? AND artifact_id NOT IN ({placeholders})",
        (run_id, *artifact_ids),
    )


def import_artifact_directory(
    database: str | Path,
    directory: str | Path,
    *,
    expected_run_type: str | None = None,
) -> LedgerImportResult:
    database_path = _database_path(database, create_parent=True)
    root, manifest, run, artifacts = _load_identity_directory(
        directory,
        expected_run_type=expected_run_type,
    )
    _ensure_database_outside_root(database_path, root)
    _required_run_fields(run)
    manifest_hash = manifest.get("manifest_sha256")
    if not isinstance(manifest_hash, str) or len(manifest_hash) != 64:
        raise LedgerImportError("identity manifest_sha256 is invalid")
    initialize_ledger(database_path)

    imported_at = _utc_now()
    decisions, policies = _explicit_projections(root, run, artifacts, imported_at=imported_at)
    run_id = str(run["run_id"])
    artifact_ids = [str(item["artifact_id"]) for item in artifacts]
    with _connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT run_key_sha256 FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if existing is not None and existing["run_key_sha256"] != run["run_key_sha256"]:
            raise LedgerImportError(f"logical run ID collision for {run_id}: full natural keys differ")
        connection.execute(
            """
            INSERT INTO runs(
                run_id, run_key_sha256, project_id, run_type, source_revision,
                source_identifier, legacy_run_id, artifact_root, manifest_sha256, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                run_key_sha256 = excluded.run_key_sha256,
                project_id = excluded.project_id,
                run_type = excluded.run_type,
                source_revision = excluded.source_revision,
                source_identifier = excluded.source_identifier,
                legacy_run_id = excluded.legacy_run_id,
                artifact_root = excluded.artifact_root,
                manifest_sha256 = excluded.manifest_sha256,
                imported_at = excluded.imported_at
            """,
            (
                run_id,
                run["run_key_sha256"],
                run["project_id"],
                run["run_type"],
                run["source_revision"],
                run["source_identifier"],
                _legacy_run_id(root, str(run["run_type"])),
                str(root),
                manifest_hash,
                imported_at,
            ),
        )
        connection.execute("DELETE FROM decisions WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM policy_snapshots WHERE run_id = ?", (run_id,))
        _delete_stale_artifacts(connection, run_id, artifact_ids)

        for item in artifacts:
            connection.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, artifact_key_sha256, run_id, artifact_type,
                    relative_path, sha256, media_type, size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    artifact_key_sha256 = excluded.artifact_key_sha256,
                    run_id = excluded.run_id,
                    artifact_type = excluded.artifact_type,
                    relative_path = excluded.relative_path,
                    sha256 = excluded.sha256,
                    media_type = excluded.media_type,
                    size_bytes = excluded.size_bytes
                """,
                (
                    item["artifact_id"],
                    item["artifact_key_sha256"],
                    run_id,
                    item["artifact_type"],
                    item["relative_path"],
                    item["sha256"],
                    item["media_type"],
                    item["size_bytes"],
                ),
            )
        from .defects import project_findings_for_run

        project_findings_for_run(
            connection,
            root,
            run,
            artifacts,
            imported_at=imported_at,
        )
        for item in policies:
            connection.execute(
                """
                INSERT INTO policy_snapshots(
                    policy_snapshot_id, run_id, policy_version, source,
                    sha256, imported_at, artifact_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(item[field] for field in (
                    "policy_snapshot_id", "run_id", "policy_version", "source",
                    "sha256", "imported_at", "artifact_id",
                )),
            )
        for item in decisions:
            connection.execute(
                """
                INSERT INTO decisions(
                    decision_id, run_id, decision_type, outcome, reasons_json,
                    policy_version, decided_at, artifact_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(item[field] for field in (
                    "decision_id", "run_id", "decision_type", "outcome",
                    "reasons_json", "policy_version", "decided_at", "artifact_id",
                )),
            )

    return LedgerImportResult(
        database=database_path,
        artifact_root=root,
        run_id=run_id,
        run_type=str(run["run_type"]),
        artifact_count=len(artifacts),
        decision_count=len(decisions),
        policy_snapshot_count=len(policies),
    )


def _migration_errors(connection: sqlite3.Connection) -> list[str]:
    try:
        rows = connection.execute(
            "SELECT version, checksum_sha256 FROM schema_migrations ORDER BY version"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        return [f"schema_migrations unavailable: {exc}"]
    expected = {version: _migration_checksum(sql) for version, sql in _MIGRATIONS}
    recorded = {row["version"]: row["checksum_sha256"] for row in rows}
    errors: list[str] = []
    for version, checksum in expected.items():
        if version not in recorded:
            errors.append(f"missing migration: {version}")
        elif recorded[version] != checksum:
            errors.append(f"migration checksum mismatch: {version}")
    for version in sorted(set(recorded) - set(expected)):
        errors.append(f"unsupported migration present: {version}")
    return errors


def _compare_rows(
    errors: list[str],
    *,
    label: str,
    expected: list[dict[str, Any]],
    stored: list[dict[str, Any]],
    key: str,
    fields: tuple[str, ...],
) -> None:
    expected_by_key = {str(item[key]): item for item in expected}
    stored_by_key = {str(item[key]): item for item in stored}
    for value in sorted(set(expected_by_key) - set(stored_by_key)):
        errors.append(f"{label} missing from ledger: {value}")
    for value in sorted(set(stored_by_key) - set(expected_by_key)):
        errors.append(f"stale ledger {label}: {value}")
    for value in sorted(set(expected_by_key) & set(stored_by_key)):
        for field in fields:
            if expected_by_key[value].get(field) != stored_by_key[value].get(field):
                errors.append(f"{label} {value} field mismatch: {field}")


def verify_ledger(database: str | Path) -> dict[str, Any]:
    path = _database_path(database, create_parent=False)
    result: dict[str, Any] = {
        "valid": False,
        "database": str(path),
        "runs_checked": 0,
        "artifacts_checked": 0,
        "errors": [],
    }
    if not path.is_file():
        result["errors"].append(f"ledger database not found: {path}")
        return result
    try:
        with _connect(path, read_only=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                value = integrity[0] if integrity else "no result"
                result["errors"].append(f"SQLite integrity_check failed: {value}")
            for row in connection.execute("PRAGMA foreign_key_check").fetchall():
                result["errors"].append(
                    f"foreign key violation: table={row[0]} rowid={row[1]} parent={row[2]}"
                )
            result["errors"].extend(_migration_errors(connection))
            if result["errors"]:
                return result

            runs = connection.execute("SELECT * FROM runs ORDER BY run_id").fetchall()
            for run_row in runs:
                run_id = str(run_row["run_id"])
                result["runs_checked"] += 1
                root = Path(run_row["artifact_root"])
                if not root.is_dir():
                    result["errors"].append(f"run {run_id} artifact root not found: {root}")
                    continue
                identity_errors = validate_identity_manifest(root, require_complete=True)
                result["errors"].extend(f"run {run_id}: {error}" for error in identity_errors)
                if identity_errors:
                    continue
                manifest = load_data(root / "identity.json")
                run = manifest["run"]
                for field in (
                    "run_id", "run_key_sha256", "project_id", "run_type",
                    "source_revision", "source_identifier",
                ):
                    if run.get(field) != run_row[field]:
                        result["errors"].append(f"run {run_id}: field mismatch: {field}")
                if manifest.get("manifest_sha256") != run_row["manifest_sha256"]:
                    result["errors"].append(f"run {run_id}: manifest hash mismatch")

                stored_artifacts = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM artifacts WHERE run_id = ? ORDER BY relative_path",
                        (run_id,),
                    ).fetchall()
                ]
                manifest_artifacts = list(manifest.get("artifacts", []))
                result["artifacts_checked"] += len(manifest_artifacts)
                _compare_rows(
                    result["errors"],
                    label=f"run {run_id} artifact",
                    expected=manifest_artifacts,
                    stored=stored_artifacts,
                    key="relative_path",
                    fields=(
                        "artifact_id", "artifact_key_sha256", "artifact_type",
                        "sha256", "media_type", "size_bytes",
                    ),
                )
                from .defects import verify_findings_for_run

                verify_findings_for_run(
                    connection,
                    root,
                    run_id,
                    manifest_artifacts,
                    result["errors"],
                    imported_at=str(run_row["imported_at"]),
                )

                expected_decisions, expected_policies = _explicit_projections(
                    root,
                    run,
                    manifest_artifacts,
                    imported_at=str(run_row["imported_at"]),
                )
                stored_decisions = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM decisions WHERE run_id = ? ORDER BY decision_id",
                        (run_id,),
                    ).fetchall()
                ]
                stored_policies = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM policy_snapshots WHERE run_id = ? ORDER BY policy_snapshot_id",
                        (run_id,),
                    ).fetchall()
                ]
                _compare_rows(
                    result["errors"],
                    label=f"run {run_id} decision",
                    expected=expected_decisions,
                    stored=stored_decisions,
                    key="decision_id",
                    fields=(
                        "run_id", "decision_type", "outcome", "reasons_json",
                        "policy_version", "decided_at", "artifact_id",
                    ),
                )
                _compare_rows(
                    result["errors"],
                    label=f"run {run_id} policy snapshot",
                    expected=expected_policies,
                    stored=stored_policies,
                    key="policy_snapshot_id",
                    fields=(
                        "run_id", "policy_version", "source", "sha256",
                        "imported_at", "artifact_id",
                    ),
                )
            registry_sources = connection.execute(
                "SELECT registry_path FROM registry_sources ORDER BY project_id"
            ).fetchall()
        from .defects import verify_defect_registry

        for source in registry_sources:
            registry_result = verify_defect_registry(path, source["registry_path"])
            result["errors"].extend(
                f"defect registry: {error}" for error in registry_result["errors"]
            )
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
        result["errors"].append(f"ledger verification failed: {exc}")
        return result
    result["valid"] = not result["errors"]
    return result


def rebuild_ledger(
    database: str | Path,
    directories: Iterable[str | Path],
    *,
    registry_paths: Iterable[str | Path] = (),
) -> dict[str, Any]:
    path = _database_path(database, create_parent=True)
    roots = [Path(item).expanduser().resolve() for item in directories]
    if not roots:
        raise LedgerImportError("rebuild requires at least one artifact directory")
    temporary = path.with_name(path.name + ".rebuild.tmp")
    temporary.unlink(missing_ok=True)
    seen: dict[str, Path] = {}
    try:
        initialize_ledger(temporary)
        imported: list[dict[str, Any]] = []
        for root in roots:
            item = import_artifact_directory(temporary, root)
            previous = seen.get(item.run_id)
            if previous is not None and previous != item.artifact_root:
                raise LedgerImportError(
                    f"rebuild input contains multiple roots for logical run {item.run_id}: "
                    f"{previous} and {item.artifact_root}"
                )
            seen[item.run_id] = item.artifact_root
            imported.append(item.to_dict())
        registries = [Path(item).expanduser().resolve() for item in registry_paths]
        seen_projects: set[str] = set()
        registry_results: list[dict[str, Any]] = []
        if registries:
            from .defects import load_defect_registry, sync_defect_registry

            for registry_path in registries:
                _, registry = load_defect_registry(registry_path)
                project_id = str(registry["project_id"])
                if project_id in seen_projects:
                    raise LedgerImportError(
                        f"rebuild input contains multiple Defect registries for project {project_id}"
                    )
                seen_projects.add(project_id)
                registry_results.append(sync_defect_registry(temporary, registry_path))
        verification = verify_ledger(temporary)
        if not verification["valid"]:
            raise LedgerError("rebuilt ledger failed verification: " + "; ".join(verification["errors"]))
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    verification["database"] = str(path)
    verification["imported"] = imported
    verification["defect_registries"] = registry_results
    return verification


def show_run(database: str | Path, run_id: str) -> dict[str, Any] | None:
    path = _database_path(database, create_parent=False)
    if not path.is_file():
        raise LedgerError(f"ledger database not found: {path}")
    with _connect(path, read_only=True) as connection:
        run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            return None
        result = {"run": dict(run)}
        for key, table, order in (
            ("artifacts", "artifacts", "relative_path"),
            ("claims", "claims", "claim_id"),
            ("evidence", "evidence", "evidence_id"),
            ("decisions", "decisions", "decision_id"),
            ("policy_snapshots", "policy_snapshots", "policy_snapshot_id"),
        ):
            result[key] = [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} WHERE run_id = ? ORDER BY {order}",
                    (run_id,),
                ).fetchall()
            ]
    return result

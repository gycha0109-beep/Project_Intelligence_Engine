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


LEDGER_SCHEMA_VERSION = "001"


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

_MIGRATIONS: tuple[tuple[str, str], ...] = ((LEDGER_SCHEMA_VERSION, _INITIAL_SCHEMA),)


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
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5.0)
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
    if run_type == "review":
        path = root / "run.json"
        if path.is_file():
            data = load_data(path)
            if isinstance(data, dict) and isinstance(data.get("run_id"), str):
                return data["run_id"]
    if run_type == "pull_request":
        path = root / "github-source.json"
        if path.is_file():
            data = load_data(path)
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
    artifact_ids = {
        item.get("relative_path"): item.get("artifact_id")
        for item in artifacts
        if isinstance(item.get("relative_path"), str) and isinstance(item.get("artifact_id"), str)
    }
    run_id = str(run["run_id"])
    decisions: list[dict[str, Any]] = []
    policies: list[dict[str, Any]] = []

    policy_path = root / "gate-policy.yml"
    if policy_path.is_file() and "gate-policy.yml" in artifact_ids:
        policy = load_data(policy_path)
        policy_version = str(policy.get("version")) if isinstance(policy, dict) and policy.get("version") is not None else None
        policy_artifact = next(item for item in artifacts if item.get("relative_path") == "gate-policy.yml")
        digest = str(policy_artifact["sha256"])
        policies.append(
            {
                "policy_snapshot_id": f"policy-{canonical_json_sha256({'run_id': run_id, 'sha256': digest})[:32]}",
                "run_id": run_id,
                "policy_version": policy_version,
                "source": "gate-policy.yml",
                "sha256": digest,
                "imported_at": imported_at,
                "artifact_id": artifact_ids["gate-policy.yml"],
            }
        )

    gate_path = root / "gate-result.json"
    if gate_path.is_file() and "gate-result.json" in artifact_ids:
        gate = load_data(gate_path)
        if isinstance(gate, dict) and isinstance(gate.get("decision"), str):
            outcome = gate["decision"]
            policy_meta = gate.get("policy") if isinstance(gate.get("policy"), dict) else {}
            policy_version = str(policy_meta.get("version")) if policy_meta.get("version") is not None else None
            natural_key = {
                "run_id": run_id,
                "decision_type": "review_gate",
                "outcome": outcome,
                "artifact_id": artifact_ids["gate-result.json"],
            }
            decisions.append(
                {
                    "decision_id": f"decision-{canonical_json_sha256(natural_key)[:32]}",
                    "run_id": run_id,
                    "decision_type": "review_gate",
                    "outcome": outcome,
                    "reasons_json": json.dumps(
                        gate.get("triggered", {}),
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "policy_version": policy_version,
                    "decided_at": gate.get("generated_at") if isinstance(gate.get("generated_at"), str) else None,
                    "artifact_id": artifact_ids["gate-result.json"],
                }
            )
    return decisions, policies


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
    initialize_ledger(database_path)

    required_run_fields = (
        "run_id",
        "run_key_sha256",
        "project_id",
        "run_type",
        "source_revision",
        "source_identifier",
    )
    missing = [field for field in required_run_fields if not isinstance(run.get(field), str) or not run.get(field)]
    if missing:
        raise LedgerImportError("identity run is missing fields: " + ", ".join(missing))
    manifest_hash = manifest.get("manifest_sha256")
    if not isinstance(manifest_hash, str) or len(manifest_hash) != 64:
        raise LedgerImportError("identity manifest_sha256 is invalid")

    imported_at = _utc_now()
    decisions, policies = _explicit_projections(root, run, artifacts, imported_at=imported_at)
    with _connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT run_key_sha256 FROM runs WHERE run_id = ?",
            (run["run_id"],),
        ).fetchone()
        if existing is not None and existing["run_key_sha256"] != run["run_key_sha256"]:
            raise LedgerImportError(
                f"logical run ID collision for {run['run_id']}: full natural keys differ"
            )
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
                run["run_id"],
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
        connection.execute("DELETE FROM claim_evidence WHERE claim_id IN (SELECT claim_id FROM claims WHERE run_id = ?)", (run["run_id"],))
        connection.execute("DELETE FROM claims WHERE run_id = ?", (run["run_id"],))
        connection.execute("DELETE FROM evidence WHERE run_id = ?", (run["run_id"],))
        connection.execute("DELETE FROM decisions WHERE run_id = ?", (run["run_id"],))
        connection.execute("DELETE FROM policy_snapshots WHERE run_id = ?", (run["run_id"],))
        connection.execute("DELETE FROM artifacts WHERE run_id = ?", (run["run_id"],))

        for item in artifacts:
            connection.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, artifact_key_sha256, run_id, artifact_type,
                    relative_path, sha256, media_type, size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["artifact_id"],
                    item["artifact_key_sha256"],
                    run["run_id"],
                    item["artifact_type"],
                    item["relative_path"],
                    item["sha256"],
                    item["media_type"],
                    item["size_bytes"],
                ),
            )
        for item in policies:
            connection.execute(
                """
                INSERT INTO policy_snapshots(
                    policy_snapshot_id, run_id, policy_version, source,
                    sha256, imported_at, artifact_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["policy_snapshot_id"],
                    item["run_id"],
                    item["policy_version"],
                    item["source"],
                    item["sha256"],
                    item["imported_at"],
                    item["artifact_id"],
                ),
            )
        for item in decisions:
            connection.execute(
                """
                INSERT INTO decisions(
                    decision_id, run_id, decision_type, outcome, reasons_json,
                    policy_version, decided_at, artifact_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["decision_id"],
                    item["run_id"],
                    item["decision_type"],
                    item["outcome"],
                    item["reasons_json"],
                    item["policy_version"],
                    item["decided_at"],
                    item["artifact_id"],
                ),
            )

    return LedgerImportResult(
        database=database_path,
        artifact_root=root,
        run_id=str(run["run_id"]),
        run_type=str(run["run_type"]),
        artifact_count=len(artifacts),
        decision_count=len(decisions),
        policy_snapshot_count=len(policies),
    )


def _migration_errors(connection: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    try:
        rows = connection.execute(
            "SELECT version, checksum_sha256 FROM schema_migrations ORDER BY version"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        return [f"schema_migrations unavailable: {exc}"]
    expected = {version: _migration_checksum(sql) for version, sql in _MIGRATIONS}
    recorded = {row["version"]: row["checksum_sha256"] for row in rows}
    for version, checksum in expected.items():
        if version not in recorded:
            errors.append(f"missing migration: {version}")
        elif recorded[version] != checksum:
            errors.append(f"migration checksum mismatch: {version}")
    for version in sorted(set(recorded) - set(expected)):
        errors.append(f"unsupported migration present: {version}")
    return errors


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
                result["errors"].append(f"SQLite integrity_check failed: {integrity[0] if integrity else 'no result'}")
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            for row in foreign_keys:
                result["errors"].append(
                    f"foreign key violation: table={row[0]} rowid={row[1]} parent={row[2]}"
                )
            result["errors"].extend(_migration_errors(connection))
            if result["errors"]:
                return result

            runs = connection.execute("SELECT * FROM runs ORDER BY run_id").fetchall()
            for run_row in runs:
                result["runs_checked"] += 1
                root = Path(run_row["artifact_root"])
                if not root.is_dir():
                    result["errors"].append(
                        f"run {run_row['run_id']} artifact root not found: {root}"
                    )
                    continue
                identity_errors = validate_identity_manifest(root, require_complete=True)
                result["errors"].extend(
                    f"run {run_row['run_id']}: {error}" for error in identity_errors
                )
                if identity_errors:
                    continue
                manifest = load_data(root / "identity.json")
                run = manifest["run"]
                if run.get("run_id") != run_row["run_id"]:
                    result["errors"].append(f"run {run_row['run_id']}: logical run ID mismatch")
                if run.get("run_key_sha256") != run_row["run_key_sha256"]:
                    result["errors"].append(f"run {run_row['run_id']}: run key mismatch")
                if manifest.get("manifest_sha256") != run_row["manifest_sha256"]:
                    result["errors"].append(f"run {run_row['run_id']}: manifest hash mismatch")

                stored_artifacts = {
                    row["relative_path"]: dict(row)
                    for row in connection.execute(
                        "SELECT * FROM artifacts WHERE run_id = ? ORDER BY relative_path",
                        (run_row["run_id"],),
                    ).fetchall()
                }
                manifest_artifacts = {
                    item["relative_path"]: item for item in manifest.get("artifacts", [])
                }
                result["artifacts_checked"] += len(manifest_artifacts)
                for relative in sorted(set(manifest_artifacts) - set(stored_artifacts)):
                    result["errors"].append(
                        f"run {run_row['run_id']}: artifact missing from ledger: {relative}"
                    )
                for relative in sorted(set(stored_artifacts) - set(manifest_artifacts)):
                    result["errors"].append(
                        f"run {run_row['run_id']}: stale ledger artifact: {relative}"
                    )
                for relative in sorted(set(manifest_artifacts) & set(stored_artifacts)):
                    source = manifest_artifacts[relative]
                    stored = stored_artifacts[relative]
                    for field in (
                        "artifact_id",
                        "artifact_key_sha256",
                        "artifact_type",
                        "sha256",
                        "media_type",
                        "size_bytes",
                    ):
                        if source.get(field) != stored.get(field):
                            result["errors"].append(
                                f"run {run_row['run_id']}: artifact {relative} field mismatch: {field}"
                            )
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
        result["errors"].append(f"ledger verification failed: {exc}")
        return result
    result["valid"] = not result["errors"]
    return result


def rebuild_ledger(
    database: str | Path,
    directories: Iterable[str | Path],
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
        verification = verify_ledger(temporary)
        if not verification["valid"]:
            raise LedgerError("rebuilt ledger failed verification: " + "; ".join(verification["errors"]))
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    verification["database"] = str(path)
    verification["imported"] = imported
    return verification


def show_run(database: str | Path, run_id: str) -> dict[str, Any] | None:
    path = _database_path(database, create_parent=False)
    if not path.is_file():
        raise LedgerError(f"ledger database not found: {path}")
    with _connect(path, read_only=True) as connection:
        run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            return None
        artifacts = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY relative_path",
                (run_id,),
            ).fetchall()
        ]
        decisions = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM decisions WHERE run_id = ? ORDER BY decision_id",
                (run_id,),
            ).fetchall()
        ]
        policies = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM policy_snapshots WHERE run_id = ? ORDER BY policy_snapshot_id",
                (run_id,),
            ).fetchall()
        ]
    return {
        "run": dict(run),
        "artifacts": artifacts,
        "decisions": decisions,
        "policy_snapshots": policies,
    }

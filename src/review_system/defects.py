from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from .identity import canonical_json_sha256
from .io import load_data
from .validation import validate_findings_file


REGISTRY_SCHEMA_VERSION = "1.0"
DEFECT_STATUSES = (
    "OBSERVED",
    "REPRODUCED",
    "CLASSIFIED",
    "RULE_CANDIDATE",
    "MITIGATED",
    "VERIFIED",
    "CLOSED",
    "REOPENED",
)
ALLOWED_TRANSITIONS = {
    "OBSERVED": {"REPRODUCED"},
    "REPRODUCED": {"CLASSIFIED"},
    "CLASSIFIED": {"RULE_CANDIDATE", "MITIGATED"},
    "RULE_CANDIDATE": {"MITIGATED"},
    "MITIGATED": {"VERIFIED"},
    "VERIFIED": {"CLOSED"},
    "CLOSED": {"REOPENED"},
    "REOPENED": {"REPRODUCED"},
}
MATCH_METHODS = {"manual", "deterministic_signature"}
ARTIFACT_RELATIONS = {
    "reproducer",
    "diagnostic",
    "mitigation",
    "verification",
    "resolution_evidence",
}


class DefectRegistryError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DefectRegistryError(f"{field} must be a non-empty string")
    text = value.strip()
    if any(ord(character) < 32 for character in text):
        raise DefectRegistryError(f"{field} must not contain control characters")
    return text


def derive_finding_identity(run_id: str, source_finding_id: str) -> tuple[str, str]:
    natural_key = {
        "run_id": _require_text(run_id, "run_id"),
        "source_finding_id": _require_text(source_finding_id, "source_finding_id"),
    }
    digest = canonical_json_sha256(natural_key)
    return f"finding-{digest[:32]}", digest


def derive_defect_identity(project_id: str, signature: str) -> tuple[str, str]:
    natural_key = {
        "project_id": _require_text(project_id, "project_id"),
        "signature": _require_text(signature, "signature"),
    }
    digest = canonical_json_sha256(natural_key)
    return f"defect-{digest[:32]}", digest


def _registry_payload_hash(registry: dict[str, Any]) -> str:
    candidate = deepcopy(registry)
    candidate.pop("registry_sha256", None)
    return canonical_json_sha256(candidate)


def _sort_registry(registry: dict[str, Any]) -> None:
    registry["defects"] = sorted(registry.get("defects", []), key=lambda item: item["defect_id"])
    registry["finding_links"] = sorted(
        registry.get("finding_links", []),
        key=lambda item: (item["defect_id"], item["finding_id"]),
    )
    registry["events"] = sorted(
        registry.get("events", []),
        key=lambda item: (item["occurred_at"], item["event_id"]),
    )
    registry["artifact_links"] = sorted(
        registry.get("artifact_links", []),
        key=lambda item: (item["defect_id"], item["artifact_id"], item["relation"]),
    )


def validate_registry_data(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(registry, dict):
        return ["registry must contain an object"]
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {REGISTRY_SCHEMA_VERSION!r}")
    project_id = registry.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        errors.append("project_id must be a non-empty string")
        project_id = ""
    for name in ("defects", "finding_links", "events", "artifact_links"):
        if not isinstance(registry.get(name), list):
            errors.append(f"{name} must be an array")

    defects = registry.get("defects") if isinstance(registry.get("defects"), list) else []
    defect_ids: set[str] = set()
    signatures: set[str] = set()
    defect_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(defects):
        prefix = f"defects[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        try:
            expected_id, expected_key = derive_defect_identity(str(project_id), str(item.get("signature", "")))
        except DefectRegistryError as exc:
            errors.append(f"{prefix}: {exc}")
            continue
        defect_id = item.get("defect_id")
        if defect_id != expected_id:
            errors.append(f"{prefix}.defect_id does not match project_id + signature")
        if item.get("defect_key_sha256") != expected_key:
            errors.append(f"{prefix}.defect_key_sha256 does not match project_id + signature")
        if defect_id in defect_ids:
            errors.append(f"duplicate defect_id: {defect_id}")
        defect_ids.add(str(defect_id))
        signature = str(item.get("signature", ""))
        if signature in signatures:
            errors.append(f"duplicate defect signature: {signature}")
        signatures.add(signature)
        status = item.get("lifecycle_status")
        if status not in DEFECT_STATUSES:
            errors.append(f"{prefix}.lifecycle_status is invalid")
        for field in ("title", "category", "created_at", "updated_at"):
            if not isinstance(item.get(field), str) or not item.get(field):
                errors.append(f"{prefix}.{field} must be a non-empty string")
        defect_by_id[str(defect_id)] = item

    finding_links = registry.get("finding_links") if isinstance(registry.get("finding_links"), list) else []
    link_keys: set[tuple[str, str]] = set()
    for index, item in enumerate(finding_links):
        prefix = f"finding_links[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        defect_id = item.get("defect_id")
        finding_id = item.get("finding_id")
        if defect_id not in defect_ids:
            errors.append(f"{prefix}.defect_id is unknown")
        if not isinstance(finding_id, str) or not finding_id:
            errors.append(f"{prefix}.finding_id must be a non-empty string")
        key = (str(defect_id), str(finding_id))
        if key in link_keys:
            errors.append(f"duplicate finding link: {key[0]} + {key[1]}")
        link_keys.add(key)
        if item.get("match_method") not in MATCH_METHODS:
            errors.append(f"{prefix}.match_method is invalid")
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            errors.append(f"{prefix}.confidence must be between 0 and 1")
        if not isinstance(item.get("approved_by"), str) or not item.get("approved_by"):
            errors.append(f"{prefix}.approved_by must be a non-empty string")
        if not isinstance(item.get("linked_at"), str) or not item.get("linked_at"):
            errors.append(f"{prefix}.linked_at must be a non-empty string")

    artifact_links = registry.get("artifact_links") if isinstance(registry.get("artifact_links"), list) else []
    artifact_keys: set[tuple[str, str, str]] = set()
    for index, item in enumerate(artifact_links):
        prefix = f"artifact_links[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        defect_id = item.get("defect_id")
        artifact_id = item.get("artifact_id")
        relation = item.get("relation")
        if defect_id not in defect_ids:
            errors.append(f"{prefix}.defect_id is unknown")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append(f"{prefix}.artifact_id must be a non-empty string")
        if relation not in ARTIFACT_RELATIONS:
            errors.append(f"{prefix}.relation is invalid")
        key = (str(defect_id), str(artifact_id), str(relation))
        if key in artifact_keys:
            errors.append(f"duplicate artifact link: {key}")
        artifact_keys.add(key)
        if not isinstance(item.get("linked_by"), str) or not item.get("linked_by"):
            errors.append(f"{prefix}.linked_by must be a non-empty string")
        if not isinstance(item.get("linked_at"), str) or not item.get("linked_at"):
            errors.append(f"{prefix}.linked_at must be a non-empty string")

    events = registry.get("events") if isinstance(registry.get("events"), list) else []
    event_ids: set[str] = set()
    current_status: dict[str, str | None] = {defect_id: None for defect_id in defect_ids}
    for index, item in enumerate(events):
        prefix = f"events[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        event_id = item.get("event_id")
        defect_id = item.get("defect_id")
        if not isinstance(event_id, str) or not event_id:
            errors.append(f"{prefix}.event_id must be a non-empty string")
        elif event_id in event_ids:
            errors.append(f"duplicate event_id: {event_id}")
        event_ids.add(str(event_id))
        if defect_id not in defect_ids:
            errors.append(f"{prefix}.defect_id is unknown")
            continue
        for field in ("event_type", "actor", "reason", "occurred_at", "event_sha256"):
            if not isinstance(item.get(field), str) or not item.get(field):
                errors.append(f"{prefix}.{field} must be a non-empty string")
        payload = dict(item)
        recorded_hash = payload.pop("event_sha256", None)
        payload.pop("event_id", None)
        if recorded_hash != canonical_json_sha256(payload):
            errors.append(f"{prefix}.event_sha256 mismatch")
        if isinstance(recorded_hash, str) and event_id != f"event-{recorded_hash[:32]}":
            errors.append(f"{prefix}.event_id does not match event_sha256")
        status_from = item.get("status_from")
        status_to = item.get("status_to")
        event_type = item.get("event_type")
        if event_type != "CREATED" and current_status[defect_id] is None:
            errors.append(f"{prefix} occurs before the Defect CREATED event")
        if event_type == "CREATED":
            if current_status[defect_id] is not None or status_from is not None or status_to != "OBSERVED":
                errors.append(f"{prefix} has invalid CREATED transition")
            current_status[defect_id] = "OBSERVED"
        elif event_type == "TRANSITIONED":
            if current_status[defect_id] != status_from:
                errors.append(f"{prefix}.status_from does not match event history")
            if status_to not in ALLOWED_TRANSITIONS.get(str(status_from), set()):
                errors.append(f"{prefix} has an invalid lifecycle transition")
            current_status[defect_id] = str(status_to)
        elif event_type not in {"FINDING_LINKED", "ARTIFACT_LINKED"}:
            errors.append(f"{prefix}.event_type is invalid")

    resolution_evidence_defects = {
        str(item.get("defect_id"))
        for item in artifact_links
        if isinstance(item, dict) and item.get("relation") == "resolution_evidence"
    }
    for defect_id, defect in defect_by_id.items():
        if current_status.get(defect_id) != defect.get("lifecycle_status"):
            errors.append(f"defect {defect_id} lifecycle_status does not match event history")
        for field in ("root_cause", "first_seen_run_id", "last_seen_run_id", "owner", "resolution"):
            value = defect.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append(f"defect {defect_id} {field} must be null or a non-empty string")
        if defect.get("lifecycle_status") == "CLOSED":
            if not isinstance(defect.get("resolution"), str) or not defect["resolution"].strip():
                errors.append(f"defect {defect_id} CLOSED requires a resolution")
            if defect_id not in resolution_evidence_defects:
                errors.append(f"defect {defect_id} CLOSED requires resolution_evidence")

    recorded_hash = registry.get("registry_sha256")
    if not isinstance(recorded_hash, str) or recorded_hash != _registry_payload_hash(registry):
        errors.append("registry_sha256 mismatch")
    return errors


def load_defect_registry(path: str | Path) -> tuple[Path, dict[str, Any]]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise DefectRegistryError(f"defect registry not found: {target}")
    data = load_data(target)
    if not isinstance(data, dict):
        raise DefectRegistryError("defect registry must contain an object")
    errors = validate_registry_data(data)
    if errors:
        raise DefectRegistryError("invalid defect registry: " + "; ".join(errors))
    return target, data


def _write_registry(path: Path, registry: dict[str, Any]) -> None:
    _sort_registry(registry)
    registry["registry_sha256"] = _registry_payload_hash(registry)
    errors = validate_registry_data(registry)
    if errors:
        raise DefectRegistryError("refusing to write invalid defect registry: " + "; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def initialize_defect_registry(path: str | Path, project_id: str) -> Path:
    target = Path(path).expanduser().resolve()
    if target.exists():
        _, existing = load_defect_registry(target)
        if existing["project_id"] != project_id:
            raise DefectRegistryError(
                f"registry project_id mismatch: existing={existing['project_id']} requested={project_id}"
            )
        return target
    registry = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "project_id": _require_text(project_id, "project_id"),
        "defects": [],
        "finding_links": [],
        "events": [],
        "artifact_links": [],
    }
    _write_registry(target, registry)
    return target


def _event(
    defect_id: str,
    event_type: str,
    *,
    actor: str,
    reason: str,
    occurred_at: str,
    status_from: str | None = None,
    status_to: str | None = None,
) -> dict[str, Any]:
    payload = {
        "defect_id": defect_id,
        "event_type": event_type,
        "status_from": status_from,
        "status_to": status_to,
        "actor": _require_text(actor, "actor"),
        "reason": _require_text(reason, "reason"),
        "occurred_at": _require_text(occurred_at, "occurred_at"),
    }
    digest = canonical_json_sha256(payload)
    return {
        "event_id": f"event-{digest[:32]}",
        **payload,
        "event_sha256": digest,
    }


def _finding_projection(
    root: Path,
    run_id: str,
    artifacts: list[dict[str, Any]],
    imported_at: str,
) -> list[dict[str, Any]]:
    artifact = next(
        (item for item in artifacts if item.get("relative_path") == "findings.json"),
        None,
    )
    if artifact is None:
        return []
    findings_path = root / "findings.json"
    findings, failures = validate_findings_file(findings_path)
    if failures:
        details = "; ".join(f"{key}: {', '.join(value)}" for key, value in failures.items())
        raise DefectRegistryError(f"invalid findings projection: {details}")
    projected: list[dict[str, Any]] = []
    for finding in findings:
        finding_id, finding_key = derive_finding_identity(run_id, finding["id"])
        projected.append(
            {
                "finding_id": finding_id,
                "finding_key_sha256": finding_key,
                "run_id": run_id,
                "source_finding_id": finding["id"],
                "title": finding["title"],
                "category": finding["category"],
                "severity": finding["severity"],
                "confidence": finding["confidence"],
                "status": finding["status"],
                "scope_json": json.dumps(
                    finding.get("scope", {}),
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "impact": finding["impact"],
                "recommended_action": finding["recommended_action"],
                "finding_sha256": canonical_json_sha256(finding),
                "artifact_id": artifact["artifact_id"],
                "imported_at": imported_at,
            }
        )
    return sorted(projected, key=lambda item: item["finding_id"])


def project_findings_for_run(
    connection: sqlite3.Connection,
    root: Path,
    run: dict[str, Any],
    artifacts: list[dict[str, Any]],
    *,
    imported_at: str,
) -> int:
    run_id = str(run["run_id"])
    try:
        projected = _finding_projection(root, run_id, artifacts, imported_at)
    except DefectRegistryError as exc:
        from .ledger import LedgerImportError

        raise LedgerImportError(str(exc)) from exc
    current_ids = [item["finding_id"] for item in projected]
    stale = connection.execute(
        "SELECT finding_id FROM findings WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    stale_ids = [str(row["finding_id"]) for row in stale if row["finding_id"] not in current_ids]
    for finding_id in stale_ids:
        linked = connection.execute(
            "SELECT 1 FROM finding_defects WHERE finding_id = ? LIMIT 1",
            (finding_id,),
        ).fetchone()
        if linked is not None:
            from .ledger import LedgerImportError

            raise LedgerImportError(
                f"cannot remove source finding {finding_id}; it is linked to a Defect"
            )
        connection.execute("DELETE FROM findings WHERE finding_id = ?", (finding_id,))
    for item in projected:
        connection.execute(
            """
            INSERT INTO findings(
                finding_id, finding_key_sha256, run_id, source_finding_id, title,
                category, severity, confidence, status, scope_json, impact,
                recommended_action, finding_sha256, artifact_id, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(finding_id) DO UPDATE SET
                finding_key_sha256 = excluded.finding_key_sha256,
                run_id = excluded.run_id,
                source_finding_id = excluded.source_finding_id,
                title = excluded.title,
                category = excluded.category,
                severity = excluded.severity,
                confidence = excluded.confidence,
                status = excluded.status,
                scope_json = excluded.scope_json,
                impact = excluded.impact,
                recommended_action = excluded.recommended_action,
                finding_sha256 = excluded.finding_sha256,
                artifact_id = excluded.artifact_id,
                imported_at = excluded.imported_at
            """,
            tuple(item[field] for field in (
                "finding_id", "finding_key_sha256", "run_id", "source_finding_id",
                "title", "category", "severity", "confidence", "status",
                "scope_json", "impact", "recommended_action", "finding_sha256",
                "artifact_id", "imported_at",
            )),
        )
    return len(projected)


def verify_findings_for_run(
    connection: sqlite3.Connection,
    root: Path,
    run_id: str,
    artifacts: list[dict[str, Any]],
    errors: list[str],
    *,
    imported_at: str,
) -> int:
    try:
        expected = _finding_projection(root, run_id, artifacts, imported_at)
    except Exception as exc:
        errors.append(f"run {run_id}: findings projection failed: {exc}")
        return 0
    stored = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM findings WHERE run_id = ? ORDER BY finding_id",
            (run_id,),
        ).fetchall()
    ]
    expected_by_id = {item["finding_id"]: item for item in expected}
    stored_by_id = {item["finding_id"]: item for item in stored}
    for finding_id in sorted(set(expected_by_id) - set(stored_by_id)):
        errors.append(f"run {run_id} finding missing from ledger: {finding_id}")
    for finding_id in sorted(set(stored_by_id) - set(expected_by_id)):
        errors.append(f"run {run_id} stale ledger finding: {finding_id}")
    fields = (
        "finding_key_sha256", "run_id", "source_finding_id", "title", "category",
        "severity", "confidence", "status", "scope_json", "impact",
        "recommended_action", "finding_sha256", "artifact_id",
    )
    for finding_id in sorted(set(expected_by_id) & set(stored_by_id)):
        for field in fields:
            if expected_by_id[finding_id].get(field) != stored_by_id[finding_id].get(field):
                errors.append(f"run {run_id} finding {finding_id} field mismatch: {field}")
    return len(expected)


def _registry_table_rows(registry: dict[str, Any], registry_path: Path) -> dict[str, list[dict[str, Any]]]:
    project_id = registry["project_id"]
    defects: list[dict[str, Any]] = []
    for item in registry["defects"]:
        defects.append(
            {
                "defect_id": item["defect_id"],
                "defect_key_sha256": item["defect_key_sha256"],
                "project_id": project_id,
                "signature": item["signature"],
                "title": item["title"],
                "category": item["category"],
                "root_cause": item.get("root_cause"),
                "lifecycle_status": item["lifecycle_status"],
                "first_seen_run_id": item.get("first_seen_run_id"),
                "last_seen_run_id": item.get("last_seen_run_id"),
                "owner": item.get("owner"),
                "resolution": item.get("resolution"),
                "created_at": item["created_at"],
                "updated_at": item["updated_at"],
            }
        )
    return {
        "defects": defects,
        "finding_defects": list(registry["finding_links"]),
        "defect_events": list(registry["events"]),
        "defect_artifacts": list(registry["artifact_links"]),
        "registry_sources": [
            {
                "project_id": project_id,
                "registry_path": str(registry_path),
                "registry_sha256": registry["registry_sha256"],
                "imported_at": _utc_now(),
            }
        ],
    }


def sync_defect_registry(database: str | Path, registry_path: str | Path) -> dict[str, Any]:
    from .ledger import _connect, _database_path, initialize_ledger

    path, registry = load_defect_registry(registry_path)
    database_path = _database_path(database, create_parent=True)
    initialize_ledger(database_path)
    rows = _registry_table_rows(registry, path)
    project_id = registry["project_id"]
    with _connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_source = connection.execute(
            "SELECT registry_path FROM registry_sources WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if existing_source is not None and Path(existing_source["registry_path"]).resolve() != path:
            raise DefectRegistryError(
                f"project {project_id} already has a different canonical registry source: "
                f"{existing_source['registry_path']}"
            )
        for link in registry["finding_links"]:
            finding = connection.execute(
                """
                SELECT f.finding_id, r.project_id
                FROM findings f JOIN runs r ON r.run_id = f.run_id
                WHERE f.finding_id = ?
                """,
                (link["finding_id"],),
            ).fetchone()
            if finding is None:
                raise DefectRegistryError(f"registry references unknown finding: {link['finding_id']}")
            if finding["project_id"] != project_id:
                raise DefectRegistryError(f"finding belongs to another project: {link['finding_id']}")
        for link in registry["artifact_links"]:
            artifact = connection.execute(
                """
                SELECT a.artifact_id, r.project_id
                FROM artifacts a JOIN runs r ON r.run_id = a.run_id
                WHERE a.artifact_id = ?
                """,
                (link["artifact_id"],),
            ).fetchone()
            if artifact is None:
                raise DefectRegistryError(f"registry references unknown artifact: {link['artifact_id']}")
            if artifact["project_id"] != project_id:
                raise DefectRegistryError(f"artifact belongs to another project: {link['artifact_id']}")
        for defect in rows["defects"]:
            for field in ("first_seen_run_id", "last_seen_run_id"):
                run_id = defect[field]
                if run_id is None:
                    continue
                run = connection.execute(
                    "SELECT project_id FROM runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if run is None or run["project_id"] != project_id:
                    raise DefectRegistryError(f"defect references invalid {field}: {run_id}")

        connection.execute("DELETE FROM defects WHERE project_id = ?", (project_id,))
        connection.execute("DELETE FROM registry_sources WHERE project_id = ?", (project_id,))
        source = rows["registry_sources"][0]
        connection.execute(
            "INSERT INTO registry_sources(project_id, registry_path, registry_sha256, imported_at) VALUES (?, ?, ?, ?)",
            (source["project_id"], source["registry_path"], source["registry_sha256"], source["imported_at"]),
        )
        for item in rows["defects"]:
            connection.execute(
                """
                INSERT INTO defects(
                    defect_id, defect_key_sha256, project_id, signature, title, category,
                    root_cause, lifecycle_status, first_seen_run_id, last_seen_run_id,
                    owner, resolution, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(item[field] for field in (
                    "defect_id", "defect_key_sha256", "project_id", "signature", "title",
                    "category", "root_cause", "lifecycle_status", "first_seen_run_id",
                    "last_seen_run_id", "owner", "resolution", "created_at", "updated_at",
                )),
            )
        for item in rows["finding_defects"]:
            connection.execute(
                """
                INSERT INTO finding_defects(
                    finding_id, defect_id, match_method, confidence, approved_by, linked_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                tuple(item[field] for field in (
                    "finding_id", "defect_id", "match_method", "confidence", "approved_by", "linked_at",
                )),
            )
        for item in rows["defect_events"]:
            connection.execute(
                """
                INSERT INTO defect_events(
                    event_id, defect_id, event_type, status_from, status_to,
                    actor, reason, occurred_at, event_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(item[field] for field in (
                    "event_id", "defect_id", "event_type", "status_from", "status_to",
                    "actor", "reason", "occurred_at", "event_sha256",
                )),
            )
        for item in rows["defect_artifacts"]:
            connection.execute(
                """
                INSERT INTO defect_artifacts(
                    defect_id, artifact_id, relation, linked_by, linked_at, note
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item["defect_id"], item["artifact_id"], item["relation"],
                    item["linked_by"], item["linked_at"], item.get("note"),
                ),
            )
    return {
        "database": str(database_path),
        "registry": str(path),
        "project_id": project_id,
        "defect_count": len(registry["defects"]),
        "finding_link_count": len(registry["finding_links"]),
        "event_count": len(registry["events"]),
        "artifact_link_count": len(registry["artifact_links"]),
    }


def _canonical_rows(rows: list[dict[str, Any]], key_fields: tuple[str, ...], ignored: set[str] | None = None) -> list[dict[str, Any]]:
    ignored = ignored or set()
    cleaned = [{key: value for key, value in row.items() if key not in ignored} for row in rows]
    return sorted(cleaned, key=lambda item: tuple(str(item.get(field)) for field in key_fields))


def verify_defect_registry(database: str | Path, registry_path: str | Path) -> dict[str, Any]:
    from .ledger import _connect, _database_path, initialize_ledger

    path, registry = load_defect_registry(registry_path)
    database_path = _database_path(database, create_parent=False)
    result = {
        "valid": False,
        "database": str(database_path),
        "registry": str(path),
        "project_id": registry["project_id"],
        "errors": [],
    }
    if not database_path.is_file():
        result["errors"].append(f"ledger database not found: {database_path}")
        return result
    initialize_ledger(database_path)
    expected = _registry_table_rows(registry, path)
    project_id = registry["project_id"]
    try:
        with _connect(database_path, read_only=True) as connection:
            stored_source = connection.execute(
                "SELECT * FROM registry_sources WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if stored_source is None:
                result["errors"].append("registry source missing from ledger")
            else:
                if Path(stored_source["registry_path"]).resolve() != path:
                    result["errors"].append("registry source path mismatch")
                if stored_source["registry_sha256"] != registry["registry_sha256"]:
                    result["errors"].append("registry source hash mismatch")
            stored = {
                "defects": [dict(row) for row in connection.execute(
                    "SELECT * FROM defects WHERE project_id = ?", (project_id,)
                ).fetchall()],
                "finding_defects": [dict(row) for row in connection.execute(
                    """
                    SELECT fd.* FROM finding_defects fd
                    JOIN defects d ON d.defect_id = fd.defect_id
                    WHERE d.project_id = ?
                    """, (project_id,)
                ).fetchall()],
                "defect_events": [dict(row) for row in connection.execute(
                    """
                    SELECT de.* FROM defect_events de
                    JOIN defects d ON d.defect_id = de.defect_id
                    WHERE d.project_id = ?
                    """, (project_id,)
                ).fetchall()],
                "defect_artifacts": [dict(row) for row in connection.execute(
                    """
                    SELECT da.* FROM defect_artifacts da
                    JOIN defects d ON d.defect_id = da.defect_id
                    WHERE d.project_id = ?
                    """, (project_id,)
                ).fetchall()],
            }
    except (sqlite3.DatabaseError, OSError) as exc:
        result["errors"].append(f"defect registry verification failed: {exc}")
        return result
    comparisons = (
        ("defects", ("defect_id",), set()),
        ("finding_defects", ("defect_id", "finding_id"), set()),
        ("defect_events", ("event_id",), set()),
        ("defect_artifacts", ("defect_id", "artifact_id", "relation"), set()),
    )
    for name, keys, ignored in comparisons:
        if _canonical_rows(expected[name], keys, ignored) != _canonical_rows(stored[name], keys, ignored):
            result["errors"].append(f"{name} projection mismatch")
    result["valid"] = not result["errors"]
    return result


def _load_mutable_registry(path: str | Path) -> tuple[Path, dict[str, Any]]:
    target, registry = load_defect_registry(path)
    return target, deepcopy(registry)


def _sync_after_write(database: str | Path, path: Path) -> dict[str, Any]:
    return sync_defect_registry(database, path)


def create_defect(
    registry_path: str | Path,
    database: str | Path,
    *,
    signature: str,
    title: str,
    category: str,
    actor: str,
    root_cause: str | None = None,
    owner: str | None = None,
    reason: str = "Defect registered",
    occurred_at: str | None = None,
) -> dict[str, Any]:
    path, registry = _load_mutable_registry(registry_path)
    defect_id, defect_key = derive_defect_identity(registry["project_id"], signature)
    existing = next((item for item in registry["defects"] if item["defect_id"] == defect_id), None)
    if existing is not None:
        expected = {
            "signature": _require_text(signature, "signature"),
            "title": _require_text(title, "title"),
            "category": _require_text(category, "category"),
            "root_cause": root_cause.strip() if isinstance(root_cause, str) and root_cause.strip() else None,
            "owner": owner.strip() if isinstance(owner, str) and owner.strip() else None,
        }
        for field, value in expected.items():
            if existing.get(field) != value:
                raise DefectRegistryError(f"existing Defect conflicts on {field}: {defect_id}")
        _sync_after_write(database, path)
        return existing
    now = occurred_at or _utc_now()
    defect = {
        "defect_id": defect_id,
        "defect_key_sha256": defect_key,
        "signature": _require_text(signature, "signature"),
        "title": _require_text(title, "title"),
        "category": _require_text(category, "category"),
        "root_cause": root_cause.strip() if isinstance(root_cause, str) and root_cause.strip() else None,
        "lifecycle_status": "OBSERVED",
        "first_seen_run_id": None,
        "last_seen_run_id": None,
        "owner": owner.strip() if isinstance(owner, str) and owner.strip() else None,
        "resolution": None,
        "created_at": now,
        "updated_at": now,
    }
    registry["defects"].append(defect)
    registry["events"].append(
        _event(defect_id, "CREATED", actor=actor, reason=reason, occurred_at=now, status_to="OBSERVED")
    )
    _write_registry(path, registry)
    _sync_after_write(database, path)
    return defect


def _find_defect(registry: dict[str, Any], defect_id: str) -> dict[str, Any]:
    defect = next((item for item in registry["defects"] if item["defect_id"] == defect_id), None)
    if defect is None:
        raise DefectRegistryError(f"Defect not found: {defect_id}")
    return defect


def _ledger_reference(database: str | Path, table: str, identifier: str) -> dict[str, Any]:
    from .ledger import _connect, _database_path, initialize_ledger

    database_path = _database_path(database, create_parent=False)
    if not database_path.is_file():
        raise DefectRegistryError(f"ledger database not found: {database_path}")
    initialize_ledger(database_path)
    id_field = "finding_id" if table == "findings" else "artifact_id"
    with _connect(database_path, read_only=True) as connection:
        row = connection.execute(
            f"""
            SELECT t.*, r.project_id, r.run_id AS source_run_id
            FROM {table} t
            JOIN runs r ON r.run_id = t.run_id
            WHERE t.{id_field} = ?
            """,
            (identifier,),
        ).fetchone()
    if row is None:
        raise DefectRegistryError(f"{table[:-1]} not found in ledger: {identifier}")
    return dict(row)


def link_finding(
    registry_path: str | Path,
    database: str | Path,
    *,
    finding_id: str,
    defect_id: str,
    match_method: str,
    confidence: float,
    approved_by: str,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    if match_method not in MATCH_METHODS:
        raise DefectRegistryError(f"unsupported match_method: {match_method}")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise DefectRegistryError("confidence must be between 0 and 1")
    path, registry = _load_mutable_registry(registry_path)
    defect = _find_defect(registry, defect_id)
    finding = _ledger_reference(database, "findings", finding_id)
    if finding["project_id"] != registry["project_id"]:
        raise DefectRegistryError("Finding and Defect registry belong to different projects")
    now = occurred_at or _utc_now()
    link = {
        "finding_id": finding_id,
        "defect_id": defect_id,
        "match_method": match_method,
        "confidence": float(confidence),
        "approved_by": _require_text(approved_by, "approved_by"),
        "linked_at": now,
    }
    existing = next(
        (item for item in registry["finding_links"] if item["finding_id"] == finding_id and item["defect_id"] == defect_id),
        None,
    )
    if existing is not None:
        if existing != link:
            raise DefectRegistryError("Finding is already linked with different metadata")
        return existing
    registry["finding_links"].append(link)
    if defect.get("first_seen_run_id") is None:
        defect["first_seen_run_id"] = finding["source_run_id"]
    defect["last_seen_run_id"] = finding["source_run_id"]
    defect["updated_at"] = now
    registry["events"].append(
        _event(
            defect_id,
            "FINDING_LINKED",
            actor=approved_by,
            reason=f"Linked Finding {finding_id} via {match_method}",
            occurred_at=now,
        )
    )
    _write_registry(path, registry)
    _sync_after_write(database, path)
    return link


def link_defect_artifact(
    registry_path: str | Path,
    database: str | Path,
    *,
    defect_id: str,
    artifact_id: str,
    relation: str,
    linked_by: str,
    note: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    if relation not in ARTIFACT_RELATIONS:
        raise DefectRegistryError(f"unsupported artifact relation: {relation}")
    path, registry = _load_mutable_registry(registry_path)
    defect = _find_defect(registry, defect_id)
    artifact = _ledger_reference(database, "artifacts", artifact_id)
    if artifact["project_id"] != registry["project_id"]:
        raise DefectRegistryError("Artifact and Defect registry belong to different projects")
    now = occurred_at or _utc_now()
    link = {
        "defect_id": defect_id,
        "artifact_id": artifact_id,
        "relation": relation,
        "linked_by": _require_text(linked_by, "linked_by"),
        "linked_at": now,
        "note": note.strip() if isinstance(note, str) and note.strip() else None,
    }
    existing = next(
        (
            item for item in registry["artifact_links"]
            if item["defect_id"] == defect_id
            and item["artifact_id"] == artifact_id
            and item["relation"] == relation
        ),
        None,
    )
    if existing is not None:
        if existing != link:
            raise DefectRegistryError("Artifact is already linked with different metadata")
        return existing
    registry["artifact_links"].append(link)
    defect["updated_at"] = now
    registry["events"].append(
        _event(
            defect_id,
            "ARTIFACT_LINKED",
            actor=linked_by,
            reason=f"Linked Artifact {artifact_id} as {relation}",
            occurred_at=now,
        )
    )
    _write_registry(path, registry)
    _sync_after_write(database, path)
    return link


def transition_defect(
    registry_path: str | Path,
    database: str | Path,
    *,
    defect_id: str,
    target_status: str,
    actor: str,
    reason: str,
    resolution: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    path, registry = _load_mutable_registry(registry_path)
    defect = _find_defect(registry, defect_id)
    current = defect["lifecycle_status"]
    if target_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise DefectRegistryError(f"invalid Defect transition: {current} -> {target_status}")
    reason_text = _require_text(reason, "reason")
    if target_status == "REOPENED" and not reason_text:
        raise DefectRegistryError("REOPENED requires a recurrence reason")
    if target_status == "CLOSED":
        resolution_text = _require_text(resolution, "resolution")
        has_resolution_evidence = any(
            item["defect_id"] == defect_id and item["relation"] == "resolution_evidence"
            for item in registry["artifact_links"]
        )
        if not has_resolution_evidence:
            raise DefectRegistryError("CLOSED requires a resolution_evidence Artifact link")
        defect["resolution"] = resolution_text
    now = occurred_at or _utc_now()
    defect["lifecycle_status"] = target_status
    defect["updated_at"] = now
    registry["events"].append(
        _event(
            defect_id,
            "TRANSITIONED",
            actor=actor,
            reason=reason_text,
            occurred_at=now,
            status_from=current,
            status_to=target_status,
        )
    )
    _write_registry(path, registry)
    _sync_after_write(database, path)
    return defect


def show_defect(database: str | Path, defect_id: str) -> dict[str, Any] | None:
    from .ledger import _connect, _database_path, initialize_ledger

    path = _database_path(database, create_parent=False)
    if not path.is_file():
        raise DefectRegistryError(f"ledger database not found: {path}")
    initialize_ledger(path)
    with _connect(path, read_only=True) as connection:
        defect = connection.execute("SELECT * FROM defects WHERE defect_id = ?", (defect_id,)).fetchone()
        if defect is None:
            return None
        result = {"defect": dict(defect)}
        result["findings"] = [dict(row) for row in connection.execute(
            """
            SELECT f.*, fd.match_method, fd.confidence, fd.approved_by, fd.linked_at
            FROM finding_defects fd JOIN findings f ON f.finding_id = fd.finding_id
            WHERE fd.defect_id = ? ORDER BY f.finding_id
            """, (defect_id,)
        ).fetchall()]
        result["events"] = [dict(row) for row in connection.execute(
            "SELECT * FROM defect_events WHERE defect_id = ? ORDER BY occurred_at, event_id",
            (defect_id,),
        ).fetchall()]
        result["artifacts"] = [dict(row) for row in connection.execute(
            """
            SELECT a.*, da.relation, da.linked_by, da.linked_at, da.note
            FROM defect_artifacts da JOIN artifacts a ON a.artifact_id = da.artifact_id
            WHERE da.defect_id = ? ORDER BY a.artifact_id, da.relation
            """, (defect_id,)
        ).fetchall()]
    return result


def list_defects(
    database: str | Path,
    *,
    project_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    from .ledger import _connect, _database_path, initialize_ledger

    if status is not None and status not in DEFECT_STATUSES:
        raise DefectRegistryError(f"invalid lifecycle status: {status}")
    path = _database_path(database, create_parent=False)
    if not path.is_file():
        raise DefectRegistryError(f"ledger database not found: {path}")
    initialize_ledger(path)
    clauses: list[str] = []
    values: list[str] = []
    if project_id is not None:
        clauses.append("project_id = ?")
        values.append(project_id)
    if status is not None:
        clauses.append("lifecycle_status = ?")
        values.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect(path, read_only=True) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM defects" + where + " ORDER BY project_id, defect_id",
            values,
        ).fetchall()]

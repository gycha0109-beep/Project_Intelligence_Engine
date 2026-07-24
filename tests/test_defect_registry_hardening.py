import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from review_system.defect_cli import main as defect_main
from review_system.defects import (
    DefectRegistryError,
    create_defect,
    initialize_defect_registry,
    link_defect_artifact,
    load_defect_registry,
    transition_defect,
)
from review_system.identity import canonical_json_sha256
from review_system.ledger import (
    _INITIAL_SCHEMA,
    _connect,
    _migration_checksum,
    initialize_ledger,
    rebuild_ledger,
    show_run,
)
from test_defects import DefectFixture, TIMES


def rewrite_registry_hash(data: dict) -> None:
    candidate = dict(data)
    candidate.pop("registry_sha256", None)
    data["registry_sha256"] = canonical_json_sha256(candidate)


class RegistryValidationHardeningTests(unittest.TestCase):
    def _created(self, root: Path):
        directory, _ = DefectFixture.run(root)
        database = root / "ledger.sqlite"
        initialize_ledger(database)
        from review_system.ledger import import_artifact_directory

        import_artifact_directory(database, directory)
        registry = initialize_defect_registry(root / "defects.json", "demo")
        defect = create_defect(
            registry,
            database,
            signature="hardening-signature",
            title="Hardening Defect",
            category="test.hardening",
            actor="reviewer",
            occurred_at=TIMES[0],
        )
        with sqlite3.connect(database) as connection:
            artifact_id = connection.execute(
                "SELECT artifact_id FROM artifacts WHERE relative_path = 'evidence.txt'"
            ).fetchone()[0]
        return directory, database, registry, defect, artifact_id

    def test_event_id_must_match_event_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, registry, _, _ = self._created(root)
            data = json.loads(registry.read_text(encoding="utf-8"))
            data["events"][0]["event_id"] = "event-" + "0" * 32
            rewrite_registry_hash(data)
            registry.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(DefectRegistryError, "event_id does not match"):
                load_defect_registry(registry)

    def test_non_creation_event_cannot_precede_created(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, registry, defect, _ = self._created(root)
            data = json.loads(registry.read_text(encoding="utf-8"))
            payload = {
                "defect_id": defect["defect_id"],
                "event_type": "FINDING_LINKED",
                "status_from": None,
                "status_to": None,
                "actor": "reviewer",
                "reason": "Invalid pre-creation event",
                "occurred_at": "2026-07-24T06:59:00+00:00",
            }
            digest = canonical_json_sha256(payload)
            data["events"].append(
                {"event_id": f"event-{digest[:32]}", **payload, "event_sha256": digest}
            )
            data["events"].sort(key=lambda item: (item["occurred_at"], item["event_id"]))
            rewrite_registry_hash(data)
            registry.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(DefectRegistryError, "before the Defect CREATED"):
                load_defect_registry(registry)

    def test_closed_registry_requires_resolution_evidence_even_after_rehash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, database, registry, defect, artifact_id = self._created(root)
            for index, status in enumerate(
                ("REPRODUCED", "CLASSIFIED", "MITIGATED", "VERIFIED"), start=1
            ):
                transition_defect(
                    registry,
                    database,
                    defect_id=defect["defect_id"],
                    target_status=status,
                    actor="reviewer",
                    reason=f"Advance to {status}",
                    occurred_at=TIMES[index],
                )
            link_defect_artifact(
                registry,
                database,
                defect_id=defect["defect_id"],
                artifact_id=artifact_id,
                relation="resolution_evidence",
                linked_by="reviewer",
                occurred_at=TIMES[5],
            )
            transition_defect(
                registry,
                database,
                defect_id=defect["defect_id"],
                target_status="CLOSED",
                actor="reviewer",
                reason="Verified resolution",
                resolution="Resolved by deterministic remediation",
                occurred_at=TIMES[6],
            )
            data = json.loads(registry.read_text(encoding="utf-8"))
            data["artifact_links"] = []
            rewrite_registry_hash(data)
            registry.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(DefectRegistryError, "CLOSED requires resolution_evidence"):
                load_defect_registry(registry)


class LedgerAndCliHardeningTests(unittest.TestCase):
    def test_stage4_database_upgrades_from_001_to_002(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "ledger.sqlite"
            with _connect(database) as connection:
                connection.execute(
                    """
                    CREATE TABLE schema_migrations (
                        version TEXT PRIMARY KEY,
                        checksum_sha256 TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                connection.executescript(_INITIAL_SCHEMA)
                connection.execute(
                    "INSERT INTO schema_migrations(version, checksum_sha256, applied_at) VALUES (?, ?, ?)",
                    ("001", _migration_checksum(_INITIAL_SCHEMA), "2026-07-24T07:00:00+00:00"),
                )
            initialize_ledger(database)
            with sqlite3.connect(database) as connection:
                versions = [row[0] for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()]
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()}
            self.assertEqual(["001", "002"], versions)
            self.assertTrue({"findings", "defects", "defect_events"}.issubset(tables))

    def test_show_run_exposes_run_local_findings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory, run_id = DefectFixture.run(root)
            database = root / "ledger.sqlite"
            from review_system.ledger import import_artifact_directory

            import_artifact_directory(database, directory)
            result = show_run(database, run_id)
            self.assertEqual(1, len(result["findings"]))
            self.assertEqual("F-001", result["findings"][0]["source_finding_id"])

    def test_rebuild_rejects_duplicate_registry_sources_for_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory, _ = DefectFixture.run(root)
            first = initialize_defect_registry(root / "first.json", "demo")
            second = initialize_defect_registry(root / "second.json", "demo")
            with self.assertRaisesRegex(Exception, "multiple Defect registries"):
                rebuild_ledger(
                    root / "rebuilt.sqlite",
                    [directory],
                    registry_paths=[first, second],
                )

    def test_defect_cli_init_sync_verify_list_and_missing_show(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = root / "defects.json"
            database = root / "ledger.sqlite"
            initialize_ledger(database)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(0, defect_main([
                    "init", "--registry", str(registry), "--project-id", "demo"
                ]))
                self.assertEqual(0, defect_main([
                    "sync", "--registry", str(registry), "--database", str(database)
                ]))
                self.assertEqual(0, defect_main([
                    "verify", "--registry", str(registry), "--database", str(database)
                ]))
                self.assertEqual(0, defect_main(["list", "--database", str(database)]))
                self.assertEqual(4, defect_main([
                    "show", "defect-missing", "--database", str(database)
                ]))
            self.assertIn('"valid": true', stdout.getvalue())
            self.assertIn("Defect not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

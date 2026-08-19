import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from review_system.defects import (
    DefectRegistryError,
    create_defect,
    derive_defect_identity,
    initialize_defect_registry,
    link_defect_artifact,
    link_finding,
    list_defects,
    load_defect_registry,
    show_defect,
    sync_defect_registry,
    transition_defect,
    verify_defect_registry,
)
from review_system.identity import derive_run_identity, write_identity_manifest
from review_system.io import dump_json
from review_system.ledger import (
    LedgerImportError,
    import_artifact_directory,
    initialize_ledger,
    rebuild_ledger,
    verify_ledger,
)


TIMES = [f"2026-07-24T07:{minute:02d}:00+00:00" for minute in range(30)]


def finding(source_id: str = "F-001", *, title: str = "Stable observed issue") -> dict:
    return {
        "id": source_id,
        "title": title,
        "category": "test.defect.registry",
        "severity": "P2",
        "confidence": "SUPPORTED",
        "status": "OPEN",
        "scope": {"files": ["src/example.py"], "symbols": []},
        "evidence": [
            {
                "level": "E2",
                "type": "code",
                "location": "src/example.py:1",
                "summary": "The source contains a deterministic defect fixture.",
            }
        ],
        "impact": "The fixture demonstrates a Run-local Finding.",
        "recommended_action": "Track the issue across Runs.",
        "verification": ["python -m unittest"],
    }


class DefectFixture:
    @staticmethod
    def run(root: Path, name: str = "run-a", *, findings: list[dict] | None = None) -> tuple[Path, str]:
        directory = root / name
        directory.mkdir()
        identity = derive_run_identity(
            project_id="demo",
            run_type="review",
            source_revision="a" * 40,
            source_identifier=f"review://demo/{name}",
        )
        dump_json(
            directory / "run.json",
            {
                "run_id": name,
                "project_id": "demo",
                "identity": {
                    "run_type": identity.run_type,
                    "source_revision": identity.source_revision,
                    "source_identifier": identity.source_identifier,
                    "logical_run_id": identity.run_id,
                    "run_key_sha256": identity.run_key_sha256,
                },
            },
        )
        dump_json(directory / "findings.json", findings if findings is not None else [finding()])
        (directory / "evidence.txt").write_text("evidence\n", encoding="utf-8")
        write_identity_manifest(directory, identity)
        return directory, identity.run_id

    @staticmethod
    def rewrite_identity(directory: Path, run_id: str) -> None:
        run = json.loads((directory / "identity.json").read_text(encoding="utf-8"))["run"]
        identity = derive_run_identity(
            project_id=run["project_id"],
            run_type=run["run_type"],
            source_revision=run["source_revision"],
            source_identifier=run["source_identifier"],
        )
        assert identity.run_id == run_id
        write_identity_manifest(directory, identity)


class FindingProjectionTests(unittest.TestCase):
    def test_import_projects_valid_findings_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory, run_id = DefectFixture.run(root)
            database = root / "ledger.sqlite"
            import_artifact_directory(database, directory)
            import_artifact_directory(database, directory)
            with sqlite3.connect(database) as connection:
                count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
                row = connection.execute(
                    "SELECT source_finding_id, run_id FROM findings"
                ).fetchone()
            self.assertEqual(1, count)
            self.assertEqual(("F-001", run_id), row)
            self.assertTrue(verify_ledger(database)["valid"])

    def test_invalid_findings_roll_back_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            invalid = finding()
            invalid["evidence"] = []
            directory, _ = DefectFixture.run(root, findings=[invalid])
            database = root / "ledger.sqlite"
            with self.assertRaisesRegex(LedgerImportError, "invalid findings projection"):
                import_artifact_directory(database, directory)
            with sqlite3.connect(database) as connection:
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def test_unlinked_stale_finding_is_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory, run_id = DefectFixture.run(root)
            database = root / "ledger.sqlite"
            import_artifact_directory(database, directory)
            dump_json(directory / "findings.json", [])
            DefectFixture.rewrite_identity(directory, run_id)
            import_artifact_directory(database, directory)
            with sqlite3.connect(database) as connection:
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0])

    def test_linked_stale_finding_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory, run_id = DefectFixture.run(root)
            database = root / "ledger.sqlite"
            import_artifact_directory(database, directory)
            registry = initialize_defect_registry(root / "defects.json", "demo")
            defect = create_defect(
                registry,
                database,
                signature="stable-signature",
                title="Stable Defect",
                category="test.defect.registry",
                actor="reviewer",
                occurred_at=TIMES[0],
            )
            with sqlite3.connect(database) as connection:
                finding_id = connection.execute("SELECT finding_id FROM findings").fetchone()[0]
            link_finding(
                registry,
                database,
                finding_id=finding_id,
                defect_id=defect["defect_id"],
                match_method="manual",
                confidence=1.0,
                approved_by="reviewer",
                occurred_at=TIMES[1],
            )
            dump_json(directory / "findings.json", [])
            DefectFixture.rewrite_identity(directory, run_id)
            with self.assertRaisesRegex(LedgerImportError, "linked to a Defect"):
                import_artifact_directory(database, directory)


class DefectRegistryTests(unittest.TestCase):
    def _setup(self, root: Path):
        directory, _ = DefectFixture.run(root)
        database = root / "ledger.sqlite"
        import_artifact_directory(database, directory)
        registry = initialize_defect_registry(root / "defects.json", "demo")
        with sqlite3.connect(database) as connection:
            finding_id = connection.execute("SELECT finding_id FROM findings").fetchone()[0]
            artifact_id = connection.execute(
                "SELECT artifact_id FROM artifacts WHERE relative_path = 'evidence.txt'"
            ).fetchone()[0]
        return directory, database, registry, finding_id, artifact_id

    def test_defect_id_is_deterministic_and_duplicate_create_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, database, registry, _, _ = self._setup(root)
            first = create_defect(
                registry,
                database,
                signature="sig-1",
                title="Defect one",
                category="test.category",
                actor="owner",
                occurred_at=TIMES[0],
            )
            second = create_defect(
                registry,
                database,
                signature="sig-1",
                title="Defect one",
                category="test.category",
                actor="owner",
                occurred_at=TIMES[0],
            )
            expected, _ = derive_defect_identity("demo", "sig-1")
            self.assertEqual(expected, first["defect_id"])
            self.assertEqual(first, second)
            self.assertEqual(1, len(list_defects(database)))

    def test_link_and_full_lifecycle_require_resolution_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, database, registry, finding_id, artifact_id = self._setup(root)
            defect = create_defect(
                registry,
                database,
                signature="sig-lifecycle",
                title="Lifecycle Defect",
                category="test.lifecycle",
                actor="owner",
                occurred_at=TIMES[0],
            )
            link_finding(
                registry,
                database,
                finding_id=finding_id,
                defect_id=defect["defect_id"],
                match_method="deterministic_signature",
                confidence=1.0,
                approved_by="reviewer",
                occurred_at=TIMES[1],
            )
            statuses = ["REPRODUCED", "CLASSIFIED", "MITIGATED", "VERIFIED"]
            for index, status in enumerate(statuses, start=2):
                transition_defect(
                    registry,
                    database,
                    defect_id=defect["defect_id"],
                    target_status=status,
                    actor="owner",
                    reason=f"Advance to {status}",
                    occurred_at=TIMES[index],
                )
            with self.assertRaisesRegex(DefectRegistryError, "resolution_evidence"):
                transition_defect(
                    registry,
                    database,
                    defect_id=defect["defect_id"],
                    target_status="CLOSED",
                    actor="owner",
                    reason="Resolved",
                    resolution="Fixed and verified",
                    occurred_at=TIMES[7],
                )
            link_defect_artifact(
                registry,
                database,
                defect_id=defect["defect_id"],
                artifact_id=artifact_id,
                relation="resolution_evidence",
                linked_by="reviewer",
                occurred_at=TIMES[6],
            )
            closed = transition_defect(
                registry,
                database,
                defect_id=defect["defect_id"],
                target_status="CLOSED",
                actor="owner",
                reason="Resolved",
                resolution="Fixed and verified",
                occurred_at=TIMES[7],
            )
            self.assertEqual("CLOSED", closed["lifecycle_status"])
            reopened = transition_defect(
                registry,
                database,
                defect_id=defect["defect_id"],
                target_status="REOPENED",
                actor="owner",
                reason="The same signature recurred",
                occurred_at=TIMES[8],
            )
            self.assertEqual("REOPENED", reopened["lifecycle_status"])
            shown = show_defect(database, defect["defect_id"])
            self.assertEqual(9, len(shown["events"]))
            self.assertEqual(1, len(shown["findings"]))
            self.assertEqual(1, len(shown["artifacts"]))
            self.assertTrue(verify_defect_registry(database, registry)["valid"])
            self.assertTrue(verify_ledger(database)["valid"])

    def test_invalid_transition_is_rejected_without_registry_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, database, registry, _, _ = self._setup(root)
            defect = create_defect(
                registry,
                database,
                signature="sig-invalid",
                title="Invalid transition Defect",
                category="test.lifecycle",
                actor="owner",
                occurred_at=TIMES[0],
            )
            before = registry.read_bytes()
            with self.assertRaisesRegex(DefectRegistryError, "invalid Defect transition"):
                transition_defect(
                    registry,
                    database,
                    defect_id=defect["defect_id"],
                    target_status="CLOSED",
                    actor="owner",
                    reason="Skip all states",
                    resolution="No",
                    occurred_at=TIMES[1],
                )
            self.assertEqual(before, registry.read_bytes())

    def test_registry_tamper_and_ledger_projection_tamper_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, database, registry, _, _ = self._setup(root)
            defect = create_defect(
                registry,
                database,
                signature="sig-tamper",
                title="Tamper Defect",
                category="test.integrity",
                actor="owner",
                occurred_at=TIMES[0],
            )
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE defects SET title = 'tampered' WHERE defect_id = ?",
                    (defect["defect_id"],),
                )
            result = verify_defect_registry(database, registry)
            self.assertFalse(result["valid"])
            self.assertIn("defects projection mismatch", result["errors"])
            data = json.loads(registry.read_text(encoding="utf-8"))
            data["defects"][0]["title"] = "registry tampered"
            registry.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(DefectRegistryError, "registry_sha256 mismatch"):
                load_defect_registry(registry)

    def test_rebuild_projects_registry_after_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory, database, registry, _, _ = self._setup(root)
            create_defect(
                registry,
                database,
                signature="sig-rebuild",
                title="Rebuild Defect",
                category="test.rebuild",
                actor="owner",
                occurred_at=TIMES[0],
            )
            rebuilt = root / "rebuilt.sqlite"
            result = rebuild_ledger(rebuilt, [directory], registry_paths=[registry])
            self.assertTrue(result["valid"])
            self.assertEqual(1, len(result["defect_registries"]))
            self.assertEqual(1, len(list_defects(rebuilt)))
            self.assertTrue(verify_defect_registry(rebuilt, registry)["valid"])


if __name__ == "__main__":
    unittest.main()

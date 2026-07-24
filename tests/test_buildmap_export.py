import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from review_system.buildmap_export import (
    build_buildmap_export,
    verify_buildmap_export_data,
    verify_buildmap_export_source,
    write_buildmap_export,
)
from review_system.defects import (
    create_defect,
    initialize_defect_registry,
    link_defect_artifact,
    link_finding,
)
from review_system.identity import derive_run_identity, write_identity_manifest
from review_system.io import dump_json
from review_system.ledger import import_artifact_directory


class BuildMapFixture:
    def __init__(self, root: Path, *, source_identifier: str = "review://demo/buildmap-export"):
        self.root = root
        self.directory = root / "run"
        self.directory.mkdir()
        dump_json(
            self.directory / "run.json",
            {
                "run_id": "legacy-buildmap-run",
                "project_id": "demo",
                "mode": "full",
                "metrics": {},
            },
        )
        (self.directory / "evidence.txt").write_text("public evidence\n", encoding="utf-8")
        dump_json(
            self.directory / "github-source.json",
            {
                "discussion": [
                    {"body": "PRIVATE_GITHUB_DISCUSSION", "author": "private-user"}
                ]
            },
        )
        (self.directory / "change.patch").write_text("SECRET_PATCH_BODY\n", encoding="utf-8")
        (self.directory / "access-token.log").write_text("SECRET_TOKEN_VALUE\n", encoding="utf-8")
        dump_json(self.directory / "private-reference.json", {"secret": "PRIVATE_REFERENCE"})
        (self.directory / "gate-policy.yml").write_text("version: '1.0'\n", encoding="utf-8")
        dump_json(
            self.directory / "findings.json",
            [
                {
                    "id": "FINDING-001",
                    "title": "PRIVATE_FINDING_TITLE",
                    "category": "test.buildmap.export",
                    "severity": "P2",
                    "confidence": "HYPOTHESIS",
                    "status": "OPEN",
                    "scope": {"files": ["src/demo.py"], "symbols": []},
                    "evidence": [
                        {
                            "level": "E1",
                            "type": "code",
                            "location": "src/demo.py:1",
                            "summary": "PRIVATE_FINDING_EVIDENCE",
                        }
                    ],
                    "impact": "PRIVATE_FINDING_IMPACT",
                    "recommended_action": "PRIVATE_FINDING_ACTION",
                    "verification": [],
                }
            ],
        )
        dump_json(
            self.directory / "gate-result.json",
            {
                "decision": "PASS",
                "generated_at": "2026-07-24T00:00:00+00:00",
                "triggered": {
                    "pass": [
                        {
                            "id": "G-P001",
                            "message": "PRIVATE_DECISION_MESSAGE",
                        }
                    ]
                },
                "policy": {"version": "1.0", "source": "gate-policy.yml"},
            },
        )
        identity = derive_run_identity(
            project_id="demo",
            run_type="review",
            source_revision="a" * 40,
            source_identifier=source_identifier,
        )
        write_identity_manifest(self.directory, identity)
        self.run_id = identity.run_id
        self.database = root / "ledger.sqlite3"
        import_artifact_directory(self.database, self.directory, expected_run_type="review")
        self._insert_claim_and_evidence()
        self._create_and_link_defect()

    def _insert_claim_and_evidence(self) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            artifact = connection.execute(
                "SELECT artifact_id FROM artifacts WHERE run_id = ? AND relative_path = 'evidence.txt'",
                (self.run_id,),
            ).fetchone()
            raw_artifact = connection.execute(
                "SELECT artifact_id FROM artifacts WHERE run_id = ? AND relative_path = 'github-source.json'",
                (self.run_id,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO claims(claim_id, run_id, claim_type, statement, scope_json, status, policy_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "claim-demo",
                    self.run_id,
                    "required_tests",
                    "PRIVATE_CLAIM_STATEMENT",
                    '{"files":["private/path.py"]}',
                    "SUPPORTED",
                    "1.0",
                ),
            )
            connection.execute(
                """
                INSERT INTO evidence(
                    evidence_id, run_id, evidence_level, evidence_type, summary,
                    result, artifact_id, locator, producer, producer_version, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "evidence-public",
                    self.run_id,
                    "E3",
                    "test",
                    "PRIVATE_EVIDENCE_SUMMARY",
                    "PRIVATE_RESULT_TEXT",
                    artifact["artifact_id"],
                    "/absolute/private/locator",
                    "private-producer",
                    "1.0",
                    "2026-07-24T00:00:00Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO evidence(
                    evidence_id, run_id, evidence_level, evidence_type, summary,
                    result, artifact_id, locator, producer, producer_version, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "evidence-redacted",
                    self.run_id,
                    "E1",
                    "discussion",
                    "PRIVATE_DISCUSSION_SUMMARY",
                    None,
                    raw_artifact["artifact_id"],
                    None,
                    None,
                    None,
                    None,
                ),
            )
            connection.execute(
                "INSERT INTO claim_evidence(claim_id, evidence_id, relation, strength) VALUES (?, ?, ?, ?)",
                ("claim-demo", "evidence-public", "supports", "strong"),
            )

    def _create_and_link_defect(self) -> None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "SELECT finding_id FROM findings WHERE run_id = ?",
                (self.run_id,),
            ).fetchone()
        self.finding_id = str(row[0])
        registry = self.root / "defect-registry.json"
        initialize_defect_registry(registry, "demo")
        defect = create_defect(
            registry,
            self.database,
            signature="PRIVATE_DEFECT_SIGNATURE",
            title="PRIVATE_DEFECT_TITLE",
            category="test.buildmap.export",
            actor="reviewer",
            root_cause="PRIVATE_ROOT_CAUSE",
            occurred_at="2026-07-24T00:10:00Z",
        )
        self.defect_id = str(defect["defect_id"])
        link_finding(
            registry,
            self.database,
            finding_id=self.finding_id,
            defect_id=self.defect_id,
            match_method="manual",
            confidence=1.0,
            approved_by="reviewer",
            occurred_at="2026-07-24T00:11:00Z",
        )
        with sqlite3.connect(self.database) as connection:
            public_artifact = connection.execute(
                "SELECT artifact_id FROM artifacts WHERE run_id = ? AND relative_path = 'evidence.txt'",
                (self.run_id,),
            ).fetchone()[0]
            private_artifact = connection.execute(
                "SELECT artifact_id FROM artifacts WHERE run_id = ? AND relative_path = 'github-source.json'",
                (self.run_id,),
            ).fetchone()[0]
        link_defect_artifact(
            registry,
            self.database,
            defect_id=self.defect_id,
            artifact_id=str(public_artifact),
            relation="diagnostic",
            linked_by="reviewer",
            note="PRIVATE_DEFECT_ARTIFACT_NOTE",
            occurred_at="2026-07-24T00:12:00Z",
        )
        link_defect_artifact(
            registry,
            self.database,
            defect_id=self.defect_id,
            artifact_id=str(private_artifact),
            relation="reproducer",
            linked_by="reviewer",
            note="PRIVATE_DISCUSSION_ARTIFACT_NOTE",
            occurred_at="2026-07-24T00:13:00Z",
        )

    def export(self, *, generated_at: str = "2026-07-24T12:00:00Z", redaction_paths=()):
        return build_buildmap_export(
            self.database,
            project_id="demo",
            run_id=self.run_id,
            redaction_paths=redaction_paths,
            generated_at=generated_at,
        )


class BuildMapExportTests(unittest.TestCase):
    def test_export_is_valid_reference_only_and_source_verifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export(redaction_paths=["private-*.json"])
            self.assertEqual([], verify_buildmap_export_data(export))
            self.assertEqual([], verify_buildmap_export_source(export, fixture.database))
            payload = json.dumps(export, sort_keys=True)
            for forbidden in (
                "PRIVATE_GITHUB_DISCUSSION",
                "PRIVATE_DECISION_MESSAGE",
                "PRIVATE_CLAIM_STATEMENT",
                "PRIVATE_EVIDENCE_SUMMARY",
                "PRIVATE_RESULT_TEXT",
                "SECRET_PATCH_BODY",
                "SECRET_TOKEN_VALUE",
                "PRIVATE_FINDING_TITLE",
                "PRIVATE_FINDING_EVIDENCE",
                "PRIVATE_FINDING_IMPACT",
                "PRIVATE_FINDING_ACTION",
                "PRIVATE_DEFECT_SIGNATURE",
                "PRIVATE_DEFECT_TITLE",
                "PRIVATE_ROOT_CAUSE",
                "PRIVATE_DEFECT_ARTIFACT_NOTE",
                "PRIVATE_DISCUSSION_ARTIFACT_NOTE",
                str(fixture.directory),
                "/absolute/private/locator",
            ):
                self.assertNotIn(forbidden, payload)
            self.assertFalse(export["redaction"]["content_included"])
            self.assertFalse(export["redaction"]["raw_github_discussion_included"])
            self.assertEqual(
                [{"group": "pass", "reason_id": "G-P001"}],
                export["projection"]["decisions"][0]["reason_refs"],
            )
            finding = export["projection"]["findings"][0]
            self.assertEqual(fixture.finding_id, finding["finding_id"])
            self.assertEqual([fixture.defect_id], finding["defect_ids"])
            defect = export["projection"]["defects"][0]
            self.assertEqual(fixture.defect_id, defect["defect_id"])
            self.assertEqual(2, len(defect["artifact_refs"]))
            self.assertEqual(
                [False, True],
                [item["artifact_redacted"] for item in defect["artifact_refs"]],
            )
            redacted_evidence = next(
                item
                for item in export["projection"]["evidence"]
                if item["evidence_id"] == "evidence-redacted"
            )
            self.assertTrue(redacted_evidence["artifact_redacted"])

    def test_export_id_is_stable_across_time_and_idempotent_reimport(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            first = fixture.export(generated_at="2026-07-24T12:00:00Z")
            import_artifact_directory(fixture.database, fixture.directory, expected_run_type="review")
            second = fixture.export(generated_at="2026-07-25T12:00:00Z")
            self.assertEqual(first["export_id"], second["export_id"])
            self.assertEqual(first["projection_sha256"], second["projection_sha256"])
            self.assertEqual(first["source_fingerprint_sha256"], second["source_fingerprint_sha256"])
            self.assertNotEqual(first["export_sha256"], second["export_sha256"])

    def test_default_and_custom_redaction_counts_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export(redaction_paths=["private-*.json"])
            paths = {item["relative_path"] for item in export["projection"]["artifacts"]}
            self.assertNotIn("github-source.json", paths)
            self.assertNotIn("change.patch", paths)
            self.assertNotIn("access-token.log", paths)
            self.assertNotIn("private-reference.json", paths)
            omitted = export["redaction"]["omitted_artifacts"]
            self.assertEqual(1, omitted["raw_github_discussion"])
            self.assertEqual(2, omitted["sensitive_path"])
            self.assertEqual(1, omitted["custom_pattern"])

    def test_unsafe_external_source_identifier_is_replaced_by_pie_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(
                Path(tmp),
                source_identifier="https://user:password@example.com/private?token=secret",
            )
            export = fixture.export()
            self.assertTrue(export["redaction"]["source_identifier_redacted"])
            self.assertEqual(export["source"]["pie_run_uri"], export["source"]["source_identifier"])
            self.assertNotIn("password", json.dumps(export))
            self.assertNotIn("token=secret", json.dumps(export))

    def test_buildmap_consumer_can_idempotently_import_reference_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export()
            consumer_store: dict[str, dict] = {}

            def consume(document: dict) -> None:
                self.assertEqual([], verify_buildmap_export_data(document))
                consumer_store[document["export_id"]] = {
                    "project_id": document["project_id"],
                    "run_id": document["source"]["run_id"],
                    "projection_sha256": document["projection_sha256"],
                    "artifact_refs": {
                        item["artifact_id"]: item["sha256"]
                        for item in document["projection"]["artifacts"]
                    },
                    "decision_refs": [
                        item["decision_id"]
                        for item in document["projection"]["decisions"]
                    ],
                }

            consume(export)
            consume(fixture.export(generated_at="2026-07-25T12:00:00Z"))
            self.assertEqual(1, len(consumer_store))
            stored = consumer_store[export["export_id"]]
            self.assertEqual(fixture.run_id, stored["run_id"])
            self.assertTrue(stored["artifact_refs"])
            self.assertTrue(stored["decision_refs"])

    def test_write_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export()
            output = Path(tmp) / "buildmap-export.json"
            self.assertEqual(output.resolve(), write_buildmap_export(output, export))
            self.assertEqual(export, json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()

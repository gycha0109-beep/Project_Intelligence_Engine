from pathlib import Path
import json


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f"missing patch anchor: {label}")
    if text.count(old) != 1:
        raise RuntimeError(f"ambiguous patch anchor: {label}")
    return text.replace(old, new, 1)


root = Path(__file__).resolve().parents[1]

for schema_path in (
    root / "schemas/buildmap-export.schema.json",
    root / "src/review_system/assets/schemas/buildmap-export.schema.json",
):
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    defs = schema["$defs"]
    if "defectArtifactReference" not in defs:
        raise RuntimeError(f"partial schema hardening missing from {schema_path}")
    if "artifact_refs" not in defs["defect"]["required"]:
        raise RuntimeError(f"Defect artifact_refs requirement missing from {schema_path}")

module_path = root / "src/review_system/buildmap_export.py"
module = module_path.read_text(encoding="utf-8")
module = replace_once(
    module,
    '''        defects = _rows(
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
        decisions = _rows(
''',
    '''        defects = _rows(
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
''',
    "load Defect Artifact references",
)
module = replace_once(
    module,
    '        "finding_defects": finding_defects,\n'
    '        "defects": defects,\n'
    '        "decisions": decisions,\n',
    '        "finding_defects": finding_defects,\n'
    '        "defects": defects,\n'
    '        "defect_artifacts": defect_artifacts,\n'
    '        "decisions": decisions,\n',
    "return Defect Artifact rows",
)
module = replace_once(
    module,
    '        "defects": without(rows["defects"], set()),\n'
    '        "decisions": without(rows["decisions"], set()),\n',
    '        "defects": without(rows["defects"], set()),\n'
    '        "defect_artifacts": without(rows["defect_artifacts"], set()),\n'
    '        "decisions": without(rows["decisions"], set()),\n',
    "Defect Artifact source fingerprint",
)
module = replace_once(
    module,
    '    defects = [\n        {\n',
    '    artifact_refs_by_defect: dict[str, list[dict[str, Any]]] = {}\n'
    '    for link in rows["defect_artifacts"]:\n'
    '        artifact_id, redacted = _artifact_reference(link.get("artifact_id"), included_artifacts)\n'
    '        if artifact_id is None:\n'
    '            continue\n'
    '        artifact_refs_by_defect.setdefault(str(link["defect_id"]), []).append(\n'
    '            {\n'
    '                "artifact_id": artifact_id,\n'
    '                "relation": str(link["relation"]),\n'
    '                "artifact_redacted": redacted,\n'
    '            }\n'
    '        )\n'
    '    for refs in artifact_refs_by_defect.values():\n'
    '        refs.sort(key=lambda item: (item["artifact_id"], item["relation"]))\n'
    '    defects = [\n'
    '        {\n',
    "Defect Artifact projection index",
)
module = replace_once(
    module,
    '            "last_seen_run_id": row.get("last_seen_run_id"),\n'
    '        }\n'
    '        for row in rows["defects"]\n',
    '            "last_seen_run_id": row.get("last_seen_run_id"),\n'
    '            "artifact_refs": artifact_refs_by_defect.get(str(row["defect_id"]), []),\n'
    '        }\n'
    '        for row in rows["defects"]\n',
    "Defect Artifact projection field",
)
module = replace_once(
    module,
    '    decisions = projection.get("decisions")\n',
    '    defects = projection.get("defects")\n'
    '    if isinstance(defects, list):\n'
    '        for index, item in enumerate(defects):\n'
    '            if not isinstance(item, dict):\n'
    '                continue\n'
    '            refs = item.get("artifact_refs")\n'
    '            if not isinstance(refs, list):\n'
    '                errors.append(f"projection.defects[{index}].artifact_refs canonical mismatch")\n'
    '                continue\n'
    '            canonical: list[dict[str, Any]] = []\n'
    '            seen: set[tuple[str, str]] = set()\n'
    '            malformed = False\n'
    '            for ref in refs:\n'
    '                if not isinstance(ref, dict):\n'
    '                    malformed = True\n'
    '                    continue\n'
    '                artifact_id = ref.get("artifact_id")\n'
    '                relation = ref.get("relation")\n'
    '                if not isinstance(artifact_id, str) or not artifact_id or not isinstance(relation, str) or not relation:\n'
    '                    malformed = True\n'
    '                    continue\n'
    '                key = (artifact_id, relation)\n'
    '                if key in seen:\n'
    '                    malformed = True\n'
    '                    continue\n'
    '                seen.add(key)\n'
    '                canonical.append(\n'
    '                    {\n'
    '                        "artifact_id": artifact_id,\n'
    '                        "relation": relation,\n'
    '                        "artifact_redacted": artifact_id not in artifact_ids,\n'
    '                    }\n'
    '                )\n'
    '            canonical.sort(key=lambda ref: (ref["artifact_id"], ref["relation"]))\n'
    '            if malformed or refs != canonical:\n'
    '                errors.append(f"projection.defects[{index}].artifact_refs canonical mismatch")\n\n'
    '    decisions = projection.get("decisions")\n',
    "Defect Artifact canonical verification",
)
module_path.write_text(module, encoding="utf-8")

test_path = root / "tests/test_buildmap_export.py"
test = test_path.read_text(encoding="utf-8")
test = replace_once(
    test,
    'from review_system.defects import create_defect, initialize_defect_registry, link_finding\n',
    'from review_system.defects import (\n'
    '    create_defect,\n'
    '    initialize_defect_registry,\n'
    '    link_defect_artifact,\n'
    '    link_finding,\n'
    ')\n',
    "Defect Artifact fixture import",
)
test = replace_once(
    test,
    '        link_finding(\n'
    '            registry,\n'
    '            self.database,\n'
    '            finding_id=self.finding_id,\n'
    '            defect_id=self.defect_id,\n'
    '            match_method="manual",\n'
    '            confidence=1.0,\n'
    '            approved_by="reviewer",\n'
    '            occurred_at="2026-07-24T00:11:00Z",\n'
    '        )\n',
    '        link_finding(\n'
    '            registry,\n'
    '            self.database,\n'
    '            finding_id=self.finding_id,\n'
    '            defect_id=self.defect_id,\n'
    '            match_method="manual",\n'
    '            confidence=1.0,\n'
    '            approved_by="reviewer",\n'
    '            occurred_at="2026-07-24T00:11:00Z",\n'
    '        )\n'
    '        with sqlite3.connect(self.database) as connection:\n'
    '            public_artifact = connection.execute(\n'
    '                "SELECT artifact_id FROM artifacts WHERE run_id = ? AND relative_path = \'evidence.txt\'",\n'
    '                (self.run_id,),\n'
    '            ).fetchone()[0]\n'
    '            private_artifact = connection.execute(\n'
    '                "SELECT artifact_id FROM artifacts WHERE run_id = ? AND relative_path = \'github-source.json\'",\n'
    '                (self.run_id,),\n'
    '            ).fetchone()[0]\n'
    '        link_defect_artifact(\n'
    '            registry,\n'
    '            self.database,\n'
    '            defect_id=self.defect_id,\n'
    '            artifact_id=str(public_artifact),\n'
    '            relation="diagnostic",\n'
    '            linked_by="reviewer",\n'
    '            note="PRIVATE_DEFECT_ARTIFACT_NOTE",\n'
    '            occurred_at="2026-07-24T00:12:00Z",\n'
    '        )\n'
    '        link_defect_artifact(\n'
    '            registry,\n'
    '            self.database,\n'
    '            defect_id=self.defect_id,\n'
    '            artifact_id=str(private_artifact),\n'
    '            relation="reproducer",\n'
    '            linked_by="reviewer",\n'
    '            note="PRIVATE_DISCUSSION_ARTIFACT_NOTE",\n'
    '            occurred_at="2026-07-24T00:13:00Z",\n'
    '        )\n',
    "Defect Artifact fixture links",
)
test = replace_once(
    test,
    '                "PRIVATE_ROOT_CAUSE",\n                str(fixture.directory),\n',
    '                "PRIVATE_ROOT_CAUSE",\n'
    '                "PRIVATE_DEFECT_ARTIFACT_NOTE",\n'
    '                "PRIVATE_DISCUSSION_ARTIFACT_NOTE",\n'
    '                str(fixture.directory),\n',
    "Defect Artifact free-text exclusion",
)
test = replace_once(
    test,
    '            self.assertEqual(fixture.defect_id, export["projection"]["defects"][0]["defect_id"])\n',
    '            defect = export["projection"]["defects"][0]\n'
    '            self.assertEqual(fixture.defect_id, defect["defect_id"])\n'
    '            self.assertEqual(2, len(defect["artifact_refs"]))\n'
    '            self.assertEqual(\n'
    '                [False, True],\n'
    '                [item["artifact_redacted"] for item in defect["artifact_refs"]],\n'
    '            )\n',
    "Defect Artifact export assertion",
)
test_path.write_text(test, encoding="utf-8")

hardening_path = root / "tests/test_buildmap_export_hardening.py"
hardening = hardening_path.read_text(encoding="utf-8")
hardening = replace_once(
    hardening,
    '    def test_rehashed_path_traversal_is_rejected(self):\n',
    '    def test_rehashed_defect_artifact_links_are_source_verified(self):\n'
    '        with tempfile.TemporaryDirectory() as tmp:\n'
    '            fixture = BuildMapFixture(Path(tmp))\n'
    '            export = fixture.export()\n'
    '            export["projection"]["defects"][0]["artifact_refs"] = []\n'
    '            rehash_export(export)\n'
    '            self.assertEqual([], verify_buildmap_export_data(export))\n'
    '            self.assertIn(\n'
    '                "BuildMap source projection mismatch",\n'
    '                verify_buildmap_export_source(export, fixture.database),\n'
    '            )\n\n'
    '    def test_rehashed_path_traversal_is_rejected(self):\n',
    "Defect Artifact source replay test",
)
hardening_path.write_text(hardening, encoding="utf-8")

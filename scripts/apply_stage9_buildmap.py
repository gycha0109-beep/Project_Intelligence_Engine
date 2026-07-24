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

# Existing additive CLI integration remains idempotent.
cli_path = root / "src/review_system/cli.py"
cli = cli_path.read_text(encoding="utf-8")
cli = replace_once(
    cli,
    "from .baseline import verify_snapshot_file, write_snapshot\n",
    "from .baseline import verify_snapshot_file, write_snapshot\n"
    "from .buildmap_cli import cmd_export as cmd_export_buildmap, cmd_validate as cmd_validate_buildmap_export\n",
    "CLI BuildMap adapter import",
)
cli = replace_once(
    cli,
    "    p.set_defaults(func=cmd_analyze_pr)\n    return parser\n",
    "    p.set_defaults(func=cmd_analyze_pr)\n\n"
    "    p = sub.add_parser(\"export-buildmap\", help=\"Export one verified PIE Run as a metadata-only BuildMap reference\")\n"
    "    p.add_argument(\"--ledger\", required=True)\n"
    "    p.add_argument(\"--project-id\", required=True)\n"
    "    p.add_argument(\"--run-id\", required=True)\n"
    "    p.add_argument(\"--output\", required=True)\n"
    "    p.add_argument(\"--redact-path\", action=\"append\", default=[])\n"
    "    p.add_argument(\"--generated-at\")\n"
    "    p.set_defaults(func=cmd_export_buildmap)\n\n"
    "    p = sub.add_parser(\"validate-buildmap-export\", help=\"Validate a BuildMap export and optionally replay it against a Ledger\")\n"
    "    p.add_argument(\"export\")\n"
    "    p.add_argument(\"--ledger\")\n"
    "    p.set_defaults(func=cmd_validate_buildmap_export)\n"
    "    return parser\n",
    "CLI BuildMap commands",
)
cli_path.write_text(cli, encoding="utf-8")

pyproject_path = root / "pyproject.toml"
pyproject = pyproject_path.read_text(encoding="utf-8")
pyproject = replace_once(
    pyproject,
    'pie-reground = "review_system.reground_cli:main"\n',
    'pie-reground = "review_system.reground_cli:main"\n'
    'pie-buildmap = "review_system.buildmap_cli:main"\n',
    "pie-buildmap entrypoint",
)
pyproject_path.write_text(pyproject, encoding="utf-8")

# Schema: preserve Finding -> Defect references without free-text duplication.
for schema_path in (
    root / "schemas/buildmap-export.schema.json",
    root / "src/review_system/assets/schemas/buildmap-export.schema.json",
):
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    finding = schema["$defs"]["finding"]
    required = finding["required"]
    if "defect_ids" not in required:
        required.insert(required.index("finding_sha256"), "defect_ids")
    finding["properties"]["defect_ids"] = {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
        "uniqueItems": True,
    }
    schema_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

module_path = root / "src/review_system/buildmap_export.py"
module = module_path.read_text(encoding="utf-8")
module = replace_once(
    module,
    '        "finding_defects": without(rows["finding_defects"], {"linked_at"}),\n',
    '        "finding_defects": without(rows["finding_defects"], set()),\n',
    "Finding-Defect source fingerprint metadata",
)
module = replace_once(
    module,
    '    findings = []\n    for row in rows["findings"]:\n',
    '    defect_ids_by_finding: dict[str, set[str]] = {}\n'
    '    for link in rows["finding_defects"]:\n'
    '        finding_id = str(link["finding_id"])\n'
    '        defect_ids_by_finding.setdefault(finding_id, set()).add(str(link["defect_id"]))\n'
    '    findings = []\n'
    '    for row in rows["findings"]:\n',
    "Finding-Defect projection index",
)
module = replace_once(
    module,
    '                "status": str(row["status"]),\n'
    '                "finding_sha256": str(row["finding_sha256"]),\n',
    '                "status": str(row["status"]),\n'
    '                "defect_ids": sorted(defect_ids_by_finding.get(str(row["finding_id"]), set())),\n'
    '                "finding_sha256": str(row["finding_sha256"]),\n',
    "Finding defect_ids projection",
)
old_reason_validation = '''            refs = item.get("reason_refs")
            if isinstance(refs, list):
                canonical = sorted(
                    refs,
                    key=lambda ref: (
                        str(ref.get("group")) if isinstance(ref, dict) else "",
                        str(ref.get("reason_id")) if isinstance(ref, dict) else "",
                    ),
                )
                if refs != canonical or len({(ref.get("group"), ref.get("reason_id")) for ref in refs if isinstance(ref, dict)}) != len(refs):
                    errors.append(f"projection.decisions[{index}].reason_refs canonical mismatch")
'''
new_reason_validation = '''            refs = item.get("reason_refs")
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
'''
module = replace_once(
    module,
    old_reason_validation,
    new_reason_validation,
    "safe reason_refs canonical verification",
)
module = replace_once(
    module,
    '    decisions = projection.get("decisions")\n',
    '    findings = projection.get("findings")\n'
    '    if isinstance(findings, list):\n'
    '        for index, item in enumerate(findings):\n'
    '            if not isinstance(item, dict):\n'
    '                continue\n'
    '            defect_ids = item.get("defect_ids")\n'
    '            if not isinstance(defect_ids, list) or not all(isinstance(value, str) and value for value in defect_ids):\n'
    '                errors.append(f"projection.findings[{index}].defect_ids canonical mismatch")\n'
    '            elif defect_ids != sorted(set(defect_ids)):\n'
    '                errors.append(f"projection.findings[{index}].defect_ids canonical mismatch")\n\n'
    '    decisions = projection.get("decisions")\n',
    "Finding defect_ids canonical validation",
)
module_path.write_text(module, encoding="utf-8")

# Integration fixture: add a valid Finding and a linked Defect with private free text.
test_path = root / "tests/test_buildmap_export.py"
test = test_path.read_text(encoding="utf-8")
test = replace_once(
    test,
    'from review_system.identity import derive_run_identity, write_identity_manifest\n',
    'from review_system.defects import create_defect, initialize_defect_registry, link_finding\n'
    'from review_system.identity import derive_run_identity, write_identity_manifest\n',
    "Defect fixture imports",
)
test = replace_once(
    test,
    '        dump_json(\n'
    '            self.directory / "gate-result.json",\n',
    '        dump_json(\n'
    '            self.directory / "findings.json",\n'
    '            [\n'
    '                {\n'
    '                    "id": "FINDING-001",\n'
    '                    "title": "PRIVATE_FINDING_TITLE",\n'
    '                    "category": "test.buildmap.export",\n'
    '                    "severity": "P2",\n'
    '                    "confidence": "HYPOTHESIS",\n'
    '                    "status": "OPEN",\n'
    '                    "scope": {"files": ["src/demo.py"], "symbols": []},\n'
    '                    "evidence": [\n'
    '                        {\n'
    '                            "level": "E1",\n'
    '                            "type": "code",\n'
    '                            "location": "src/demo.py:1",\n'
    '                            "summary": "PRIVATE_FINDING_EVIDENCE",\n'
    '                        }\n'
    '                    ],\n'
    '                    "impact": "PRIVATE_FINDING_IMPACT",\n'
    '                    "recommended_action": "PRIVATE_FINDING_ACTION",\n'
    '                    "verification": [],\n'
    '                }\n'
    '            ],\n'
    '        )\n'
    '        dump_json(\n'
    '            self.directory / "gate-result.json",\n',
    "Finding fixture artifact",
)
test = replace_once(
    test,
    '        self._insert_claim_and_evidence()\n\n'
    '    def _insert_claim_and_evidence(self) -> None:\n',
    '        self._insert_claim_and_evidence()\n'
    '        self._create_and_link_defect()\n\n'
    '    def _insert_claim_and_evidence(self) -> None:\n',
    "Defect fixture lifecycle call",
)
test = replace_once(
    test,
    '    def export(self, *, generated_at: str = "2026-07-24T12:00:00Z", redaction_paths=()):\n',
    '    def _create_and_link_defect(self) -> None:\n'
    '        with sqlite3.connect(self.database) as connection:\n'
    '            row = connection.execute(\n'
    '                "SELECT finding_id FROM findings WHERE run_id = ?",\n'
    '                (self.run_id,),\n'
    '            ).fetchone()\n'
    '        self.finding_id = str(row[0])\n'
    '        registry = self.root / "defect-registry.json"\n'
    '        initialize_defect_registry(registry, "demo")\n'
    '        defect = create_defect(\n'
    '            registry,\n'
    '            self.database,\n'
    '            signature="PRIVATE_DEFECT_SIGNATURE",\n'
    '            title="PRIVATE_DEFECT_TITLE",\n'
    '            category="test.buildmap.export",\n'
    '            actor="reviewer",\n'
    '            root_cause="PRIVATE_ROOT_CAUSE",\n'
    '            occurred_at="2026-07-24T00:10:00Z",\n'
    '        )\n'
    '        self.defect_id = str(defect["defect_id"])\n'
    '        link_finding(\n'
    '            registry,\n'
    '            self.database,\n'
    '            finding_id=self.finding_id,\n'
    '            defect_id=self.defect_id,\n'
    '            match_method="manual",\n'
    '            confidence=1.0,\n'
    '            approved_by="reviewer",\n'
    '            occurred_at="2026-07-24T00:11:00Z",\n'
    '        )\n\n'
    '    def export(self, *, generated_at: str = "2026-07-24T12:00:00Z", redaction_paths=()):\n',
    "Defect fixture helper",
)
test = replace_once(
    test,
    '                "SECRET_TOKEN_VALUE",\n'
    '                str(fixture.directory),\n',
    '                "SECRET_TOKEN_VALUE",\n'
    '                "PRIVATE_FINDING_TITLE",\n'
    '                "PRIVATE_FINDING_EVIDENCE",\n'
    '                "PRIVATE_FINDING_IMPACT",\n'
    '                "PRIVATE_FINDING_ACTION",\n'
    '                "PRIVATE_DEFECT_SIGNATURE",\n'
    '                "PRIVATE_DEFECT_TITLE",\n'
    '                "PRIVATE_ROOT_CAUSE",\n'
    '                str(fixture.directory),\n',
    "Private Finding and Defect content exclusions",
)
test = replace_once(
    test,
    '            redacted_evidence = next(\n',
    '            finding = export["projection"]["findings"][0]\n'
    '            self.assertEqual(fixture.finding_id, finding["finding_id"])\n'
    '            self.assertEqual([fixture.defect_id], finding["defect_ids"])\n'
    '            self.assertEqual(fixture.defect_id, export["projection"]["defects"][0]["defect_id"])\n'
    '            redacted_evidence = next(\n',
    "Finding-Defect export assertion",
)
test_path.write_text(test, encoding="utf-8")

hardening_path = root / "tests/test_buildmap_export_hardening.py"
hardening = hardening_path.read_text(encoding="utf-8")
hardening = hardening.replace(
    '            with self.assertRaisesRegex(BuildMapExportError, "symlinks"):\n'
    '                fixture.export()\n',
    "",
    1,
)
hardening = replace_once(
    hardening,
    '    def test_rehashed_path_traversal_is_rejected(self):\n',
    '    def test_malformed_reason_reference_is_a_validation_error_not_an_exception(self):\n'
    '        with tempfile.TemporaryDirectory() as tmp:\n'
    '            fixture = BuildMapFixture(Path(tmp))\n'
    '            export = fixture.export()\n'
    '            export["projection"]["decisions"][0]["reason_refs"] = [\n'
    '                {"group": [], "reason_id": {}}\n'
    '            ]\n'
    '            rehash_export(export)\n'
    '            errors = verify_buildmap_export_data(export)\n'
    '            self.assertTrue(errors)\n'
    '            self.assertTrue(any("reason_refs" in error for error in errors))\n\n'
    '    def test_rehashed_finding_defect_links_are_source_verified(self):\n'
    '        with tempfile.TemporaryDirectory() as tmp:\n'
    '            fixture = BuildMapFixture(Path(tmp))\n'
    '            export = fixture.export()\n'
    '            export["projection"]["findings"][0]["defect_ids"] = []\n'
    '            rehash_export(export)\n'
    '            self.assertEqual([], verify_buildmap_export_data(export))\n'
    '            self.assertIn(\n'
    '                "BuildMap source projection mismatch",\n'
    '                verify_buildmap_export_source(export, fixture.database),\n'
    '            )\n\n'
    '    def test_rehashed_path_traversal_is_rejected(self):\n',
    "Reason and Finding-Defect hardening tests",
)
hardening_path.write_text(hardening, encoding="utf-8")

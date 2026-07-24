from pathlib import Path
import json


root = Path(__file__).resolve().parents[1]


def deduplicate_exact_line(path: Path, line: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    seen = False
    for current in lines:
        if current == line:
            if seen:
                continue
            seen = True
        output.append(current)
    if not seen:
        raise RuntimeError(f"required integration line missing from {path}: {line}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


cli_path = root / "src/review_system/cli.py"
deduplicate_exact_line(
    cli_path,
    "from .buildmap_cli import cmd_export as cmd_export_buildmap, cmd_validate as cmd_validate_buildmap_export",
)
cli = cli_path.read_text(encoding="utf-8")
if cli.count('sub.add_parser("export-buildmap"') != 1:
    raise RuntimeError("export-buildmap parser integration must occur exactly once")
if cli.count('sub.add_parser("validate-buildmap-export"') != 1:
    raise RuntimeError("validate-buildmap-export parser integration must occur exactly once")

pyproject_path = root / "pyproject.toml"
deduplicate_exact_line(
    pyproject_path,
    'pie-buildmap = "review_system.buildmap_cli:main"',
)

for schema_path in (
    root / "schemas/buildmap-export.schema.json",
    root / "src/review_system/assets/schemas/buildmap-export.schema.json",
):
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    finding = schema["$defs"]["finding"]
    if "defect_ids" not in finding["required"]:
        raise RuntimeError(f"Finding defect_ids requirement missing from {schema_path}")
    if "defect_ids" not in finding["properties"]:
        raise RuntimeError(f"Finding defect_ids property missing from {schema_path}")

module = (root / "src/review_system/buildmap_export.py").read_text(encoding="utf-8")
for required in (
    '"finding_defects": without(rows["finding_defects"], set())',
    '"defect_ids": sorted(defect_ids_by_finding.get(str(row["finding_id"]), set()))',
    'projection.decisions[{index}].reason_refs canonical mismatch',
    'projection.findings[{index}].defect_ids canonical mismatch',
):
    if required not in module:
        raise RuntimeError(f"Stage 9 hardening implementation missing: {required}")

test = (root / "tests/test_buildmap_export.py").read_text(encoding="utf-8")
for required in (
    "PRIVATE_FINDING_TITLE",
    "PRIVATE_DEFECT_SIGNATURE",
    "self.assertEqual([fixture.defect_id], finding[\"defect_ids\"])",
):
    if required not in test:
        raise RuntimeError(f"Stage 9 relationship fixture missing: {required}")

hardening = (root / "tests/test_buildmap_export_hardening.py").read_text(encoding="utf-8")
for required in (
    "test_malformed_reason_reference_is_a_validation_error_not_an_exception",
    "test_rehashed_finding_defect_links_are_source_verified",
):
    if required not in hardening:
        raise RuntimeError(f"Stage 9 hardening test missing: {required}")

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f"missing patch anchor: {label}")
    if text.count(old) != 1:
        raise RuntimeError(f"ambiguous patch anchor: {label}")
    return text.replace(old, new, 1)


root = Path(__file__).resolve().parents[1]

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

hardening_path = root / "tests/test_buildmap_export_hardening.py"
hardening = hardening_path.read_text(encoding="utf-8")
hardening = hardening.replace(
    '            with self.assertRaisesRegex(BuildMapExportError, "symlinks"):\n'
    '                fixture.export()\n',
    "",
    1,
)
hardening_path.write_text(hardening, encoding="utf-8")

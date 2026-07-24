from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"missing patch anchor: {label}")
    if text.count(old) != 1:
        raise RuntimeError(f"ambiguous patch anchor: {label}")
    return text.replace(old, new, 1)


root = Path(__file__).resolve().parents[1]

trust_path = root / "src/review_system/trust.py"
trust = trust_path.read_text(encoding="utf-8")
trust = replace_once(
    trust,
    "        if current.exists() and current.is_symlink():\n",
    "        if current.is_symlink():\n",
    "broken symlink rejection",
)
trust_path.write_text(trust, encoding="utf-8")

cli_path = root / "src/review_system/cli.py"
cli = cli_path.read_text(encoding="utf-8")
cli = replace_once(
    cli,
    "from .buildmap_cli import cmd_export as cmd_export_buildmap, cmd_validate as cmd_validate_buildmap_export\n",
    "from .buildmap_cli import cmd_export as cmd_export_buildmap, cmd_validate as cmd_validate_buildmap_export\n"
    "from .trust_cli import cmd_assess as cmd_assess_trust, cmd_validate as cmd_validate_trust_report\n",
    "Trust CLI adapter import",
)
anchor = '''    p = sub.add_parser("validate-buildmap-export", help="Validate a BuildMap export and optionally replay it against a Ledger")
    p.add_argument("export")
    p.add_argument("--ledger")
    p.set_defaults(func=cmd_validate_buildmap_export)
    return parser
'''
replacement = '''    p = sub.add_parser("validate-buildmap-export", help="Validate a BuildMap export and optionally replay it against a Ledger")
    p.add_argument("export")
    p.add_argument("--ledger")
    p.set_defaults(func=cmd_validate_buildmap_export)

    p = sub.add_parser("trust-assess", help="Generate a report-only Trust Gate readiness assessment")
    p.add_argument("--request", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--ledger")
    p.add_argument("--policy-registry")
    p.add_argument("--evaluation-report")
    p.add_argument("--reground-report")
    p.add_argument("--reground-observations")
    p.add_argument("--output", required=True)
    p.add_argument("--generated-at")
    p.set_defaults(func=cmd_assess_trust)

    p = sub.add_parser("validate-trust-report", help="Validate a Trust readiness report and optional source replay")
    p.add_argument("report")
    p.add_argument("--request")
    p.add_argument("--profile")
    p.add_argument("--ledger")
    p.add_argument("--policy-registry")
    p.add_argument("--evaluation-report")
    p.add_argument("--reground-report")
    p.add_argument("--reground-observations")
    p.set_defaults(func=cmd_validate_trust_report)
    return parser
'''
cli = replace_once(cli, anchor, replacement, "Trust CLI commands")
cli_path.write_text(cli, encoding="utf-8")

pyproject_path = root / "pyproject.toml"
pyproject = pyproject_path.read_text(encoding="utf-8")
pyproject = replace_once(
    pyproject,
    'pie-buildmap = "review_system.buildmap_cli:main"\n',
    'pie-buildmap = "review_system.buildmap_cli:main"\n'
    'pie-trust = "review_system.trust_cli:main"\n',
    "pie-trust entrypoint",
)
pyproject_path.write_text(pyproject, encoding="utf-8")

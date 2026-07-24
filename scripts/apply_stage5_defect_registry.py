from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing {label}")
    return text.replace(old, new, 1)


ledger_path = Path("src/review_system/ledger.py")
ledger = ledger_path.read_text(encoding="utf-8")
ledger = replace_once(
    ledger,
    'LEDGER_SCHEMA_VERSION = "001"\n',
    'LEDGER_SCHEMA_VERSION = "002"\n',
    "ledger schema version",
)

marker = '''CREATE INDEX IF NOT EXISTS idx_policy_snapshots_run_id ON policy_snapshots(run_id);
"""

_MIGRATIONS: tuple[tuple[str, str], ...] = ((LEDGER_SCHEMA_VERSION, _INITIAL_SCHEMA),)
'''
replacement = '''CREATE INDEX IF NOT EXISTS idx_policy_snapshots_run_id ON policy_snapshots(run_id);
"""

_DEFECT_REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    finding_key_sha256 TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    source_finding_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    impact TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    finding_sha256 TEXT NOT NULL,
    artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    imported_at TEXT NOT NULL,
    UNIQUE (run_id, source_finding_id)
);

CREATE TABLE IF NOT EXISTS registry_sources (
    project_id TEXT PRIMARY KEY,
    registry_path TEXT NOT NULL,
    registry_sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS defects (
    defect_id TEXT PRIMARY KEY,
    defect_key_sha256 TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    root_cause TEXT,
    lifecycle_status TEXT NOT NULL CHECK (
        lifecycle_status IN (
            'OBSERVED', 'REPRODUCED', 'CLASSIFIED', 'RULE_CANDIDATE',
            'MITIGATED', 'VERIFIED', 'CLOSED', 'REOPENED'
        )
    ),
    first_seen_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
    last_seen_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
    owner TEXT,
    resolution TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, signature)
);

CREATE TABLE IF NOT EXISTS finding_defects (
    finding_id TEXT NOT NULL REFERENCES findings(finding_id) ON DELETE RESTRICT,
    defect_id TEXT NOT NULL REFERENCES defects(defect_id) ON DELETE CASCADE,
    match_method TEXT NOT NULL CHECK (match_method IN ('manual', 'deterministic_signature')),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    approved_by TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (finding_id, defect_id)
);

CREATE TABLE IF NOT EXISTS defect_events (
    event_id TEXT PRIMARY KEY,
    defect_id TEXT NOT NULL REFERENCES defects(defect_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('CREATED', 'FINDING_LINKED', 'ARTIFACT_LINKED', 'TRANSITIONED')
    ),
    status_from TEXT,
    status_to TEXT,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS defect_artifacts (
    defect_id TEXT NOT NULL REFERENCES defects(defect_id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
    relation TEXT NOT NULL CHECK (
        relation IN ('reproducer', 'diagnostic', 'mitigation', 'verification', 'resolution_evidence')
    ),
    linked_by TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    note TEXT,
    PRIMARY KEY (defect_id, artifact_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_findings_run_id ON findings(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_category ON findings(category);
CREATE INDEX IF NOT EXISTS idx_defects_project_status ON defects(project_id, lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_finding_defects_defect_id ON finding_defects(defect_id);
CREATE INDEX IF NOT EXISTS idx_defect_events_defect_id ON defect_events(defect_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_defect_artifacts_defect_id ON defect_artifacts(defect_id);
"""

_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("001", _INITIAL_SCHEMA),
    (LEDGER_SCHEMA_VERSION, _DEFECT_REGISTRY_SCHEMA),
)
'''
ledger = replace_once(ledger, marker, replacement, "migration list")

artifact_loop_end = '''                ),
            )
        for item in policies:
'''
artifact_loop_replacement = '''                ),
            )
        from .defects import project_findings_for_run

        project_findings_for_run(
            connection,
            root,
            run,
            artifacts,
            imported_at=imported_at,
        )
        for item in policies:
'''
ledger = replace_once(ledger, artifact_loop_end, artifact_loop_replacement, "finding projection hook")

verify_artifacts = '''                _compare_rows(
                    result["errors"],
                    label=f"run {run_id} artifact",
                    expected=manifest_artifacts,
                    stored=stored_artifacts,
                    key="relative_path",
                    fields=(
                        "artifact_id", "artifact_key_sha256", "artifact_type",
                        "sha256", "media_type", "size_bytes",
                    ),
                )

                expected_decisions, expected_policies = _explicit_projections(
'''
verify_artifacts_replacement = '''                _compare_rows(
                    result["errors"],
                    label=f"run {run_id} artifact",
                    expected=manifest_artifacts,
                    stored=stored_artifacts,
                    key="relative_path",
                    fields=(
                        "artifact_id", "artifact_key_sha256", "artifact_type",
                        "sha256", "media_type", "size_bytes",
                    ),
                )
                from .defects import verify_findings_for_run

                verify_findings_for_run(
                    connection,
                    root,
                    run_id,
                    manifest_artifacts,
                    result["errors"],
                    imported_at=str(run_row["imported_at"]),
                )

                expected_decisions, expected_policies = _explicit_projections(
'''
ledger = replace_once(ledger, verify_artifacts, verify_artifacts_replacement, "finding verification hook")

verify_end = '''                _compare_rows(
                    result["errors"],
                    label=f"run {run_id} policy snapshot",
                    expected=expected_policies,
                    stored=stored_policies,
                    key="policy_snapshot_id",
                    fields=(
                        "run_id", "policy_version", "source", "sha256",
                        "imported_at", "artifact_id",
                    ),
                )
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
'''
verify_end_replacement = '''                _compare_rows(
                    result["errors"],
                    label=f"run {run_id} policy snapshot",
                    expected=expected_policies,
                    stored=stored_policies,
                    key="policy_snapshot_id",
                    fields=(
                        "run_id", "policy_version", "source", "sha256",
                        "imported_at", "artifact_id",
                    ),
                )
            registry_sources = connection.execute(
                "SELECT registry_path FROM registry_sources ORDER BY project_id"
            ).fetchall()
        from .defects import verify_defect_registry

        for source in registry_sources:
            registry_result = verify_defect_registry(path, source["registry_path"])
            result["errors"].extend(
                f"defect registry: {error}" for error in registry_result["errors"]
            )
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
'''
ledger = replace_once(ledger, verify_end, verify_end_replacement, "registry verification hook")

rebuild_signature = '''def rebuild_ledger(database: str | Path, directories: Iterable[str | Path]) -> dict[str, Any]:
'''
rebuild_signature_new = '''def rebuild_ledger(
    database: str | Path,
    directories: Iterable[str | Path],
    *,
    registry_paths: Iterable[str | Path] = (),
) -> dict[str, Any]:
'''
ledger = replace_once(ledger, rebuild_signature, rebuild_signature_new, "rebuild signature")

rebuild_import = '''            seen[item.run_id] = item.artifact_root
            imported.append(item.to_dict())
        verification = verify_ledger(temporary)
'''
rebuild_import_new = '''            seen[item.run_id] = item.artifact_root
            imported.append(item.to_dict())
        registries = [Path(item).expanduser().resolve() for item in registry_paths]
        seen_projects: set[str] = set()
        registry_results: list[dict[str, Any]] = []
        if registries:
            from .defects import load_defect_registry, sync_defect_registry

            for registry_path in registries:
                _, registry = load_defect_registry(registry_path)
                project_id = str(registry["project_id"])
                if project_id in seen_projects:
                    raise LedgerImportError(
                        f"rebuild input contains multiple Defect registries for project {project_id}"
                    )
                seen_projects.add(project_id)
                registry_results.append(sync_defect_registry(temporary, registry_path))
        verification = verify_ledger(temporary)
'''
ledger = replace_once(ledger, rebuild_import, rebuild_import_new, "rebuild registry sync")
ledger = replace_once(
    ledger,
    '    verification["imported"] = imported\n    return verification\n',
    '    verification["imported"] = imported\n    verification["defect_registries"] = registry_results\n    return verification\n',
    "rebuild result",
)
ledger_path.write_text(ledger, encoding="utf-8")


cli_path = Path("src/review_system/ledger_cli.py")
cli = cli_path.read_text(encoding="utf-8")
cli = replace_once(
    cli,
    '        result = rebuild_ledger(args.database, args.directories)\n',
    '        result = rebuild_ledger(\n            args.database,\n            args.directories,\n            registry_paths=args.defect_registry,\n        )\n',
    "ledger CLI rebuild call",
)
cli = replace_once(
    cli,
    '    command.add_argument("--database", required=True)\n    command.set_defaults(func=cmd_rebuild)\n',
    '    command.add_argument("--database", required=True)\n    command.add_argument(\n        "--defect-registry",\n        action="append",\n        default=[],\n        help="Canonical Defect Registry JSON to project after Run imports; repeatable",\n    )\n    command.set_defaults(func=cmd_rebuild)\n',
    "ledger CLI rebuild parser",
)
cli_path.write_text(cli, encoding="utf-8")


pyproject_path = Path("pyproject.toml")
pyproject = pyproject_path.read_text(encoding="utf-8")
pyproject = replace_once(
    pyproject,
    'pie-ledger = "review_system.ledger_cli:main"\n',
    'pie-ledger = "review_system.ledger_cli:main"\npie-defect = "review_system.defect_cli:main"\n',
    "defect entrypoint",
)
pyproject_path.write_text(pyproject, encoding="utf-8")


readme_path = Path("docs/architecture/README.md")
readme = readme_path.read_text(encoding="utf-8")
readme = replace_once(
    readme,
    '22. [STAGE-4-VALIDATION.md](STAGE-4-VALIDATION.md) — Stage 4 검증 결과\n',
    '22. [STAGE-4-VALIDATION.md](STAGE-4-VALIDATION.md) — Stage 4 검증 결과\n23. [STAGE-5-DEFECT-REGISTRY.md](STAGE-5-DEFECT-REGISTRY.md) — Finding·Defect identity·lifecycle·registry 설계\n',
    "architecture document index",
)
readme = replace_once(
    readme,
    '- Stage 4 — Evidence Ledger Foundation: `PASS`, PR #12 검토 대기\n\n## 다음 단계\n\nStage 5에서 Run-local Finding과 cross-run Defect를 분리하는 Defect Registry를 설계한다.\n',
    '- Stage 4 — Evidence Ledger Foundation: `PASS`, PR #12 검토 대기\n- Stage 5 — Defect Registry: 구현 리뷰 진행\n\n## 다음 단계\n\nStage 5 승인 후 Stage 6 Evaluation Lab의 dataset·runner·metric 계약을 상세 설계한다.\n',
    "architecture progress",
)
readme_path.write_text(readme, encoding="utf-8")

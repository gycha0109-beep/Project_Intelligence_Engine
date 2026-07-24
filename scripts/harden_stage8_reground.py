from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)


path = Path("src/review_system/reground.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    '''def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
''',
    '''def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size
''',
    "raw file digest",
)

text = replace_once(
    text,
    '''        if not isinstance(node_id, str) or not node_id:
            raise RegroundError(f"Graph file node {index} id is invalid")
        recorded = node.get("sha256")
''',
    '''        if not isinstance(node_id, str) or not node_id:
            raise RegroundError(f"Graph file node {index} id is invalid")
        if node_id != f"file:{path}":
            raise RegroundError(f"Graph file node id does not match normalized path: {node_id}")
        recorded = node.get("sha256")
''',
    "file node natural id",
)

text = replace_once(
    text,
    '''    current_hash = _file_sha256(current)
    current_size = current.stat().st_size
''',
    '''    current_hash, current_size = _file_digest(current)
''',
    "digest and size single read",
)

text = replace_once(
    text,
    '''def _snapshot_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "graph_sha256": report.get("graph", {}).get("graph_sha256")
        if isinstance(report.get("graph"), dict)
        else None,
        "last_verified_run": report.get("ledger", {}).get("last_verified_run")
        if isinstance(report.get("ledger"), dict)
        else None,
        "files": deepcopy(report.get("files")),
        "relations": deepcopy(report.get("relations")),
        "impacted_rechecks": deepcopy(report.get("impacted_rechecks")),
        "warnings": deepcopy(report.get("warnings")),
    }
''',
    '''_LAST_RUN_FIELDS = (
    "run_id",
    "run_key_sha256",
    "project_id",
    "run_type",
    "source_revision",
    "source_identifier",
    "manifest_sha256",
    "imported_at",
)
_STABLE_LAST_RUN_FIELDS = tuple(field for field in _LAST_RUN_FIELDS if field != "imported_at")


def _stable_last_run(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {field: deepcopy(value.get(field)) for field in _STABLE_LAST_RUN_FIELDS}


def _snapshot_payload(report: dict[str, Any]) -> dict[str, Any]:
    ledger = report.get("ledger") if isinstance(report.get("ledger"), dict) else {}
    return {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "graph_sha256": report.get("graph", {}).get("graph_sha256")
        if isinstance(report.get("graph"), dict)
        else None,
        "last_verified_run": _stable_last_run(ledger.get("last_verified_run")),
        "files": deepcopy(report.get("files")),
        "relations": deepcopy(report.get("relations")),
        "impacted_rechecks": deepcopy(report.get("impacted_rechecks")),
        "warnings": deepcopy(report.get("warnings")),
    }
''',
    "stable snapshot run projection",
)

text = replace_once(
    text,
    '''    return {**item, "path": path, "status": expected_status, "reasons": expected_reasons}
''',
    '''    return {
        "node_id": f"file:{path}",
        "path": path,
        "recorded_sha256": recorded,
        "current_sha256": current,
        "size_bytes": size,
        "status": expected_status,
        "reasons": expected_reasons,
    }
''',
    "canonical file projection",
)

text = replace_once(
    text,
    '''    last_run = ledger.get("last_verified_run")
    if last_run is not None:
        if not isinstance(last_run, dict):
            errors.append("ledger.last_verified_run must be an object or null")
            last_run = None
        else:
            for field in (
                "run_id", "run_key_sha256", "project_id", "run_type",
                "source_revision", "source_identifier", "manifest_sha256", "imported_at",
            ):
                if not isinstance(last_run.get(field), str) or not last_run[field]:
                    errors.append(f"ledger.last_verified_run.{field} is required")
            if last_run.get("project_id") != report.get("project_id"):
                errors.append("ledger.last_verified_run.project_id mismatch")
''',
    '''    last_run = ledger.get("last_verified_run")
    if last_run is not None:
        if not isinstance(last_run, dict):
            errors.append("ledger.last_verified_run must be an object or null")
            last_run = None
        else:
            if set(last_run) != set(_LAST_RUN_FIELDS):
                errors.append("ledger.last_verified_run fields mismatch")
            for field in _LAST_RUN_FIELDS:
                if not isinstance(last_run.get(field), str) or not last_run[field]:
                    errors.append(f"ledger.last_verified_run.{field} is required")
            if last_run.get("project_id") != report.get("project_id"):
                errors.append("ledger.last_verified_run.project_id mismatch")
''',
    "canonical last run fields",
)

text = replace_once(
    text,
    '''        paths.add(path)
        files.append(normalized)
    files_by_path = {str(item["path"]): item for item in files}
''',
    '''        paths.add(path)
        files.append(normalized)
    files = sorted(files, key=lambda item: item["path"])
    if files_raw != files:
        errors.append("files canonical projection mismatch")
    files_by_path = {str(item["path"]): item for item in files}
''',
    "canonical file order",
)

text = replace_once(
    text,
    '''        relations.append(
            {
                "relation_id": expected_id,
                "source_path": source,
                "target_path": target,
                "type": edge_type,
                "status": expected_status,
                "reasons": reasons,
            }
        )

    expected_impacted = _impacted_rechecks(files, relations)
''',
    '''        relations.append(
            {
                "relation_id": expected_id,
                "source_path": source,
                "target_path": target,
                "type": edge_type,
                "status": expected_status,
                "reasons": reasons,
            }
        )
    relations = sorted(
        relations,
        key=lambda item: (item["source_path"], item["target_path"], item["type"]),
    )
    if relations_raw != relations:
        errors.append("relations canonical projection mismatch")

    expected_impacted = _impacted_rechecks(files, relations)
''',
    "canonical relation order",
)

path.write_text(text, encoding="utf-8")

cli_path = Path("src/review_system/reground_cli.py")
cli = cli_path.read_text(encoding="utf-8")
cli = replace_once(
    cli,
    '''from .io import load_data
from .reground import (
    RegroundError,
    analyze_reground,
    verify_reground_report_data,
    write_reground_report,
)
''',
    '''from .reground import (
    RegroundError,
    RegroundVerificationError,
    analyze_reground,
    load_reground_report,
    write_reground_report,
)
''',
    "CLI imports",
)
cli = replace_once(
    cli,
    '''        if args.command == "verify-report":
            data = load_data(args.report)
            errors = verify_reground_report_data(data)
            result = {"valid": not errors, "report": str(args.report), "errors": errors}
            _print_json(result, stream=sys.stdout if not errors else sys.stderr)
            return 0 if not errors else 4
    except (RegroundError, OSError, ValueError) as exc:
''',
    '''        if args.command == "verify-report":
            try:
                source, _ = load_reground_report(args.report)
            except RegroundVerificationError as exc:
                _print_json(
                    {"valid": False, "report": str(args.report), "errors": list(exc.errors)},
                    stream=sys.stderr,
                )
                return 4
            _print_json({"valid": True, "report": str(source), "errors": []})
            return 0
    except (RegroundError, OSError, ValueError) as exc:
''',
    "safe verify CLI",
)
cli_path.write_text(cli, encoding="utf-8")

test_path = Path("tests/test_reground.py")
tests = test_path.read_text(encoding="utf-8")
tests = replace_once(
    tests,
    '''    def test_windows_graph_path_normalizes_to_posix(self):
''',
    '''    def test_idempotent_reimport_time_does_not_change_snapshot_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            first = fixture.analyze()
            with sqlite3.connect(fixture.ledger) as connection:
                connection.execute(
                    "UPDATE runs SET imported_at = ? WHERE run_id = ?",
                    ("2026-07-25T12:00:00+00:00", fixture.run_id),
                )
            second = fixture.analyze()
            self.assertNotEqual(
                first["ledger"]["last_verified_run"]["imported_at"],
                second["ledger"]["last_verified_run"]["imported_at"],
            )
            self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])
            self.assertEqual(first["report_id"], second["report_id"])
            self.assertNotEqual(first["report_sha256"], second["report_sha256"])

    def test_windows_graph_path_normalizes_to_posix(self):
''',
    "stable reimport identity test",
)

tests = replace_once(
    tests,
    '''    def test_cli_invalid_report_returns_verification_exit(self):
''',
    '''    @unittest.skipUnless(hasattr(__import__("os"), "symlink"), "symlink support required")
    def test_cli_verify_rejects_symlink_report_as_input_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = RegroundFixture(root)
            output = root / "report.json"
            write_reground_report(output, fixture.analyze())
            link = root / "report-link.json"
            try:
                link.symlink_to(output)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(3, reground_main(["verify-report", "--report", str(link)]))

    def test_cli_invalid_report_returns_verification_exit(self):
''',
    "CLI symlink test",
)
test_path.write_text(tests, encoding="utf-8")

hardening_path = Path("tests/test_reground_hardening.py")
hardening = hardening_path.read_text(encoding="utf-8")
hardening = replace_once(
    hardening,
    '''    def test_report_id_and_snapshot_hash_are_natural_key_verified(self):
''',
    '''    def test_rehashed_reordered_or_extended_projection_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            report = fixture.analyze()
            report["files"].reverse()
            report["relations"][0]["unexpected"] = "forged"
            rehash_report(report)
            errors = verify_reground_report_data(report)
            self.assertIn("files canonical projection mismatch", errors)
            self.assertIn("relations canonical projection mismatch", errors)

    def test_report_id_and_snapshot_hash_are_natural_key_verified(self):
''',
    "canonical projection tamper test",
)
hardening = replace_once(
    hardening,
    '''    def test_duplicate_file_relation_is_rejected_even_with_valid_graph_hash(self):
''',
    '''    def test_file_node_id_must_match_normalized_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RegroundFixture(Path(tmp))
            graph = load_data(fixture.graph)
            graph["nodes"][0]["id"] = "file:src/other.py"
            graph["edges"][0]["source"] = "file:src/other.py"
            graph["graph_sha256"] = calculate_graph_sha256(graph)
            dump_json(fixture.graph, graph)
            with self.assertRaisesRegex(RegroundError, "id does not match"):
                fixture.analyze()

    def test_duplicate_file_relation_is_rejected_even_with_valid_graph_hash(self):
''',
    "node natural id test",
)
hardening_path.write_text(hardening, encoding="utf-8")

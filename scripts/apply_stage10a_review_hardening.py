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
    "from .identity import canonical_json_sha256, file_sha256\n",
    "from .identity import canonical_json_sha256, file_sha256, normalize_source_revision\n",
    "stable source revision import",
)
trust = replace_once(
    trust,
    '''    normalized = {
        "schema_version": TRUST_SCHEMA_VERSION,
        "task_id": candidate["task_id"].strip(),
        "source_revision": candidate["source_revision"].strip(),
''',
    '''    try:
        source_revision = normalize_source_revision(candidate["source_revision"])
    except ValueError as exc:
        raise TrustError(f"Trust request source_revision: {exc}") from exc
    if source_revision == "unresolved":
        raise TrustError("Trust request source_revision must be a stable revision")
    normalized = {
        "schema_version": TRUST_SCHEMA_VERSION,
        "task_id": candidate["task_id"].strip(),
        "source_revision": source_revision,
''',
    "stable source revision normalization",
)
trust = replace_once(
    trust,
    '''        or any(token in name for token in ("credential", "secret", "token", "permission", "migration"))
''',
    '''        or name.startswith("auth")
        or any(
            token in name
            for token in (
                "credential", "secret", "token", "permission", "migration",
                "authentication", "authorization", "oauth", "jwt", "security",
                "role", "rls",
            )
        )
''',
    "high-risk filename classification",
)
trust = replace_once(
    trust,
    '''    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    false_positive_rate = fp / (fp + tn) if fp + tn else 0.0
    exact_rate = (tp + tn) / count if count else 0.0
    coverage = count / relation_count if relation_count else 0.0
    return {
        "observation_count": count,
        "coverage": round(coverage, 6),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "false_positive_rate": round(false_positive_rate, 6),
        "exact_rate": round(exact_rate, 6),
    }
''',
    '''    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    false_positive_rate = fp / (fp + tn) if fp + tn else None
    exact_rate = (tp + tn) / count if count else None
    coverage = count / relation_count if relation_count else 0.0
    return {
        "observation_count": count,
        "coverage": round(coverage, 6),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 6) if precision is not None else None,
        "recall": round(recall, 6) if recall is not None else None,
        "false_positive_rate": (
            round(false_positive_rate, 6)
            if false_positive_rate is not None
            else None
        ),
        "exact_rate": round(exact_rate, 6) if exact_rate is not None else None,
    }
''',
    "undefined classification metrics",
)
trust_path.write_text(trust, encoding="utf-8")

cli_path = root / "src/review_system/trust_cli.py"
cli = cli_path.read_text(encoding="utf-8")
cli = replace_once(
    cli,
    '''    except (TrustError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3
    _print_json(
''',
    '''    except TrustVerificationError as exc:
        _print_json({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (TrustError, OSError, ValueError) as exc:
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3
    _print_json(
''',
    "assessment verification exit code",
)
cli_path.write_text(cli, encoding="utf-8")

test_path = root / "tests/test_trust_gate.py"
test = test_path.read_text(encoding="utf-8")
test = replace_once(test, "import io\n", "import hashlib\nimport io\n", "test hashlib import")
test = replace_once(
    test,
    "from review_system.io import dump_json, dump_yaml\n",
    "from review_system.intelligence_graph import calculate_graph_sha256\n"
    "from review_system.io import dump_json, dump_yaml, load_data\n",
    "test graph imports",
)
test = replace_once(
    test,
    '''        self.reground_fixture = RegroundFixture(root)
        gated_root, self.gated_run_id = LedgerFixture.create(root, "gated-run", with_gate=True)
''',
    '''        self.reground_fixture = RegroundFixture(root)
        other = self.reground_fixture.repository / "src" / "other.py"
        other.write_text("from .source import VALUE\\n", encoding="utf-8")
        graph = load_data(self.reground_fixture.graph)
        graph["nodes"].append(
            {
                "id": "file:src/other.py",
                "type": "file",
                "path": "src/other.py",
                "language": "python",
                "size_bytes": other.stat().st_size,
                "sha256": hashlib.sha256(other.read_bytes()).hexdigest(),
            }
        )
        graph["edges"].append(
            {
                "source": "file:src/other.py",
                "target": "file:src/source.py",
                "type": "imports",
            }
        )
        graph["graph_sha256"] = calculate_graph_sha256(graph)
        dump_json(self.reground_fixture.graph, graph)
        self.reground_fixture.target.write_text("VALUE = 2\\n", encoding="utf-8")
        gated_root, self.gated_run_id = LedgerFixture.create(root, "gated-run", with_gate=True)
''',
    "mixed Reground label fixture",
)
test = replace_once(
    test,
    '''        relation = self.reground["relations"][0]
        self.observations = root / "reground-observations.json"
        dump_json(
            self.observations,
            {
                "schema_version": "1.0",
                "dataset_id": "trust-reground-human-1",
                "project_id": "demo",
                "reground_report_id": self.reground["report_id"],
                "observations": [
                    {
                        "observation_id": "obs-1",
                        "relation_id": relation["relation_id"],
                        "expected_status": relation["status"],
                        "confirmed_by": "human-reviewer",
                        "confirmed_at": "2026-07-25T01:00:00Z",
                    }
                ],
            },
        )
''',
    '''        self.observations = root / "reground-observations.json"
        dump_json(
            self.observations,
            {
                "schema_version": "1.0",
                "dataset_id": "trust-reground-human-1",
                "project_id": "demo",
                "reground_report_id": self.reground["report_id"],
                "observations": [
                    {
                        "observation_id": f"obs-{index}",
                        "relation_id": relation["relation_id"],
                        "expected_status": relation["status"],
                        "confirmed_by": "human-reviewer",
                        "confirmed_at": "2026-07-25T01:00:00Z",
                    }
                    for index, relation in enumerate(self.reground["relations"], start=1)
                ],
            },
        )
''',
    "mixed Reground observations",
)
test_path.write_text(test, encoding="utf-8")

hardening_path = root / "tests/test_trust_gate_hardening.py"
hardening = hardening_path.read_text(encoding="utf-8")
hardening = replace_once(
    hardening,
    '''    def test_duplicate_relation_observation_is_rejected(self):
''',
    '''    def test_symbolic_source_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            data = json.loads(fixture.request.read_text(encoding="utf-8"))
            data["source_revision"] = "HEAD"
            dump_json(fixture.request, data)
            with self.assertRaisesRegex(TrustError, "symbolic revision"):
                load_trust_request(fixture.request)

    def test_duplicate_relation_observation_is_rejected(self):
''',
    "symbolic revision hardening test",
)
hardening = replace_once(
    hardening,
    '''    def test_policy_evaluation_mismatch_is_not_ready_and_hard_gate(self):
''',
    '''    def test_missing_positive_or_negative_sample_cannot_claim_perfect_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            observations = json.loads(fixture.observations.read_text(encoding="utf-8"))
            current = next(
                item
                for item in observations["observations"]
                if item["expected_status"] == "CURRENT"
            )
            observations["observations"] = [current]
            dump_json(fixture.observations, observations)
            request = json.loads(fixture.request.read_text(encoding="utf-8"))
            request["readiness_policy"]["min_reground_coverage"] = 0.5
            dump_json(fixture.request, request)
            report = fixture.assess()
            self.assertIsNone(report["evidence"]["reground"]["precision"])
            self.assertIsNone(report["evidence"]["reground"]["recall"])
            self.assertEqual("NOT_READY", report["readiness"]["status"])
            self.assertIn("reground_precision_threshold", report["readiness"]["failed_conditions"])

    def test_policy_evaluation_mismatch_is_not_ready_and_hard_gate(self):
''',
    "undefined metric hardening test",
)
hardening_path.write_text(hardening, encoding="utf-8")

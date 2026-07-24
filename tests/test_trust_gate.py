import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from review_system.defects import create_defect, initialize_defect_registry
from review_system.intelligence_graph import calculate_graph_sha256
from review_system.io import dump_json, dump_yaml, load_data
from review_system.ledger import import_artifact_directory
from review_system.reground import write_reground_report
from review_system.trust import (
    assess_trust,
    verify_trust_report_data,
    verify_trust_report_sources,
    write_trust_report,
)
from review_system.trust_cli import main as trust_main
from test_ledger import LedgerFixture
from test_policy_registry import PolicyFixture
from test_reground import RegroundFixture


class TrustReadinessFixture:
    def __init__(self, root: Path):
        self.root = root
        self.profile = root / "profile.yml"
        dump_yaml(
            self.profile,
            {
                "schema_version": "1.0",
                "project": {
                    "id": "demo",
                    "name": "Demo",
                    "type": "web-application",
                    "repository_root": ".",
                    "baseline_branch": "main",
                },
                "inherits": [],
                "technology": {
                    "languages": ["python", "sql"],
                    "frameworks": [],
                    "database": {"engine": "postgresql"},
                },
                "scope": {"include": ["src/**", "docs/**", "database/**"], "exclude": []},
                "protected_paths": ["database/migrations/**"],
                "commands": {"baseline": ["python -m unittest"], "integration": []},
                "review": {
                    "packs": [
                        "universal.architecture",
                        "universal.requirements-traceability",
                        "universal.test-completeness",
                        "data.migration-safety",
                    ]
                },
                "gate": {
                    "block_on": ["P0", "P1"],
                    "require": {
                        "baseline_tests": True,
                        "regression_tests": True,
                    },
                },
                "constraints": {
                    "production_changes_allowed": False,
                    "hosted_database_changes_allowed": False,
                    "external_network_allowed": False,
                },
            },
        )

        self.reground_fixture = RegroundFixture(root)
        other = self.reground_fixture.repository / "src" / "other.py"
        other.write_text("from .source import VALUE\n", encoding="utf-8")
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
        self.reground_fixture.target.write_text("VALUE = 2\n", encoding="utf-8")
        gated_root, self.gated_run_id = LedgerFixture.create(root, "gated-run", with_gate=True)
        import_artifact_directory(self.reground_fixture.ledger, gated_root)

        self.defect_registry = root / "defect-registry.json"
        initialize_defect_registry(self.defect_registry, "demo")
        self.defect = create_defect(
            self.defect_registry,
            self.reground_fixture.ledger,
            signature="trust-readiness-seed",
            title="Trust readiness seed",
            category="trust.readiness",
            actor="fixture",
            occurred_at="2026-07-25T00:00:00Z",
        )

        policy_root = root / "policy"
        policy_root.mkdir()
        self.policy_fixture = PolicyFixture(policy_root)
        self.active_policy = self.policy_fixture.activate_root()
        self.policy_registry = self.policy_fixture.registry
        self.evaluation_report = self.policy_fixture.report_a

        self.reground = self.reground_fixture.analyze()
        self.reground_report = root / "reground-report.json"
        write_reground_report(self.reground_report, self.reground)
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
        self.request = root / "trust-request.json"
        self.write_request()

    @staticmethod
    def readiness_policy() -> dict:
        return {
            "policy_id": "trust-readiness-default",
            "policy_version": "1.0.0",
            "min_ledger_runs": 1,
            "min_ledger_decisions": 1,
            "min_defects": 1,
            "min_closed_defects": 0,
            "min_reground_observations": 1,
            "min_reground_coverage": 1.0,
            "min_reground_precision": 1.0,
            "min_reground_recall": 1.0,
            "max_reground_false_positive_rate": 0.0,
            "require_active_policy": True,
            "require_pass_evaluation": True,
            "require_holdout": True,
            "require_repeatability": True,
            "require_zero_protected_negative_regressions": True,
        }

    def write_request(
        self,
        *,
        task_class: str = "documentation",
        changed_files: list[str] | None = None,
        required_scenarios: list[str] | None = None,
        completed_scenarios: list[str] | None = None,
        repository_match: bool = True,
        head_match: bool = True,
        rollback_evidence: bool = True,
        replay_evidence: bool = True,
    ) -> Path:
        required = ["trust-unit"] if required_scenarios is None else required_scenarios
        completed = required if completed_scenarios is None else completed_scenarios
        dump_json(
            self.request,
            {
                "schema_version": "1.0",
                "task_id": "TASK-TRUST-001",
                "source_revision": "git:" + "a" * 40,
                "task_class": task_class,
                "changed_files": changed_files or ["docs/trust-readiness.md"],
                "required_scenarios": required,
                "completed_scenarios": completed,
                "repository_match": repository_match,
                "head_match": head_match,
                "rollback_evidence": rollback_evidence,
                "replay_evidence": replay_evidence,
                "readiness_policy": self.readiness_policy(),
            },
        )
        return self.request

    def assess(self, *, generated_at: str = "2026-07-25T02:00:00Z", **overrides):
        return assess_trust(
            overrides.get("request", self.request),
            overrides.get("profile", self.profile),
            ledger=overrides.get("ledger", self.reground_fixture.ledger),
            policy_registry=overrides.get("policy_registry", self.policy_registry),
            evaluation_report=overrides.get("evaluation_report", self.evaluation_report),
            reground_report=overrides.get("reground_report", self.reground_report),
            reground_observations=overrides.get("reground_observations", self.observations),
            generated_at=generated_at,
        )

    def source_args(self) -> dict:
        return {
            "request": self.request,
            "profile": self.profile,
            "ledger": self.reground_fixture.ledger,
            "policy_registry": self.policy_registry,
            "evaluation_report": self.evaluation_report,
            "reground_report": self.reground_report,
            "reground_observations": self.observations,
        }


class TrustReadinessTests(unittest.TestCase):
    def test_ready_report_is_reference_based_report_only_and_source_verifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            report = fixture.assess()
            self.assertEqual([], verify_trust_report_data(report))
            self.assertEqual([], verify_trust_report_sources(report, **fixture.source_args()))
            self.assertEqual("REPORT_ONLY", report["mode"])
            self.assertFalse(report["automation_authorized"])
            self.assertEqual("NONE", report["maximum_automation_band"])
            self.assertEqual("READY_FOR_HUMAN_COMPARISON", report["readiness"]["status"])
            self.assertEqual("R1", report["risk"]["effective_band"])
            self.assertTrue(report["task_advisory"]["human_action_required"])
            self.assertFalse(report["task_advisory"]["auto_pass_candidate"])
            self.assertEqual([], report["task_advisory"]["triggered_hard_gates"])
            self.assertEqual(1, report["evidence"]["ledger"]["decision_count"])
            self.assertEqual(1, report["evidence"]["defects"]["total"])
            self.assertEqual(1, report["evidence"]["policy"]["holdout_cases"])
            self.assertEqual(1.0, report["evidence"]["reground"]["coverage"])
            payload = json.dumps(report, sort_keys=True)
            self.assertNotIn(str(fixture.root), payload)
            self.assertNotIn("human-reviewer", payload)
            self.assertNotIn("trust-readiness-seed", payload)

    def test_report_identity_is_stable_across_generated_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            first = fixture.assess(generated_at="2026-07-25T02:00:00Z")
            second = fixture.assess(generated_at="2026-07-26T02:00:00Z")
            self.assertEqual(first["report_id"], second["report_id"])
            self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])
            self.assertNotEqual(first["report_sha256"], second["report_sha256"])

    def test_missing_evidence_is_valid_not_ready_and_does_not_authorize_automation(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            report = assess_trust(
                fixture.request,
                fixture.profile,
                generated_at="2026-07-25T02:00:00Z",
            )
            self.assertEqual([], verify_trust_report_data(report))
            self.assertEqual("NOT_READY", report["readiness"]["status"])
            self.assertFalse(report["automation_authorized"])
            self.assertIn("ledger_available", report["readiness"]["failed_conditions"])
            self.assertIn("POLICY_EVALUATION_MISSING", report["task_advisory"]["triggered_hard_gates"])

    def test_declared_formatting_cannot_hide_verifier_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            fixture.write_request(
                task_class="formatting",
                changed_files=["src/review_system/trust.py"],
            )
            report = fixture.assess()
            self.assertEqual("R0", report["risk"]["base_band"])
            self.assertEqual("R4", report["risk"]["effective_band"])
            self.assertIn("VERIFIER_CHANGED", report["task_advisory"]["triggered_hard_gates"])
            self.assertEqual(
                "DUAL_INDEPENDENT_REVIEW_REQUIRED",
                report["task_advisory"]["review_requirement"],
            )

    def test_protected_migration_is_r3_and_requires_replay_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            fixture.write_request(
                task_class="database_migration",
                changed_files=["database/migrations/V2__accounts.sql"],
                rollback_evidence=False,
                replay_evidence=False,
            )
            report = fixture.assess()
            self.assertEqual("R3", report["risk"]["effective_band"])
            self.assertEqual(
                ["database/migrations/V2__accounts.sql"],
                report["risk"]["protected_files"],
            )
            gates = set(report["task_advisory"]["triggered_hard_gates"])
            self.assertIn("PROTECTED_PATH_CHANGED", gates)
            self.assertIn("AUTHORIZATION_OR_MIGRATION_CHANGE", gates)
            self.assertIn("ROLLBACK_OR_REPLAY_EVIDENCE_MISSING", gates)

    def test_cli_assess_and_verify_return_zero_even_when_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            output = Path(tmp) / "trust-report.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = trust_main(
                    [
                        "assess",
                        "--request", str(fixture.request),
                        "--profile", str(fixture.profile),
                        "--output", str(output),
                        "--generated-at", "2026-07-25T02:00:00Z",
                    ]
                )
            self.assertEqual(0, code)
            self.assertEqual("NOT_READY", json.loads(stdout.getvalue())["readiness"])
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = trust_main(["verify-report", "--report", str(output)])
            self.assertEqual(0, code)
            self.assertTrue(json.loads(stdout.getvalue())["valid"])

    def test_write_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            report = fixture.assess()
            output = Path(tmp) / "trust-report.json"
            self.assertEqual(output.resolve(), write_trust_report(output, report))
            self.assertEqual(report, json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()

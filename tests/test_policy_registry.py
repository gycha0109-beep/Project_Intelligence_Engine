import json
from pathlib import Path
import tempfile
import unittest

from review_system.evaluation import run_evaluation, write_evaluation_report
from review_system.intelligence_graph import calculate_graph_sha256
from review_system.io import dump_json, dump_yaml, load_data
from review_system.intelligence_config import load_rules
from review_system.policy_registry import (
    PolicyRegistryError,
    approve_policy,
    build_policy,
    compare_policies,
    list_policies,
    materialize_active_policy,
    retire_policy,
    show_policy,
    verify_policy_registry_file,
)


class PolicyFixture:
    def __init__(self, root: Path):
        self.root = root
        self.registry = root / "policy-registry.json"
        self.materialized = root / "approved-rules.yml"
        graph = {
            "schema_version": "1.0",
            "repository": {"root": "."},
            "nodes": [
                {"id": "file:src/a.py", "type": "file", "path": "src/a.py", "language": "python", "size_bytes": 1, "sha256": "a" * 64},
                {"id": "file:src/b.py", "type": "file", "path": "src/b.py", "language": "python", "size_bytes": 1, "sha256": "b" * 64},
                {"id": "file:src/c.py", "type": "file", "path": "src/c.py", "language": "python", "size_bytes": 1, "sha256": "c" * 64},
            ],
            "edges": [],
            "stats": {"files": 3, "symbols": 0, "components": 0, "database_objects": 0, "edges": 0},
            "warnings": [],
        }
        graph["graph_sha256"] = calculate_graph_sha256(graph)
        self.graph = root / "graph.json"
        self.changed = root / "changed.txt"
        dump_json(self.graph, graph)
        self.changed.write_text("src/a.py\n", encoding="utf-8")
        self.empty_rules = self._write_rules("empty.yml", [])
        self.rules_a = self._write_rules("rules-a.yml", [self._rule("RULE_A", "src/b.py")])
        self.rules_ab = self._write_rules(
            "rules-ab.yml",
            [self._rule("RULE_A", "src/b.py"), self._rule("RULE_B", "src/c.py")],
        )
        self.report_a = self._evaluation(
            "a",
            baseline=self.empty_rules,
            challenger=self.rules_a,
            expected_scope=["src/a.py", "src/b.py"],
        )
        self.report_ab = self._evaluation(
            "ab",
            baseline=self.rules_a,
            challenger=self.rules_ab,
            expected_scope=["src/a.py", "src/b.py", "src/c.py"],
        )

    @staticmethod
    def _rule(rule_id: str, impact_path: str) -> dict:
        return {
            "id": rule_id,
            "title": f"Review {impact_path}",
            "status": "approved",
            "trigger": {"paths_any": ["src/a.py"]},
            "impact": {"components": [], "paths": [impact_path]},
            "review": {"packs": [], "required_tests": []},
            "rationale": "Evaluation fixture.",
            "evidence": {"sample_count": 3},
            "approval": {
                "approved_by": "fixture",
                "approved_at": "2026-07-24T00:00:00Z",
            },
        }

    def _write_rules(self, name: str, rules: list[dict]) -> Path:
        path = self.root / name
        dump_yaml(path, {"schema_version": "1.0", "rules": rules})
        return path

    def _evaluation(
        self,
        suffix: str,
        *,
        baseline: Path,
        challenger: Path,
        expected_scope: list[str],
    ) -> Path:
        dataset = self.root / f"dataset-{suffix}.yml"
        cases = []
        for split in ("development", "validation", "holdout"):
            cases.append(
                {
                    "case_id": f"{suffix}-{split}",
                    "repository": "demo/repo",
                    "source_revision": "git:abcdef1",
                    "input_artifacts": {"graph": self.graph.name, "changed_files": self.changed.name},
                    "configured_packs": [],
                    "expected_changed_scope": expected_scope,
                    "expected_packs": [],
                    "expected_tests": [],
                    "expected_protected_result": "PASS",
                    "labels": ["fixture"],
                    "provenance": {
                        "source": "unit-test",
                        "labeled_by": "human",
                        "labeled_at": "2026-07-24T00:00:00Z",
                    },
                    "split": split,
                }
            )
        dump_yaml(
            dataset,
            {"schema_version": "1.0", "dataset_id": f"dataset-{suffix}", "cases": cases},
        )
        report = run_evaluation(dataset, baseline, challenger)
        self.assert_pass(report)
        target = self.root / f"evaluation-{suffix}.json"
        write_evaluation_report(target, report)
        return target

    @staticmethod
    def assert_pass(report: dict) -> None:
        if report["gate"]["decision"] != "PASS":
            raise AssertionError(report["gate"])

    def build_root(self) -> dict:
        return build_policy(
            self.registry,
            project_id="demo",
            version="1.0.0",
            rules=self.rules_a,
            evaluation_report=self.report_a,
            created_by="builder",
            created_at="2026-07-24T01:00:00Z",
        )

    def activate_root(self) -> dict:
        policy = self.build_root()
        return approve_policy(
            self.registry,
            policy["policy_id"],
            approved_by="approver",
            approved_at="2026-07-24T02:00:00Z",
            effective_at="2026-07-24T02:00:00Z",
            rationale="Initial active Policy.",
            materialized_rules=self.materialized,
        )

    def build_child(self, parent_id: str) -> dict:
        return build_policy(
            self.registry,
            project_id="demo",
            version="1.1.0",
            rules=self.rules_ab,
            evaluation_report=self.report_ab,
            created_by="builder",
            created_at="2026-07-24T03:00:00Z",
            parent_policy_id=parent_id,
        )


class PolicyRegistryLifecycleTests(unittest.TestCase):
    def test_build_and_first_activation_materialize_active_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            draft = fixture.build_root()
            self.assertEqual("DRAFT", draft["status"])
            self.assertEqual([], verify_policy_registry_file(fixture.registry))

            active = approve_policy(
                fixture.registry,
                draft["policy_id"],
                approved_by="approver",
                approved_at="2026-07-24T02:00:00Z",
                materialized_rules=fixture.materialized,
            )
            self.assertEqual("ACTIVE", active["status"])
            registry = load_data(fixture.registry)
            self.assertEqual(active["policy_id"], registry["active_policy_id"])
            self.assertEqual(
                active["ruleset"]["rules"],
                load_rules(fixture.materialized, required_status="approved"),
            )
            self.assertEqual([], verify_policy_registry_file(
                fixture.registry,
                materialized_rules=fixture.materialized,
            ))
            self.assertEqual(active["policy_id"], list_policies(fixture.registry)[0]["policy_id"])
            self.assertEqual(active, show_policy(fixture.registry, active["policy_id"]))

    def test_child_activation_supersedes_parent_and_compare_reports_added_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            parent = fixture.activate_root()
            child = fixture.build_child(parent["policy_id"])
            active_child = approve_policy(
                fixture.registry,
                child["policy_id"],
                approved_by="approver",
                approved_at="2026-07-24T04:00:00Z",
                effective_at="2026-07-24T04:00:00Z",
                materialized_rules=fixture.materialized,
            )
            registry = load_data(fixture.registry)
            policy_map = {item["policy_id"]: item for item in registry["policies"]}
            self.assertEqual("SUPERSEDED", policy_map[parent["policy_id"]]["status"])
            self.assertEqual(active_child["policy_id"], policy_map[parent["policy_id"]]["superseded_by"])
            self.assertEqual("ACTIVE", policy_map[active_child["policy_id"]]["status"])
            comparison = compare_policies(fixture.registry, parent["policy_id"], active_child["policy_id"])
            self.assertEqual(["RULE_B"], comparison["added_rule_ids"])
            self.assertFalse(comparison["same_ruleset"])
            self.assertEqual([], verify_policy_registry_file(
                fixture.registry,
                materialized_rules=fixture.materialized,
            ))

    def test_retire_active_clears_materialized_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            active = fixture.activate_root()
            retired = retire_policy(
                fixture.registry,
                active["policy_id"],
                retired_by="operator",
                retired_at="2026-07-24T05:00:00Z",
                reason="Policy replaced by external control.",
                materialized_rules=fixture.materialized,
            )
            self.assertEqual("RETIRED", retired["status"])
            self.assertIsNone(load_data(fixture.registry)["active_policy_id"])
            self.assertEqual([], load_rules(fixture.materialized, required_status="approved")["rules"])
            self.assertEqual([], verify_policy_registry_file(
                fixture.registry,
                materialized_rules=fixture.materialized,
            ))

    def test_materialize_command_recreates_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            active = fixture.activate_root()
            fixture.materialized.unlink()
            target = materialize_active_policy(fixture.registry, fixture.materialized)
            self.assertEqual(fixture.materialized.resolve(), target)
            self.assertEqual(active["ruleset"]["rules"], load_rules(target, required_status="approved"))

    def test_mismatched_evaluation_and_duplicate_version_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            with self.assertRaisesRegex(PolicyRegistryError, "challenger Policy hash"):
                build_policy(
                    fixture.registry,
                    project_id="demo",
                    version="1.0.0",
                    rules=fixture.rules_ab,
                    evaluation_report=fixture.report_a,
                    created_by="builder",
                    created_at="2026-07-24T01:00:00Z",
                )
            fixture.build_root()
            with self.assertRaisesRegex(PolicyRegistryError, "version already exists"):
                fixture.build_root()

    def test_activation_requires_current_active_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            parent_draft = fixture.build_root()
            child = fixture.build_child(parent_draft["policy_id"])
            with self.assertRaisesRegex(PolicyRegistryError, "first active Policy"):
                approve_policy(
                    fixture.registry,
                    child["policy_id"],
                    approved_by="approver",
                    approved_at="2026-07-24T04:00:00Z",
                    materialized_rules=fixture.materialized,
                )


if __name__ == "__main__":
    unittest.main()

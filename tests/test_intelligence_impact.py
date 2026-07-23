import unittest

from review_system.intelligence_impact import analyze_change, compare_change_sets


GRAPH = {
    "schema_version": "1.0",
    "graph_sha256": "abc",
    "nodes": [
        {"id": "file:src/core.py", "type": "file", "path": "src/core.py"},
        {"id": "file:src/api.py", "type": "file", "path": "src/api.py"},
        {"id": "file:tests/test_core.py", "type": "file", "path": "tests/test_core.py"},
        {"id": "file:docs/contract.md", "type": "file", "path": "docs/contract.md"},
        {"id": "component:recommendation", "type": "component", "name": "Recommendation"},
    ],
    "edges": [
        {"source": "file:src/api.py", "target": "file:src/core.py", "type": "imports"},
        {"source": "file:tests/test_core.py", "target": "file:src/core.py", "type": "verifies"},
        {"source": "component:recommendation", "target": "file:src/core.py", "type": "contains"},
    ],
}


class IntelligenceImpactTests(unittest.TestCase):
    def test_analyzes_dependents_rules_packs_and_tests(self):
        rules = [{
            "id": "RULE_001",
            "title": "Core contract",
            "status": "approved",
            "trigger": {"paths_any": ["src/core.py"]},
            "impact": {"paths": ["docs/contract.md"], "components": ["recommendation"]},
            "review": {"packs": ["domain.recommendation"], "required_tests": ["python -m unittest"]},
            "rationale": "Explicit contract",
            "approval": {"approved_by": "owner", "approved_at": "2026-07-20T00:00:00Z"},
        }]
        result = analyze_change(
            GRAPH,
            ["src/core.py"],
            configured_packs=["domain.recommendation", "universal.test-completeness"],
            approved_rules=rules,
        )
        impacted = {item["path"] for item in result["impact"]["dependent_files"]}
        self.assertIn("src/api.py", impacted)
        self.assertIn("tests/test_core.py", impacted)
        self.assertIn("docs/contract.md", impacted)
        self.assertIn("domain.recommendation", result["review"]["selected_packs"])
        self.assertIn("python -m unittest", result["review"]["required_tests"])

    def test_compare_change_sets_is_advisory_and_deterministic(self):
        result = compare_change_sets([
            {"id": "PR-1", "base_revision": "a", "changed_files": ["src/a.py"], "impacted_files": ["src/shared.py"], "components": ["core"]},
            {"id": "PR-2", "base_revision": "b", "changed_files": ["src/b.py"], "impacted_files": ["src/shared.py"], "components": ["core"]},
        ])
        item = result["comparisons"][0]
        self.assertEqual("medium", item["risk_level"])
        self.assertTrue(item["base_revision_mismatch"])
        self.assertIn("src/shared.py", item["impact_overlap"])

    def test_directly_changed_verifier_is_a_required_test(self):
        graph = {
            **GRAPH,
            "nodes": [
                *GRAPH["nodes"],
                {
                    "id": "file:scripts/verify-evaluator.mjs",
                    "type": "file",
                    "path": "scripts/verify-evaluator.mjs",
                    "language": "javascript",
                },
            ],
        }
        result = analyze_change(
            graph,
            ["scripts/verify-evaluator.mjs"],
            configured_packs=["universal.test-completeness"],
        )
        self.assertIn("scripts/verify-evaluator.mjs", result["review"]["required_tests"])

    def test_test_substrings_inside_normal_words_are_not_required_tests(self):
        paths = ("scripts/inspect-source.mjs", "scripts/generate-attestation.mjs")
        graph = {
            **GRAPH,
            "nodes": [
                *GRAPH["nodes"],
                *(
                    {"id": f"file:{path}", "type": "file", "path": path, "language": "javascript"}
                    for path in paths
                ),
            ],
        }
        result = analyze_change(graph, paths, configured_packs=["universal.test-completeness"])
        self.assertEqual([], result["review"]["required_tests"])

    def test_changed_verification_script_is_a_required_test(self):
        path = "verification/dp4/run_dp4_static_verification.py"
        graph = {
            **GRAPH,
            "nodes": [
                *GRAPH["nodes"],
                {"id": f"file:{path}", "type": "file", "path": path, "language": "python"},
            ],
        }
        result = analyze_change(graph, [path], configured_packs=["universal.test-completeness"])
        self.assertEqual([path], result["review"]["required_tests"])

    def test_test_helpers_and_verification_sources_are_not_runnable_tests(self):
        paths = (
            "src/test/java/demo/CanonicalPostgresInitializer.java",
            "src/test/resources/db/27_projection.sql",
            "verification/ip12/direct-src/demo/OperationalContract.java",
        )
        languages = ("java", "sql", "java")
        graph = {
            **GRAPH,
            "nodes": [
                *GRAPH["nodes"],
                *(
                    {"id": f"file:{path}", "type": "file", "path": path, "language": language}
                    for path, language in zip(paths, languages)
                ),
            ],
        }
        result = analyze_change(graph, paths, configured_packs=["universal.test-completeness"])
        self.assertEqual([], result["review"]["required_tests"])

    def test_rule_pack_not_in_profile_is_reported_not_selected(self):
        rules = [{
            "id": "RULE_002",
            "title": "Unknown pack request",
            "status": "approved",
            "trigger": {"paths_any": ["src/core.py"]},
            "impact": {"paths": [], "components": []},
            "review": {"packs": ["domain.ai-inference"], "required_tests": []},
            "rationale": "Explicit rule",
            "approval": {"approved_by": "owner", "approved_at": "2026-07-20T00:00:00Z"},
        }]
        result = analyze_change(GRAPH, ["src/core.py"], configured_packs=["universal.test-completeness"], approved_rules=rules)
        self.assertNotIn("domain.ai-inference", result["review"]["selected_packs"])
        self.assertIn("domain.ai-inference", result["review"]["unconfigured_rule_packs"])

    def test_compare_detects_cross_component_shared_review_domain(self):
        result = compare_change_sets([
            {"id": "CORE", "changed_files": ["core/P2.java"], "components": ["core"], "review_packs": ["domain.recommendation"]},
            {"id": "DB", "changed_files": ["db/25.sql"], "components": ["database"], "review_packs": ["domain.recommendation"]},
        ])
        item = result["comparisons"][0]
        self.assertEqual("medium", item["risk_level"])
        self.assertEqual(["domain.recommendation"], item["review_pack_overlap"])


if __name__ == "__main__":
    unittest.main()

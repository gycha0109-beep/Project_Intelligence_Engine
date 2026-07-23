import unittest

from review_system.intelligence_learning import approve_candidate_rule, discover_rule_candidates, merge_rule_candidates


class IntelligenceLearningTests(unittest.TestCase):
    def test_discovers_asymmetric_candidate_without_auto_approval(self):
        history = [
            {"id": "1", "changed_files": ["src/survey/a.ts", "src/recommend/b.ts"]},
            {"id": "2", "changed_files": ["src/survey/c.ts", "src/recommend/d.ts"]},
            {"id": "3", "changed_files": ["src/survey/e.ts", "src/recommend/f.ts"]},
            {"id": "4", "changed_files": ["src/recommend/g.ts"]},
        ]
        result = discover_rule_candidates(history, min_samples=3, min_confidence=0.75, min_support=0.5)
        self.assertTrue(result["rules"])
        self.assertTrue(all(rule["status"] == "candidate" for rule in result["rules"]))

    def test_approval_requires_explicit_actor_and_preserves_candidate_audit(self):
        candidates = discover_rule_candidates([
            {"id": "1", "changed_files": ["src/survey/a.ts", "src/recommend/b.ts"]},
            {"id": "2", "changed_files": ["src/survey/c.ts", "src/recommend/d.ts"]},
            {"id": "3", "changed_files": ["src/survey/e.ts", "src/recommend/f.ts"]},
        ], min_samples=3, min_confidence=0.75, min_support=0.5)
        candidate_id = candidates["rules"][0]["id"]
        updated_candidates, approved = approve_candidate_rule(
            candidates,
            {"schema_version": "1.0", "rules": []},
            candidate_id,
            approved_by="maintainer",
            approved_at="2026-07-20T00:00:00Z",
        )
        self.assertEqual("approved", updated_candidates["rules"][0]["status"])
        self.assertEqual("approved", approved["rules"][0]["status"])
        self.assertEqual("maintainer", approved["rules"][0]["approval"]["approved_by"])

    def test_candidate_rediscovery_preserves_human_decision(self):
        discovered = discover_rule_candidates([
            {"id": "1", "changed_files": ["src/a/x.ts", "src/b/y.ts"]},
            {"id": "2", "changed_files": ["src/a/z.ts", "src/b/q.ts"]},
            {"id": "3", "changed_files": ["src/a/m.ts", "src/b/n.ts"]},
        ], min_samples=3, min_confidence=0.75, min_support=0.5)
        candidate_id = discovered["rules"][0]["id"]
        existing = {
            "schema_version": "1.0",
            "rules": [{**discovered["rules"][0], "status": "rejected", "decision": {"rejected_by": "owner", "reason": "false association"}}],
        }
        merged = merge_rule_candidates(existing, discovered)
        rule = next(item for item in merged["rules"] if item["id"] == candidate_id)
        self.assertEqual("rejected", rule["status"])
        self.assertIn("latest_observation", rule)


if __name__ == "__main__":
    unittest.main()

import unittest

from review_system.packs import lock_packs, select_packs, select_packs_with_reasons


class PackSelectionTests(unittest.TestCase):
    def test_sql_migration_selects_data_packs(self):
        configured = ["data.relational-integrity", "data.migration-safety", "universal.test-completeness"]
        selected = select_packs(["supabase/migrations/001.sql"], configured)
        self.assertEqual(sorted(configured), selected)

    def test_test_fixture_sql_does_not_select_migration_safety(self):
        configured = ["data.relational-integrity", "data.migration-safety", "universal.test-completeness"]
        selected = select_packs(["src/test/resources/db/canonical/28_projection_smoke_test.sql"], configured)
        self.assertEqual(["data.relational-integrity", "universal.test-completeness"], selected)

    def test_only_configured_packs_are_returned(self):
        selected = select_packs(["src/auth/session.ts"], ["universal.test-completeness"])
        self.assertEqual(["universal.test-completeness"], selected)

    def test_token_matching_avoids_api_substring_false_positive(self):
        configured = ["application.authorization", "universal.test-completeness"]
        selected = select_packs(["src/capitalization.ts"], configured)
        self.assertEqual(["universal.test-completeness"], selected)

    def test_empty_change_set_selects_nothing(self):
        self.assertEqual([], select_packs([], ["universal.test-completeness"]))

    def test_reasons_are_preserved(self):
        result = select_packs_with_reasons(["src/search/cursor.ts"], ["domain.search", "universal.test-completeness"])
        self.assertIn("src/search/cursor.ts", result["domain.search"])

    def test_pack_lock_contains_versions(self):
        lock = lock_packs(["domain.search"])
        self.assertEqual("domain.search", lock[0]["pack_id"])
        self.assertRegex(lock[0]["version"], r"^\d+\.\d+\.\d+$")

    def test_contract_decision_selects_traceability(self):
        configured = ["universal.requirements-traceability", "universal.test-completeness"]
        selected = select_packs(["docs/DP-2-ENTRY-CONTRACT-DECISION.md"], configured)
        self.assertEqual(sorted(configured), selected)

class PackPathSafetyTests(unittest.TestCase):
    def test_invalid_pack_id_is_rejected(self):
        with self.assertRaises(ValueError):
            lock_packs(["domain..search"])

if __name__ == "__main__":
    unittest.main()

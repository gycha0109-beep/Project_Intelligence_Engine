from __future__ import annotations

import unittest

from review_system.prospective_execution_identity import build_prospective_execution_identity


class ProspectiveExecutionIdentityTests(unittest.TestCase):
    def test_same_binding_produces_same_identity(self):
        kwargs = {
            "repository": "Demo/Repo",
            "pull_request": 7,
            "source_revision": "a" * 40,
            "pie_revision": "b" * 40,
            "profile_sha256": "c" * 64,
            "config_sha256": "d" * 64,
            "trust_request_sha256": None,
        }
        first = build_prospective_execution_identity(**kwargs)
        second = build_prospective_execution_identity(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual("demo/repo", first.repository)
        self.assertTrue(first.execution_id.startswith("pie-pr-auto-"))

    def test_binding_change_changes_identity(self):
        common = {
            "repository": "demo/repo",
            "pull_request": 7,
            "pie_revision": "b" * 40,
            "profile_sha256": "c" * 64,
            "config_sha256": "d" * 64,
            "trust_request_sha256": None,
        }
        first = build_prospective_execution_identity(source_revision="a" * 40, **common)
        second = build_prospective_execution_identity(source_revision="e" * 40, **common)
        self.assertNotEqual(first.execution_id, second.execution_id)
        self.assertNotEqual(first.execution_key_sha256, second.execution_key_sha256)

    def test_rejects_symbolic_or_short_revision(self):
        with self.assertRaisesRegex(ValueError, "exact 40-character"):
            build_prospective_execution_identity(
                repository="demo/repo",
                pull_request=7,
                source_revision="main",
                pie_revision="b" * 40,
                profile_sha256="c" * 64,
                config_sha256="d" * 64,
                trust_request_sha256=None,
            )


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from review_system.baseline import compare_snapshot, create_snapshot
from review_system.io import dump_yaml


class ProtectedBaselineTests(unittest.TestCase):
    def _profile(self, root: Path) -> Path:
        profile = root / ".review" / "project.yml"
        profile.parent.mkdir()
        dump_yaml(profile, {
            "schema_version": "1.0",
            "project": {"id": "baseline-test", "name": "Baseline", "repository_root": ".", "baseline_branch": "main"},
            "technology": {"languages": ["python"]},
            "scope": {"include": ["src/**"], "exclude": []},
            "protected_paths": ["protected/**"],
            "commands": {"baseline": ["pytest"]},
            "review": {"packs": ["universal.test-completeness"]},
            "gate": {"block_on": ["P0", "P1"], "require": {"baseline_tests": True}},
            "constraints": {},
        })
        return profile

    def test_snapshot_detects_modified_added_and_deleted_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = self._profile(root)
            protected = root / "protected"
            protected.mkdir()
            (protected / "a.txt").write_text("a", encoding="utf-8")
            (protected / "b.txt").write_text("b", encoding="utf-8")
            snapshot = create_snapshot(profile)
            self.assertTrue(compare_snapshot(snapshot)["intact"])

            (protected / "a.txt").write_text("changed", encoding="utf-8")
            (protected / "b.txt").unlink()
            (protected / "c.txt").write_text("c", encoding="utf-8")
            result = compare_snapshot(snapshot)
            self.assertFalse(result["intact"])
            self.assertEqual(["protected/a.txt"], result["modified"])
            self.assertEqual(["protected/b.txt"], result["deleted"])
            self.assertEqual(["protected/c.txt"], result["added"])

    def test_journey_sql_protection_patterns_match_01_through_34_only(self):
        from review_system.baseline import collect_protected_files
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "database" / "journey-connect-db-v2.7"
            directory.mkdir(parents=True)
            for name in ("01_initial_schema.sql", "28_search.sql", "34_retry.sql", "35_new.sql"):
                (directory / name).write_text("-- sql\n", encoding="utf-8")
            patterns = [
                "database/journey-connect-db-v2.7/0[1-9]_*",
                "database/journey-connect-db-v2.7/1[0-9]_*",
                "database/journey-connect-db-v2.7/2[0-9]_*",
                "database/journey-connect-db-v2.7/3[0-4]_*",
            ]
            matched = {path.name for path in collect_protected_files(root, patterns)}
            self.assertEqual({"01_initial_schema.sql", "28_search.sql", "34_retry.sql"}, matched)

class ProtectedBaselineSafetyTests(unittest.TestCase):
    def test_unsafe_pattern_is_rejected(self):
        from review_system.baseline import BaselineError, collect_protected_files
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BaselineError):
                collect_protected_files(Path(tmp), ["../outside/**"])

    def test_protected_symlink_is_rejected(self):
        import os
        from review_system.baseline import BaselineError, collect_protected_files
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "target.txt").write_text("x", encoding="utf-8")
            try:
                os.symlink(root / "target.txt", root / "protected-link")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(BaselineError):
                collect_protected_files(root, ["protected-link"])

if __name__ == "__main__":
    unittest.main()

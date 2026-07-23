import tempfile
import unittest
from pathlib import Path

from review_system.io import dump_yaml
from review_system.profile import ProfileResolutionError, resolve_profile_data, resolve_profile_file


class ProfileResolutionTests(unittest.TestCase):
    def test_stack_defaults_are_inherited_and_project_overrides_commands(self):
        profile = resolve_profile_file("profiles/examples/journey-connect.yml")
        self.assertIn("application.authentication", profile["review"]["packs"])
        self.assertIn("domain.recommendation", profile["review"]["packs"])
        self.assertIn("data.migration-safety", profile["review"]["packs"])
        self.assertEqual(["./jc-backend/gradlew -p jc-backend test"], profile["commands"]["baseline"])
        self.assertEqual(["spring-postgres"], profile["resolved_inherits"])

    def test_excluded_pack_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = root / "project.yml"
            dump_yaml(profile_path, {
                "schema_version": "1.0",
                "inherits": ["spring-postgres"],
                "project": {"id": "x", "name": "X", "repository_root": ".", "baseline_branch": "main"},
                "technology": {"languages": ["java"]},
                "scope": {"include": ["src/**"], "exclude": []},
                "review": {"packs": ["universal.architecture"], "exclude_packs": ["application.authentication"]},
                "gate": {"block_on": ["P0", "P1"], "require": {}},
                "constraints": {},
            })
            resolved = resolve_profile_file(profile_path)
            self.assertNotIn("application.authentication", resolved["review"]["packs"])
            self.assertIn("universal.architecture", resolved["review"]["packs"])

    def test_unknown_stack_is_rejected(self):
        with self.assertRaises(ProfileResolutionError):
            resolve_profile_data({"inherits": ["missing-stack"]})

    def test_stack_cycle_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dump_yaml(root / "a.yml", {"stack_id": "a", "inherits": ["b"]})
            dump_yaml(root / "b.yml", {"stack_id": "b", "inherits": ["a"]})
            with self.assertRaises(ProfileResolutionError):
                resolve_profile_data({"inherits": ["a"]}, stack_directories=[root])

class LocalStackTests(unittest.TestCase):
    def test_project_local_stack_directory_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stacks = root / "stacks"
            stacks.mkdir()
            dump_yaml(stacks / "custom.yml", {
                "stack_id": "custom",
                "technology": {"languages": ["python"]},
                "commands": {"baseline": ["pytest"]},
                "review": {"packs": ["universal.test-completeness"]},
            })
            profile = root / "project.yml"
            dump_yaml(profile, {
                "schema_version": "1.0",
                "inherits": ["custom"],
                "project": {"id": "custom-project", "name": "Custom", "repository_root": ".", "baseline_branch": "main"},
                "technology": {"languages": ["sql"]},
                "scope": {"include": ["src/**"], "exclude": []},
                "review": {"packs": []},
                "gate": {"block_on": ["P0"], "require": {}},
                "constraints": {},
            })
            resolved = resolve_profile_file(profile)
            self.assertEqual(["python", "sql"], resolved["technology"]["languages"])
            self.assertEqual(["pytest"], resolved["commands"]["baseline"])

class ProfilePathSafetyTests(unittest.TestCase):
    def test_stack_path_traversal_is_rejected(self):
        with self.assertRaises(ProfileResolutionError):
            resolve_profile_data({"inherits": ["../secret"]})

if __name__ == "__main__":
    unittest.main()

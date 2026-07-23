import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from review_system.io import dump_json, load_data
from review_system.run import (
    archive_run,
    calculate_gate_directory,
    initialize_run,
    sync_run,
    validate_run_directory,
    verify_manifest,
)


class RunTests(unittest.TestCase):
    def test_initialize_sync_archive_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = initialize_run("profiles/examples/journey-connect.yml", root / "run", "full")
            self.assertTrue((run / "run.json").exists())
            self.assertTrue((run / "initial-manifest.sha256").exists())
            self.assertTrue((run / "project-profile.resolved.yml").exists())
            self.assertTrue((run / "packs.lock.json").exists())
            resolved = load_data(run / "project-profile.resolved.yml")
            self.assertIn("application.authentication", resolved["review"]["packs"])

            synced = sync_run(run)
            self.assertEqual([], synced["findings"])
            self.assertEqual([], validate_run_directory(run))
            calculate_gate_directory(run)
            self.assertEqual([], validate_run_directory(run, require_gate=True))

            archive = archive_run(run, root / "run.zip")
            self.assertTrue(archive.exists())
            self.assertTrue((run / "manifest.sha256").exists())
            self.assertTrue(verify_manifest(run)["valid"])
            with zipfile.ZipFile(archive) as handle:
                self.assertIn("run/manifest.sha256", handle.namelist())

    def test_sync_run_hydrates_findings_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = initialize_run("profiles/examples/journey-connect.yml", Path(tmp) / "run", "full")
            finding = load_data("examples/findings.sample.json")[0]
            dump_json(run / "findings.json", [finding])
            synced = sync_run(run)
            self.assertEqual(1, len(synced["findings"]))
            self.assertEqual(1, synced["metrics"]["open_confirmed_p1"])

    def test_unsynchronized_run_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = initialize_run("profiles/examples/journey-connect.yml", root / "run", "full")
            dump_json(run / "findings.json", load_data("examples/findings.sample.json"))
            errors = validate_run_directory(run)
            self.assertTrue(any("not synchronized" in error for error in errors))
            with self.assertRaises(ValueError):
                archive_run(run, root / "run.zip")

    def test_archive_output_inside_run_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = initialize_run("profiles/examples/journey-connect.yml", Path(tmp) / "run", "full")
            sync_run(run)
            with self.assertRaises(ValueError):
                archive_run(run, run / "archive.zip")

class RelativeManifestTests(unittest.TestCase):
    def test_relative_run_path_manifest_verification(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            try:
                os.chdir(tmp)
                run = initialize_run(str(Path(previous) / "profiles/examples/journey-connect.yml"), "relative-run", "full")
                sync_run(run)
                calculate_gate_directory(run)
                archive_run(run, "relative-run.zip")
                self.assertTrue(verify_manifest("relative-run")["valid"])
            finally:
                os.chdir(previous)

class RunInputAndGateConsistencyTests(unittest.TestCase):
    def test_companion_review_inputs_are_copied(self):
        from review_system.io import dump_yaml
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / ".review"
            review.mkdir()
            profile = review / "project.yml"
            dump_yaml(profile, {
                "schema_version": "1.0",
                "project": {"id": "inputs", "name": "Inputs", "repository_root": ".", "baseline_branch": "main"},
                "technology": {"languages": ["python"]},
                "scope": {"include": ["src/**"], "exclude": []},
                "commands": {"baseline": ["pytest"]},
                "review": {"packs": ["universal.test-completeness"]},
                "gate": {"block_on": ["P0", "P1"], "require": {"baseline_tests": True}},
                "constraints": {},
            })
            (review / "invariants.md").write_text("# Invariants\n", encoding="utf-8")
            (review / "architecture-entrypoints.yml").write_text("entrypoints: []\n", encoding="utf-8")
            (review / "accepted-risks.md").write_text("# Risks\n", encoding="utf-8")
            run = initialize_run(profile, root / "run", "full")
            self.assertTrue((run / "inputs/invariants.md").exists())
            self.assertTrue((run / "inputs/architecture-entrypoints.yml").exists())
            self.assertTrue((run / "inputs/accepted-risks.md").exists())

    def test_archive_rejects_stale_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = initialize_run("profiles/examples/journey-connect.yml", root / "run", "full")
            sync_run(run)
            calculate_gate_directory(run)
            data = load_data(run / "run.json")
            data["metrics"]["required_tests_passed"] = True
            dump_json(run / "run.json", data)
            errors = validate_run_directory(run, require_gate=True)
            self.assertTrue(any("gate-result.json" in error for error in errors))
            with self.assertRaises(ValueError):
                archive_run(run, root / "run.zip")

class ManifestPathSafetyTests(unittest.TestCase):
    def test_manifest_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.sha256").write_text("0" * 64 + "  ../outside.txt\n", encoding="utf-8")
            result = verify_manifest(root)
            self.assertFalse(result["valid"])
            self.assertTrue(any("unsafe path" in item for item in result["malformed"]))

if __name__ == "__main__":
    unittest.main()

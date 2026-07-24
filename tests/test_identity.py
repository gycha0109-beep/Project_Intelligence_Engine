import tempfile
import unittest
from pathlib import Path

from review_system.application import AnalyzePullRequestRequest, analyze_pull_request
from review_system.identity import (
    IDENTITY_FILENAME,
    build_identity_manifest,
    derive_artifact_identity,
    derive_run_identity,
    normalize_relative_path,
    normalize_source_revision,
    validate_identity_manifest,
    write_identity_manifest,
)
from review_system.io import dump_json, load_data
from review_system.project_init import initialize_project
from review_system.run import calculate_gate_directory, initialize_run, sync_run
from tests.test_github_connector import StubGitHubCLI


class IdentityPrimitiveTests(unittest.TestCase):
    def test_run_identity_is_deterministic_and_revision_sensitive(self):
        first = derive_run_identity(
            project_id="demo",
            run_type="pull_request",
            source_revision="ABCDEF1",
            source_identifier="github://github.com/demo/repo/pull/7",
        )
        second = derive_run_identity(
            project_id="demo",
            run_type="pull_request",
            source_revision="abcdef1",
            source_identifier="github://github.com/demo/repo/pull/7",
        )
        changed = derive_run_identity(
            project_id="demo",
            run_type="pull_request",
            source_revision="abcdef2",
            source_identifier="github://github.com/demo/repo/pull/7",
        )
        self.assertEqual(first, second)
        self.assertEqual("git:abcdef1", first.source_revision)
        self.assertNotEqual(first.run_id, changed.run_id)
        self.assertEqual(36, len(first.run_id))

    def test_symbolic_revision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "symbolic revision"):
            normalize_source_revision("HEAD")

    def test_artifact_path_move_changes_identity_but_not_content_hash(self):
        run = derive_run_identity(
            project_id="demo",
            run_type="review",
            source_revision="unresolved",
            source_identifier="review://demo/run-1",
        )
        first = derive_artifact_identity(
            run_key_sha256=run.run_key_sha256,
            relative_path="reports/result.json",
            sha256="1" * 64,
            size_bytes=10,
        )
        moved = derive_artifact_identity(
            run_key_sha256=run.run_key_sha256,
            relative_path="archive/result.json",
            sha256="1" * 64,
            size_bytes=10,
        )
        self.assertNotEqual(first.artifact_id, moved.artifact_id)
        self.assertEqual(first.sha256, moved.sha256)

    def test_path_escape_and_symlink_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            outside = Path(tmp) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escapes root"):
                normalize_relative_path(root, "../outside.txt")
            link = root / "outside-link.txt"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                return
            with self.assertRaisesRegex(ValueError, "escapes root"):
                normalize_relative_path(root, link)


class IdentityManifestTests(unittest.TestCase):
    def test_manifest_is_sorted_deterministic_and_excludes_recursive_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "z.txt").write_text("z", encoding="utf-8")
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "initial-manifest.sha256").write_text("snapshot\n", encoding="utf-8")
            run = derive_run_identity(
                project_id="demo",
                run_type="review",
                source_revision="unresolved",
                source_identifier="review://demo/run-1",
            )
            first = build_identity_manifest(root, run)
            write_identity_manifest(root, run)
            second = build_identity_manifest(root, run)
            self.assertEqual(first, second)
            self.assertEqual(["a.txt", "z.txt"], [item["relative_path"] for item in first["artifacts"]])
            self.assertNotIn(IDENTITY_FILENAME, {item["relative_path"] for item in first["artifacts"]})
            self.assertEqual([], validate_identity_manifest(root))

    def test_validation_detects_modified_missing_and_unexpected_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            run = derive_run_identity(
                project_id="demo",
                run_type="review",
                source_revision="unresolved",
                source_identifier="review://demo/run-1",
            )
            write_identity_manifest(root, run)
            first.write_text("changed", encoding="utf-8")
            second.unlink()
            (root / "third.txt").write_text("third", encoding="utf-8")
            errors = validate_identity_manifest(root)
            self.assertTrue(any("modified artifact: first.txt" in error for error in errors))
            self.assertTrue(any("missing artifact: second.txt" in error for error in errors))
            self.assertTrue(any("unexpected artifact: third.txt" in error for error in errors))

    def test_manifest_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence.json").write_text("{}\n", encoding="utf-8")
            run = derive_run_identity(
                project_id="demo",
                run_type="review",
                source_revision="unresolved",
                source_identifier="review://demo/run-1",
            )
            write_identity_manifest(root, run)
            manifest = load_data(root / IDENTITY_FILENAME)
            manifest["run"]["project_id"] = "other"
            dump_json(root / IDENTITY_FILENAME, manifest)
            errors = validate_identity_manifest(root)
            self.assertTrue(any("manifest_sha256 mismatch" in error for error in errors))
            self.assertTrue(any("run.run_id" in error or "run.run_key_sha256" in error for error in errors))


class IdentityIntegrationTests(unittest.TestCase):
    def test_review_run_identity_is_created_refreshed_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = initialize_run("profiles/examples/journey-connect.yml", root / "review-run", "full")
            run = load_data(run_root / "run.json")
            logical_run_id = run["identity"]["logical_run_id"]
            self.assertTrue((run_root / IDENTITY_FILENAME).is_file())

            sync_run(run_root)
            calculate_gate_directory(run_root)
            refreshed = load_data(run_root / "run.json")
            self.assertEqual(logical_run_id, refreshed["identity"]["logical_run_id"])
            self.assertEqual([], validate_identity_manifest(run_root))

    def test_legacy_review_run_is_upgraded_on_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = initialize_run("profiles/examples/journey-connect.yml", root / "legacy-run", "full")
            run = load_data(run_root / "run.json")
            run.pop("identity", None)
            dump_json(run_root / "run.json", run)
            (run_root / IDENTITY_FILENAME).unlink()

            synced = sync_run(run_root)
            self.assertEqual("review", synced["identity"]["run_type"])
            self.assertEqual("unresolved", synced["identity"]["source_revision"])
            self.assertEqual([], validate_identity_manifest(run_root))

    def test_pr_analysis_writes_identity_without_changing_existing_hash_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "app").mkdir()
            (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
            (root / "app" / "api.ts").write_text("import { score } from '../src/core'\n", encoding="utf-8")
            initialize_project(root, preset="generic-webapp")
            output = root / "analysis"

            result = analyze_pull_request(
                AnalyzePullRequestRequest(
                    pull_request="https://github.com/demo/repo/pull/7",
                    repository_root=root,
                    output_dir=output,
                ),
                github_cli=StubGitHubCLI(),
            )

            source = load_data(result.source_path)
            impact = load_data(result.impact_path)
            identity = load_data(output / IDENTITY_FILENAME)
            self.assertEqual(source["source_sha256"], impact["source_evidence_sha256"])
            self.assertEqual("pull_request", identity["run"]["run_type"])
            self.assertEqual("github://github.com/demo/repo/pull/7", identity["run"]["source_identifier"])
            self.assertEqual([], validate_identity_manifest(output))


if __name__ == "__main__":
    unittest.main()

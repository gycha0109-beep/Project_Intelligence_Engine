import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from review_system.cli import main
from review_system.io import load_data
from tests.test_github_connector import StubGitHubCLI


class ProjectInitAndPullRequestCliTests(unittest.TestCase):
    def test_all_presets_initialize_and_validate(self):
        for preset in ("bejewely", "buildmap", "journey-connect", "generic-webapp"):
            with self.subTest(preset=preset), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.assertEqual(0, main(["init-project", "--preset", preset, "--repository-root", str(root)]))
                self.assertEqual(0, main(["validate-profile", str(root / ".review" / "project.yml")]))
                self.assertEqual(0, main(["validate-intelligence-config", str(root / ".review" / "intelligence" / "config.yml")]))

    def test_init_project_is_non_destructive_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root)]))
            profile = root / ".review" / "project.yml"
            profile.write_text("custom: true\n", encoding="utf-8")
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root)]))
            self.assertEqual("custom: true\n", profile.read_text(encoding="utf-8"))
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root), "--force"]))
            self.assertIn('schema_version: "1.0"', profile.read_text(encoding="utf-8"))

    def test_init_project_adds_pie_to_gitignore_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gitignore = root / ".gitignore"
            gitignore.write_text("node_modules/\n", encoding="utf-8")
            self.assertEqual(0, main(["init-project", "--preset", "bejewely", "--repository-root", str(root)]))
            self.assertEqual("node_modules/\n.pie/\n", gitignore.read_text(encoding="utf-8"))
            self.assertEqual(0, main(["init-project", "--preset", "bejewely", "--repository-root", str(root)]))
            self.assertEqual(1, gitignore.read_text(encoding="utf-8").count(".pie/"))

    def test_analyze_pr_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "app").mkdir()
            (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
            (root / "app" / "api.ts").write_text("import { score } from '../src/core'\n", encoding="utf-8")
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root)]))
            output = root / "analysis"
            with patch("review_system.cli.GitHubCLI", return_value=StubGitHubCLI()):
                code = main([
                    "analyze-pr",
                    "https://github.com/demo/repo/pull/7",
                    "--repository-root", str(root),
                    "--output-dir", str(output),
                ])
            self.assertEqual(0, code)
            self.assertTrue((output / "github-source.json").is_file())
            self.assertTrue((output / "pull-request.diff").is_file())
            self.assertTrue((output / "REPORT.md").is_file())
            impact = load_data(output / "impact.json")
            impacted = {item["path"] for item in impact["impact"]["dependent_files"]}
            self.assertIn("app/api.ts", impacted)
            source = load_data(output / "github-source.json")
            self.assertEqual(0, main(["validate-github-source", str(output / "github-source.json")]))
            self.assertEqual("matched", source["local_repository_verification"]["status"])
            self.assertEqual(source["source_sha256"], impact["source_evidence_sha256"])
            self.assertEqual(
                source["diff"]["sha256"],
                hashlib.sha256((output / "pull-request.diff").read_bytes()).hexdigest(),
            )

    def test_repository_mismatch_is_blocked_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root)]))
            with patch("review_system.cli.GitHubCLI", return_value=StubGitHubCLI(repository="other/repo")):
                code = main([
                    "analyze-pr",
                    "https://github.com/demo/repo/pull/7",
                    "--repository-root", str(root),
                    "--output-dir", str(root / "analysis"),
                ])
            self.assertEqual(2, code)
            self.assertFalse((root / "analysis" / "impact.json").exists())

    def test_unverified_repository_is_blocked_by_default(self):
        class UnverifiedGitHubCLI(StubGitHubCLI):
            def current_repository(self, cwd):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root)]))
            with patch("review_system.cli.GitHubCLI", return_value=UnverifiedGitHubCLI()):
                blocked = main([
                    "analyze-pr", "https://github.com/demo/repo/pull/7",
                    "--repository-root", str(root), "--output-dir", str(root / "blocked"),
                ])
                allowed = main([
                    "analyze-pr", "https://github.com/demo/repo/pull/7",
                    "--repository-root", str(root), "--output-dir", str(root / "allowed"),
                    "--allow-repository-mismatch",
                ])
            self.assertEqual(2, blocked)
            self.assertEqual(0, allowed)

    def test_head_mismatch_requires_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root)]))
            state = {"repository": {"head_revision": "different", "working_tree_dirty": False, "working_tree_entries": []}}
            with (
                patch("review_system.cli.GitHubCLI", return_value=StubGitHubCLI()),
                patch("review_system.cli.capture_project_state", return_value=state),
            ):
                blocked = main([
                    "analyze-pr", "https://github.com/demo/repo/pull/7",
                    "--repository-root", str(root), "--output-dir", str(root / "blocked"),
                ])
                allowed = main([
                    "analyze-pr", "https://github.com/demo/repo/pull/7",
                    "--repository-root", str(root), "--output-dir", str(root / "allowed"),
                    "--allow-head-mismatch",
                ])
            self.assertEqual(2, blocked)
            self.assertEqual(0, allowed)

    def test_failed_diff_collection_removes_stale_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root)]))
            output = root / "analysis"
            with patch("review_system.cli.GitHubCLI", return_value=StubGitHubCLI()):
                self.assertEqual(0, main(["analyze-pr", "https://github.com/demo/repo/pull/7", "--repository-root", str(root), "--output-dir", str(output)]))
            self.assertTrue((output / "pull-request.diff").exists())
            with patch("review_system.cli.GitHubCLI", return_value=StubGitHubCLI(diff_failure=True)):
                self.assertEqual(0, main(["analyze-pr", "https://github.com/demo/repo/pull/7", "--repository-root", str(root), "--output-dir", str(output)]))
            self.assertFalse((output / "pull-request.diff").exists())

    def test_stale_cached_graph_is_rebuilt_for_pr_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "app").mkdir()
            (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
            (root / "app" / "api.ts").write_text("import { score } from '../src/core'\n", encoding="utf-8")
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root)]))
            graph_path = root / ".review" / "intelligence" / "graph.json"
            graph_path.write_text(json.dumps({"schema_version": "1.0", "nodes": [], "edges": [], "graph_sha256": "stale"}), encoding="utf-8")
            output = root / "analysis"
            with patch("review_system.cli.GitHubCLI", return_value=StubGitHubCLI()):
                self.assertEqual(0, main(["analyze-pr", "https://github.com/demo/repo/pull/7", "--repository-root", str(root), "--output-dir", str(output)]))
            impact = load_data(output / "impact.json")
            self.assertIn("app/api.ts", {item["path"] for item in impact["impact"]["dependent_files"]})

    def test_scoped_dirty_worktree_requires_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
            self.assertEqual(0, main(["init-project", "--preset", "generic-webapp", "--repository-root", str(root)]))
            state = {"repository": {
                "head_revision": "head123", "working_tree_dirty": True,
                "working_tree_entries": ["R  src/core.ts -> docs/core.ts", "?? .review/intelligence/graph.json"],
            }}
            with (
                patch("review_system.cli.GitHubCLI", return_value=StubGitHubCLI()),
                patch("review_system.cli.capture_project_state", return_value=state),
            ):
                blocked = main(["analyze-pr", "https://github.com/demo/repo/pull/7", "--repository-root", str(root), "--output-dir", str(root / "blocked")])
                allowed = main([
                    "analyze-pr", "https://github.com/demo/repo/pull/7", "--repository-root", str(root),
                    "--output-dir", str(root / "allowed"), "--allow-dirty-worktree",
                ])
            self.assertEqual(2, blocked)
            self.assertEqual(0, allowed)

    def test_github_doctor_reports_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "doctor.json"
            with patch("review_system.cli.GitHubCLI", return_value=StubGitHubCLI()):
                self.assertEqual(0, main([
                    "github-doctor",
                    "--repository-root", str(root),
                    "--output", str(output),
                ]))
            self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["ready"])


if __name__ == "__main__":
    unittest.main()

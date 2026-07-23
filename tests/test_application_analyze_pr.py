import hashlib
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from review_system.application import (
    AnalyzePullRequestRequest,
    AnalyzePullRequestResult,
    analyze_pull_request,
)
from review_system.cli import main
from review_system.io import load_data
from review_system.project_init import initialize_project
from tests.test_github_connector import StubGitHubCLI


class AnalyzePullRequestApplicationTests(unittest.TestCase):
    def _project(self, root: Path) -> None:
        (root / "src").mkdir()
        (root / "app").mkdir()
        (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
        (root / "app" / "api.ts").write_text(
            "import { score } from '../src/core'\n",
            encoding="utf-8",
        )
        initialize_project(root, preset="generic-webapp")

    def test_direct_use_case_preserves_artifact_and_hash_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            output = root / "analysis"

            result = analyze_pull_request(
                AnalyzePullRequestRequest(
                    pull_request="https://github.com/demo/repo/pull/7",
                    repository_root=root,
                    output_dir=output,
                ),
                github_cli=StubGitHubCLI(),
            )

            self.assertEqual(("src/core.ts",), result.changed_files)
            self.assertEqual(output.resolve(), result.output_dir)
            self.assertEqual(output / "github-source.json", result.source_path)
            self.assertEqual(output / "impact.json", result.impact_path)
            self.assertEqual(output / "REPORT.md", result.report_path)
            self.assertEqual(output / "pull-request.diff", result.diff_path)
            self.assertTrue(result.source_path.is_file())
            self.assertTrue(result.impact_path.is_file())
            self.assertTrue(result.report_path.is_file())
            self.assertTrue(result.diff_path.is_file())

            source = load_data(result.source_path)
            impact = load_data(result.impact_path)
            self.assertEqual(source["source_sha256"], impact["source_evidence_sha256"])
            self.assertEqual(
                source["diff"]["sha256"],
                hashlib.sha256(result.diff_path.read_bytes()).hexdigest(),
            )
            self.assertIn(
                "app/api.ts",
                {item["path"] for item in impact["impact"]["dependent_files"]},
            )

    def test_direct_use_case_preserves_fail_closed_repository_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            output = root / "analysis"

            with self.assertRaisesRegex(ValueError, "does not match"):
                analyze_pull_request(
                    AnalyzePullRequestRequest(
                        pull_request="https://github.com/demo/repo/pull/7",
                        repository_root=root,
                        output_dir=output,
                    ),
                    github_cli=StubGitHubCLI(repository="other/repo"),
                )

            self.assertFalse(output.exists())

    def test_empty_output_directory_uses_default_pr_artifact_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)

            result = analyze_pull_request(
                AnalyzePullRequestRequest(
                    pull_request="https://github.com/demo/repo/pull/7",
                    repository_root=root,
                    output_dir="",
                ),
                github_cli=StubGitHubCLI(),
            )

            self.assertEqual((root / ".pie" / "pr-7").resolve(), result.output_dir)
            self.assertTrue(result.source_path.is_file())

    def test_cli_maps_arguments_and_delegates_to_use_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "analysis"
            source = {
                "repository": {"name_with_owner": "demo/repo"},
                "pull_request": {"number": 7},
            }
            impact = {
                "impact": {"dependent_files": []},
                "review": {"selected_packs": []},
            }
            result = AnalyzePullRequestResult(
                source=source,
                impact=impact,
                output_dir=output,
                source_path=output / "github-source.json",
                impact_path=output / "impact.json",
                report_path=output / "REPORT.md",
                diff_path=None,
                changed_files=("src/core.ts",),
            )
            github_cli = StubGitHubCLI()

            with (
                patch("review_system.cli.GitHubCLI", return_value=github_cli),
                patch("review_system.cli.analyze_pull_request", return_value=result) as use_case,
                redirect_stdout(io.StringIO()),
            ):
                code = main([
                    "analyze-pr",
                    "7",
                    "--repo", "demo/repo",
                    "--repository-root", str(root),
                    "--profile", "custom/project.yml",
                    "--config", "custom/config.yml",
                    "--graph", "custom/graph.json",
                    "--approved-rules", "custom/rules.yml",
                    "--refresh-graph",
                    "--skip-diff",
                    "--skip-discussion",
                    "--allow-repository-mismatch",
                    "--allow-head-mismatch",
                    "--allow-dirty-worktree",
                    "--max-depth", "5",
                    "--timeout", "45",
                    "--gh-executable", "gh-test",
                    "--output-dir", str(output),
                ])

            self.assertEqual(0, code)
            request = use_case.call_args.args[0]
            self.assertEqual("7", request.pull_request)
            self.assertEqual(str(root), request.repository_root)
            self.assertEqual("demo/repo", request.repository)
            self.assertEqual("custom/project.yml", request.profile)
            self.assertEqual("custom/config.yml", request.config)
            self.assertEqual("custom/graph.json", request.graph)
            self.assertEqual("custom/rules.yml", request.approved_rules)
            self.assertTrue(request.refresh_graph)
            self.assertTrue(request.skip_diff)
            self.assertTrue(request.skip_discussion)
            self.assertTrue(request.allow_repository_mismatch)
            self.assertTrue(request.allow_head_mismatch)
            self.assertTrue(request.allow_dirty_worktree)
            self.assertEqual(5, request.max_depth)
            self.assertEqual(str(output), request.output_dir)
            self.assertIs(github_cli, use_case.call_args.kwargs["github_cli"])
            self.assertTrue(callable(use_case.call_args.kwargs["capture_state"]))


if __name__ == "__main__":
    unittest.main()

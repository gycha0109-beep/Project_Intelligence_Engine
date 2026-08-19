import io
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from review_system.application import (
    AnalyzeChangeRequest,
    AnalyzeChangeResult,
    IndexProjectRequest,
    IndexProjectResult,
    analyze_project_change,
    index_project,
)
from review_system.cli import main
from review_system.io import load_data


class IndexAnalyzeApplicationTests(unittest.TestCase):
    def _project(self, root: Path) -> tuple[Path, Path, Path]:
        (root / ".review" / "intelligence").mkdir(parents=True)
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "src" / "core.py").write_text("def score():\n    return 1\n", encoding="utf-8")
        (root / "src" / "api.py").write_text("from src.core import score\n", encoding="utf-8")

        profile = root / ".review" / "project.yml"
        profile.write_text(
            '''schema_version: "1.0"
project:
  id: demo
  name: Demo
  repository_root: "."
  baseline_branch: main
technology:
  languages: [python]
scope:
  include: ["src/**", "tests/**"]
  exclude: []
review:
  packs: [universal.test-completeness]
gate:
  block_on: [P0, P1]
  require: {}
constraints: {}
''',
            encoding="utf-8",
        )
        config = root / ".review" / "intelligence" / "config.yml"
        config.write_text(
            '''schema_version: "1.0"
graph:
  max_file_size_bytes: 1000000
components:
  - id: core
    paths: ["src/**"]
''',
            encoding="utf-8",
        )
        rules = root / ".review" / "intelligence" / "approved-rules.yml"
        rules.write_text('schema_version: "1.0"\nrules: []\n', encoding="utf-8")
        return profile, config, rules

    def _graph(self, root: Path, profile: Path, config: Path) -> Path:
        graph = root / "graph.json"
        index_project(
            IndexProjectRequest(
                profile=profile,
                config=config,
                output=graph,
                repository_root=root,
            )
        )
        return graph

    def test_index_project_preserves_graph_and_artifact_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile, config, _ = self._project(root)
            output = root / "graph.json"

            result = index_project(
                IndexProjectRequest(
                    profile=profile,
                    config=config,
                    output=output,
                    repository_root=root,
                )
            )

            self.assertEqual(root.resolve(), result.repository_root)
            self.assertEqual(output, result.output_path)
            self.assertTrue(output.is_file())
            self.assertEqual(result.graph, load_data(output))
            self.assertEqual(2, result.graph["stats"]["files"])
            self.assertGreaterEqual(result.graph["stats"]["edges"], 1)

    def test_analyze_change_files_source_preserves_json_markdown_and_impact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile, config, rules = self._project(root)
            graph = self._graph(root, profile, config)
            changed = root / "changed.txt"
            changed.write_text("src/core.py\n\n", encoding="utf-8")
            output = root / "impact.json"
            markdown = root / "reports" / "impact.md"

            result = analyze_project_change(
                AnalyzeChangeRequest(
                    profile=profile,
                    graph=graph,
                    approved_rules=rules,
                    files=changed,
                    output=output,
                    markdown_output=markdown,
                    repository_root=root,
                    change_id="CHANGE-1",
                )
            )

            self.assertEqual(("src/core.py",), result.changed_files)
            self.assertEqual(output, result.output_path)
            self.assertEqual(markdown, result.markdown_path)
            self.assertTrue(output.is_file())
            self.assertTrue(markdown.is_file())
            self.assertEqual(result.analysis, load_data(output))
            impacted = {item["path"] for item in result.analysis["impact"]["dependent_files"]}
            self.assertIn("src/api.py", impacted)

    def test_analyze_change_base_source_uses_injected_git_diff_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile, config, _ = self._project(root)
            graph = self._graph(root, profile, config)
            calls = []

            def reader(repository_root: Path, base: str, head: str) -> list[str]:
                calls.append((repository_root, base, head))
                return ["src/core.py"]

            result = analyze_project_change(
                AnalyzeChangeRequest(
                    profile=profile,
                    graph=graph,
                    base="main",
                    head="feature",
                    output=root / "impact.json",
                    repository_root=root,
                ),
                git_diff_reader=reader,
            )

            self.assertEqual([(root.resolve(), "main", "feature")], calls)
            self.assertEqual("main", result.analysis["change"]["base_revision"])
            self.assertEqual("feature", result.analysis["change"]["head_revision"])

    def test_invalid_graph_fails_before_output_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile, _, _ = self._project(root)
            graph = root / "graph.json"
            graph.write_text("[]\n", encoding="utf-8")
            changed = root / "changed.txt"
            changed.write_text("src/core.py\n", encoding="utf-8")
            output = root / "impact.json"

            with self.assertRaisesRegex(ValueError, "graph must be an object"):
                analyze_project_change(
                    AnalyzeChangeRequest(
                        profile=profile,
                        graph=graph,
                        files=changed,
                        output=output,
                        repository_root=root,
                    )
                )

            self.assertFalse(output.exists())

    def test_missing_approved_rules_fails_before_output_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile, config, _ = self._project(root)
            graph = self._graph(root, profile, config)
            changed = root / "changed.txt"
            changed.write_text("src/core.py\n", encoding="utf-8")
            output = root / "impact.json"

            with self.assertRaisesRegex(ValueError, "approved rules file does not exist"):
                analyze_project_change(
                    AnalyzeChangeRequest(
                        profile=profile,
                        graph=graph,
                        approved_rules=root / "missing.yml",
                        files=changed,
                        output=output,
                        repository_root=root,
                    )
                )

            self.assertFalse(output.exists())

    def test_changed_file_source_requires_exactly_one_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile, config, _ = self._project(root)
            graph = self._graph(root, profile, config)
            changed = root / "changed.txt"
            changed.write_text("src/core.py\n", encoding="utf-8")

            for request in (
                AnalyzeChangeRequest(profile=profile, graph=graph, output=root / "none.json", repository_root=root),
                AnalyzeChangeRequest(
                    profile=profile,
                    graph=graph,
                    files=changed,
                    base="main",
                    output=root / "both.json",
                    repository_root=root,
                ),
            ):
                with self.subTest(request=request), self.assertRaisesRegex(ValueError, "exactly one"):
                    analyze_project_change(request)

    def test_request_contracts_are_frozen(self):
        index_request = IndexProjectRequest(profile="profile.yml", config="config.yml", output="graph.json")
        analyze_request = AnalyzeChangeRequest(profile="profile.yml", graph="graph.json", files="changed.txt", output="impact.json")

        with self.assertRaises(FrozenInstanceError):
            index_request.output = "other.json"
        with self.assertRaises(FrozenInstanceError):
            analyze_request.max_depth = 5

    def test_index_project_cli_maps_arguments_and_delegates(self):
        graph = {"stats": {"files": 2, "edges": 1}, "warnings": []}
        result = IndexProjectResult(graph=graph, repository_root=Path("repo"), output_path=Path("graph.json"))

        with patch("review_system.cli.index_project", return_value=result) as use_case, redirect_stdout(io.StringIO()):
            code = main([
                "index-project",
                "project.yml",
                "--config", "config.yml",
                "--output", "graph.json",
                "--repository-root", "repo",
            ])

        self.assertEqual(0, code)
        request = use_case.call_args.args[0]
        self.assertEqual("project.yml", request.profile)
        self.assertEqual("config.yml", request.config)
        self.assertEqual("graph.json", request.output)
        self.assertEqual("repo", request.repository_root)

    def test_analyze_change_cli_maps_arguments_and_dependency(self):
        analysis = {
            "change": {"changed_files": ["src/core.py"]},
            "impact": {"dependent_files": []},
            "review": {"selected_packs": []},
        }
        result = AnalyzeChangeResult(
            analysis=analysis,
            changed_files=("src/core.py",),
            repository_root=Path("repo"),
            output_path=Path("impact.json"),
            markdown_path=Path("impact.md"),
        )

        with patch("review_system.cli.analyze_project_change", return_value=result) as use_case, redirect_stdout(io.StringIO()):
            code = main([
                "analyze-change",
                "project.yml",
                "--graph", "graph.json",
                "--approved-rules", "rules.yml",
                "--base", "main",
                "--head", "feature",
                "--change-id", "CHANGE-1",
                "--max-depth", "5",
                "--repository-root", "repo",
                "--output", "impact.json",
                "--markdown-output", "impact.md",
            ])

        self.assertEqual(0, code)
        request = use_case.call_args.args[0]
        self.assertEqual("project.yml", request.profile)
        self.assertEqual("graph.json", request.graph)
        self.assertEqual("rules.yml", request.approved_rules)
        self.assertIsNone(request.files)
        self.assertEqual("main", request.base)
        self.assertEqual("feature", request.head)
        self.assertEqual("CHANGE-1", request.change_id)
        self.assertEqual(5, request.max_depth)
        self.assertEqual("repo", request.repository_root)
        self.assertEqual("impact.json", request.output)
        self.assertEqual("impact.md", request.markdown_output)
        self.assertTrue(callable(use_case.call_args.kwargs["git_diff_reader"]))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.prospective_automation import RunGitHubPRRequest, run_github_pr


HEAD = "a" * 40
PIE = "b" * 40


class _CLI:
    pass


class Auto2CleanMaterializationTests(unittest.TestCase):
    def test_analysis_graph_is_routed_into_execution_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "project"
            (root / ".review" / "intelligence").mkdir(parents=True)
            (root / ".review" / "project.yml").write_text("project: demo\n", encoding="utf-8")
            (root / ".review" / "intelligence" / "config.yml").write_text(
                "components: []\n",
                encoding="utf-8",
            )
            output_root = base / "external-output"
            captured = {}

            def capture_and_stop(request, *, github_cli):
                captured["request"] = request
                raise RuntimeError("stop-after-capture")

            with patch(
                "review_system.prospective_automation.analyze_pull_request",
                side_effect=capture_and_stop,
            ):
                with self.assertRaisesRegex(RuntimeError, "stop-after-capture"):
                    run_github_pr(
                        RunGitHubPRRequest(
                            pull_request="7",
                            event_head_sha=HEAD,
                            pie_revision=PIE,
                            repository_root=root,
                            repository="demo/repo",
                            output_root=output_root,
                        ),
                        github_cli=_CLI(),
                    )

            analysis_dir = (output_root / "analysis" / f"pr-7-{HEAD[:12]}").resolve()
            analyze_request = captured["request"]
            self.assertEqual(analysis_dir, Path(analyze_request.output_dir).resolve())
            self.assertEqual(analysis_dir / "graph.json", Path(analyze_request.graph).resolve())
            self.assertFalse((root / ".review" / "intelligence" / "graph.json").exists())


if __name__ == "__main__":
    unittest.main()

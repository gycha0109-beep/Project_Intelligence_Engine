import tempfile
import unittest
from pathlib import Path

from review_system.intelligence_config import load_intelligence_config
from review_system.intelligence_graph import build_project_graph
from review_system.intelligence_impact import analyze_change
from review_system.profile import resolve_profile_file


PHASE49_CHANGED_FILES = [
    "apps/web/app/api/projects/[projectId]/integrations/notion/resource/route.ts",
    "apps/web/app/projects/[projectId]/evidence/page.tsx",
    "apps/web/app/projects/[projectId]/notion-capture-actions.ts",
    "apps/web/components/buildmap/notion-resource-preview.tsx",
    "apps/web/lib/notion/provenance.ts",
    "apps/web/lib/notion/read.ts",
    "docs/access-policy-tests/phase49-notion-observation-explicit-capture-provenance.md",
    "docs/decisions/phase49-notion-observation-explicit-capture-provenance.md",
    "supabase/migrations/20260819060000_buildmap_20_capture_observation_keys.sql",
]


class BuildMapPresetRegressionTests(unittest.TestCase):
    def _assets(self):
        root = Path(__file__).resolve().parents[1]
        profile = resolve_profile_file(root / "profiles/examples/buildmap.yml")
        config = load_intelligence_config(root / "intelligence/examples/buildmap-config.yml")
        return profile, config

    def _write(self, root: Path, path: str, text: str = "export const value = 1;\n") -> None:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def _graph(self, root: Path):
        profile, config = self._assets()
        graph_config = config.get("graph", {})
        graph = build_project_graph(
            root,
            include=profile.get("scope", {}).get("include", ["**/*"]),
            exclude=profile.get("scope", {}).get("exclude", []),
            components=config.get("components", []),
            max_file_size_bytes=int(graph_config.get("max_file_size_bytes", 1_000_000)),
        )
        return profile, graph

    def test_phase49_retrospective_change_set_is_fully_graph_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in PHASE49_CHANGED_FILES:
                text = "# retrospective fixture\n" if path.endswith(".md") else "create table if not exists fixture(id bigint);\n" if path.endswith(".sql") else "export const value = 1;\n"
                self._write(root, path, text)

            profile, graph = self._graph(root)
            analysis = analyze_change(
                graph,
                PHASE49_CHANGED_FILES,
                configured_packs=profile.get("review", {}).get("packs", []),
            )

            self.assertEqual([], analysis["direct"]["files_missing_from_graph"])
            self.assertEqual(sorted(PHASE49_CHANGED_FILES), analysis["direct"]["files_in_graph"])

    def test_apps_web_generated_and_dependency_paths_remain_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "apps/web/app/projects/demo/page.tsx")
            excluded = [
                "apps/web/node_modules/pkg/index.ts",
                "apps/web/.next/server/generated.ts",
                "apps/web/dist/bundle.js",
                "apps/web/coverage/report.json",
                "apps/web/output/generated.ts",
            ]
            for path in excluded:
                self._write(root, path)

            _, graph = self._graph(root)
            graph_paths = {
                node["path"]
                for node in graph["nodes"]
                if node.get("type") == "file" and isinstance(node.get("path"), str)
            }

            self.assertIn("apps/web/app/projects/demo/page.tsx", graph_paths)
            for path in excluded:
                self.assertNotIn(path, graph_paths)

    def test_current_decision_and_feedback_routes_map_to_existing_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decision = "apps/web/app/projects/demo/decision-actions.ts"
            feedback = "apps/web/app/projects/demo/feedback/page.tsx"
            review = "apps/web/app/projects/demo/workspace/review/page.tsx"
            for path in (decision, feedback, review):
                self._write(root, path)

            profile, graph = self._graph(root)
            decision_analysis = analyze_change(
                graph,
                [decision],
                configured_packs=profile.get("review", {}).get("packs", []),
            )
            feedback_analysis = analyze_change(
                graph,
                [feedback],
                configured_packs=profile.get("review", {}).get("packs", []),
            )
            review_analysis = analyze_change(
                graph,
                [review],
                configured_packs=profile.get("review", {}).get("packs", []),
            )

            self.assertIn("decision-timeline", decision_analysis["direct"]["components"])
            self.assertIn("public-feedback", feedback_analysis["direct"]["components"])
            self.assertIn("change-card", review_analysis["direct"]["components"])


if __name__ == "__main__":
    unittest.main()

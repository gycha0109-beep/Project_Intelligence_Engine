import os
import tempfile
import unittest
from pathlib import Path

from review_system.intelligence_graph import build_project_graph, validate_project_graph


class IntelligenceGraphTests(unittest.TestCase):
    def test_builds_cross_language_graph_and_component_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src" / "core.py").write_text("def score():\n    return 1\n", encoding="utf-8")
            (root / "src" / "api.py").write_text("from src.core import score\n", encoding="utf-8")
            (root / "src" / "view.ts").write_text("import {x} from './util';\nexport function render() {}\n", encoding="utf-8")
            (root / "src" / "util.ts").write_text("export const x = 1;\n", encoding="utf-8")
            (root / "tests" / "test_core.py").write_text("from src.core import score\n", encoding="utf-8")
            graph = build_project_graph(
                root,
                include=["src/**", "tests/**"],
                components=[{"id": "recommendation", "paths": ["src/**"]}],
            )
            edge_keys = {(e["source"], e["target"], e["type"]) for e in graph["edges"]}
            self.assertIn(("file:src/api.py", "file:src/core.py", "imports"), edge_keys)
            self.assertIn(("file:src/view.ts", "file:src/util.ts", "imports"), edge_keys)
            self.assertIn(("component:recommendation", "file:src/core.py", "contains"), edge_keys)
            self.assertIn(("file:tests/test_core.py", "file:src/core.py", "likely_verifies"), edge_keys)
            self.assertGreaterEqual(graph["stats"]["symbols"], 3)

    @unittest.skipIf(not hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_file_is_not_indexed(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            external = Path(outside) / "secret.py"
            external.write_text("SECRET = 1\n", encoding="utf-8")
            link = root / "linked.py"
            try:
                link.symlink_to(external)
            except OSError:
                self.skipTest("symlink creation unavailable")
            graph = build_project_graph(root)
            paths = {node.get("path") for node in graph["nodes"] if node.get("type") == "file"}
            self.assertNotIn("linked.py", paths)

    @unittest.skipIf(not hasattr(os, "symlink"), "symlink unavailable")
    def test_internal_symlink_alias_is_not_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "real").mkdir()
            (root / "real" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            link = root / "alias"
            try:
                link.symlink_to(root / "real", target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation unavailable")
            graph = build_project_graph(root)
            paths = {node.get("path") for node in graph["nodes"] if node.get("type") == "file"}
            self.assertIn("real/module.py", paths)
            self.assertNotIn("alias/module.py", paths)

    def test_unsafe_scope_pattern_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                build_project_graph(tmp, include=["../**"])

    def test_graph_hash_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
            graph = build_project_graph(root)
            self.assertEqual([], validate_project_graph(graph))
            graph["nodes"][0]["path"] = "changed.py"
            self.assertIn("graph_sha256 does not match graph contents", validate_project_graph(graph))

    def test_invalid_max_file_size_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                build_project_graph(tmp, max_file_size_bytes=1)

    def test_markdown_parent_link_is_resolved_or_ignored_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "data").mkdir(parents=True)
            (root / "docs" / "proposals").mkdir(parents=True)
            (root / "docs" / "data" / "index.md").write_text(
                "[existing](../proposals/plan.md) [missing](../proposals/missing.md)\n",
                encoding="utf-8",
            )
            (root / "docs" / "proposals" / "plan.md").write_text("# Plan\n", encoding="utf-8")
            graph = build_project_graph(root, include=["docs/**"])
            edges = {(item["source"], item["target"], item["type"]) for item in graph["edges"]}
            self.assertIn(
                ("file:docs/data/index.md", "file:docs/proposals/plan.md", "documents"),
                edges,
            )


if __name__ == "__main__":
    unittest.main()

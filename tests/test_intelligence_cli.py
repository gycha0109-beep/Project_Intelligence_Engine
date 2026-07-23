import tempfile
import unittest
from pathlib import Path

from review_system.cli import main
from review_system.io import load_data


class IntelligenceCliTests(unittest.TestCase):
    def test_index_and_analyze_change_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".review" / "intelligence").mkdir(parents=True)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src" / "core.py").write_text("def score():\n    return 1\n", encoding="utf-8")
            (root / "src" / "api.py").write_text("from src.core import score\n", encoding="utf-8")
            profile = root / ".review" / "project.yml"
            profile.write_text('''schema_version: "1.0"\nproject:\n  id: demo\n  name: Demo\n  repository_root: "."\n  baseline_branch: main\ntechnology:\n  languages: [python]\nscope:\n  include: ["src/**", "tests/**"]\n  exclude: []\nreview:\n  packs: [universal.test-completeness]\ngate:\n  block_on: [P0, P1]\n  require: {}\nconstraints: {}\n''', encoding="utf-8")
            config = root / ".review" / "intelligence" / "config.yml"
            config.write_text('''schema_version: "1.0"\ngraph:\n  max_file_size_bytes: 1000000\ncomponents:\n  - id: core\n    paths: ["src/**"]\n''', encoding="utf-8")
            rules = root / ".review" / "intelligence" / "approved-rules.yml"
            rules.write_text('schema_version: "1.0"\nrules: []\n', encoding="utf-8")
            changed = root / "changed.txt"
            changed.write_text("src/core.py\n", encoding="utf-8")
            graph = root / "graph.json"
            impact = root / "impact.json"
            self.assertEqual(0, main(["index-project", str(profile), "--config", str(config), "--output", str(graph)]))
            self.assertEqual(0, main(["analyze-change", str(profile), "--graph", str(graph), "--approved-rules", str(rules), "--files", str(changed), "--output", str(impact)]))
            data = load_data(impact)
            impacted = {item["path"] for item in data["impact"]["dependent_files"]}
            self.assertIn("src/api.py", impacted)


if __name__ == "__main__":
    unittest.main()

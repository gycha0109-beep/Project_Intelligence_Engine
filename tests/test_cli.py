import tempfile
import unittest
from pathlib import Path

from review_system.cli import main
from review_system.io import dump_json, load_data
from tests.helpers import finding


class CliTests(unittest.TestCase):
    def test_merge_findings_writes_array_and_separate_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.json"
            b = root / "b.json"
            output = root / "merged.json"
            conflicts = root / "conflicts.json"
            dump_json(a, [finding()])
            dump_json(b, [finding(severity="P3")])
            code = main(["merge-findings", str(a), str(b), "--output", str(output), "--conflicts-output", str(conflicts)])
            self.assertEqual(0, code)
            self.assertIsInstance(load_data(output), list)
            self.assertEqual(1, len(load_data(conflicts)))

if __name__ == "__main__":
    unittest.main()

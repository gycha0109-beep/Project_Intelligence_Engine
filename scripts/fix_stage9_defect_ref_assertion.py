from pathlib import Path


path = Path(__file__).resolve().parents[1] / "tests/test_buildmap_export.py"
text = path.read_text(encoding="utf-8")
old = '''            self.assertEqual(
                [False, True],
                [item["artifact_redacted"] for item in defect["artifact_refs"]],
            )
'''
new = '''            refs_by_relation = {
                item["relation"]: item
                for item in defect["artifact_refs"]
            }
            self.assertFalse(refs_by_relation["diagnostic"]["artifact_redacted"])
            self.assertTrue(refs_by_relation["reproducer"]["artifact_redacted"])
'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise RuntimeError("Defect Artifact assertion anchor not found")
path.write_text(text, encoding="utf-8")

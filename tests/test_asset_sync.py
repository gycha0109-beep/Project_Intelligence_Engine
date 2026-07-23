import hashlib
import unittest
from pathlib import Path


class AssetSyncTests(unittest.TestCase):
    def _digest(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_packaged_assets_match_source_assets(self):
        root = Path(__file__).resolve().parents[1]
        pairs = [
            (root / "core", root / "src/review_system/assets/core"),
            (root / "packs", root / "src/review_system/assets/packs"),
            (root / "templates", root / "src/review_system/assets/templates"),
            (root / "schemas", root / "src/review_system/assets/schemas"),
            (root / "intelligence", root / "src/review_system/assets/intelligence"),
            (root / "profiles/stacks", root / "src/review_system/assets/profiles/stacks"),
            (root / "profiles/examples", root / "src/review_system/assets/profiles/examples"),
            (root / "bootstrap/.review/intelligence", root / "src/review_system/assets/bootstrap/intelligence"),
        ]
        for source, packaged in pairs:
            source_files = {p.relative_to(source): self._digest(p) for p in source.rglob("*") if p.is_file()}
            packaged_files = {p.relative_to(packaged): self._digest(p) for p in packaged.rglob("*") if p.is_file()}
            self.assertEqual(source_files, packaged_files)
        self.assertEqual(
            (root / "VERSION").read_text(encoding="utf-8"),
            (root / "src/review_system/assets/VERSION").read_text(encoding="utf-8"),
        )

if __name__ == "__main__":
    unittest.main()

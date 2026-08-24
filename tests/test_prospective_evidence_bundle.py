from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.prospective_evidence_bundle import verify_evidence_bundle, write_evidence_bundle


class ProspectiveEvidenceBundleTests(unittest.TestCase):
    def test_manifest_hashes_bundle_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.json"
            source.write_text('{"value": 1}\n', encoding="utf-8")
            bundle = root / "bundle"
            identity = {
                "execution_id": "pie-pr-auto-" + "a" * 32,
                "execution_key_sha256": "b" * 64,
            }
            summary = {
                "repository": "demo/repo",
                "pull_request": 7,
                "source_revision": "c" * 40,
                "pie_revision": "d" * 40,
                "assessment_id": None,
                "packet_id": None,
            }
            manifest = write_evidence_bundle(
                bundle,
                summary=summary,
                identity=identity,
                evidence_files={"source/github-source.json": source},
            )
            self.assertEqual([], verify_evidence_bundle(bundle))
            self.assertEqual("PIE_PROSPECTIVE_EVIDENCE_BUNDLE_V1", manifest["schema_version"])
            self.assertTrue((bundle / "manifest.json").is_file())

            target = bundle / "source" / "github-source.json"
            target.write_text('{"value": 2}\n', encoding="utf-8")
            self.assertIn("artifact sha256 mismatch: source/github-source.json", verify_evidence_bundle(bundle))

    def test_summary_and_identity_are_hashed_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.txt"
            source.write_text("evidence\n", encoding="utf-8")
            bundle = root / "bundle"
            manifest = write_evidence_bundle(
                bundle,
                summary={
                    "repository": "demo/repo",
                    "pull_request": 7,
                    "source_revision": "c" * 40,
                    "pie_revision": "d" * 40,
                },
                identity={
                    "execution_id": "pie-pr-auto-" + "a" * 32,
                    "execution_key_sha256": "b" * 64,
                },
                evidence_files={"analysis/report.txt": source},
            )
            paths = {item["path"] for item in manifest["artifacts"]}
            self.assertIn("summary.json", paths)
            self.assertIn("source/execution-identity.json", paths)
            self.assertIn("analysis/report.txt", paths)
            parsed = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_sha256"], parsed["manifest_sha256"])


if __name__ == "__main__":
    unittest.main()

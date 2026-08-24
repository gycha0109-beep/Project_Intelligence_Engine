from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from review_system.prospective_evidence_bundle import verify_evidence_bundle, write_evidence_bundle
from review_system.prospective_replay import build_deterministic_result


class ProspectiveEvidenceBundleTests(unittest.TestCase):
    def _deterministic_result(self) -> dict:
        return build_deterministic_result(
            identity={
                "execution_id": "pie-pr-auto-" + "a" * 32,
                "execution_key_sha256": "b" * 64,
            },
            summary={
                "repository": "demo/repo",
                "pull_request": 7,
                "source_revision": "c" * 40,
                "pie_revision": "d" * 40,
                "status": "WAITING_FOR_TRUST_INPUT",
                "next_step": "PROVIDE_EXPLICIT_TRUST_REQUEST",
                "candidate_id": "candidate-1",
                "assessment_id": None,
                "packet_id": None,
                "risk_band": None,
                "readiness": None,
                "auto_capture": True,
                "auto_analysis": True,
                "auto_trust_assessment": False,
                "auto_packet_prepare": False,
                "human_review_recorded": False,
                "outcome_recorded": False,
                "automation_authorized": False,
                "pilot_authorized": False,
            },
            base_revision="e" * 40,
            changed_files=["src/core.py"],
            diff_sha256="f" * 64,
            impact={"change_id": "PR-7", "source_evidence_sha256": "1" * 64},
            candidate={
                "candidate_id": "candidate-1",
                "generated_at": "2026-08-24T00:00:00Z",
                "source_evidence_sha256": "1" * 64,
                "evidence_snapshot_sha256": "2" * 64,
                "report_sha256": "3" * 64,
                "status": "BLOCKED_OPERATOR_INPUT_REQUIRED",
            },
            workflow_semantics=None,
        )

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

    def test_summary_identity_and_deterministic_result_are_hashed_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.txt"
            source.write_text("evidence\n", encoding="utf-8")
            bundle = root / "bundle"
            deterministic = self._deterministic_result()
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
                deterministic_result=deterministic,
            )
            paths = {item["path"] for item in manifest["artifacts"]}
            self.assertIn("summary.json", paths)
            self.assertIn("source/execution-identity.json", paths)
            self.assertIn("analysis/report.txt", paths)
            self.assertIn("deterministic-result.json", paths)
            self.assertEqual(
                deterministic["deterministic_result_sha256"],
                manifest["deterministic_result_sha256"],
            )
            parsed = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_sha256"], parsed["manifest_sha256"])
            self.assertEqual([], verify_evidence_bundle(bundle))

    def test_raw_observation_can_change_without_changing_deterministic_result_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_source = root / "first.json"
            second_source = root / "second.json"
            first_source.write_text('{"retrieved_at":"first"}\n', encoding="utf-8")
            second_source.write_text('{"retrieved_at":"second"}\n', encoding="utf-8")
            deterministic = self._deterministic_result()
            identity = {
                "execution_id": "pie-pr-auto-" + "a" * 32,
                "execution_key_sha256": "b" * 64,
            }
            summary = {
                "repository": "demo/repo",
                "pull_request": 7,
                "source_revision": "c" * 40,
                "pie_revision": "d" * 40,
            }
            first = write_evidence_bundle(
                root / "bundle-1",
                summary=summary,
                identity=identity,
                evidence_files={"source/github-source.json": first_source},
                deterministic_result=deterministic,
            )
            second = write_evidence_bundle(
                root / "bundle-2",
                summary=summary,
                identity=identity,
                evidence_files={"source/github-source.json": second_source},
                deterministic_result=deterministic,
            )
            self.assertNotEqual(first["manifest_sha256"], second["manifest_sha256"])
            self.assertEqual(first["deterministic_result_sha256"], second["deterministic_result_sha256"])

    def test_deterministic_result_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.txt"
            source.write_text("evidence\n", encoding="utf-8")
            deterministic = self._deterministic_result()
            bundle = root / "bundle"
            write_evidence_bundle(
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
                deterministic_result=deterministic,
            )
            target = bundle / "deterministic-result.json"
            forged = deepcopy(deterministic)
            forged["source"]["changed_files"] = ["src/other.py"]
            target.write_text(json.dumps(forged, indent=2) + "\n", encoding="utf-8")
            errors = verify_evidence_bundle(bundle)
            self.assertIn("artifact sha256 mismatch: deterministic-result.json", errors)
            self.assertIn("deterministic_result_sha256 mismatch", errors)


if __name__ == "__main__":
    unittest.main()

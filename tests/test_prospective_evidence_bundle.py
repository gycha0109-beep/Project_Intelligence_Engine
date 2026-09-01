from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from review_system.operational_policy import normalize_operational_policy_data
from review_system.prospective_evidence_bundle import verify_evidence_bundle, write_evidence_bundle
from review_system.prospective_replay import build_deterministic_result


def _readiness() -> dict:
    return {
        "policy_id": "demo-operational",
        "policy_version": "1.0.0",
        "min_ledger_runs": 1,
        "min_ledger_decisions": 1,
        "min_defects": 1,
        "min_closed_defects": 0,
        "min_reground_observations": 1,
        "min_reground_coverage": 1.0,
        "min_reground_precision": 1.0,
        "min_reground_recall": 1.0,
        "max_reground_false_positive_rate": 0.0,
        "require_active_policy": True,
        "require_pass_evaluation": True,
        "require_holdout": True,
        "require_repeatability": True,
        "require_zero_protected_negative_regressions": True,
    }


def _operational_class(paths: list[str]) -> dict:
    return {
        "paths": paths,
        "trust_task_class": "routine_code",
        "required_scenarios": ["process-restart"],
        "required_evidence": ["ci"],
        "readiness_policy": _readiness(),
    }


def _raw_operational_policy() -> dict:
    return {
        "schema_version": "1.0",
        "contract_version": "PIE_OPERATIONAL_POLICY_V1",
        "project_id": "demo",
        "policy_authority": "PR_BASE_REVISION",
        "operational_classes": {
            "application-runtime": _operational_class(["app/**"]),
            "pipeline-runtime": _operational_class(["scripts/**"]),
        },
    }


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

    def test_operational_policy_match_explanation_sidecar_is_generated_and_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_policy = _raw_operational_policy()
            normalized_policy = normalize_operational_policy_data(raw_policy)
            policy_path = root / "policy.yml"
            policy_path.write_text(yaml.safe_dump(raw_policy, sort_keys=False), encoding="utf-8")

            changed_files = ["scripts/verify.sh", "app/page.tsx"]
            candidate_path = root / "candidate.json"
            candidate_path.write_text(
                json.dumps({"changed_files": changed_files}, indent=2) + "\n",
                encoding="utf-8",
            )
            binding_path = root / "binding.json"
            binding_path.write_text(
                json.dumps(
                    {
                        "policy": {"policy_sha256": normalized_policy["policy_sha256"]},
                        "changed_files": changed_files,
                        "matched_operational_classes": ["application-runtime", "pipeline-runtime"],
                        "match_status": "AMBIGUOUS_POLICY_MATCH",
                    },
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

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
                evidence_files={
                    "prospective/candidate.json": candidate_path,
                    "operational/base-policy.yml": policy_path,
                    "operational/binding.json": binding_path,
                },
            )

            sidecar_path = bundle / "operational" / "policy-match-explanation.json"
            self.assertTrue(sidecar_path.is_file())
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            self.assertEqual("PIE_OPERATIONAL_POLICY_MATCH_EXPLANATION_V1", sidecar["contract_version"])
            self.assertEqual("MULTI_PATH_MULTI_CLASS", sidecar["ambiguity_mechanism"])
            self.assertEqual(
                ["application-runtime", "pipeline-runtime"],
                sidecar["matched_operational_classes"],
            )
            self.assertEqual(normalized_policy["policy_sha256"], sidecar["policy"]["policy_sha256"])
            for value in sidecar["authority"].values():
                self.assertFalse(value)
            artifact_paths = {item["path"] for item in manifest["artifacts"]}
            self.assertIn("operational/policy-match-explanation.json", artifact_paths)
            self.assertEqual([], verify_evidence_bundle(bundle))

    def test_operational_policy_match_explanation_disagreement_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_policy = _raw_operational_policy()
            normalized_policy = normalize_operational_policy_data(raw_policy)
            policy_path = root / "policy.yml"
            policy_path.write_text(yaml.safe_dump(raw_policy, sort_keys=False), encoding="utf-8")
            changed_files = ["scripts/verify.sh", "app/page.tsx"]
            candidate_path = root / "candidate.json"
            candidate_path.write_text(json.dumps({"changed_files": changed_files}), encoding="utf-8")
            binding_path = root / "binding.json"
            binding_path.write_text(
                json.dumps(
                    {
                        "policy": {"policy_sha256": normalized_policy["policy_sha256"]},
                        "changed_files": changed_files,
                        "matched_operational_classes": ["application-runtime"],
                        "match_status": "UNIQUE_POLICY_MATCH",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "classes disagree with binding"):
                write_evidence_bundle(
                    root / "bundle",
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
                    evidence_files={
                        "prospective/candidate.json": candidate_path,
                        "operational/base-policy.yml": policy_path,
                        "operational/binding.json": binding_path,
                    },
                )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import unittest

from review_system.trust import BAND_ORDER, _profile_descriptor, _risk_projection
from review_system.trust_r4_semantics_shadow import (
    CONTRACT_VERSION,
    analyze_r4_semantics,
    project_r4_semantic_candidate,
)
from test_trust_authoritative_risk_promotion import holdout_semantics, wrapped_semantics


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
R4_FIXTURE = FIXTURE_DIR / "r4-semantic-underdetection-seen-v1.json"
SEEN = FIXTURE_DIR / "wave1-seen-baseline.json"
SEEN_WORKFLOW = FIXTURE_DIR / "workflow-semantic-bridge-d1-seen-v1.json"
HOLDOUT = FIXTURE_DIR / "wave1-holdout-shadow-predictions.json"
HOLDOUT_LABELS = FIXTURE_DIR / "wave1-holdout-adjudication.json"

PROFILE_PATHS = {
    "buildmap": ROOT / "profiles" / "examples" / "buildmap.yml",
    "bejewely": ROOT / "profiles" / "examples" / "bejewely.yml",
    "generic-webapp": ROOT / "profiles" / "examples" / "generic-webapp.yml",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TrustR4SemanticUnderdetectionShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_json(R4_FIXTURE)
        cls.seen = load_json(SEEN)
        cls.seen_workflow = load_json(SEEN_WORKFLOW)
        cls.holdout = load_json(HOLDOUT)
        cls.holdout_labels = load_json(HOLDOUT_LABELS)
        cls.profiles = {
            key: _profile_descriptor(path)[1]
            for key, path in PROFILE_PATHS.items()
        }
        cls.seen_workflow_by_id = {
            item["sample_id"]: item for item in cls.seen_workflow["cases"]
        }
        cls.holdout_labels_by_id = {
            item["sample_id"]: item for item in cls.holdout_labels["samples"]
        }

    def test_fixture_declares_seen_only_authority_ceiling(self) -> None:
        self.assertEqual(self.fixture["defect_id"], "R4_SEMANTIC_UNDERDETECTION")
        self.assertEqual(self.fixture["contract_version"], CONTRACT_VERSION)
        self.assertEqual(
            self.fixture["authority"]["pie_main_sha"],
            "e5cb12b902baa1579253714922d099a74705fae2",
        )
        self.assertTrue(self.fixture["scope"]["seen_real_world_cases"])
        self.assertFalse(self.fixture["scope"]["blind_generalization_claim"])
        self.assertFalse(self.fixture["scope"]["authoritative_runtime_change"])
        self.assertFalse(self.fixture["authority"]["blind_r4_holdout_available"])

    def test_seen_semantic_discriminator_replays_exactly(self) -> None:
        for case in self.fixture["cases"]:
            with self.subTest(sample_id=case["sample_id"]):
                result = analyze_r4_semantics(case["path"], case["excerpt"])
                self.assertEqual(result["contract_version"], CONTRACT_VERSION)
                self.assertEqual(
                    result["classification"],
                    case["expected_classification"],
                )
                self.assertEqual(
                    result["is_r4_authority"],
                    case["human_band"] == "R4",
                )

    def test_real_seen_r4_cases_raise_shadow_path_floor_to_r4(self) -> None:
        profile = self.profiles["generic-webapp"]
        positives = [case for case in self.fixture["cases"] if case["human_band"] == "R4"]
        self.assertEqual({case["sample_id"] for case in positives}, {"KB-262", "KB-272", "KB-277", "KB-279", "AR-30"})
        for case in positives:
            with self.subTest(sample_id=case["sample_id"]):
                request = {"task_class": "routine_code", "changed_files": [case["path"]]}
                result = project_r4_semantic_candidate(
                    request,
                    profile,
                    {case["path"]: case["excerpt"]},
                )
                self.assertEqual(result["authority"], "SHADOW_ONLY")
                self.assertFalse(result["automation_authorized"])
                self.assertFalse(result["pilot_authorized"])
                self.assertLess(
                    BAND_ORDER[result["current_risk"]["effective_band"]],
                    BAND_ORDER["R4"],
                )
                self.assertEqual(result["candidate_risk"]["effective_band"], "R4")
                self.assertEqual(result["r4_semantic_paths"], [case["path"]])
                self.assertTrue(result["band_changed"])

    def test_supporting_harnesses_do_not_gain_r4_authority(self) -> None:
        profile = self.profiles["generic-webapp"]
        by_id = {case["sample_id"]: case for case in self.fixture["cases"]}
        for sample_id in ("RW-54", "KB-275", "NEG-DOMAIN-POLICY"):
            case = by_id[sample_id]
            with self.subTest(sample_id=sample_id):
                request = {"task_class": "routine_code", "changed_files": [case["path"]]}
                result = project_r4_semantic_candidate(
                    request,
                    profile,
                    {case["path"]: case["excerpt"]},
                )
                self.assertFalse(result["r4_semantic_paths"])
                self.assertEqual(result["candidate_risk"], result["current_risk"])

    def test_documentation_verification_text_is_not_semantic_r4_evidence(self) -> None:
        case = next(
            item for item in self.fixture["cases"]
            if item["sample_id"] == "NEG-DOC-VERIFICATION"
        )
        result = analyze_r4_semantics(case["path"], case["excerpt"])
        self.assertEqual(result["classification"], "UNKNOWN")
        self.assertFalse(result["is_r4_authority"])

    def test_wave1_v12_authoritative_regression_remains_34_of_34(self) -> None:
        seen_evidence: dict[str, dict] = {}
        for sample_id, case in self.seen_workflow_by_id.items():
            seen_evidence[sample_id] = wrapped_semantics(
                source_revision=case["source_revision"],
                changed_files=case["changed_files"],
                diff_text=case["diff_text"],
                source_evidence_sha256=case["source_evidence_sha256"],
            )

        observed = acceptable = 0
        under: list[str] = []
        for item in self.seen["samples"]:
            request = {"task_class": item["task_class"], "changed_files": item["changed_files"]}
            evidence = seen_evidence.get(item["sample_id"])
            if evidence is not None:
                request["source_revision"] = self.seen_workflow_by_id[item["sample_id"]]["source_revision"]
            band = _risk_projection(
                request,
                self.profiles[item["profile_basis"]],
                evidence,
            )["effective_band"]
            observed += 1
            acceptable += int(band in item["acceptable_bands"])
            if BAND_ORDER[band] < BAND_ORDER[item["expected_band"]]:
                under.append(item["sample_id"])

        for item in self.holdout["predictions"]:
            expected = self.holdout_labels_by_id[item["sample_id"]]
            request = {
                "source_revision": item["frozen_head_sha"],
                "task_class": item["task_class"],
                "changed_files": item["changed_files"],
            }
            band = _risk_projection(
                request,
                self.profiles[item["profile_basis"]],
                holdout_semantics(item),
            )["effective_band"]
            observed += 1
            acceptable += int(band in expected["acceptable_bands"])
            if BAND_ORDER[band] < BAND_ORDER[expected["expected_band"]]:
                under.append(item["sample_id"])

        self.assertEqual(observed, 34)
        self.assertEqual(acceptable, 34)
        self.assertEqual(under, [])


if __name__ == "__main__":
    unittest.main()

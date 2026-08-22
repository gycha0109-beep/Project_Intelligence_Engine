from __future__ import annotations

import json
from pathlib import Path
import unittest

from review_system.trust import TRUST_RISK_MODEL_VERSION, _profile_descriptor
from review_system.trust_r4_verifier_role_shadow import (
    CONTRACT_VERSION,
    analyze_r4_verifier_role_candidate,
    project_r4_verifier_role_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
CALIBRATION = FIXTURE_DIR / "r4-verifier-role-remediation-shadow-v1.json"
R4_REGRESSION = FIXTURE_DIR / "r4-semantic-underdetection-seen-v1.json"
PROFILE = ROOT / "profiles" / "examples" / "generic-webapp.yml"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TrustR4VerifierRoleRemediationShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_json(CALIBRATION)
        cls.r4_regression = load_json(R4_REGRESSION)
        cls.profile = _profile_descriptor(PROFILE)[1]
        cls.cases = {item["case_id"]: item for item in cls.fixture["cases"]}

    def test_contract_is_shadow_only_on_v13_authority(self) -> None:
        self.assertEqual(TRUST_RISK_MODEL_VERSION, "1.3")
        self.assertEqual(self.fixture["contract_version"], CONTRACT_VERSION)
        self.assertEqual(self.fixture["defect_id"], "EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_GAP")
        ceiling = self.fixture["authority_ceiling"]
        self.assertTrue(ceiling["shadow_only"])
        self.assertFalse(ceiling["automation_authorized"])
        self.assertFalse(ceiling["pilot_authorized"])
        self.assertFalse(ceiling["authoritative_remediation_authorized"])
        self.assertFalse(ceiling["blind_holdout_claim"])

    def test_calibration_matrix_matches_current_and_candidate_classes(self) -> None:
        triggered = []
        for case in self.fixture["cases"]:
            with self.subTest(case_id=case["case_id"]):
                result = analyze_r4_verifier_role_candidate(case["path"], case["excerpt"])
                self.assertEqual(
                    result["current"]["classification"],
                    case["current_classification"],
                )
                self.assertEqual(
                    result["candidate"]["classification"],
                    case["candidate_classification"],
                )
                self.assertEqual(result["candidate_triggered"], case["candidate_triggered"])
                if result["candidate_triggered"]:
                    triggered.append(case["case_id"])
        self.assertEqual(triggered, ["MV-7-LIVE-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER"])

    def test_mv7_live_verifier_requires_combined_authority_signals(self) -> None:
        case = self.cases["MV-7-LIVE-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER"]
        result = analyze_r4_verifier_role_candidate(case["path"], case["excerpt"])
        self.assertTrue(result["candidate_triggered"])
        self.assertEqual(
            result["candidate"]["classification"],
            "EXECUTABLE_VERIFICATION_GATE_AUTHORITY",
        )
        self.assertTrue(result["candidate"]["is_r4_authority"])
        self.assertEqual(
            set(result["candidate"]["reason_ids"]),
            {
                "R4_EXECUTABLE_ACCEPTANCE_OUTCOME",
                "R4_EXTERNAL_OPERATIONAL_OBSERVATION",
                "R4_DURABLE_ACCEPTANCE_EVIDENCE",
                "R4_FAIL_CLOSED_EXECUTION",
            },
        )
        self.assertTrue(all(result["candidate_signals"].values()))

    def test_same_pr_supporting_contract_is_not_promoted(self) -> None:
        case = self.cases["MV-7-SUPPORTING-CONTRACT-NEGATIVE"]
        result = analyze_r4_verifier_role_candidate(case["path"], case["excerpt"])
        self.assertFalse(result["candidate_triggered"])
        self.assertEqual(result["candidate"]["classification"], "SUPPORTING_REGRESSION_ONLY")
        self.assertFalse(result["candidate"]["is_r4_authority"])
        self.assertTrue(result["candidate_signals"]["acceptance_outcome"])
        self.assertFalse(result["candidate_signals"]["external_observation"])
        self.assertFalse(result["candidate_signals"]["durable_evidence"])

    def test_evaluation_only_ceiling_wins_even_with_live_acceptance_signals(self) -> None:
        case = self.cases["NEG-EVALUATION-ONLY-LIVE-ACCEPTANCE"]
        result = analyze_r4_verifier_role_candidate(case["path"], case["excerpt"])
        self.assertEqual(result["current"]["classification"], "SUPPORTING_EVALUATION_ONLY")
        self.assertFalse(result["candidate_triggered"])
        self.assertEqual(result["candidate"]["classification"], "SUPPORTING_EVALUATION_ONLY")

    def test_existing_v13_r4_semantic_calibration_is_unchanged(self) -> None:
        observed = {}
        for case in self.r4_regression["cases"]:
            with self.subTest(sample_id=case["sample_id"]):
                result = analyze_r4_verifier_role_candidate(case["path"], case["excerpt"])
                observed[case["sample_id"]] = result["candidate"]["classification"]
                self.assertEqual(
                    result["current"]["classification"],
                    case["expected_classification"],
                )
                self.assertEqual(
                    result["candidate"]["classification"],
                    case["expected_classification"],
                )
                self.assertFalse(result["candidate_triggered"])
        self.assertEqual(
            {sample_id for sample_id, classification in observed.items() if classification in {
                "NORMATIVE_DECISION_AUTHORITY",
                "EXECUTABLE_VERIFICATION_GATE_AUTHORITY",
            }},
            {"KB-262", "KB-272", "KB-277", "KB-279", "AR-30"},
        )

    def test_candidate_projection_promotes_only_mv7_core_path_to_r4(self) -> None:
        case = self.cases["MV-7-LIVE-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER"]
        request = {
            "task_class": "routine_code",
            "changed_files": [case["path"]],
        }
        result = project_r4_verifier_role_candidate(
            request,
            self.profile,
            {case["path"]: case["excerpt"]},
        )
        self.assertEqual(result["current_risk"]["effective_band"], "R2")
        self.assertEqual(result["candidate_risk"]["effective_band"], "R4")
        self.assertEqual(result["candidate_r4_paths"], [case["path"]])
        self.assertTrue(result["band_changed"])
        self.assertIn(
            "SEMANTIC_R4_VERIFIER_ROLE_CANDIDATE",
            {item["reason_id"] for item in result["candidate_risk"]["reasons"]},
        )

    def test_candidate_is_not_masterv_named(self) -> None:
        case = self.cases["MV-7-LIVE-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER"]
        neutral_text = case["excerpt"].replace(
            "MASTERV_REL_1C_PUBLISHED_UPDATER_SIGNATURE_ACCEPTANCE_PASS",
            "PRODUCT_PUBLISHED_UPDATE_SIGNATURE_ACCEPTANCE_PASS",
        )
        result = analyze_r4_verifier_role_candidate(
            "scripts/published-update-acceptance.mjs",
            neutral_text,
        )
        self.assertTrue(result["candidate_triggered"])
        self.assertEqual(
            result["candidate"]["classification"],
            "EXECUTABLE_VERIFICATION_GATE_AUTHORITY",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import inspect
import json
from pathlib import Path
import unittest

from review_system.trust import TRUST_RISK_MODEL_VERSION, _profile_descriptor
from review_system import trust_signing_trust_root_shadow as shadow_module
from review_system.trust_signing_trust_root_shadow import (
    CONTRACT_VERSION,
    REASON_ID,
    analyze_signing_trust_root_candidate,
    project_signing_trust_root_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "trust-risk-calibration"
    / "signing-trust-root-remediation-shadow-v1.json"
)
PROFILE = ROOT / "profiles" / "examples" / "generic-webapp.yml"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TrustSigningTrustRootShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture()
        cls.profile = _profile_descriptor(PROFILE)[1]
        cls.cases = {case["case_id"]: case for case in cls.fixture["cases"]}

    def project(self, case: dict) -> dict:
        request = {
            "task_class": "routine_code",
            "changed_files": [case["path"]],
        }
        return project_signing_trust_root_candidate(
            request,
            self.profile,
            {case["path"]: case["excerpt"]},
        )

    def test_contract_is_shadow_only_on_current_v14_authority(self) -> None:
        self.assertEqual(TRUST_RISK_MODEL_VERSION, "1.4")
        self.assertEqual(self.fixture["contract_version"], CONTRACT_VERSION)
        self.assertEqual(self.fixture["defect_id"], "SIGNING_TRUST_ROOT_AUTHORITY_GAP")
        self.assertEqual(self.fixture["target_band"], "R3")
        ceiling = self.fixture["authority_ceiling"]
        self.assertTrue(ceiling["shadow_only"])
        self.assertFalse(ceiling["automation_authorized"])
        self.assertFalse(ceiling["pilot_authorized"])
        self.assertFalse(ceiling["authoritative_remediation_authorized"])
        self.assertFalse(ceiling["blind_holdout_claim"])

    def test_fixture_trigger_expectations_match_candidate(self) -> None:
        triggered = []
        for case in self.fixture["cases"]:
            with self.subTest(case_id=case["case_id"]):
                result = analyze_signing_trust_root_candidate(case["path"], case["excerpt"])
                self.assertEqual(result["candidate_triggered"], case["expected_candidate_triggered"])
                if result["candidate_triggered"]:
                    triggered.append(case["case_id"])
        self.assertEqual(
            triggered,
            [
                "MV-3-RUST-UPDATER-TRUST-ROOT",
                "MV-3-TAURI-UPDATER-CONFIG-TRUST-ROOT",
                "GENERIC-SYNTHETIC-PRODUCTION-TRUST-ROOT-POSITIVE",
            ],
        )

    def test_mv3_runtime_trust_root_paths_move_r2_to_r3_candidate(self) -> None:
        for case_id in (
            "MV-3-RUST-UPDATER-TRUST-ROOT",
            "MV-3-TAURI-UPDATER-CONFIG-TRUST-ROOT",
        ):
            with self.subTest(case_id=case_id):
                case = self.cases[case_id]
                result = self.project(case)
                self.assertEqual(result["current_risk"]["effective_band"], case["expected_current_band"])
                self.assertEqual(result["candidate_risk"]["effective_band"], "R3")
                self.assertTrue(result["band_changed"])
                self.assertEqual(result["candidate_paths"], [case["path"]])
                reason_ids = {item["reason_id"] for item in result["candidate_risk"]["reasons"]}
                self.assertIn(REASON_ID, reason_ids)
                self.assertNotEqual(result["candidate_risk"]["effective_band"], "R4")

    def test_same_pr_contract_is_supporting_evidence_not_trust_root_mutation(self) -> None:
        case = self.cases["MV-3-SUPPORTING-CONTRACT-NEGATIVE"]
        result = analyze_signing_trust_root_candidate(case["path"], case["excerpt"])
        self.assertFalse(result["candidate_triggered"])
        self.assertFalse(result["signals"]["runtime_or_config_surface"])

    def test_docs_tests_examples_and_ordinary_crypto_do_not_promote(self) -> None:
        for case_id in (
            "NEG-DOCUMENTATION-SIGNING-TRUST-ROOT",
            "NEG-TEST-SIGNATURE-PUBLIC-KEY",
            "NEG-ORDINARY-CRYPTO-PUBLIC-KEY",
            "NEG-EXAMPLE-UPDATER-CONFIG",
        ):
            with self.subTest(case_id=case_id):
                case = self.cases[case_id]
                result = analyze_signing_trust_root_candidate(case["path"], case["excerpt"])
                self.assertFalse(result["candidate_triggered"])

    def test_candidate_requires_concrete_trust_root_assignment(self) -> None:
        case = self.cases["MV-3-RUST-UPDATER-TRUST-ROOT"]
        no_assignment = case["excerpt"].replace("UPDATE_PUBLIC_KEY: &str =", "read_update_public_key(")
        result = analyze_signing_trust_root_candidate(case["path"], no_assignment)
        self.assertFalse(result["signals"]["trust_root_assignment"])
        self.assertFalse(result["candidate_triggered"])

    def test_generic_positive_does_not_depend_on_tauri_or_masterv_tokens(self) -> None:
        case = self.cases["GENERIC-SYNTHETIC-PRODUCTION-TRUST-ROOT-POSITIVE"]
        result = analyze_signing_trust_root_candidate(case["path"], case["excerpt"])
        self.assertTrue(result["candidate_triggered"])
        self.assertEqual(result["candidate_band"], "R3")

        implementation = inspect.getsource(shadow_module).lower()
        self.assertNotIn("masterv", implementation)
        self.assertNotIn("src-tauri", implementation)

    def test_candidate_never_downgrades_existing_r3(self) -> None:
        path = "auth/production-updater.py"
        excerpt = 'UPDATE_PUBLIC_KEY = "rotated-production-signature-key"\nverify_release_signature()'
        result = project_signing_trust_root_candidate(
            {"task_class": "routine_code", "changed_files": [path]},
            self.profile,
            {path: excerpt},
        )
        self.assertEqual(result["current_risk"]["effective_band"], "R3")
        self.assertEqual(result["candidate_risk"]["effective_band"], "R3")
        self.assertFalse(result["band_changed"])


if __name__ == "__main__":
    unittest.main()

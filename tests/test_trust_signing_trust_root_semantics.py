from __future__ import annotations

import json
from pathlib import Path
import unittest

from review_system.trust_signing_trust_root_semantics import analyze_signing_trust_root_semantics
from review_system.trust_signing_trust_root_shadow import analyze_signing_trust_root_candidate


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "trust-risk-calibration"
    / "signing-trust-root-remediation-shadow-v1.json"
)


class TrustSigningTrustRootSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_pure_semantics_replay_frozen_shadow_matrix_exactly(self) -> None:
        for case in self.fixture["cases"]:
            with self.subTest(case_id=case["case_id"]):
                semantics = analyze_signing_trust_root_semantics(
                    case["path"],
                    case["excerpt"],
                )
                shadow = analyze_signing_trust_root_candidate(
                    case["path"],
                    case["excerpt"],
                )
                self.assertEqual(
                    semantics["candidate_triggered"],
                    case["expected_candidate_triggered"],
                )
                self.assertEqual(
                    semantics["candidate_triggered"],
                    shadow["candidate_triggered"],
                )
                self.assertEqual(semantics["path"], shadow["path"])
                self.assertEqual(semantics["signals"], shadow["signals"])

    def test_semantics_module_has_no_trust_or_repository_identity_dependency(self) -> None:
        import review_system.trust_signing_trust_root_semantics as module

        source = Path(module.__file__).read_text(encoding="utf-8").lower()
        self.assertNotIn("from .trust import", source)
        self.assertNotIn("masterv", source)
        self.assertNotIn("tauri", source)
        self.assertNotIn("k_beauty", source)
        self.assertNotIn("buildmap", source)


if __name__ == "__main__":
    unittest.main()

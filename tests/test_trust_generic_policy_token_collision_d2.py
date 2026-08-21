from __future__ import annotations

import json
from pathlib import Path
import unittest

from review_system.trust import BAND_ORDER, _profile_descriptor
from review_system.trust_policy_token_shadow import (
    CANDIDATE_CONTRACT,
    project_generic_policy_collision_candidate,
)
from test_trust_authoritative_risk_promotion import holdout_semantics, wrapped_semantics


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
D2 = FIXTURE_DIR / "generic-policy-token-collision-d2-v1.json"
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


class TrustGenericPolicyTokenCollisionD2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_json(D2)
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

    def test_fixture_is_bounded_synthetic_shadow_contract(self) -> None:
        self.assertEqual(
            self.fixture["defect_id"],
            "GENERIC_POLICY_TOKEN_ACCESS_CONTROL_COLLISION",
        )
        self.assertEqual(self.fixture["candidate_contract"], CANDIDATE_CONTRACT)
        self.assertEqual(
            self.fixture["authority"]["pie_main_sha"],
            "30b05828e1b3227e9f721cd00c65a2d3a96ef33f",
        )
        self.assertTrue(self.fixture["scope"]["synthetic_only"])
        self.assertFalse(self.fixture["scope"]["human_holdout_claim"])
        self.assertFalse(self.fixture["scope"]["authoritative_runtime_change"])

    def test_synthetic_discriminator_matrix_replays_exactly(self) -> None:
        profile = self.profiles["generic-webapp"]
        for case in self.fixture["cases"]:
            with self.subTest(sample_id=case["sample_id"]):
                result = project_generic_policy_collision_candidate(
                    {
                        "task_class": case["task_class"],
                        "changed_files": case["changed_files"],
                    },
                    profile,
                )
                self.assertEqual(result["candidate_contract"], CANDIDATE_CONTRACT)
                self.assertEqual(result["mode"], "REPORT_ONLY")
                self.assertEqual(result["authority"], "SHADOW_ONLY")
                self.assertFalse(result["automation_authorized"])
                self.assertFalse(result["pilot_authorized"])
                self.assertEqual(
                    result["current_risk"]["effective_band"],
                    case["expected_current_band"],
                )
                self.assertEqual(
                    result["candidate_risk"]["effective_band"],
                    case["expected_candidate_band"],
                )
                self.assertEqual(
                    result["collision"]["collision_detected"],
                    case["expected_collision"],
                )

    def test_only_generic_policy_only_shapes_change_band(self) -> None:
        profile = self.profiles["generic-webapp"]
        changed: list[str] = []
        for case in self.fixture["cases"]:
            result = project_generic_policy_collision_candidate(
                {
                    "task_class": case["task_class"],
                    "changed_files": case["changed_files"],
                },
                profile,
            )
            if result["band_changed"]:
                changed.append(case["sample_id"])
                current_reasons = {
                    item["reason_id"] for item in result["current_risk"]["reasons"]
                }
                candidate_reasons = {
                    item["reason_id"] for item in result["candidate_risk"]["reasons"]
                }
                self.assertIn(
                    "REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS",
                    current_reasons,
                )
                self.assertNotIn(
                    "REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS",
                    candidate_reasons,
                )
        self.assertEqual(
            changed,
            [
                "D2-GENERIC-CANDIDATE-POLICY",
                "D2-GENERIC-RANKING-POLICY",
                "D2-GENERIC-ACCESS-CONTROL-POLICY",
            ],
        )

    def test_explicit_authority_signals_remain_r3_or_higher(self) -> None:
        profile = self.profiles["generic-webapp"]
        protected = {
            "D2-CONTROL-RLS": "R3",
            "D2-CONTROL-SUPABASE": "R3",
            "D2-CONTROL-AUTH": "R3",
            "D2-CONTROL-INDEPENDENT-AUTH-RLS": "R3",
            "D2-CONTROL-MIGRATION": "R3",
            "D2-CONTROL-R4": "R4",
        }
        by_id = {case["sample_id"]: case for case in self.fixture["cases"]}
        for sample_id, expected in protected.items():
            with self.subTest(sample_id=sample_id):
                case = by_id[sample_id]
                result = project_generic_policy_collision_candidate(
                    {
                        "task_class": case["task_class"],
                        "changed_files": case["changed_files"],
                    },
                    profile,
                )
                self.assertEqual(result["candidate_risk"]["effective_band"], expected)

    def test_wave1_34_authoritative_bands_do_not_change(self) -> None:
        seen_evidence: dict[str, dict] = {}
        for sample_id, case in self.seen_workflow_by_id.items():
            seen_evidence[sample_id] = wrapped_semantics(
                source_revision=case["source_revision"],
                changed_files=case["changed_files"],
                diff_text=case["diff_text"],
                source_evidence_sha256=case["source_evidence_sha256"],
            )

        observed = 0
        acceptable = 0
        under: list[str] = []
        band_changes: list[str] = []

        for item in self.seen["samples"]:
            request = {
                "task_class": item["task_class"],
                "changed_files": item["changed_files"],
            }
            evidence = seen_evidence.get(item["sample_id"])
            if evidence is not None:
                request["source_revision"] = self.seen_workflow_by_id[item["sample_id"]]["source_revision"]
            result = project_generic_policy_collision_candidate(
                request,
                self.profiles[item["profile_basis"]],
                workflow_evidence=evidence,
            )
            current = result["current_risk"]["effective_band"]
            candidate = result["candidate_risk"]["effective_band"]
            observed += 1
            acceptable += int(candidate in item["acceptable_bands"])
            if BAND_ORDER[candidate] < BAND_ORDER[item["expected_band"]]:
                under.append(item["sample_id"])
            if current != candidate:
                band_changes.append(item["sample_id"])

        for item in self.holdout["predictions"]:
            expected = self.holdout_labels_by_id[item["sample_id"]]
            request = {
                "source_revision": item["frozen_head_sha"],
                "task_class": item["task_class"],
                "changed_files": item["changed_files"],
            }
            result = project_generic_policy_collision_candidate(
                request,
                self.profiles[item["profile_basis"]],
                workflow_evidence=holdout_semantics(item),
            )
            current = result["current_risk"]["effective_band"]
            candidate = result["candidate_risk"]["effective_band"]
            observed += 1
            acceptable += int(candidate in expected["acceptable_bands"])
            if BAND_ORDER[candidate] < BAND_ORDER[expected["expected_band"]]:
                under.append(item["sample_id"])
            if current != candidate:
                band_changes.append(item["sample_id"])

        self.assertEqual(observed, 34)
        self.assertEqual(acceptable, 34)
        self.assertEqual(under, [])
        self.assertEqual(band_changes, [])


if __name__ == "__main__":
    unittest.main()

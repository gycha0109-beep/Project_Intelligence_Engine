from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.trust import (
    BAND_ORDER,
    TRUST_RISK_MODEL_V1_1,
    TRUST_RISK_MODEL_V1_2,
    TRUST_RISK_MODEL_V1_3,
    TRUST_RISK_MODEL_VERSION,
    _hard_gate_projection,
    _profile_descriptor,
    _risk_projection,
    assess_trust,
    verify_trust_report_data,
    verify_trust_report_sources,
)
from review_system.trust_policy_token_shadow import (
    project_generic_policy_collision_candidate,
)
from test_trust_authoritative_risk_promotion import holdout_semantics, wrapped_semantics
from test_trust_gate import TrustReadinessFixture


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


def gate_request(task_class: str, changed_files: list[str]) -> dict:
    return {
        "task_class": task_class,
        "changed_files": changed_files,
        "required_scenarios": [],
        "completed_scenarios": [],
        "repository_match": True,
        "head_match": True,
        "rollback_evidence": True,
        "replay_evidence": True,
    }


class TrustGenericPolicyTokenAuthoritativePromotionTests(unittest.TestCase):
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

    def test_risk_model_versions_are_explicit_and_distinct(self) -> None:
        self.assertEqual(TRUST_RISK_MODEL_V1_1, "1.1")
        self.assertEqual(TRUST_RISK_MODEL_V1_2, "1.2")
        self.assertEqual(TRUST_RISK_MODEL_V1_3, "1.3")
        self.assertEqual(TRUST_RISK_MODEL_VERSION, "1.4")
        self.assertNotEqual(TRUST_RISK_MODEL_V1_1, TRUST_RISK_MODEL_V1_2)
        self.assertNotEqual(TRUST_RISK_MODEL_V1_2, TRUST_RISK_MODEL_V1_3)
        self.assertNotEqual(TRUST_RISK_MODEL_V1_3, TRUST_RISK_MODEL_VERSION)

    def test_v12_matches_frozen_shadow_candidate_for_d2_matrix(self) -> None:
        profile = self.profiles["generic-webapp"]
        for case in self.fixture["cases"]:
            with self.subTest(sample_id=case["sample_id"]):
                request = {
                    "task_class": case["task_class"],
                    "changed_files": case["changed_files"],
                }
                shadow = project_generic_policy_collision_candidate(request, profile)
                v11 = _risk_projection(
                    request,
                    profile,
                    risk_model_version=TRUST_RISK_MODEL_V1_1,
                )
                v12 = _risk_projection(
                    request,
                    profile,
                    risk_model_version=TRUST_RISK_MODEL_V1_2,
                )
                self.assertEqual(v11, shadow["current_risk"])
                self.assertEqual(v12, shadow["candidate_risk"])
                self.assertEqual(v11["effective_band"], case["expected_current_band"])
                self.assertEqual(v12["effective_band"], case["expected_candidate_band"])

    def test_v12_removes_only_generic_policy_self_corroboration(self) -> None:
        profile = self.profiles["generic-webapp"]
        generic_ids = {
            "D2-GENERIC-CANDIDATE-POLICY",
            "D2-GENERIC-RANKING-POLICY",
            "D2-GENERIC-ACCESS-CONTROL-POLICY",
        }
        for case in self.fixture["cases"]:
            request = {
                "task_class": case["task_class"],
                "changed_files": case["changed_files"],
            }
            v11 = _risk_projection(
                request,
                profile,
                risk_model_version=TRUST_RISK_MODEL_V1_1,
            )
            v12 = _risk_projection(
                request,
                profile,
                risk_model_version=TRUST_RISK_MODEL_V1_2,
            )
            v11_reasons = {item["reason_id"] for item in v11["reasons"]}
            v12_reasons = {item["reason_id"] for item in v12["reasons"]}
            if case["sample_id"] in generic_ids:
                self.assertIn(
                    "REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS",
                    v11_reasons,
                )
                self.assertNotIn(
                    "REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS",
                    v12_reasons,
                )
                self.assertEqual(v11["effective_band"], "R3")
                self.assertEqual(v12["effective_band"], "R2")

    def test_true_authority_controls_remain_r3_or_r4(self) -> None:
        profile = self.profiles["generic-webapp"]
        expected = {
            "D2-CONTROL-RLS": "R3",
            "D2-CONTROL-SUPABASE": "R3",
            "D2-CONTROL-AUTH": "R3",
            "D2-CONTROL-INDEPENDENT-AUTH-RLS": "R3",
            "D2-CONTROL-MIGRATION": "R3",
            "D2-CONTROL-R4": "R4",
        }
        by_id = {case["sample_id"]: case for case in self.fixture["cases"]}
        for sample_id, band in expected.items():
            with self.subTest(sample_id=sample_id):
                case = by_id[sample_id]
                result = _risk_projection(
                    {
                        "task_class": case["task_class"],
                        "changed_files": case["changed_files"],
                    },
                    profile,
                    risk_model_version=TRUST_RISK_MODEL_VERSION,
                )
                self.assertEqual(result["effective_band"], band)

    def test_hard_gate_tracks_authority_after_d2_correction(self) -> None:
        profile = self.profiles["generic-webapp"]
        evidence = {"policy": {"policy_evaluation_ready": True}}

        generic_request = gate_request(
            "routine_code",
            ["src/recommendation/candidate-policy.ts"],
        )
        generic_v11 = _risk_projection(
            generic_request,
            profile,
            risk_model_version=TRUST_RISK_MODEL_V1_1,
        )
        generic_v12 = _risk_projection(
            generic_request,
            profile,
            risk_model_version=TRUST_RISK_MODEL_V1_2,
        )
        gate_v11 = next(
            item
            for item in _hard_gate_projection(generic_request, generic_v11, evidence)
            if item["gate_id"] == "AUTHORIZATION_OR_MIGRATION_CHANGE"
        )
        gate_v12 = next(
            item
            for item in _hard_gate_projection(generic_request, generic_v12, evidence)
            if item["gate_id"] == "AUTHORIZATION_OR_MIGRATION_CHANGE"
        )
        self.assertTrue(gate_v11["triggered"])
        self.assertFalse(gate_v12["triggered"])

        for path in (
            "src/rls/policy.ts",
            "src/auth/policy.ts",
            "supabase/migrations/20260822_policy.sql",
        ):
            with self.subTest(path=path):
                request = gate_request("routine_code", [path])
                risk = _risk_projection(
                    request,
                    profile,
                    risk_model_version=TRUST_RISK_MODEL_VERSION,
                )
                gate = next(
                    item
                    for item in _hard_gate_projection(request, risk, evidence)
                    if item["gate_id"] == "AUTHORIZATION_OR_MIGRATION_CHANGE"
                )
                self.assertTrue(gate["triggered"])

    def test_wave1_v12_has_zero_band_delta_from_v11(self) -> None:
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
        deltas: list[str] = []

        for item in self.seen["samples"]:
            request = {
                "task_class": item["task_class"],
                "changed_files": item["changed_files"],
            }
            evidence = seen_evidence.get(item["sample_id"])
            if evidence is not None:
                request["source_revision"] = self.seen_workflow_by_id[item["sample_id"]]["source_revision"]
            v11 = _risk_projection(
                request,
                self.profiles[item["profile_basis"]],
                evidence,
                risk_model_version=TRUST_RISK_MODEL_V1_1,
            )["effective_band"]
            v12 = _risk_projection(
                request,
                self.profiles[item["profile_basis"]],
                evidence,
                risk_model_version=TRUST_RISK_MODEL_V1_2,
            )["effective_band"]
            observed += 1
            acceptable += int(v12 in item["acceptable_bands"])
            if BAND_ORDER[v12] < BAND_ORDER[item["expected_band"]]:
                under.append(item["sample_id"])
            if v11 != v12:
                deltas.append(item["sample_id"])

        for item in self.holdout["predictions"]:
            expected = self.holdout_labels_by_id[item["sample_id"]]
            request = {
                "source_revision": item["frozen_head_sha"],
                "task_class": item["task_class"],
                "changed_files": item["changed_files"],
            }
            evidence = holdout_semantics(item)
            v11 = _risk_projection(
                request,
                self.profiles[item["profile_basis"]],
                evidence,
                risk_model_version=TRUST_RISK_MODEL_V1_1,
            )["effective_band"]
            v12 = _risk_projection(
                request,
                self.profiles[item["profile_basis"]],
                evidence,
                risk_model_version=TRUST_RISK_MODEL_V1_2,
            )["effective_band"]
            observed += 1
            acceptable += int(v12 in expected["acceptable_bands"])
            if BAND_ORDER[v12] < BAND_ORDER[expected["expected_band"]]:
                under.append(item["sample_id"])
            if v11 != v12:
                deltas.append(item["sample_id"])

        self.assertEqual(observed, 34)
        self.assertEqual(acceptable, 34)
        self.assertEqual(under, [])
        self.assertEqual(deltas, [])

    def test_v11_report_and_source_replay_remain_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            report = assess_trust(
                fixture.request,
                fixture.profile,
                ledger=fixture.reground_fixture.ledger,
                policy_registry=fixture.policy_registry,
                evaluation_report=fixture.evaluation_report,
                reground_report=fixture.reground_report,
                reground_observations=fixture.observations,
                generated_at="2026-07-25T02:00:00Z",
                _risk_model_version=TRUST_RISK_MODEL_V1_1,
            )
            self.assertEqual(report["risk_model_version"], TRUST_RISK_MODEL_V1_1)
            self.assertEqual([], verify_trust_report_data(report))
            self.assertEqual(
                [],
                verify_trust_report_sources(report, **fixture.source_args()),
            )


if __name__ == "__main__":
    unittest.main()

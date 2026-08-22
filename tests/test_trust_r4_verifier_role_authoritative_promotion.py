from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.io import dump_json
from review_system.trust import (
    TRUST_RISK_MODEL_V1_3,
    TRUST_RISK_MODEL_VERSION,
    _profile_descriptor,
    _risk_projection,
    assess_trust,
    verify_trust_report_data,
    verify_trust_report_sources,
)
from review_system.trust_r4_semantics_authority import (
    CONTRACT_VERSION_V1_3,
    CONTRACT_VERSION_V1_4,
    build_trust_r4_semantic_evidence,
    normalize_trust_r4_semantic_evidence,
)
from test_trust_authoritative_risk_promotion import github_source_for
from test_trust_gate import TrustReadinessFixture


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
VERIFIER_FIXTURE = FIXTURE_DIR / "r4-verifier-role-remediation-shadow-v1.json"
R4_FIXTURE = FIXTURE_DIR / "r4-semantic-underdetection-seen-v1.json"
GENERIC_PROFILE = ROOT / "profiles" / "examples" / "generic-webapp.yml"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def diff_for(path: str, excerpt: str) -> str:
    lines = excerpt.splitlines() or [""]
    additions = "\n".join(f"+{line}" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{additions}\n"
    )


class TrustR4VerifierRoleAuthoritativePromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier_fixture = load_json(VERIFIER_FIXTURE)
        cls.r4_fixture = load_json(R4_FIXTURE)
        cls.verifier_by_id = {
            item["case_id"]: item for item in cls.verifier_fixture["cases"]
        }
        cls.r4_by_id = {item["sample_id"]: item for item in cls.r4_fixture["cases"]}
        cls.profile = _profile_descriptor(GENERIC_PROFILE)[1]

    def bound_evidence(
        self,
        *,
        path: str,
        excerpt: str,
        risk_model_version: str,
        revision: str = "a" * 40,
    ) -> tuple[str, dict, dict]:
        diff_text = diff_for(path, excerpt)
        source = github_source_for(
            revision=revision,
            changed_files=[path],
            diff_text=diff_text,
        )
        evidence = build_trust_r4_semantic_evidence(
            github_source=source,
            diff_text=diff_text,
            source_revision=revision,
            changed_files=[path],
            risk_model_version=risk_model_version,
        )
        return diff_text, source, evidence

    def risk_for(self, path: str, evidence: dict, risk_model_version: str) -> dict:
        return _risk_projection(
            {
                "source_revision": "a" * 40,
                "task_class": "routine_code",
                "changed_files": [path],
            },
            self.profile,
            None,
            evidence,
            risk_model_version=risk_model_version,
        )

    def test_current_model_is_v14_and_v13_remains_explicit(self) -> None:
        self.assertEqual(TRUST_RISK_MODEL_V1_3, "1.3")
        self.assertEqual(TRUST_RISK_MODEL_VERSION, "1.4")
        self.assertNotEqual(TRUST_RISK_MODEL_V1_3, TRUST_RISK_MODEL_VERSION)

    def test_mv7_live_acceptance_verifier_promotes_only_in_v14(self) -> None:
        case = self.verifier_by_id["MV-7-LIVE-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER"]
        path = case["path"]

        _, _, v13 = self.bound_evidence(
            path=path,
            excerpt=case["excerpt"],
            risk_model_version=TRUST_RISK_MODEL_V1_3,
        )
        v13_analysis = v13["semantics"]["files"][0]
        self.assertEqual(v13["semantics"]["contract_version"], CONTRACT_VERSION_V1_3)
        self.assertEqual(v13_analysis["classification"], "SUPPORTING_REGRESSION_ONLY")
        self.assertFalse(v13_analysis["is_r4_authority"])
        self.assertNotEqual(
            self.risk_for(path, v13, TRUST_RISK_MODEL_V1_3)["effective_band"],
            "R4",
        )

        _, _, v14 = self.bound_evidence(
            path=path,
            excerpt=case["excerpt"],
            risk_model_version=TRUST_RISK_MODEL_VERSION,
        )
        normalized = normalize_trust_r4_semantic_evidence(
            v14,
            source_revision="a" * 40,
            changed_files=[path],
            risk_model_version=TRUST_RISK_MODEL_VERSION,
        )
        self.assertEqual(normalized, v14)
        analysis = v14["semantics"]["files"][0]
        self.assertEqual(v14["semantics"]["contract_version"], CONTRACT_VERSION_V1_4)
        self.assertEqual(analysis["classification"], "EXECUTABLE_VERIFICATION_GATE_AUTHORITY")
        self.assertTrue(analysis["is_r4_authority"])
        self.assertTrue(analysis["signals"]["verifier_role_promoted"])
        self.assertTrue(analysis["signals"]["verifier_role_candidate"]["acceptance_outcome"])
        self.assertTrue(analysis["signals"]["verifier_role_candidate"]["external_observation"])
        self.assertTrue(analysis["signals"]["verifier_role_candidate"]["durable_evidence"])
        self.assertTrue(analysis["signals"]["verifier_role_candidate"]["operational_acceptance_context"])
        risk = self.risk_for(path, v14, TRUST_RISK_MODEL_VERSION)
        self.assertEqual(risk["effective_band"], "R4")
        self.assertIn(
            "SEMANTIC_R4_AUTHORITY",
            {item["reason_id"] for item in risk["reasons"]},
        )

    def test_verifier_role_negative_matrix_does_not_gain_r4(self) -> None:
        negatives = [
            case for case in self.verifier_fixture["cases"]
            if not case["candidate_triggered"]
        ]
        self.assertGreaterEqual(len(negatives), 5)
        for case in negatives:
            with self.subTest(case_id=case["case_id"]):
                _, _, evidence = self.bound_evidence(
                    path=case["path"],
                    excerpt=case["excerpt"],
                    risk_model_version=TRUST_RISK_MODEL_VERSION,
                )
                analysis = evidence["semantics"]["files"][0]
                self.assertEqual(analysis["classification"], case["candidate_classification"])
                self.assertFalse(analysis["is_r4_authority"])
                self.assertFalse(analysis["signals"].get("verifier_role_promoted", False))

    def test_existing_v13_r4_positive_and_negative_matrix_is_preserved_in_v14(self) -> None:
        positives = [case for case in self.r4_fixture["cases"] if case["human_band"] == "R4"]
        self.assertEqual(len(positives), 5)
        for case in positives:
            with self.subTest(sample_id=case["sample_id"]):
                _, _, evidence = self.bound_evidence(
                    path=case["path"],
                    excerpt=case["excerpt"],
                    risk_model_version=TRUST_RISK_MODEL_VERSION,
                )
                analysis = evidence["semantics"]["files"][0]
                self.assertTrue(analysis["is_r4_authority"])
                self.assertEqual(self.risk_for(case["path"], evidence, TRUST_RISK_MODEL_VERSION)["effective_band"], "R4")

        for sample_id in ("RW-54", "KB-275", "NEG-DOC-VERIFICATION", "NEG-DOMAIN-POLICY"):
            case = self.r4_by_id[sample_id]
            with self.subTest(sample_id=sample_id):
                _, _, evidence = self.bound_evidence(
                    path=case["path"],
                    excerpt=case["excerpt"],
                    risk_model_version=TRUST_RISK_MODEL_VERSION,
                )
                self.assertFalse(evidence["semantics"]["files"][0]["is_r4_authority"])

    def test_v13_evidence_contract_remains_historically_replayable(self) -> None:
        case = self.r4_by_id["KB-272"]
        _, _, evidence = self.bound_evidence(
            path=case["path"],
            excerpt=case["excerpt"],
            risk_model_version=TRUST_RISK_MODEL_V1_3,
        )
        self.assertEqual(evidence["semantics"]["contract_version"], CONTRACT_VERSION_V1_3)
        self.assertNotIn("verifier_role_promoted", evidence["semantics"]["files"][0]["signals"])
        normalized = normalize_trust_r4_semantic_evidence(
            evidence,
            source_revision="a" * 40,
            changed_files=[case["path"]],
            risk_model_version=TRUST_RISK_MODEL_V1_3,
        )
        self.assertEqual(normalized, evidence)
        self.assertEqual(
            self.risk_for(case["path"], evidence, TRUST_RISK_MODEL_V1_3)["effective_band"],
            "R4",
        )

    def test_assess_and_source_replay_support_both_v13_and_v14(self) -> None:
        case = self.verifier_by_id["MV-7-LIVE-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = TrustReadinessFixture(root)
            path = case["path"]
            revision = "a" * 40
            fixture.write_request(task_class="routine_code", changed_files=[path])
            diff_text = diff_for(path, case["excerpt"])
            source = github_source_for(
                revision=revision,
                changed_files=[path],
                diff_text=diff_text,
            )
            source_path = root / "github-source.json"
            diff_path = root / "pull-request.diff"
            dump_json(source_path, source)
            diff_path.write_text(diff_text, encoding="utf-8")

            common = dict(
                ledger=fixture.reground_fixture.ledger,
                policy_registry=fixture.policy_registry,
                evaluation_report=fixture.evaluation_report,
                reground_report=fixture.reground_report,
                reground_observations=fixture.observations,
                github_source=source_path,
                workflow_diff=diff_path,
                generated_at="2026-08-22T02:00:00Z",
            )
            v13_report = assess_trust(
                fixture.request,
                fixture.profile,
                _risk_model_version=TRUST_RISK_MODEL_V1_3,
                **common,
            )
            self.assertEqual(v13_report["risk_model_version"], "1.3")
            self.assertEqual(v13_report["evidence"]["r4_semantics"]["semantics"]["contract_version"], CONTRACT_VERSION_V1_3)
            self.assertNotEqual(v13_report["risk"]["effective_band"], "R4")
            self.assertEqual([], verify_trust_report_data(v13_report))
            self.assertEqual(
                [],
                verify_trust_report_sources(
                    v13_report,
                    **fixture.source_args(),
                    github_source=source_path,
                    workflow_diff=diff_path,
                ),
            )

            v14_report = assess_trust(
                fixture.request,
                fixture.profile,
                _risk_model_version=TRUST_RISK_MODEL_VERSION,
                **common,
            )
            self.assertEqual(v14_report["risk_model_version"], "1.4")
            self.assertEqual(v14_report["evidence"]["r4_semantics"]["semantics"]["contract_version"], CONTRACT_VERSION_V1_4)
            self.assertEqual(v14_report["risk"]["effective_band"], "R4")
            self.assertEqual([], verify_trust_report_data(v14_report))
            self.assertEqual(
                [],
                verify_trust_report_sources(
                    v14_report,
                    **fixture.source_args(),
                    github_source=source_path,
                    workflow_diff=diff_path,
                ),
            )

    def test_no_source_pair_does_not_claim_verifier_role_r4(self) -> None:
        case = self.verifier_by_id["MV-7-LIVE-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER"]
        risk = _risk_projection(
            {
                "task_class": "routine_code",
                "changed_files": [case["path"]],
            },
            self.profile,
        )
        self.assertNotEqual(risk["effective_band"], "R4")
        self.assertNotIn(
            "SEMANTIC_R4_AUTHORITY",
            {item["reason_id"] for item in risk["reasons"]},
        )


if __name__ == "__main__":
    unittest.main()

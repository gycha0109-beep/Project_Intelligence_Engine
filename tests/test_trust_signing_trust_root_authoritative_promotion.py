from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from review_system.io import dump_json
from review_system.trust import (
    TRUST_RISK_MODEL_V1_4,
    TRUST_RISK_MODEL_VERSION,
    _profile_descriptor,
    _risk_projection,
    assess_trust,
    verify_trust_report_data,
    verify_trust_report_sources,
)
from review_system.trust_signing_trust_root_authority import (
    CONTRACT_VERSION,
    REASON_ID,
    build_trust_signing_trust_root_evidence,
    normalize_trust_signing_trust_root_evidence,
)
from test_trust_authoritative_risk_promotion import github_source_for
from test_trust_gate import TrustReadinessFixture


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "trust-risk-calibration"
    / "signing-trust-root-remediation-shadow-v1.json"
)
GENERIC_PROFILE = ROOT / "profiles" / "examples" / "generic-webapp.yml"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


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


class TrustSigningTrustRootAuthoritativePromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture()
        cls.by_id = {case["case_id"]: case for case in cls.fixture["cases"]}
        cls.profile = _profile_descriptor(GENERIC_PROFILE)[1]

    def bound_evidence(
        self,
        case: dict,
        *,
        revision: str = "a" * 40,
    ) -> tuple[str, dict, dict]:
        path = case["path"]
        diff_text = diff_for(path, case["excerpt"])
        source = github_source_for(
            revision=revision,
            changed_files=[path],
            diff_text=diff_text,
        )
        evidence = build_trust_signing_trust_root_evidence(
            github_source=source,
            diff_text=diff_text,
            source_revision=revision,
            changed_files=[path],
        )
        return diff_text, source, evidence

    def risk_for(
        self,
        path: str,
        signing_evidence: dict | None,
        *,
        risk_model_version: str,
    ) -> dict:
        return _risk_projection(
            {
                "source_revision": "a" * 40,
                "task_class": "routine_code",
                "changed_files": [path],
            },
            self.profile,
            None,
            None,
            signing_evidence,
            risk_model_version=risk_model_version,
        )

    def test_current_model_is_v15_and_v14_remains_explicit(self) -> None:
        self.assertEqual(TRUST_RISK_MODEL_V1_4, "1.4")
        self.assertEqual(TRUST_RISK_MODEL_VERSION, "1.5")
        self.assertNotEqual(TRUST_RISK_MODEL_V1_4, TRUST_RISK_MODEL_VERSION)

    def test_real_mv3_surfaces_gain_source_bound_r3_only_in_v15(self) -> None:
        for case_id in (
            "MV-3-RUST-UPDATER-TRUST-ROOT",
            "MV-3-TAURI-UPDATER-CONFIG-TRUST-ROOT",
        ):
            with self.subTest(case_id=case_id):
                case = self.by_id[case_id]
                _, _, evidence = self.bound_evidence(case)
                normalized = normalize_trust_signing_trust_root_evidence(
                    evidence,
                    source_revision="a" * 40,
                    changed_files=[case["path"]],
                )
                self.assertEqual(normalized, evidence)
                analysis = evidence["semantics"]["files"][0]
                self.assertEqual(evidence["semantics"]["contract_version"], CONTRACT_VERSION)
                self.assertTrue(analysis["is_signing_trust_root_authority"])
                self.assertEqual(analysis["reason_ids"], [REASON_ID])
                self.assertEqual(
                    self.risk_for(
                        case["path"],
                        None,
                        risk_model_version=TRUST_RISK_MODEL_V1_4,
                    )["effective_band"],
                    "R2",
                )
                promoted = self.risk_for(
                    case["path"],
                    evidence,
                    risk_model_version=TRUST_RISK_MODEL_VERSION,
                )
                self.assertEqual(promoted["effective_band"], "R3")
                self.assertIn(
                    REASON_ID,
                    {item["reason_id"] for item in promoted["reasons"]},
                )
                with self.assertRaisesRegex(ValueError, "requires Trust risk model v1.5"):
                    self.risk_for(
                        case["path"],
                        evidence,
                        risk_model_version=TRUST_RISK_MODEL_V1_4,
                    )

    def test_calibrated_negative_matrix_does_not_gain_r3_authority(self) -> None:
        negatives = [
            case for case in self.fixture["cases"]
            if not case["expected_candidate_triggered"]
        ]
        self.assertGreaterEqual(len(negatives), 5)
        for case in negatives:
            with self.subTest(case_id=case["case_id"]):
                _, _, evidence = self.bound_evidence(case)
                analysis = evidence["semantics"]["files"][0]
                self.assertFalse(analysis["is_signing_trust_root_authority"])
                self.assertEqual(analysis["reason_ids"], [])
                risk = self.risk_for(
                    case["path"],
                    evidence,
                    risk_model_version=TRUST_RISK_MODEL_VERSION,
                )
                self.assertNotIn(
                    REASON_ID,
                    {item["reason_id"] for item in risk["reasons"]},
                )

    def test_generic_repository_neutral_positive_gains_r3(self) -> None:
        case = self.by_id["GENERIC-SYNTHETIC-PRODUCTION-TRUST-ROOT-POSITIVE"]
        _, _, evidence = self.bound_evidence(case)
        risk = self.risk_for(
            case["path"],
            evidence,
            risk_model_version=TRUST_RISK_MODEL_VERSION,
        )
        self.assertEqual(risk["effective_band"], "R3")
        self.assertNotEqual(risk["effective_band"], "R4")

    def test_source_binding_rejects_head_changed_files_and_diff_tampering(self) -> None:
        case = self.by_id["MV-3-RUST-UPDATER-TRUST-ROOT"]
        diff_text, source, _ = self.bound_evidence(case)
        with self.assertRaisesRegex(ValueError, "head revision"):
            build_trust_signing_trust_root_evidence(
                github_source=source,
                diff_text=diff_text,
                source_revision="b" * 40,
                changed_files=[case["path"]],
            )
        with self.assertRaisesRegex(ValueError, "changed files"):
            build_trust_signing_trust_root_evidence(
                github_source=source,
                diff_text=diff_text,
                source_revision="a" * 40,
                changed_files=[case["path"], "src/extra.py"],
            )
        with self.assertRaisesRegex(ValueError, "diff SHA-256"):
            build_trust_signing_trust_root_evidence(
                github_source=source,
                diff_text=diff_text + "# tamper\n",
                source_revision="a" * 40,
                changed_files=[case["path"]],
            )

    def test_normalizer_rejects_evidence_fingerprint_tampering(self) -> None:
        case = self.by_id["MV-3-TAURI-UPDATER-CONFIG-TRUST-ROOT"]
        _, _, evidence = self.bound_evidence(case)
        tampered = deepcopy(evidence)
        tampered["semantics"]["files"][0]["signals"]["operational_context"] = False
        with self.assertRaisesRegex(ValueError, "evidence_sha256 mismatch"):
            normalize_trust_signing_trust_root_evidence(
                tampered,
                source_revision="a" * 40,
                changed_files=[case["path"]],
            )

    def test_assess_and_source_replay_promote_only_v15(self) -> None:
        case = self.by_id["MV-3-RUST-UPDATER-TRUST-ROOT"]
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
                generated_at="2026-08-22T04:00:00Z",
            )
            v14 = assess_trust(
                fixture.request,
                fixture.profile,
                _risk_model_version=TRUST_RISK_MODEL_V1_4,
                **common,
            )
            self.assertEqual(v14["risk_model_version"], "1.4")
            self.assertNotIn("signing_trust_root", v14["evidence"])
            self.assertEqual(v14["risk"]["effective_band"], "R2")
            self.assertEqual([], verify_trust_report_data(v14))

            v15 = assess_trust(
                fixture.request,
                fixture.profile,
                _risk_model_version=TRUST_RISK_MODEL_VERSION,
                **common,
            )
            self.assertEqual(v15["risk_model_version"], "1.5")
            self.assertEqual(
                v15["evidence"]["signing_trust_root"]["semantics"]["contract_version"],
                CONTRACT_VERSION,
            )
            self.assertEqual(v15["risk"]["effective_band"], "R3")
            self.assertEqual([], verify_trust_report_data(v15))
            self.assertEqual(
                [],
                verify_trust_report_sources(
                    v15,
                    **fixture.source_args(),
                    github_source=source_path,
                    workflow_diff=diff_path,
                ),
            )

    def test_report_rejects_signing_evidence_under_v14(self) -> None:
        case = self.by_id["MV-3-RUST-UPDATER-TRUST-ROOT"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = TrustReadinessFixture(root)
            path = case["path"]
            fixture.write_request(task_class="routine_code", changed_files=[path])
            diff_text = diff_for(path, case["excerpt"])
            source = github_source_for(
                revision="a" * 40,
                changed_files=[path],
                diff_text=diff_text,
            )
            source_path = root / "github-source.json"
            diff_path = root / "pull-request.diff"
            dump_json(source_path, source)
            diff_path.write_text(diff_text, encoding="utf-8")
            report = assess_trust(
                fixture.request,
                fixture.profile,
                ledger=fixture.reground_fixture.ledger,
                policy_registry=fixture.policy_registry,
                evaluation_report=fixture.evaluation_report,
                reground_report=fixture.reground_report,
                reground_observations=fixture.observations,
                github_source=source_path,
                workflow_diff=diff_path,
                generated_at="2026-08-22T04:10:00Z",
            )
            report["risk_model_version"] = TRUST_RISK_MODEL_V1_4
            errors = verify_trust_report_data(report)
            self.assertTrue(any("signing trust-root evidence requires Trust risk model v1.5" in item for item in errors))


if __name__ == "__main__":
    unittest.main()

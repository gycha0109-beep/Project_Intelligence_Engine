from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.io import dump_json
from review_system.trust import (
    TRUST_RISK_MODEL_V1_2,
    TRUST_RISK_MODEL_VERSION,
    _profile_descriptor,
    _risk_projection,
    assess_trust,
    verify_trust_report_data,
    verify_trust_report_sources,
)
from review_system.trust_r4_semantics_authority import (
    build_trust_r4_semantic_evidence,
    normalize_trust_r4_semantic_evidence,
)
from test_trust_authoritative_risk_promotion import github_source_for
from test_trust_gate import TrustReadinessFixture


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
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


class TrustR4SemanticAuthoritativePromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_json(R4_FIXTURE)
        cls.profile = _profile_descriptor(GENERIC_PROFILE)[1]
        cls.by_id = {item["sample_id"]: item for item in cls.fixture["cases"]}

    def bound_evidence(self, case: dict, *, revision: str = "a" * 40) -> tuple[str, dict, dict]:
        path = case["path"]
        diff_text = diff_for(path, case["excerpt"])
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
        )
        return diff_text, source, evidence

    def test_current_risk_model_is_v13(self) -> None:
        self.assertEqual(TRUST_RISK_MODEL_VERSION, "1.3")
        self.assertEqual(TRUST_RISK_MODEL_V1_2, "1.2")

    def test_all_real_seen_r4_cases_promote_authoritatively(self) -> None:
        positives = [
            case for case in self.fixture["cases"] if case["human_band"] == "R4"
        ]
        self.assertEqual(
            {case["sample_id"] for case in positives},
            {"KB-262", "KB-272", "KB-277", "KB-279", "AR-30"},
        )
        for case in positives:
            with self.subTest(sample_id=case["sample_id"]):
                _, _, evidence = self.bound_evidence(case)
                normalized = normalize_trust_r4_semantic_evidence(
                    evidence,
                    source_revision="a" * 40,
                    changed_files=[case["path"]],
                )
                self.assertEqual(normalized, evidence)
                risk = _risk_projection(
                    {
                        "source_revision": "a" * 40,
                        "task_class": "routine_code",
                        "changed_files": [case["path"]],
                    },
                    self.profile,
                    None,
                    evidence,
                )
                self.assertEqual(risk["effective_band"], "R4")
                semantic_reason = next(
                    item for item in risk["reasons"]
                    if item["reason_id"] == "SEMANTIC_R4_AUTHORITY"
                )
                self.assertEqual(semantic_reason["band"], "R4")
                self.assertEqual(semantic_reason["paths"], [case["path"]])

    def test_supporting_seen_controls_do_not_gain_r4(self) -> None:
        for sample_id in ("RW-54", "KB-275", "NEG-DOMAIN-POLICY"):
            case = self.by_id[sample_id]
            with self.subTest(sample_id=sample_id):
                _, _, evidence = self.bound_evidence(case)
                analysis = evidence["semantics"]["files"][0]
                self.assertFalse(analysis["is_r4_authority"])
                risk = _risk_projection(
                    {
                        "source_revision": "a" * 40,
                        "task_class": "routine_code",
                        "changed_files": [case["path"]],
                    },
                    self.profile,
                    None,
                    evidence,
                )
                self.assertNotEqual(risk["effective_band"], "R4")
                self.assertNotIn(
                    "SEMANTIC_R4_AUTHORITY",
                    {item["reason_id"] for item in risk["reasons"]},
                )

    def test_v12_remains_frozen_without_r4_semantic_authority(self) -> None:
        case = self.by_id["KB-272"]
        _, _, evidence = self.bound_evidence(case)
        request = {
            "source_revision": "a" * 40,
            "task_class": "routine_code",
            "changed_files": [case["path"]],
        }
        with self.assertRaisesRegex(ValueError, "requires Trust risk model v1.3"):
            _risk_projection(
                request,
                self.profile,
                None,
                evidence,
                risk_model_version=TRUST_RISK_MODEL_V1_2,
            )
        v12 = _risk_projection(
            request,
            self.profile,
            None,
            None,
            risk_model_version=TRUST_RISK_MODEL_V1_2,
        )
        self.assertEqual(v12["effective_band"], "R2")

    def test_v12_preserves_generic_policy_token_correction(self) -> None:
        request = {
            "task_class": "routine_code",
            "changed_files": ["src/recommendation/candidate-policy.ts"],
        }
        v12 = _risk_projection(
            request,
            self.profile,
            risk_model_version=TRUST_RISK_MODEL_V1_2,
        )
        v13 = _risk_projection(request, self.profile)
        self.assertEqual(v12["effective_band"], "R2")
        self.assertEqual(v13["effective_band"], "R2")

    def test_source_binding_rejects_head_changed_files_diff_and_missing_sections(self) -> None:
        case = self.by_id["KB-272"]
        diff_text, source, _ = self.bound_evidence(case)
        path = case["path"]
        with self.assertRaisesRegex(ValueError, "head revision"):
            build_trust_r4_semantic_evidence(
                github_source=source,
                diff_text=diff_text,
                source_revision="b" * 40,
                changed_files=[path],
            )
        with self.assertRaisesRegex(ValueError, "changed files"):
            build_trust_r4_semantic_evidence(
                github_source=source,
                diff_text=diff_text,
                source_revision="a" * 40,
                changed_files=[path, "src/extra.py"],
            )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_trust_r4_semantic_evidence(
                github_source=source,
                diff_text=diff_text + "\n",
                source_revision="a" * 40,
                changed_files=[path],
            )

        missing_source = github_source_for(
            revision="a" * 40,
            changed_files=[path, "src/extra.py"],
            diff_text=diff_text,
        )
        with self.assertRaisesRegex(ValueError, "missing changed file sections"):
            build_trust_r4_semantic_evidence(
                github_source=missing_source,
                diff_text=diff_text,
                source_revision="a" * 40,
                changed_files=[path, "src/extra.py"],
            )

    def test_assess_and_source_replay_bind_r4_semantics(self) -> None:
        case = self.by_id["KB-272"]
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
                generated_at="2026-08-22T00:00:00Z",
            )
            self.assertEqual(report["risk_model_version"], "1.3")
            self.assertEqual(report["risk"]["effective_band"], "R4")
            self.assertIn("workflow_diff", report["evidence"])
            self.assertIn("r4_semantics", report["evidence"])
            self.assertEqual([], verify_trust_report_data(report))
            self.assertEqual(
                [],
                verify_trust_report_sources(
                    report,
                    **fixture.source_args(),
                    github_source=source_path,
                    workflow_diff=diff_path,
                ),
            )

            diff_path.write_text(diff_text + "\n", encoding="utf-8")
            replay_errors = verify_trust_report_sources(
                report,
                **fixture.source_args(),
                github_source=source_path,
                workflow_diff=diff_path,
            )
            self.assertTrue(replay_errors)
            self.assertIn("SHA-256", " ".join(replay_errors))

    def test_no_source_pair_does_not_claim_semantic_r4(self) -> None:
        case = self.by_id["KB-272"]
        risk = _risk_projection(
            {
                "task_class": "routine_code",
                "changed_files": [case["path"]],
            },
            self.profile,
        )
        self.assertEqual(risk["effective_band"], "R2")
        self.assertNotIn(
            "SEMANTIC_R4_AUTHORITY",
            {item["reason_id"] for item in risk["reasons"]},
        )


if __name__ == "__main__":
    unittest.main()

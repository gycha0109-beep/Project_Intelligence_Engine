from __future__ import annotations

import json
from pathlib import Path
import unittest

from review_system.trust import BAND_ORDER, _profile_descriptor, _risk_projection
from review_system.trust_workflow_bridge import project_candidate_risk
from review_system.workflow_semantics import build_workflow_diff_evidence


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
BASELINE = FIXTURE_DIR / "wave1-seen-baseline.json"
BRIDGE = FIXTURE_DIR / "workflow-semantic-bridge-d1-seen-v1.json"
SPLIT = FIXTURE_DIR / "wave1-split.json"

PROFILE_PATHS = {
    "buildmap": ROOT / "profiles" / "examples" / "buildmap.yml",
    "bejewely": ROOT / "profiles" / "examples" / "bejewely.yml",
    "generic-webapp": ROOT / "profiles" / "examples" / "generic-webapp.yml",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TrustWorkflowSemanticBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load_json(BASELINE)
        cls.fixture = load_json(BRIDGE)
        cls.split = load_json(SPLIT)
        cls.cases = {item["sample_id"]: item for item in cls.fixture["cases"]}
        cls.profiles = {
            key: _profile_descriptor(path)[1]
            for key, path in PROFILE_PATHS.items()
        }

    @staticmethod
    def evidence(case: dict) -> dict:
        return build_workflow_diff_evidence(
            source_revision=case["source_revision"],
            source_evidence_sha256=case["source_evidence_sha256"],
            changed_files=case["changed_files"],
            diff_text=case["diff_text"],
        )

    def test_candidate_fixture_is_seen_only_and_explicitly_synthetic(self) -> None:
        self.assertFalse(self.fixture["authority"]["frozen_holdout_replayed"])
        self.assertIn("synthetic calibration bindings", self.fixture["fixture_evidence_note"])
        self.assertEqual(set(self.cases), {"RW-54", "KB-269", "KB-275"})
        seen = set(self.split["calibration_seen"]) | set(self.split["seen_validation"])
        self.assertTrue(set(self.cases).issubset(seen))
        self.assertTrue(set(self.cases).isdisjoint(self.split["frozen_holdout"]))

    def test_evidence_builder_binds_revision_changed_files_and_workflow_classes(self) -> None:
        for case in self.fixture["cases"]:
            with self.subTest(sample_id=case["sample_id"]):
                evidence = self.evidence(case)
                self.assertEqual(evidence["source_revision"], "git:" + case["source_revision"])
                self.assertEqual(evidence["workflow_count"], 1)
                self.assertEqual(evidence["workflows"][0]["path"], case["workflow_path"])
                self.assertEqual(
                    evidence["workflows"][0]["classification"],
                    case["expected_classification"],
                )

    def test_evidence_builder_rejects_missing_workflow_section(self) -> None:
        case = self.cases["RW-54"]
        with self.assertRaisesRegex(ValueError, "missing changed workflow sections"):
            build_workflow_diff_evidence(
                source_revision=case["source_revision"],
                source_evidence_sha256=case["source_evidence_sha256"],
                changed_files=case["changed_files"],
                diff_text="diff --git a/package.json b/package.json\n+{}\n",
            )

    def test_bridge_rejects_revision_and_changed_file_drift(self) -> None:
        case = self.cases["RW-54"]
        evidence = self.evidence(case)
        baseline = next(item for item in self.baseline["samples"] if item["sample_id"] == "RW-54")
        profile = self.profiles[baseline["profile_basis"]]
        request = {
            "source_revision": "f" * 40,
            "task_class": baseline["task_class"],
            "changed_files": baseline["changed_files"],
        }
        with self.assertRaisesRegex(ValueError, "source_revision mismatch"):
            project_candidate_risk(request, profile, workflow_evidence=evidence)

        request["source_revision"] = case["source_revision"]
        request["changed_files"] = [*baseline["changed_files"], "src/unexpected.ts"]
        with self.assertRaisesRegex(ValueError, "changed_files_sha256 mismatch"):
            project_candidate_risk(request, profile, workflow_evidence=evidence)

    def test_diff_tamper_changes_bound_evidence_identity(self) -> None:
        case = self.cases["RW-54"]
        original = self.evidence(case)
        tampered = build_workflow_diff_evidence(
            source_revision=case["source_revision"],
            source_evidence_sha256=case["source_evidence_sha256"],
            changed_files=case["changed_files"],
            diff_text=case["diff_text"] + "\n",
        )
        self.assertNotEqual(original["diff_sha256"], tampered["diff_sha256"])
        self.assertNotEqual(original["evidence_sha256"], tampered["evidence_sha256"])

    def test_seen_semantic_cases_have_expected_candidate_bands(self) -> None:
        baseline_by_id = {item["sample_id"]: item for item in self.baseline["samples"]}
        for sample_id, case in self.cases.items():
            with self.subTest(sample_id=sample_id):
                baseline = baseline_by_id[sample_id]
                request = {
                    "source_revision": case["source_revision"],
                    "task_class": baseline["task_class"],
                    "changed_files": baseline["changed_files"],
                }
                result = project_candidate_risk(
                    request,
                    self.profiles[baseline["profile_basis"]],
                    workflow_evidence=self.evidence(case),
                )
                self.assertTrue(result["workflow_semantics_applied"])
                self.assertEqual(
                    result["risk"]["effective_band"],
                    case["expected_candidate_effective_band"],
                )

        self.assertEqual(
            self.cases["RW-54"]["expected_candidate_effective_band"],
            "R2",
        )
        self.assertEqual(
            self.cases["KB-269"]["expected_candidate_effective_band"],
            "R3",
        )
        self.assertEqual(
            self.cases["KB-275"]["expected_candidate_effective_band"],
            "R3",
        )

    def test_non_semantic_seen_samples_remain_exactly_pre_promotion_projection(self) -> None:
        for item in self.baseline["samples"]:
            if item["sample_id"] in self.cases:
                continue
            with self.subTest(sample_id=item["sample_id"]):
                request = {
                    "task_class": item["task_class"],
                    "changed_files": item["changed_files"],
                }
                profile = self.profiles[item["profile_basis"]]
                baseline = _risk_projection(request, profile, risk_model_version=None)
                candidate = project_candidate_risk(request, profile)
                self.assertFalse(candidate["workflow_semantics_applied"])
                self.assertEqual(candidate["risk"], baseline)

    def test_seen_candidate_replay_reaches_23_of_23_acceptable_without_underclassification(self) -> None:
        observed: dict[str, str] = {}
        acceptable = 0
        exact = 0
        under: list[str] = []
        for item in self.baseline["samples"]:
            case = self.cases.get(item["sample_id"])
            request = {
                "task_class": item["task_class"],
                "changed_files": item["changed_files"],
            }
            if case is not None:
                request["source_revision"] = case["source_revision"]
            result = project_candidate_risk(
                request,
                self.profiles[item["profile_basis"]],
                workflow_evidence=None if case is None else self.evidence(case),
            )
            band = result["risk"]["effective_band"]
            observed[item["sample_id"]] = band
            acceptable += int(band in item["acceptable_bands"])
            exact += int(band == item["expected_band"])
            if BAND_ORDER[band] < BAND_ORDER[item["expected_band"]]:
                under.append(item["sample_id"])

        self.assertEqual(len(observed), 23)
        self.assertEqual(acceptable, 23)
        self.assertEqual(exact, 22)
        self.assertEqual(under, [])
        self.assertEqual(observed["RW-54"], "R2")
        self.assertEqual(observed["KB-269"], "R3")
        self.assertEqual(observed["KB-275"], "R3")


if __name__ == "__main__":
    unittest.main()

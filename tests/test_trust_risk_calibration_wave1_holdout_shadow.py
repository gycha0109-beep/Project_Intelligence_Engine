from __future__ import annotations

import json
from pathlib import Path
import unittest

from review_system.trust import _profile_descriptor, _risk_projection
from review_system.trust_workflow_bridge import project_candidate_risk
from review_system.workflow_semantics import build_workflow_diff_evidence


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
PREDICTIONS = FIXTURE_DIR / "wave1-holdout-shadow-predictions.json"
SPLIT = FIXTURE_DIR / "wave1-split.json"

PROFILE_PATHS = {
    "buildmap": ROOT / "profiles" / "examples" / "buildmap.yml",
    "bejewely": ROOT / "profiles" / "examples" / "bejewely.yml",
    "generic-webapp": ROOT / "profiles" / "examples" / "generic-webapp.yml",
}

FORBIDDEN_LABEL_FIELDS = {
    "expected_band",
    "acceptable_bands",
    "confidence",
    "semantic_classes",
    "rationale",
    "acceptable_band_match",
    "exact_expected_match",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_label_free(test: unittest.TestCase, value: object) -> None:
    if isinstance(value, dict):
        test.assertTrue(FORBIDDEN_LABEL_FIELDS.isdisjoint(value))
        for child in value.values():
            _assert_label_free(test, child)
    elif isinstance(value, list):
        for child in value:
            _assert_label_free(test, child)


def _workflow_evidence(item: dict) -> dict | None:
    semantics = item["workflow_semantics"]
    if not semantics:
        return None

    source_hashes = {entry["source_evidence_sha256"] for entry in semantics}
    if len(source_hashes) != 1:
        raise AssertionError("workflow semantics must share one source evidence hash")

    sections: list[str] = []
    for entry in semantics:
        path = entry["path"]
        patch = entry["patch"]
        sections.append(
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            f"{patch}\n"
        )
    return build_workflow_diff_evidence(
        source_revision=item["frozen_head_sha"],
        source_evidence_sha256=next(iter(source_hashes)),
        changed_files=item["changed_files"],
        diff_text="".join(sections),
    )


class TrustRiskCalibrationWave1HoldoutShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.predictions = load_json(PREDICTIONS)
        cls.split = load_json(SPLIT)
        cls.profiles = {
            key: _profile_descriptor(path)[1]
            for key, path in PROFILE_PATHS.items()
        }

    def test_artifact_is_prediction_only_and_labels_remain_unopened(self) -> None:
        self.assertEqual(
            self.predictions["artifact_kind"],
            "BLIND_HOLDOUT_PREDICTIONS_ONLY",
        )
        self.assertEqual(
            self.predictions["prediction_status"],
            "PREDICTIONS_FROZEN_BEFORE_LABEL_OPEN",
        )
        self.assertFalse(
            self.predictions["authority"]["labels_opened_for_this_replay"]
        )
        _assert_label_free(self, self.predictions)

    def test_scope_is_exact_frozen_holdout(self) -> None:
        sample_ids = [item["sample_id"] for item in self.predictions["predictions"]]
        self.assertEqual(len(sample_ids), 11)
        self.assertEqual(set(sample_ids), set(self.split["frozen_holdout"]))
        self.assertEqual(len(sample_ids), len(set(sample_ids)))
        self.assertTrue(set(sample_ids).isdisjoint(self.split["calibration_seen"]))
        self.assertTrue(set(sample_ids).isdisjoint(self.split["seen_validation"]))
        self.assertTrue(set(sample_ids).isdisjoint(self.split["external_seen_probe"]))

    def test_all_observed_heads_match_frozen_heads(self) -> None:
        for item in self.predictions["predictions"]:
            with self.subTest(sample_id=item["sample_id"]):
                self.assertTrue(item["head_match"])
                self.assertEqual(
                    item["observed_current_head_sha"],
                    item["frozen_head_sha"],
                )

    def test_pre_promotion_authoritative_predictions_recompute_from_legacy_model(self) -> None:
        for item in self.predictions["predictions"]:
            with self.subTest(sample_id=item["sample_id"]):
                request = {
                    "source_revision": "git:" + item["frozen_head_sha"],
                    "task_class": item["task_class"],
                    "changed_files": item["changed_files"],
                }
                projection = _risk_projection(
                    request,
                    self.profiles[item["profile_basis"]],
                    risk_model_version=None,
                )
                self.assertEqual(
                    projection["effective_band"],
                    item["authoritative_band_prediction"],
                )

    def test_workflow_classifications_recompute_from_frozen_patches(self) -> None:
        for item in self.predictions["predictions"]:
            evidence = _workflow_evidence(item)
            if evidence is None:
                self.assertEqual(item["workflow_semantics"], [])
                continue
            observed = {
                entry["path"]: entry["classification"]
                for entry in evidence["workflows"]
            }
            expected = {
                entry["path"]: entry["classification_prediction"]
                for entry in item["workflow_semantics"]
            }
            self.assertEqual(observed, expected)

    def test_candidate_predictions_recompute_from_current_bridge(self) -> None:
        for item in self.predictions["predictions"]:
            with self.subTest(sample_id=item["sample_id"]):
                request = {
                    "source_revision": "git:" + item["frozen_head_sha"],
                    "task_class": item["task_class"],
                    "changed_files": item["changed_files"],
                }
                result = project_candidate_risk(
                    request,
                    self.profiles[item["profile_basis"]],
                    workflow_evidence=_workflow_evidence(item),
                )
                self.assertEqual(
                    result["risk"]["effective_band"],
                    item["candidate_band_prediction"],
                )

    def test_only_rw57_changes_band_in_blind_predictions(self) -> None:
        changed = [
            item["sample_id"]
            for item in self.predictions["predictions"]
            if item["authoritative_band_prediction"]
            != item["candidate_band_prediction"]
        ]
        self.assertEqual(changed, ["RW-57"])
        rw57 = next(
            item
            for item in self.predictions["predictions"]
            if item["sample_id"] == "RW-57"
        )
        self.assertEqual(rw57["authoritative_band_prediction"], "R3")
        self.assertEqual(rw57["candidate_band_prediction"], "R2")


if __name__ == "__main__":
    unittest.main()
from __future__ import annotations

import json
from pathlib import Path
import unittest

from review_system.trust import _profile_descriptor, _risk_projection


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
BASELINE = FIXTURE_DIR / "wave1-seen-baseline.json"
SPLIT = FIXTURE_DIR / "wave1-split.json"
LABELS = FIXTURE_DIR / "wave1-labels.json"

PROFILE_PATHS = {
    "buildmap": ROOT / "profiles" / "examples" / "buildmap.yml",
    "bejewely": ROOT / "profiles" / "examples" / "bejewely.yml",
    "generic-webapp": ROOT / "profiles" / "examples" / "generic-webapp.yml",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TrustRiskCalibrationWave1SeenBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load_json(BASELINE)
        cls.split = load_json(SPLIT)
        cls.labels = load_json(LABELS)
        cls.label_map = {
            item[0]: {
                "expected_band": item[1],
                "acceptable_bands": item[2],
            }
            for item in cls.labels["labels"]
        }
        cls.profiles = {
            key: _profile_descriptor(path)[1]
            for key, path in PROFILE_PATHS.items()
        }

    def test_seen_only_scope_does_not_replay_holdout(self) -> None:
        sample_ids = {item["sample_id"] for item in self.baseline["samples"]}
        expected_seen = set(self.split["calibration_seen"]) | set(self.split["seen_validation"])
        self.assertEqual(sample_ids, expected_seen)
        self.assertEqual(len(sample_ids), 23)
        self.assertTrue(sample_ids.isdisjoint(self.split["frozen_holdout"]))
        self.assertTrue(sample_ids.isdisjoint(self.split["external_seen_probe"]))
        self.assertFalse(self.baseline["scope"]["frozen_holdout_replayed"])
        self.assertFalse(self.baseline["scope"]["external_seen_probe_replayed"])

    def test_authority_is_pinned_to_wave1a_main(self) -> None:
        self.assertEqual(
            self.baseline["pie_authority"]["main_sha"],
            "96b053f63a25465a4e75e58d755a62462b20ee68",
        )
        self.assertEqual(
            self.baseline["pie_authority"]["tree_sha"],
            "478e938fafa800d410ca9bf25b45ee03a1557967",
        )
        self.assertEqual(
            self.baseline["freeze_dependency"]["commit_sha"],
            "c599f53f12bb9e8218b472752b3a8039f48413fb",
        )

    def test_frozen_human_labels_are_not_rewritten(self) -> None:
        for item in self.baseline["samples"]:
            frozen = self.label_map[item["sample_id"]]
            self.assertEqual(item["expected_band"], frozen["expected_band"])
            self.assertEqual(item["acceptable_bands"], frozen["acceptable_bands"])

    def test_exact_current_risk_projection_matches_frozen_baseline(self) -> None:
        for item in self.baseline["samples"]:
            with self.subTest(sample_id=item["sample_id"]):
                request = {
                    "task_class": item["task_class"],
                    "changed_files": item["changed_files"],
                }
                projection = _risk_projection(
                    request,
                    self.profiles[item["profile_basis"]],
                )
                self.assertEqual(
                    projection["path_floor_band"],
                    item["observed_path_floor_band"],
                )
                self.assertEqual(
                    projection["effective_band"],
                    item["observed_effective_band"],
                )

    def test_summary_metrics_are_reproducible(self) -> None:
        exact = sum(item["exact_expected_match"] for item in self.baseline["samples"])
        acceptable = sum(item["acceptable_band_match"] for item in self.baseline["samples"])
        self.assertEqual(exact, 21)
        self.assertEqual(acceptable, 22)
        self.assertEqual(
            self.baseline["summary"]["unacceptable_mismatches"],
            ["RW-54"],
        )
        self.assertEqual(
            self.baseline["summary"]["boundary_acceptable_mismatches"],
            ["KB-275"],
        )

    def test_no_underclassification_in_seen_baseline(self) -> None:
        order = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
        under = [
            item["sample_id"]
            for item in self.baseline["samples"]
            if order[item["observed_effective_band"]] < order[item["expected_band"]]
        ]
        self.assertEqual(under, [])

    def test_rw54_is_workflow_floor_false_positive(self) -> None:
        item = next(item for item in self.baseline["samples"] if item["sample_id"] == "RW-54")
        self.assertEqual(item["task_class"], "routine_code")
        self.assertEqual(item["expected_band"], "R2")
        self.assertEqual(item["acceptable_bands"], ["R2"])
        self.assertEqual(item["observed_path_floor_band"], "R3")
        self.assertEqual(item["observed_effective_band"], "R3")
        self.assertEqual(item["max_path_floor_contributors"], [".github/workflows/ci.yml"])

    def test_kb275_remains_a_frozen_boundary_case(self) -> None:
        item = next(item for item in self.baseline["samples"] if item["sample_id"] == "KB-275")
        self.assertEqual(item["expected_band"], "R2")
        self.assertEqual(item["acceptable_bands"], ["R2", "R3"])
        self.assertEqual(item["observed_effective_band"], "R3")
        self.assertTrue(item["acceptable_band_match"])


if __name__ == "__main__":
    unittest.main()

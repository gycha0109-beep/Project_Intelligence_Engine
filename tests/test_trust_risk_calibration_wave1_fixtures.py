from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "trust-risk-calibration"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TrustRiskCalibrationWave1FixtureTests(unittest.TestCase):
    def setUp(self):
        self.corpus = load("wave1-corpus.json")
        self.labels = load("wave1-labels.json")
        self.split = load("wave1-split.json")
        sample_fields = self.corpus["sample_fields"]
        label_fields = self.labels["label_fields"]
        self.samples = {
            item["sample_id"]: item
            for item in (dict(zip(sample_fields, row)) for row in self.corpus["samples"])
        }
        self.label_map = {
            item["sample_id"]: item
            for item in (dict(zip(label_fields, row)) for row in self.labels["labels"])
        }

    def test_raw_inventory_is_frozen_to_original_69_pr_snapshot(self):
        expected = {
            "BM": ([42, 67], 26),
            "AR": ([30, 33], 4),
            "RW": ([41, 60], 20),
            "MV": ([3, 3], 1),
            "KB": ([262, 279], 18),
        }
        actual = {
            item["repository_key"]: (item["range"], item["count"])
            for item in self.corpus["raw_inventory"]
        }
        self.assertEqual(expected, actual)
        self.assertEqual(69, self.corpus["raw_total"])
        self.assertEqual(69, sum(item["count"] for item in self.corpus["raw_inventory"]))
        self.assertEqual("2026-08-21T03:00:00Z", self.corpus["source_window"]["created_at_end_exclusive"])

    def test_pie_authority_is_pinned(self):
        self.assertEqual(
            "96b053f63a25465a4e75e58d755a62462b20ee68",
            self.corpus["pie_authority"]["main_sha"],
        )
        self.assertEqual(
            "478e938fafa800d410ca9bf25b45ee03a1557967",
            self.corpus["pie_authority"]["tree_sha"],
        )

    def test_partition_membership_is_disjoint_and_fully_labeled(self):
        names = ("calibration_seen", "seen_validation", "frozen_holdout", "external_seen_probe")
        groups = {name: set(self.split[name]) for name in names}
        for left, right in ((a, b) for index, a in enumerate(names) for b in names[index + 1 :]):
            self.assertTrue(groups[left].isdisjoint(groups[right]), f"{left} overlaps {right}")
        union = set().union(*groups.values())
        self.assertEqual(set(self.label_map), union)
        self.assertEqual(set(self.samples), union)

    def test_frozen_holdout_has_no_lifecycle_leakage(self):
        holdout = set(self.split["frozen_holdout"])
        non_holdout = set(self.samples) - holdout
        holdout_clusters = {self.samples[sid]["lifecycle_cluster_id"] for sid in holdout}
        non_holdout_clusters = {self.samples[sid]["lifecycle_cluster_id"] for sid in non_holdout}
        self.assertTrue(holdout_clusters.isdisjoint(non_holdout_clusters))
        self.assertTrue(
            all(self.samples[sid]["exposure_status"] == "FROZEN_UNREPLAYED" for sid in holdout)
        )

    def test_holdout_band_coverage_and_r4_limitation_are_explicit(self):
        bands = Counter(self.label_map[sid]["expected_band"] for sid in self.split["frozen_holdout"])
        self.assertEqual(Counter({"R1": 6, "R2": 3, "R3": 2}), bands)
        self.assertEqual(0, bands["R4"])
        limitation = " ".join(self.split["holdout_limitations"])
        self.assertIn("no independent R4 sample", limitation)
        self.assertIn("must not claim blind R4 generalization", limitation)

    def test_labels_contain_only_priors_not_pie_outputs(self):
        forbidden = {
            "pie_result",
            "effective_band",
            "path_floor_band",
            "corroborated_semantic_floor_band",
            "selected_review_packs",
            "task_class_underdeclared",
            "hard_gates",
        }

        def walk(value):
            if isinstance(value, dict):
                self.assertTrue(forbidden.isdisjoint(value))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(self.labels)
        self.assertEqual(
            "HUMAN_PRIOR_FROZEN_BEFORE_HOLDOUT_REPLAY",
            self.labels["label_authority"],
        )

    def test_sample_revisions_are_exactly_pinned(self):
        sha = re.compile(r"^[0-9a-f]{40}$")
        for sample in self.samples.values():
            self.assertRegex(sample["base_sha"], sha)
            self.assertRegex(sample["head_sha"], sha)

    def test_revision_drifted_buildmap_pr67_is_not_scored(self):
        excluded = {item["sample_id"] for item in self.split["excluded_from_scoring"]}
        self.assertIn("BM-67", excluded)
        self.assertNotIn("BM-67", self.samples)
        self.assertNotIn("BM-67", self.label_map)


if __name__ == "__main__":
    unittest.main()

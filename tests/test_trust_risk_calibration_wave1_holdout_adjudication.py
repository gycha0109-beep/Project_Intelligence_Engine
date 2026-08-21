from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
ADJUDICATION = FIXTURE_DIR / "wave1-holdout-adjudication.json"
PREDICTIONS = FIXTURE_DIR / "wave1-holdout-shadow-predictions.json"
LABELS = FIXTURE_DIR / "wave1-labels.json"
SPLIT = FIXTURE_DIR / "wave1-split.json"
BAND_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def label_map(labels: dict) -> dict[str, dict]:
    fields = labels["label_fields"]
    return {
        row[0]: dict(zip(fields, row, strict=True))
        for row in labels["labels"]
    }


class TrustRiskCalibrationWave1HoldoutAdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adjudication = load_json(ADJUDICATION)
        cls.predictions = load_json(PREDICTIONS)
        cls.labels = load_json(LABELS)
        cls.split = load_json(SPLIT)
        cls.labels_by_id = label_map(cls.labels)
        cls.predictions_by_id = {
            item["sample_id"]: item
            for item in cls.predictions["predictions"]
        }
        cls.samples_by_id = {
            item["sample_id"]: item
            for item in cls.adjudication["samples"]
        }

    def test_label_open_gate_is_bound_to_successful_prediction_freeze(self) -> None:
        authority = self.adjudication["authority"]
        self.assertEqual(
            authority["prediction_head_sha"],
            "c9aa348edd617b34f07d37d4bcfdaf448750be08",
        )
        self.assertEqual(authority["prediction_ci_run_number"], 1154)
        self.assertEqual(authority["prediction_ci_conclusion"], "success")
        self.assertTrue(authority["labels_opened_only_after_prediction_ci_success"])
        self.assertFalse(
            self.predictions["authority"]["labels_opened_for_this_replay"]
        )

    def test_scope_is_exact_frozen_holdout(self) -> None:
        expected = set(self.split["frozen_holdout"])
        self.assertEqual(len(expected), 11)
        self.assertEqual(set(self.samples_by_id), expected)
        self.assertEqual(set(self.predictions_by_id), expected)

    def test_adjudication_rows_are_derived_from_frozen_predictions_and_labels(self) -> None:
        for sample_id, observed in self.samples_by_id.items():
            with self.subTest(sample_id=sample_id):
                prediction = self.predictions_by_id[sample_id]
                label = self.labels_by_id[sample_id]
                self.assertEqual(observed["expected_band"], label["expected_band"])
                self.assertEqual(observed["acceptable_bands"], label["acceptable_bands"])
                self.assertEqual(observed["confidence"], label["confidence"])
                self.assertEqual(
                    observed["authoritative_band"],
                    prediction["authoritative_band_prediction"],
                )
                self.assertEqual(
                    observed["candidate_band"],
                    prediction["candidate_band_prediction"],
                )
                self.assertEqual(
                    observed["authoritative_exact_match"],
                    observed["authoritative_band"] == observed["expected_band"],
                )
                self.assertEqual(
                    observed["candidate_exact_match"],
                    observed["candidate_band"] == observed["expected_band"],
                )
                self.assertEqual(
                    observed["candidate_acceptable_match"],
                    observed["candidate_band"] in observed["acceptable_bands"],
                )

    def test_summary_recomputes_exactly(self) -> None:
        rows = list(self.samples_by_id.values())
        authoritative_exact = sum(row["authoritative_exact_match"] for row in rows)
        candidate_exact = sum(row["candidate_exact_match"] for row in rows)
        authoritative_acceptable = sum(
            row["authoritative_band"] in row["acceptable_bands"]
            for row in rows
        )
        candidate_acceptable = sum(row["candidate_acceptable_match"] for row in rows)
        authoritative_under = sum(
            BAND_ORDER[row["authoritative_band"]] < BAND_ORDER[row["expected_band"]]
            for row in rows
        )
        candidate_under = sum(
            BAND_ORDER[row["candidate_band"]] < BAND_ORDER[row["expected_band"]]
            for row in rows
        )
        authoritative_over = sum(
            BAND_ORDER[row["authoritative_band"]] > BAND_ORDER[row["expected_band"]]
            for row in rows
        )
        candidate_over = sum(
            BAND_ORDER[row["candidate_band"]] > BAND_ORDER[row["expected_band"]]
            for row in rows
        )

        summary = self.adjudication["summary"]
        self.assertEqual(authoritative_exact, summary["authoritative"]["exact_expected_matches"])
        self.assertEqual(authoritative_acceptable, summary["authoritative"]["acceptable_band_matches"])
        self.assertEqual(authoritative_under, summary["authoritative"]["underclassifications"])
        self.assertEqual(authoritative_over, summary["authoritative"]["overclassifications_vs_expected"])
        self.assertEqual(candidate_exact, summary["candidate"]["exact_expected_matches"])
        self.assertEqual(candidate_acceptable, summary["candidate"]["acceptable_band_matches"])
        self.assertEqual(candidate_under, summary["candidate"]["underclassifications"])
        self.assertEqual(candidate_over, summary["candidate"]["overclassifications_vs_expected"])
        self.assertEqual(candidate_exact - authoritative_exact, summary["delta"]["exact_expected_matches"])
        self.assertEqual(candidate_acceptable - authoritative_acceptable, summary["delta"]["acceptable_band_matches"])
        self.assertEqual(candidate_under - authoritative_under, summary["delta"]["underclassifications"])
        self.assertEqual(candidate_over - authoritative_over, summary["delta"]["overclassifications_vs_expected"])

    def test_d1_workflow_scope_is_exact_without_underclassification(self) -> None:
        d1_ids = self.adjudication["scope"]["d1_workflow_bearing_samples"]
        self.assertEqual(d1_ids, ["RW-43", "RW-46", "RW-57"])
        for sample_id in d1_ids:
            row = self.samples_by_id[sample_id]
            with self.subTest(sample_id=sample_id):
                self.assertTrue(row["candidate_exact_match"])
                self.assertGreaterEqual(
                    BAND_ORDER[row["candidate_band"]],
                    BAND_ORDER[row["expected_band"]],
                )
        self.assertEqual(
            self.adjudication["summary"]["d1_workflow_scope"]["result"],
            "PASS_FOR_WORKFLOW_SEMANTIC_SCOPE",
        )

    def test_only_remaining_candidate_mismatch_is_kb274(self) -> None:
        mismatches = [
            row["sample_id"]
            for row in self.adjudication["samples"]
            if not row["candidate_acceptable_match"]
        ]
        self.assertEqual(mismatches, ["KB-274"])
        defect = self.adjudication["defects"][0]
        self.assertEqual(
            defect["defect_id"],
            "DOCUMENTATION_HIGH_RISK_FILENAME_TOKEN_COLLISION",
        )
        self.assertEqual(defect["sample_ids"], ["KB-274"])
        self.assertFalse(defect["d1_related"])
        self.assertFalse(defect["remediation_in_this_artifact"])

    def test_holdout_does_not_claim_blind_r4_generalization(self) -> None:
        self.assertEqual(self.adjudication["scope"]["r4_holdout_sample_count"], 0)
        self.assertTrue(
            any("no independent R4 sample" in item for item in self.adjudication["limits"])
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "prospective-pr.yml"


class CalibrationTrustSupplyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_calibration_artifact_includes_future_live_supply_sidecar(self):
        text = self.text
        self.assertIn("from review_system.calibration_trust_supply import (", text)
        self.assertIn("build_calibration_trust_supply_sidecar", text)
        self.assertIn("write_calibration_trust_supply_sidecar", text)
        self.assertIn('bundle / "operational" / "trust-facts-supply.json"', text)
        self.assertIn("EVIDENCE_HASH_MISMATCH: operational Trust supply observation is missing", text)
        self.assertIn("write_calibration_record(calibration_staging, calibration_record)", text)
        self.assertIn("write_calibration_trust_supply_sidecar(", text)
        self.assertIn("calibration_staging,", text)

    def test_sidecar_does_not_replace_or_mutate_calibration_v1_surface(self):
        text = self.text
        self.assertIn("PIE_CALIBRATION_RECORD_V1", text)
        self.assertIn('calibration_record["calibration_key_sha256"]', text)
        self.assertIn('calibration_record["record_sha256"]', text)
        self.assertIn("calibration_artifact_name(calibration_record)", text)
        self.assertNotIn("historical Trust supply", text)
        self.assertNotIn("backfill Trust supply", text)


if __name__ == "__main__":
    unittest.main()

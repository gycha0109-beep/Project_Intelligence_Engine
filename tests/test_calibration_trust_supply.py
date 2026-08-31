from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.calibration_observation import build_calibration_record
from review_system.calibration_trust_supply import (
    CONTRACT_VERSION,
    CalibrationTrustSupplyError,
    build_calibration_trust_supply_sidecar,
    verify_calibration_trust_supply_sidecar,
    write_calibration_trust_supply_sidecar,
)
from review_system.operational_trust_supply import build_operational_trust_supply_observation


HEAD = "a" * 40
PIE = "b" * 40
INTERFACE = "d" * 64


def _record() -> dict:
    return build_calibration_record(
        repository="gycha0109-beep/BuildMap",
        pull_request=87,
        source_revision=HEAD,
        pie_revision=PIE,
        execution_id="exec-1",
        workflow_run_id="33429986237",
        workflow_run_attempt=1,
        interface={
            "signal": {
                "contract_version": "PIE_SIGNAL_V1",
                "status": "CLEAR",
                "reason": "NO_POLICY_MATCH",
                "match_status": "NO_POLICY_MATCH",
                "next": "NONE",
            },
            "brief": None,
            "targeted_evidence_ids": [],
            "targeted_evidence": {},
            "interface_sha256": INTERFACE,
        },
    )


def _absent_observation() -> dict:
    return build_operational_trust_supply_observation(
        operational_policy_requested=True,
        explicit_input_declared=False,
        explicit_input_available=False,
        operational_binding={
            "status": "CLEAR",
            "match_status": "NO_POLICY_MATCH",
            "facts": {"supplied": False, "facts_sha256": None},
        },
    )


class CalibrationTrustSupplyTests(unittest.TestCase):
    def test_builds_future_live_sidecar_without_mutating_calibration_v1(self):
        record = _record()
        original_record_hash = record["record_sha256"]
        sidecar = build_calibration_trust_supply_sidecar(
            calibration_record=record,
            trust_supply_observation=_absent_observation(),
        )

        self.assertEqual(CONTRACT_VERSION, sidecar["contract_version"])
        self.assertEqual(record["identity"], sidecar["identity"])
        self.assertEqual(record["calibration_key_sha256"], sidecar["calibration_key_sha256"])
        self.assertEqual(record["semantic_sha256"], sidecar["calibration_semantic_sha256"])
        self.assertEqual("EXPLICIT_INPUT_ABSENT", sidecar["supply"]["status"])
        self.assertEqual("EXPLICIT_INPUT_ONLY", sidecar["supply"]["producer_mode"])
        self.assertFalse(sidecar["supply"]["binder"]["facts_consumed"])
        self.assertIsNone(sidecar["supply"]["binder"]["facts_sha256"])
        self.assertTrue(sidecar["authority"]["calibration_only"])
        self.assertFalse(sidecar["authority"]["trust_fact_inferred"])
        self.assertFalse(sidecar["authority"]["human_review_inferred"])
        self.assertFalse(sidecar["authority"]["outcome_inferred"])
        self.assertFalse(sidecar["authority"]["merge_authorized"])
        self.assertFalse(sidecar["authority"]["deploy_authorized"])
        self.assertFalse(sidecar["authority"]["production_effect_authorized"])
        self.assertEqual([], verify_calibration_trust_supply_sidecar(sidecar))
        self.assertEqual(original_record_hash, record["record_sha256"])

    def test_consumed_explicit_input_is_projected_without_creating_authority(self):
        facts_sha = "c" * 64
        observation = build_operational_trust_supply_observation(
            operational_policy_requested=True,
            explicit_input_declared=True,
            explicit_input_available=True,
            operational_binding={
                "status": "ACTION_REQUIRED",
                "match_status": "UNIQUE_POLICY_MATCH",
                "facts": {"supplied": True, "facts_sha256": facts_sha},
            },
        )
        sidecar = build_calibration_trust_supply_sidecar(
            calibration_record=_record(),
            trust_supply_observation=observation,
        )
        self.assertEqual("EXPLICIT_INPUT_VALIDATED_AND_CONSUMED", sidecar["supply"]["status"])
        self.assertTrue(sidecar["supply"]["binder"]["facts_consumed"])
        self.assertEqual(facts_sha, sidecar["supply"]["binder"]["facts_sha256"])
        self.assertFalse(sidecar["authority"]["trust_fact_inferred"])

    def test_rejects_invalid_source_observation(self):
        observation = _absent_observation()
        observation["trust_fact_inferred"] = True
        with self.assertRaisesRegex(CalibrationTrustSupplyError, "trust_fact_inferred"):
            build_calibration_trust_supply_sidecar(
                calibration_record=_record(),
                trust_supply_observation=observation,
            )

    def test_tampered_sidecar_authority_is_rejected(self):
        sidecar = build_calibration_trust_supply_sidecar(
            calibration_record=_record(),
            trust_supply_observation=_absent_observation(),
        )
        sidecar["authority"]["merge_authorized"] = True
        errors = verify_calibration_trust_supply_sidecar(sidecar)
        self.assertIn("authority boundary must remain calibration-only and explicitly false", errors)

    def test_writer_materializes_sidecar_next_to_calibration_record(self):
        sidecar = build_calibration_trust_supply_sidecar(
            calibration_record=_record(),
            trust_supply_observation=_absent_observation(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = write_calibration_trust_supply_sidecar(tmp, sidecar)
            self.assertEqual(Path(tmp).resolve() / "trust-facts-supply.json", path)
            self.assertEqual(sidecar, json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()

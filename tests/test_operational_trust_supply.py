from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from review_system.operational_trust_supply import (
    build_operational_trust_supply_observation,
    verify_operational_trust_supply_observation,
    write_operational_trust_supply_observation,
)


class OperationalTrustSupplyObservationTests(unittest.TestCase):
    def test_policy_disabled_is_observational_only(self):
        value = build_operational_trust_supply_observation(
            operational_policy_requested=False,
            explicit_input_declared=False,
            explicit_input_available=False,
            operational_binding=None,
        )
        self.assertEqual("PIE_OPERATIONAL_TRUST_FACTS_SUPPLY_V1", value["contract_version"])
        self.assertEqual("POLICY_DISABLED", value["status"])
        self.assertEqual("EXPLICIT_INPUT_ONLY", value["producer_mode"])
        self.assertFalse(value["binder"]["facts_consumed"])
        self.assertIsNone(value["binder"]["facts_sha256"])
        self.assertFalse(value["trust_fact_inferred"])
        self.assertFalse(value["human_review_inferred"])
        self.assertFalse(value["outcome_inferred"])
        self.assertFalse(value["merge_authorized"])
        self.assertFalse(value["deploy_authorized"])
        self.assertFalse(value["production_effect_authorized"])
        self.assertEqual([], verify_operational_trust_supply_observation(value))

    def test_absent_explicit_input_is_recorded_without_inference(self):
        binding = {
            "status": "MISSING_TRUST_FIELDS",
            "match_status": "UNIQUE_POLICY_MATCH",
            "facts": {"supplied": False, "facts_sha256": None},
        }
        value = build_operational_trust_supply_observation(
            operational_policy_requested=True,
            explicit_input_declared=False,
            explicit_input_available=False,
            operational_binding=binding,
        )
        self.assertEqual("EXPLICIT_INPUT_ABSENT", value["status"])
        self.assertTrue(value["binder"]["attempted"])
        self.assertEqual("UNIQUE_POLICY_MATCH", value["binder"]["match_status"])
        self.assertFalse(value["binder"]["facts_consumed"])
        self.assertEqual([], verify_operational_trust_supply_observation(value))

    def test_present_input_can_be_unconsumed_on_fail_closed_ambiguity(self):
        binding = {
            "status": "AMBIGUOUS_POLICY_MATCH",
            "match_status": "AMBIGUOUS_POLICY_MATCH",
            "facts": {"supplied": False, "facts_sha256": None},
        }
        value = build_operational_trust_supply_observation(
            operational_policy_requested=True,
            explicit_input_declared=True,
            explicit_input_available=True,
            operational_binding=binding,
        )
        self.assertEqual("EXPLICIT_INPUT_PRESENT_NOT_CONSUMED", value["status"])
        self.assertFalse(value["binder"]["facts_consumed"])
        self.assertIsNone(value["binder"]["facts_sha256"])
        self.assertEqual([], verify_operational_trust_supply_observation(value))

    def test_validated_input_records_existing_canonical_hash_only(self):
        binding = {
            "status": "TRUST_REQUEST_MATERIALIZED",
            "match_status": "UNIQUE_POLICY_MATCH",
            "facts": {"supplied": True, "facts_sha256": "a" * 64},
        }
        value = build_operational_trust_supply_observation(
            operational_policy_requested=True,
            explicit_input_declared=True,
            explicit_input_available=True,
            operational_binding=binding,
        )
        self.assertEqual("EXPLICIT_INPUT_VALIDATED_AND_CONSUMED", value["status"])
        self.assertTrue(value["binder"]["facts_consumed"])
        self.assertEqual("a" * 64, value["binder"]["facts_sha256"])
        self.assertFalse(value["trust_fact_inferred"])
        self.assertEqual([], verify_operational_trust_supply_observation(value))

    def test_writer_rejects_authority_widening(self):
        value = build_operational_trust_supply_observation(
            operational_policy_requested=True,
            explicit_input_declared=False,
            explicit_input_available=False,
            operational_binding={
                "status": "MISSING_TRUST_FIELDS",
                "match_status": "UNIQUE_POLICY_MATCH",
                "facts": {"supplied": False, "facts_sha256": None},
            },
        )
        value["merge_authorized"] = True
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                write_operational_trust_supply_observation(Path(tmp) / "supply.json", value)


if __name__ == "__main__":
    unittest.main()

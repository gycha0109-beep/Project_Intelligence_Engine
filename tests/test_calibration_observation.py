from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.calibration_observation import (
    CALIBRATION_LEDGER_CONTRACT_VERSION,
    CALIBRATION_RECORD_CONTRACT_VERSION,
    CalibrationObservationError,
    build_calibration_ledger,
    build_calibration_record,
    calibration_artifact_name,
    write_calibration_record,
)


HEAD = "a" * 40
PIE = "b" * 40
INTERFACE = "d" * 64


def _interface(
    *,
    status: str = "CLEAR",
    reason: str = "NO_POLICY_MATCH",
    match_status: str | None = "NO_POLICY_MATCH",
    next_step: str = "NONE",
    level1: bool = False,
    level2: int = 0,
) -> dict:
    return {
        "signal": {
            "contract_version": "PIE_SIGNAL_V1",
            "status": status,
            "reason": reason,
            "match_status": match_status,
            "next": next_step,
        },
        "brief": {"contract_version": "PIE_OPERATIONAL_BRIEF_V1"} if level1 else None,
        "targeted_evidence_ids": [f"scenario:item-{index}" for index in range(level2)],
        "targeted_evidence": {},
        "interface_sha256": INTERFACE,
    }


def _record(
    *,
    interface: dict | None = None,
    workflow_run_id: str = "32813398689",
    workflow_run_attempt: int = 1,
    execution_id: str = "exec-1",
) -> dict:
    return build_calibration_record(
        repository="Gycha0109-Beep/BuildMap",
        pull_request=78,
        source_revision=HEAD,
        pie_revision=PIE,
        execution_id=execution_id,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
        interface=interface or _interface(),
    )


class CalibrationObservationTests(unittest.TestCase):
    def test_clear_record_is_read_only_projection_with_stable_logical_key(self):
        first = _record()
        replay = _record(
            workflow_run_id="32813399999",
            workflow_run_attempt=2,
            execution_id="exec-2",
        )
        self.assertEqual(CALIBRATION_RECORD_CONTRACT_VERSION, first["contract_version"])
        self.assertEqual("gycha0109-beep/buildmap", first["identity"]["repository"])
        self.assertEqual(INTERFACE, first["interface_sha256"])
        self.assertEqual("CLEAR", first["signal"]["status"])
        self.assertEqual("NO_POLICY_MATCH", first["signal"]["reason"])
        self.assertFalse(first["lazy_interface"]["level1_materialized"])
        self.assertEqual(0, first["lazy_interface"]["level2_item_count"])
        self.assertTrue(first["lazy_interface"]["full_capsule_separate"])
        self.assertEqual(first["calibration_key_sha256"], replay["calibration_key_sha256"])
        self.assertEqual(first["semantic_sha256"], replay["semantic_sha256"])
        self.assertNotEqual(first["record_sha256"], replay["record_sha256"])
        self.assertFalse(any(first["authority"].values()))

    def test_action_required_record_exposes_materialized_read_depth_without_inference(self):
        record = _record(
            interface=_interface(
                status="ACTION_REQUIRED",
                reason="MISSING_TRUST_FIELDS",
                match_status="UNIQUE_POLICY_MATCH",
                next_step="READ_TRUST_GAPS",
                level1=True,
                level2=7,
            )
        )
        self.assertEqual("ACTION_REQUIRED", record["signal"]["status"])
        self.assertEqual("MISSING_TRUST_FIELDS", record["signal"]["reason"])
        self.assertEqual("UNIQUE_POLICY_MATCH", record["signal"]["match_status"])
        self.assertTrue(record["lazy_interface"]["level1_materialized"])
        self.assertEqual(7, record["lazy_interface"]["level2_item_count"])
        self.assertFalse(record["authority"]["trust_fact_inferred"])
        self.assertFalse(record["authority"]["human_review_inferred"])

    def test_artifact_name_carries_bulk_inventory_dimensions_and_exact_key(self):
        record = _record(
            interface=_interface(
                status="ACTION_REQUIRED",
                reason="MISSING_TRUST_FIELDS",
                match_status="UNIQUE_POLICY_MATCH",
                next_step="READ_TRUST_GAPS",
                level1=True,
                level2=7,
            )
        )
        name = calibration_artifact_name(record)
        self.assertTrue(name.startswith(f"pie-cal-v1--k-{record['calibration_key_sha256']}"))
        self.assertIn("--s-ACTION_REQUIRED", name)
        self.assertIn("--r-MISSING_TRUST_FIELDS", name)
        self.assertIn("--m-UNIQUE_POLICY_MATCH", name)
        self.assertTrue(name.endswith("--l1-1--l2-7"))
        self.assertNotIn("/", name)
        self.assertLessEqual(len(name), 255)

    def test_artifact_name_bounds_unexpected_long_signal_tokens(self):
        record = _record(interface=_interface(reason="X" * 500, match_status="Y" * 500))
        name = calibration_artifact_name(record)
        self.assertLessEqual(len(name), 255)
        self.assertTrue(name.startswith(f"pie-cal-v1--k-{record['calibration_key_sha256']}"))
        self.assertTrue(name.endswith("--l1-0--l2-0"))

    def test_writer_materializes_single_machine_readable_record(self):
        record = _record()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_calibration_record(tmp, record)
            self.assertEqual(Path(tmp).resolve() / "calibration.json", path)
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record, written)

    def test_ledger_deduplicates_reruns_and_reports_signal_histograms(self):
        clear = _record()
        clear_rerun = _record(
            workflow_run_id="32813399999",
            workflow_run_attempt=2,
            execution_id="exec-2",
        )
        action = build_calibration_record(
            repository="gycha0109-beep/Saju",
            pull_request=142,
            source_revision="c" * 40,
            pie_revision=PIE,
            execution_id="exec-3",
            workflow_run_id="33265918058",
            workflow_run_attempt=1,
            interface=_interface(
                status="ACTION_REQUIRED",
                reason="MISSING_TRUST_FIELDS",
                match_status="UNIQUE_POLICY_MATCH",
                next_step="READ_TRUST_GAPS",
                level1=True,
                level2=7,
            ),
        )
        ledger = build_calibration_ledger([clear, clear_rerun, action])
        self.assertEqual(CALIBRATION_LEDGER_CONTRACT_VERSION, ledger["contract_version"])
        self.assertEqual(3, ledger["input_record_count"])
        self.assertEqual(2, ledger["unique_calibration_count"])
        self.assertEqual(1, ledger["duplicate_observation_count"])
        self.assertEqual({"ACTION_REQUIRED": 1, "CLEAR": 1}, ledger["histograms"]["status"])
        self.assertEqual(
            {"MISSING_TRUST_FIELDS": 1, "NO_POLICY_MATCH": 1},
            ledger["histograms"]["reason"],
        )
        self.assertEqual(1, ledger["lazy_interface"]["level1_materialized_count"])
        self.assertEqual(1, ledger["lazy_interface"]["level0_only_count"])
        self.assertEqual(7, ledger["lazy_interface"]["level2_item_total"])
        self.assertTrue(ledger["authority"]["calibration_only"])
        for field in (
            "trust_fact_inferred",
            "outcome_inferred",
            "merge_authorized",
            "deploy_authorized",
            "production_effect_authorized",
        ):
            self.assertFalse(ledger["authority"][field])

    def test_ledger_fails_closed_when_same_logical_key_changes_semantics(self):
        clear = _record()
        changed = _record(
            interface=_interface(
                status="ACTION_REQUIRED",
                reason="HUMAN_REVIEW_REQUIRED",
                match_status=None,
                next_step="READ_OPERATIONAL_BRIEF",
                level1=True,
                level2=0,
            ),
            workflow_run_id="32813399999",
            workflow_run_attempt=2,
            execution_id="exec-2",
        )
        with self.assertRaisesRegex(CalibrationObservationError, "conflicting semantic observations"):
            build_calibration_ledger([clear, changed])

    def test_tampered_semantics_are_rejected_before_aggregation(self):
        record = _record()
        record["signal"]["reason"] = "MISSING_TRUST_FIELDS"
        with self.assertRaisesRegex(CalibrationObservationError, "semantic hash"):
            build_calibration_ledger([record])

    def test_tampered_authority_is_rejected_even_with_observation_payload_present(self):
        record = _record()
        record["authority"]["merge_authorized"] = True
        with self.assertRaisesRegex(CalibrationObservationError, "authority boundary"):
            build_calibration_ledger([record])

    def test_non_signal_interface_is_rejected(self):
        interface = _interface()
        interface["signal"]["contract_version"] = "OTHER_SIGNAL"
        with self.assertRaisesRegex(CalibrationObservationError, "PIE_SIGNAL_V1"):
            _record(interface=interface)


if __name__ == "__main__":
    unittest.main()

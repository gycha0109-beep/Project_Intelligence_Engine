from __future__ import annotations

from io import BytesIO
import json
import unittest
from zipfile import ZipFile

from review_system.calibration_backfill import (
    BACKFILL_SOURCE_CONTRACT_VERSION,
    CalibrationBackfillError,
    build_historical_calibration_record,
    parse_legacy_interface_artifact,
    parse_pull_request_from_interface_artifact_name,
)


PIE = "a" * 40
HEAD = "b" * 40
INTERFACE = "c" * 64


def _zip(*, action_required: bool = False, manifest_items_match: bool = True) -> bytes:
    signal = {
        "contract_version": "PIE_SIGNAL_V1",
        "status": "ACTION_REQUIRED" if action_required else "CLEAR",
        "reason": "MISSING_TRUST_FIELDS" if action_required else "NO_POLICY_MATCH",
        "match_status": "UNIQUE_POLICY_MATCH" if action_required else "NO_POLICY_MATCH",
        "next": "READ_TRUST_GAPS" if action_required else "NONE",
    }
    targeted = {
        "control:replay_evidence": "targeted/01-control-replay_evidence.json",
        "scenario:deterministic-output": "targeted/02-scenario-deterministic-output.json",
    } if action_required else {}
    manifest_items = targeted if manifest_items_match else {}
    manifest = {
        "contract_version": "PIE_GPT_OPERATIONAL_INTERFACE_V1",
        "level0": {"signal": "signal.json", "text": "SIGNAL.txt"},
        "level1": {"brief": "brief.json" if action_required else None},
        "level2": {"index": "targeted/index.json", "items": manifest_items},
        "level3": {"full_capsule": "SEPARATE_ARTIFACT"},
        "interface_sha256": INTERFACE,
        "manifest_sha256": "d" * 64,
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("signal.json", json.dumps(signal))
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("targeted/index.json", json.dumps(targeted))
        if action_required:
            archive.writestr("brief.json", json.dumps({"contract_version": "PIE_OPERATIONAL_BRIEF_V1"}))
    return buffer.getvalue()


def _run() -> dict:
    return {
        "id": 123456789,
        "run_attempt": 1,
        "head_sha": HEAD,
        "referenced_workflows": [
            {
                "path": f"gycha0109-beep/Project_Intelligence_Engine/.github/workflows/prospective-pr.yml@{PIE}",
                "sha": PIE,
            }
        ],
    }


def _artifact(name: str = "pie-owner-repo-pr-42-bbbbbbbbbbbb-eeeeeeeeeeee-interface") -> dict:
    return {
        "id": 987654321,
        "name": name,
        "digest": "sha256:" + "f" * 64,
        "created_at": "2026-08-30T00:00:00Z",
        "workflow_run": {"id": 123456789, "head_sha": HEAD},
    }


class CalibrationBackfillTests(unittest.TestCase):
    def test_clear_legacy_artifact_reconstructs_current_record_contract_without_authority(self):
        record, source = build_historical_calibration_record(
            repository="Gycha0109-Beep/BuildMap",
            pie_revision=PIE,
            run=_run(),
            artifact=_artifact(),
            artifact_zip=_zip(),
        )
        self.assertEqual("PIE_CALIBRATION_RECORD_V1", record["contract_version"])
        self.assertEqual(42, record["identity"]["pull_request"])
        self.assertEqual(HEAD, record["identity"]["source_revision"])
        self.assertEqual(PIE, record["identity"]["pie_revision"])
        self.assertEqual("CLEAR", record["signal"]["status"])
        self.assertEqual("NO_POLICY_MATCH", record["signal"]["reason"])
        self.assertFalse(record["lazy_interface"]["level1_materialized"])
        self.assertEqual(0, record["lazy_interface"]["level2_item_count"])
        self.assertTrue(record["lazy_interface"]["full_capsule_separate"])
        self.assertFalse(any(record["authority"].values()))
        self.assertEqual(BACKFILL_SOURCE_CONTRACT_VERSION, source["contract_version"])
        self.assertTrue(source["authority"]["historical_observation_only"])
        self.assertFalse(source["authority"]["trust_fact_inferred"])

    def test_action_required_reconstructs_materialized_depth_from_legacy_manifest(self):
        record, _ = build_historical_calibration_record(
            repository="gycha0109-beep/Saju",
            pie_revision=PIE,
            run=_run(),
            artifact=_artifact("pie-owner-saju-pr-142-bbbbbbbbbbbb-eeeeeeeeeeee-interface"),
            artifact_zip=_zip(action_required=True),
        )
        self.assertEqual("ACTION_REQUIRED", record["signal"]["status"])
        self.assertEqual("MISSING_TRUST_FIELDS", record["signal"]["reason"])
        self.assertEqual("UNIQUE_POLICY_MATCH", record["signal"]["match_status"])
        self.assertTrue(record["lazy_interface"]["level1_materialized"])
        self.assertEqual(2, record["lazy_interface"]["level2_item_count"])

    def test_parser_uses_artifact_encoded_pr_number(self):
        self.assertEqual(
            341,
            parse_pull_request_from_interface_artifact_name(
                "pie-owner-k_beauty-pr-341-aaaaaaaaaaaa-bbbbbbbbbbbb-interface"
            ),
        )

    def test_manifest_targeted_index_mismatch_fails_closed(self):
        with self.assertRaisesRegex(CalibrationBackfillError, "must match targeted/index.json"):
            parse_legacy_interface_artifact(_zip(action_required=True, manifest_items_match=False))

    def test_wrong_pie_revision_is_rejected(self):
        with self.assertRaisesRegex(CalibrationBackfillError, "does not reference"):
            build_historical_calibration_record(
                repository="gycha0109-beep/BuildMap",
                pie_revision="e" * 40,
                run=_run(),
                artifact=_artifact(),
                artifact_zip=_zip(),
            )

    def test_artifact_head_prefix_mismatch_is_rejected(self):
        with self.assertRaisesRegex(CalibrationBackfillError, "head prefix"):
            build_historical_calibration_record(
                repository="gycha0109-beep/BuildMap",
                pie_revision=PIE,
                run=_run(),
                artifact=_artifact("pie-owner-repo-pr-42-aaaaaaaaaaaa-eeeeeeeeeeee-interface"),
                artifact_zip=_zip(),
            )

    def test_artifact_run_identity_mismatch_is_rejected(self):
        artifact = _artifact()
        artifact["workflow_run"] = {"id": 123456789, "head_sha": "f" * 40}
        with self.assertRaisesRegex(CalibrationBackfillError, "does not match workflow run"):
            build_historical_calibration_record(
                repository="gycha0109-beep/BuildMap",
                pie_revision=PIE,
                run=_run(),
                artifact=artifact,
                artifact_zip=_zip(),
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.identity import canonical_json_sha256
from review_system.trust_pilot_evidence_run import (
    ELIGIBLE_STATUS,
    NOT_ELIGIBLE_STATUS,
    PilotEvidenceRunError,
    EXPECTED_FILES,
    _report_payload,
    _run_id,
    _snapshot_payload,
    run_r0_pilot_evidence,
    verify_pilot_evidence_run_report_data,
    verify_pilot_evidence_run_report_sources,
    write_pilot_evidence_run_report,
)


class PilotEvidenceRunTests(unittest.TestCase):
    def _complete_package(self, root: Path) -> None:
        for index, (_, filename) in enumerate(EXPECTED_FILES, start=1):
            (root / filename).write_text(f"evidence-{index}\n", encoding="utf-8")

    def _pilot_report(
        self,
        *,
        eligible: bool = True,
        reconciliation_verified: bool = True,
        observation_verified: bool = True,
    ) -> dict:
        status = ELIGIBLE_STATUS if eligible else NOT_ELIGIBLE_STATUS
        blockers = [] if eligible else ["OBSERVATION_THRESHOLDS_SATISFIED"]
        next_step = (
            "REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION"
            if eligible
            else "RESOLVE_OBSERVATION_SAFETY_BLOCKERS"
        )
        return {
            "review_id": "r0-pilot-safety-review-" + "1" * 32,
            "project_id": "demo",
            "report_sha256": "a" * 64,
            "status": status,
            "next_step": next_step,
            "blockers": blockers,
            "source_replay": {
                "reconciliation_verified": reconciliation_verified,
                "observation_verified": observation_verified,
            },
        }

    def test_missing_package_is_valid_not_eligible_without_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "r0-pilot-evidence"
            report = run_r0_pilot_evidence(root, generated_at="2026-08-18T05:00:00Z")
            self.assertEqual(NOT_ELIGIBLE_STATUS, report["status"])
            self.assertFalse(report["package_complete"])
            self.assertFalse(report["source_replay"]["attempted"])
            self.assertFalse(report["pilot_review"]["attempted"])
            self.assertEqual("PROVIDE_COMPLETE_R0_EVIDENCE_PACKAGE", report["next_step"])
            self.assertEqual(5, len(report["blockers"]))
            self.assertTrue(all(item.startswith("EVIDENCE_FILE_MISSING:") for item in report["blockers"]))
            self.assertFalse(report["automation_authorized"])
            self.assertFalse(report["pilot_authorized"])
            self.assertEqual([], verify_pilot_evidence_run_report_data(report))

    def test_partial_package_does_not_attempt_stage10e(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "r0-pilot-evidence"
            root.mkdir()
            (root / EXPECTED_FILES[0][1]).write_text("registry\n", encoding="utf-8")
            with patch("review_system.trust_pilot_evidence_run.review_r0_pilot") as review:
                report = run_r0_pilot_evidence(root, generated_at="2026-08-18T05:00:00Z")
            review.assert_not_called()
            self.assertFalse(report["package_complete"])
            self.assertFalse(report["source_replay"]["attempted"])
            self.assertEqual(4, len(report["blockers"]))

    def test_complete_package_can_reach_human_authorization_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "r0-pilot-evidence"
            root.mkdir()
            self._complete_package(root)
            with patch(
                "review_system.trust_pilot_evidence_run.review_r0_pilot",
                return_value=self._pilot_report(),
            ):
                report = run_r0_pilot_evidence(root, generated_at="2026-08-18T05:00:00Z")
            self.assertEqual(ELIGIBLE_STATUS, report["status"])
            self.assertTrue(report["package_complete"])
            self.assertTrue(report["source_replay"]["attempted"])
            self.assertTrue(report["source_replay"]["verified"])
            self.assertEqual([], report["blockers"])
            self.assertEqual("REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION", report["next_step"])
            self.assertFalse(report["automation_authorized"])
            self.assertFalse(report["pilot_authorized"])
            self.assertEqual([], verify_pilot_evidence_run_report_data(report))

    def test_stage10e_not_eligible_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "r0-pilot-evidence"
            root.mkdir()
            self._complete_package(root)
            with patch(
                "review_system.trust_pilot_evidence_run.review_r0_pilot",
                return_value=self._pilot_report(eligible=False),
            ):
                report = run_r0_pilot_evidence(root, generated_at="2026-08-18T05:00:00Z")
            self.assertEqual(NOT_ELIGIBLE_STATUS, report["status"])
            self.assertEqual(["OBSERVATION_THRESHOLDS_SATISFIED"], report["blockers"])
            self.assertEqual("RESOLVE_OBSERVATION_SAFETY_BLOCKERS", report["next_step"])

    def test_stage10e_source_replay_failure_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "r0-pilot-evidence"
            root.mkdir()
            self._complete_package(root)
            with patch(
                "review_system.trust_pilot_evidence_run.review_r0_pilot",
                return_value=self._pilot_report(reconciliation_verified=False),
            ):
                report = run_r0_pilot_evidence(root, generated_at="2026-08-18T05:00:00Z")
            self.assertEqual(NOT_ELIGIBLE_STATUS, report["status"])
            self.assertFalse(report["source_replay"]["verified"])
            self.assertEqual(["RECONCILIATION_SOURCE_REPLAY_FAILED"], report["source_replay"]["error_codes"])
            self.assertIn("SOURCE_REPLAY_FAILED", report["blockers"])
            self.assertEqual("REPAIR_AND_REPLAY_SOURCE_EVIDENCE", report["next_step"])

    def test_generated_at_does_not_change_evidence_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "r0-pilot-evidence"
            first = run_r0_pilot_evidence(root, generated_at="2026-08-18T05:00:00Z")
            second = run_r0_pilot_evidence(root, generated_at="2026-08-19T05:00:00Z")
            self.assertEqual(first["evidence_snapshot_sha256"], second["evidence_snapshot_sha256"])
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertNotEqual(first["report_sha256"], second["report_sha256"])

    def test_semantic_rehash_cannot_flip_missing_package_to_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_r0_pilot_evidence(
                Path(temporary) / "r0-pilot-evidence",
                generated_at="2026-08-18T05:00:00Z",
            )
            forged = deepcopy(report)
            forged["status"] = ELIGIBLE_STATUS
            forged["blockers"] = []
            forged["next_step"] = "REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION"
            snapshot = canonical_json_sha256(_snapshot_payload(forged))
            forged["evidence_snapshot_sha256"] = snapshot
            forged["run_id"] = _run_id(forged, snapshot)
            forged["report_sha256"] = canonical_json_sha256(_report_payload(forged))
            errors = verify_pilot_evidence_run_report_data(forged)
            self.assertTrue(any("status projection mismatch" in error for error in errors))
            self.assertTrue(any("blockers projection mismatch" in error for error in errors))

    def test_source_mutation_is_detected_by_exact_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "r0-pilot-evidence"
            root.mkdir()
            self._complete_package(root)
            with patch(
                "review_system.trust_pilot_evidence_run.review_r0_pilot",
                return_value=self._pilot_report(),
            ):
                report = run_r0_pilot_evidence(root, generated_at="2026-08-18T05:00:00Z")
                (root / EXPECTED_FILES[0][1]).write_text("mutated\n", encoding="utf-8")
                errors = verify_pilot_evidence_run_report_sources(report, evidence_root=root)
            self.assertTrue(any("inventory mismatch" in error for error in errors))

    def test_evidence_root_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            real = base / "real"
            real.mkdir()
            link = base / "evidence"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(PilotEvidenceRunError):
                run_r0_pilot_evidence(link, generated_at="2026-08-18T05:00:00Z")

    def test_atomic_replace_failure_preserves_existing_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_r0_pilot_evidence(root / "missing", generated_at="2026-08-18T05:00:00Z")
            output = root / "report.json"
            output.write_text("original\n", encoding="utf-8")
            with patch("review_system.trust_pilot_evidence_run.os.replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    write_pilot_evidence_run_report(output, report)
            self.assertEqual("original\n", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

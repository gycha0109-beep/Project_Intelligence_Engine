from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from review_system.identity import canonical_json_sha256
from review_system.trust_pilot_evidence_run import (
    EXPECTED_FILES,
    PilotEvidenceRunError,
    _report_payload,
    _run_id,
    _snapshot_payload,
    run_r0_pilot_evidence,
    verify_pilot_evidence_run_report_data,
    write_pilot_evidence_run_report,
)


class PilotEvidenceRunHardeningTests(unittest.TestCase):
    def _complete_invalid_package(self, root: Path) -> None:
        root.mkdir()
        for index, (_, filename) in enumerate(EXPECTED_FILES, start=1):
            (root / filename).write_text(f"invalid-{index}\n", encoding="utf-8")

    def test_complete_but_invalid_authority_package_fails_closed_as_valid_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "r0-pilot-evidence"
            self._complete_invalid_package(root)
            report = run_r0_pilot_evidence(root, generated_at="2026-08-18T05:00:00Z")
            self.assertTrue(report["package_complete"])
            self.assertTrue(report["source_replay"]["attempted"])
            self.assertFalse(report["source_replay"]["verified"])
            self.assertEqual("NOT_ELIGIBLE", report["status"])
            self.assertIn("SOURCE_REPLAY_FAILED", report["blockers"])
            self.assertEqual("REPAIR_AND_REPLAY_SOURCE_EVIDENCE", report["next_step"])
            self.assertEqual([], verify_pilot_evidence_run_report_data(report))

    def test_symlinked_required_file_is_not_usable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "r0-pilot-evidence"
            root.mkdir()
            for index, (_, filename) in enumerate(EXPECTED_FILES, start=1):
                (root / filename).write_text(f"evidence-{index}\n", encoding="utf-8")
            target = root / "real-policy.json"
            target.write_text("real\n", encoding="utf-8")
            policy = root / "observation-policy.json"
            policy.unlink()
            policy.symlink_to(target.name)
            report = run_r0_pilot_evidence(root, generated_at="2026-08-18T05:00:00Z")
            self.assertFalse(report["package_complete"])
            self.assertIn("EVIDENCE_FILE_MISSING:OBSERVATION_POLICY", report["blockers"])
            self.assertFalse(report["source_replay"]["attempted"])

    def test_output_symlink_is_rejected_without_mutating_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_r0_pilot_evidence(root / "missing", generated_at="2026-08-18T05:00:00Z")
            target = root / "target.json"
            target.write_text("original\n", encoding="utf-8")
            output = root / "report.json"
            output.symlink_to(target.name)
            with self.assertRaises(PilotEvidenceRunError):
                write_pilot_evidence_run_report(output, report)
            self.assertEqual("original\n", target.read_text(encoding="utf-8"))

    def test_pilot_authorization_flag_cannot_be_rehashed_true(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_r0_pilot_evidence(
                Path(temporary) / "missing",
                generated_at="2026-08-18T05:00:00Z",
            )
            forged = deepcopy(report)
            forged["pilot_authorized"] = True
            snapshot = canonical_json_sha256(_snapshot_payload(forged))
            forged["evidence_snapshot_sha256"] = snapshot
            forged["run_id"] = _run_id(forged, snapshot)
            forged["report_sha256"] = canonical_json_sha256(_report_payload(forged))
            errors = verify_pilot_evidence_run_report_data(forged)
            self.assertTrue(any("pilot_authorized" in error or "False was expected" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from review_system.trust_comparison import record_decision, write_registry
from review_system.trust_observation import (
    TrustObservationError,
    assess_observation,
    verify_report_sources,
    write_report,
)
from review_system.trust_observation_cli import main as observation_main
from test_trust_observation import ObservationFixture


class TrustObservationHardeningTests(unittest.TestCase):
    def test_output_symlink_is_rejected_as_observation_input_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ObservationFixture(root)
            fixture.passing_registry()
            report = assess_observation(fixture.registry_path, fixture.policy_path)
            target = root / "actual-report.json"
            link = root / "report-link.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks unavailable")

            with self.assertRaises(TrustObservationError):
                write_report(link, report)

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = observation_main([
                    "observe-readiness",
                    "--registry", str(fixture.registry_path),
                    "--policy", str(fixture.policy_path),
                    "--output", str(link),
                ])
            self.assertEqual(3, code)
            self.assertIn("symlink", stderr.getvalue().lower())

    def test_atomic_replace_failure_preserves_existing_report_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ObservationFixture(root)
            fixture.passing_registry()
            report = assess_observation(fixture.registry_path, fixture.policy_path)
            output = root / "observation-report.json"
            write_report(output, report)
            original = output.read_bytes()

            with patch("review_system.trust_comparison.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    write_report(output, report)

            self.assertEqual(original, output.read_bytes())

    def test_valid_registry_change_is_detected_by_source_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ObservationFixture(root)
            fixture.passing_registry()
            report = assess_observation(fixture.registry_path, fixture.policy_path)
            self.assertEqual([], verify_report_sources(
                report,
                registry_path=fixture.registry_path,
                policy_path=fixture.policy_path,
            ))

            r0 = next(
                item for item in fixture.registry["assessments"]
                if item["predicted_risk_band"] == "R0"
            )
            fixture.registry = record_decision(
                fixture.registry,
                assessment_id=r0["assessment_id"],
                review_level="REVIEWED",
                decision="APPROVE",
                confirmed_risk_band="R0",
                actor="later-reviewer",
                occurred_at="2026-08-16T00:00:00Z",
                reason_codes=["FOLLOW_UP_REVIEW"],
            )
            write_registry(fixture.registry_path, fixture.registry)

            errors = verify_report_sources(
                report,
                registry_path=fixture.registry_path,
                policy_path=fixture.policy_path,
            )
            self.assertEqual(
                ["observation report does not replay from registry and policy sources"],
                errors,
            )


if __name__ == "__main__":
    unittest.main()

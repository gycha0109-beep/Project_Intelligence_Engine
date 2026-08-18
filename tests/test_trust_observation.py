import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from review_system.identity import canonical_json_sha256
from review_system.io import dump_json, load_data
from review_system.trust import write_trust_report
from review_system.trust_cli import main as trust_main
from review_system.trust_comparison import (
    capture_assessment,
    new_registry,
    record_decision,
    record_outcome,
    write_registry,
)
from review_system.trust_observation import (
    TrustObservationVerificationError,
    assess_observation,
    load_policy,
    load_report,
    policy_id,
    policy_sha256,
    verify_policy_data,
    verify_report_data,
    verify_report_sources,
    write_report,
)
from review_system.trust_observation_cli import main as observation_main
from test_trust_gate import TrustReadinessFixture


class ObservationFixture:
    def __init__(self, root: Path):
        self.root = root
        self.trust = TrustReadinessFixture(root)
        self.registry = new_registry("demo", created_at="2026-08-01T00:00:00Z")
        self.registry_path = root / "trust-comparisons.json"
        self.policy_path = root / "observation-policy.json"
        self.policy = {
            "schema_version": "1.0",
            "policy_version": "1.0.0",
            "mode": "REPORT_ONLY",
            "target_band": "R0",
            "thresholds": {
                "minimum_r0_assessment_count": 1,
                "minimum_r0_reviewed_count": 1,
                "minimum_r0_conclusive_outcome_count": 1,
                "minimum_r0_confirmed_safe_count": 1,
                "minimum_confirmed_unsafe_challenge_count": 1,
                "minimum_r0_independent_audit_count": 1,
                "minimum_r0_outcome_coverage": 1.0,
                "minimum_r0_evidence_span_days": 10,
                "maximum_r0_false_negatives": 0,
                "maximum_r0_false_negative_rate": 0.0,
            },
        }
        dump_json(self.policy_path, self.policy)
        self.counter = 0

    def capture(self, task_class: str, changed_file: str, captured_at: str) -> str:
        self.counter += 1
        self.trust.write_request(task_class=task_class, changed_files=[changed_file])
        request = load_data(self.trust.request)
        request["task_id"] = f"TASK-OBS-{self.counter:03d}"
        request["source_revision"] = "git:" + f"{self.counter:040x}"
        dump_json(self.trust.request, request)
        report = self.trust.assess(generated_at="2026-07-25T02:00:00Z")
        report_path = self.root / f"trust-report-{self.counter}.json"
        write_trust_report(report_path, report)
        self.registry = capture_assessment(
            self.registry,
            report_path,
            captured_at=captured_at,
        )
        return next(
            item["assessment_id"]
            for item in self.registry["assessments"]
            if item["trust_report_id"] == report["report_id"]
        )

    def add_safe_r0(self, *, review_level: str = "REVIEWED") -> str:
        assessment_id = self.capture(
            "generated_artifact",
            f"generated/report-{self.counter + 1}.json",
            "2026-08-01T00:00:00Z",
        )
        self.registry = record_decision(
            self.registry,
            assessment_id=assessment_id,
            review_level=review_level,
            decision="APPROVE",
            confirmed_risk_band="R0",
            actor="reviewer-r0",
            occurred_at="2026-08-02T00:00:00Z",
        )
        self.registry = record_outcome(
            self.registry,
            assessment_id=assessment_id,
            outcome_type="INDEPENDENT_AUDIT",
            verdict="SAFE",
            actor="auditor-r0",
            occurred_at="2026-08-15T00:00:00Z",
            evidence_refs=["pie://audit/r0-safe"],
        )
        return assessment_id

    def add_unsafe_challenge(self) -> str:
        assessment_id = self.capture(
            "routine_code",
            f"src/service_{self.counter + 1}.py",
            "2026-08-03T00:00:00Z",
        )
        self.registry = record_outcome(
            self.registry,
            assessment_id=assessment_id,
            outcome_type="CONTROLLED_EVALUATION",
            verdict="UNSAFE",
            actor="evaluation-lab",
            occurred_at="2026-08-04T00:00:00Z",
            evidence_refs=["pie://evaluation/unsafe-challenge"],
        )
        return assessment_id

    def persist(self) -> None:
        write_registry(self.registry_path, self.registry)

    def passing_registry(self) -> None:
        self.add_safe_r0()
        self.add_unsafe_challenge()
        self.persist()


class TrustObservationPolicyTests(unittest.TestCase):
    def test_policy_is_derived_identity_and_cannot_allow_observed_misses(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ObservationFixture(Path(tmp))
            source, policy = load_policy(fixture.policy_path)
            self.assertEqual(fixture.policy_path.resolve(), source)
            self.assertEqual([], verify_policy_data(policy))
            self.assertTrue(policy_id(policy).startswith("trust-observation-policy-"))
            self.assertEqual(64, len(policy_sha256(policy)))

            bad = copy.deepcopy(policy)
            bad["thresholds"]["maximum_r0_false_negatives"] = 1
            self.assertTrue(verify_policy_data(bad))
            bad = copy.deepcopy(policy)
            bad["thresholds"]["maximum_r0_false_negative_rate"] = 0.01
            self.assertTrue(verify_policy_data(bad))

    def test_no_unsafe_challenge_keeps_fnr_null_and_evidence_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ObservationFixture(Path(tmp))
            fixture.add_safe_r0()
            fixture.persist()
            report = assess_observation(
                fixture.registry_path,
                fixture.policy_path,
                generated_at="2026-08-18T00:00:00Z",
            )
            self.assertEqual("INSUFFICIENT_EVIDENCE", report["status"])
            self.assertIsNone(report["observation"]["r0_false_negative_rate"])
            self.assertIn("MINIMUM_CONFIRMED_UNSAFE_CHALLENGE_COUNT", report["blockers"])
            self.assertIn("MAXIMUM_R0_FALSE_NEGATIVE_RATE", report["blockers"])
            self.assertFalse(report["automation_authorized"])
            self.assertFalse(report["pilot_authorized"])

    def test_safe_r0_plus_non_r0_unsafe_challenge_satisfies_thresholds_report_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ObservationFixture(Path(tmp))
            fixture.passing_registry()
            report = assess_observation(
                fixture.registry_path,
                fixture.policy_path,
                generated_at="2026-08-18T00:00:00Z",
            )
            observation = report["observation"]
            self.assertEqual(1, observation["r0_assessment_count"])
            self.assertEqual(1, observation["r0_confirmed_safe_count"])
            self.assertEqual(1, observation["confirmed_unsafe_challenge_count"])
            self.assertEqual(1, observation["r0_true_positive"])
            self.assertEqual(1, observation["r0_true_negative"])
            self.assertEqual(0, observation["r0_false_negative"])
            self.assertEqual(0.0, observation["r0_false_negative_rate"])
            self.assertGreaterEqual(observation["r0_evidence_span_days"], 10)
            self.assertEqual(
                "THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION",
                report["status"],
            )
            self.assertEqual([], report["blockers"])
            self.assertFalse(report["automation_authorized"])
            self.assertFalse(report["pilot_authorized"])
            self.assertEqual(
                {"required_before_pilot": True, "verified_in_this_stage": False},
                report["source_reconciliation"],
            )

    def test_unsafe_r0_is_confirmed_false_negative_and_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ObservationFixture(Path(tmp))
            r0_id = fixture.capture(
                "generated_artifact",
                "generated/unsafe.report.json",
                "2026-08-01T00:00:00Z",
            )
            fixture.registry = record_decision(
                fixture.registry,
                assessment_id=r0_id,
                review_level="REVIEWED",
                decision="APPROVE",
                confirmed_risk_band="R0",
                actor="reviewer-r0",
                occurred_at="2026-08-02T00:00:00Z",
            )
            fixture.registry = record_outcome(
                fixture.registry,
                assessment_id=r0_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                actor="incident-auditor",
                occurred_at="2026-08-15T00:00:00Z",
                defect_id="defect-r0-miss",
            )
            fixture.add_unsafe_challenge()
            fixture.persist()
            report = assess_observation(fixture.registry_path, fixture.policy_path)
            self.assertEqual("THRESHOLD_BLOCKED", report["status"])
            self.assertEqual(1, report["observation"]["r0_false_negative"])
            self.assertGreater(report["observation"]["r0_false_negative_rate"], 0)
            self.assertIn("MAXIMUM_R0_FALSE_NEGATIVES", report["blockers"])
            self.assertEqual("INVESTIGATE_CONFIRMED_FALSE_NEGATIVES", report["next_step"])

    def test_workflow_accepted_does_not_satisfy_reviewed_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ObservationFixture(Path(tmp))
            fixture.add_safe_r0(review_level="WORKFLOW_ACCEPTED")
            fixture.add_unsafe_challenge()
            fixture.persist()
            report = assess_observation(fixture.registry_path, fixture.policy_path)
            self.assertEqual(0, report["observation"]["r0_reviewed_count"])
            self.assertEqual("INSUFFICIENT_EVIDENCE", report["status"])
            self.assertIn("MINIMUM_R0_REVIEWED_COUNT", report["blockers"])

    def test_generated_at_cannot_inflate_evidence_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ObservationFixture(Path(tmp))
            fixture.passing_registry()
            first = assess_observation(
                fixture.registry_path,
                fixture.policy_path,
                generated_at="2026-08-18T00:00:00Z",
            )
            second = assess_observation(
                fixture.registry_path,
                fixture.policy_path,
                generated_at="2027-08-18T00:00:00Z",
            )
            self.assertEqual(first["report_id"], second["report_id"])
            self.assertEqual(
                first["observation"]["r0_evidence_span_days"],
                second["observation"]["r0_evidence_span_days"],
            )
            self.assertNotEqual(first["report_sha256"], second["report_sha256"])

    def test_embedded_policy_and_check_rehash_tamper_fail_self_contained_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ObservationFixture(Path(tmp))
            fixture.passing_registry()
            report = assess_observation(fixture.registry_path, fixture.policy_path)
            tampered = copy.deepcopy(report)
            tampered["policy"]["thresholds"]["minimum_r0_assessment_count"] = 99
            tampered["report_sha256"] = canonical_json_sha256({
                key: value for key, value in tampered.items() if key != "report_sha256"
            })
            errors = verify_report_data(tampered)
            self.assertTrue(any("policy_id mismatch" in item or "policy_sha256 mismatch" in item for item in errors))
            self.assertIn("threshold check projection mismatch", errors)

    def test_source_replay_detects_registry_or_policy_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ObservationFixture(Path(tmp))
            fixture.passing_registry()
            report = assess_observation(fixture.registry_path, fixture.policy_path)
            self.assertEqual([], verify_report_sources(
                report,
                registry_path=fixture.registry_path,
                policy_path=fixture.policy_path,
            ))
            changed = copy.deepcopy(fixture.policy)
            changed["thresholds"]["minimum_r0_assessment_count"] = 2
            dump_json(fixture.policy_path, changed)
            self.assertTrue(verify_report_sources(
                report,
                registry_path=fixture.registry_path,
                policy_path=fixture.policy_path,
            ))

    def test_report_round_trip_and_symlink_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ObservationFixture(root)
            fixture.passing_registry()
            report = assess_observation(fixture.registry_path, fixture.policy_path)
            path = root / "observation-report.json"
            write_report(path, report)
            loaded_path, loaded = load_report(path)
            self.assertEqual(path.resolve(), loaded_path)
            self.assertEqual(report, loaded)
            link = root / "policy-link.json"
            try:
                link.symlink_to(fixture.policy_path)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaises(Exception):
                load_policy(link)

    def test_cli_end_to_end_and_source_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ObservationFixture(root)
            fixture.passing_registry()
            report_path = root / "report.json"
            with redirect_stdout(io.StringIO()):
                code = trust_main([
                    "verify-observation-policy",
                    "--policy", str(fixture.policy_path),
                ])
            self.assertEqual(0, code)
            with redirect_stdout(io.StringIO()):
                code = trust_main([
                    "observe-readiness",
                    "--registry", str(fixture.registry_path),
                    "--policy", str(fixture.policy_path),
                    "--output", str(report_path),
                    "--generated-at", "2026-08-18T00:00:00Z",
                ])
            self.assertEqual(0, code)
            with redirect_stdout(io.StringIO()):
                code = trust_main([
                    "verify-observation-report",
                    "--report", str(report_path),
                    "--registry", str(fixture.registry_path),
                    "--policy", str(fixture.policy_path),
                ])
            self.assertEqual(0, code)
            with redirect_stdout(io.StringIO()):
                code = observation_main([
                    "verify-observation-report",
                    "--report", str(report_path),
                ])
            self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()

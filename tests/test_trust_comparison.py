import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from review_system.trust import write_trust_report
from review_system.trust_cli import main as trust_main
from review_system.trust_comparison import (
    TrustComparisonError,
    TrustComparisonVerificationError,
    capture_assessment,
    load_registry,
    new_registry,
    record_decision,
    record_outcome,
    sample_audit,
    verify_registry_data,
    write_registry,
)
from test_trust_gate import TrustReadinessFixture


class ComparisonFixture:
    def __init__(self, root: Path):
        self.root = root
        self.trust = TrustReadinessFixture(root)
        self.report = root / "trust-report.json"
        write_trust_report(self.report, self.trust.assess())
        self.registry_path = root / "trust-comparisons.json"
        registry = new_registry("demo", created_at="2026-08-02T00:00:00Z")
        self.registry = capture_assessment(
            registry,
            self.report,
            captured_at="2026-08-02T00:01:00Z",
        )
        write_registry(self.registry_path, self.registry)
        self.assessment_id = self.registry["assessments"][0]["assessment_id"]

    def reviewed(self, *, actor: str = "reviewer-a", decision: str = "APPROVE", band: str = "R1"):
        self.registry = record_decision(
            self.registry,
            assessment_id=self.assessment_id,
            review_level="REVIEWED",
            decision=decision,
            confirmed_risk_band=band,
            reason_codes=["REVIEW_COMPLETE"],
            actor=actor,
            occurred_at="2026-08-02T00:02:00Z",
        )
        return self.registry


class TrustComparisonTests(unittest.TestCase):
    def test_capture_is_idempotent_and_reference_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            second = capture_assessment(
                fixture.registry,
                fixture.report,
                captured_at="2026-08-03T00:01:00Z",
            )
            self.assertEqual(fixture.registry, second)
            self.assertEqual(1, len(second["assessments"]))
            payload = json.dumps(second, sort_keys=True)
            self.assertNotIn(str(fixture.root), payload)
            self.assertNotIn("human-reviewer", payload)
            self.assertEqual([], verify_registry_data(second))

    def test_workflow_accepted_is_not_reviewed_or_alignment_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            registry = record_decision(
                fixture.registry,
                assessment_id=fixture.assessment_id,
                review_level="WORKFLOW_ACCEPTED",
                decision="APPROVE",
                actor="operator",
                occurred_at="2026-08-02T00:02:00Z",
            )
            comparison = registry["comparisons"][0]
            self.assertEqual("UNREVIEWED", comparison["provisional_status"])
            self.assertEqual(1, registry["metrics"]["maturity"]["workflow_accepted_count"])
            self.assertEqual(0, registry["metrics"]["maturity"]["reviewed_count"])
            self.assertEqual(0, registry["metrics"]["reviewer_alignment"]["comparable_count"])
            self.assertIsNone(registry["metrics"]["reviewer_alignment"]["alignment_rate"])

    def test_reviewed_decision_is_provisional_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            registry = fixture.reviewed()
            comparison = registry["comparisons"][0]
            self.assertEqual("PROVISIONAL_MATCH", comparison["provisional_status"])
            self.assertEqual("UNCONFIRMED", comparison["confirmed_status"])
            self.assertEqual(1.0, registry["metrics"]["reviewer_alignment"]["alignment_rate"])
            self.assertEqual(0, registry["metrics"]["confirmed_outcomes"]["sample_count"])
            self.assertIsNone(registry["metrics"]["confirmed_outcomes"]["accuracy"])

    def test_unsafe_outcome_confirms_false_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            fixture.reviewed()
            registry = record_outcome(
                fixture.registry,
                assessment_id=fixture.assessment_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                defect_id="defect-123",
                evidence_refs=["pie://defects/defect-123"],
                actor="incident-reviewer",
                occurred_at="2026-08-03T00:00:00Z",
            )
            self.assertEqual(
                "CONFIRMED_FALSE_NEGATIVE",
                registry["comparisons"][0]["confirmed_status"],
            )
            metrics = registry["metrics"]["confirmed_outcomes"]
            self.assertEqual(1, metrics["sample_count"])
            self.assertEqual(1, metrics["false_negative"])
            self.assertEqual(1.0, metrics["false_negative_rate"])
            self.assertEqual(0.0, metrics["accuracy"])

    def test_independent_audit_actor_must_differ_from_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            fixture.reviewed(actor="same-person")
            with self.assertRaisesRegex(TrustComparisonError, "must differ"):
                record_outcome(
                    fixture.registry,
                    assessment_id=fixture.assessment_id,
                    outcome_type="INDEPENDENT_AUDIT",
                    verdict="SAFE",
                    actor="same-person",
                    occurred_at="2026-08-03T00:00:00Z",
                )

    def test_event_chain_and_projection_tamper_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            registry = fixture.reviewed()
            tampered = copy.deepcopy(registry)
            tampered["events"][0]["payload"]["decision"] = "REJECT"
            self.assertTrue(any("event_sha256 mismatch" in item for item in verify_registry_data(tampered)))
            tampered = copy.deepcopy(registry)
            tampered["comparisons"][0]["provisional_status"] = "PROVISIONAL_UNDER_ESTIMATE"
            self.assertIn("comparisons projection mismatch", verify_registry_data(tampered))

    def test_deterministic_audit_sample_excludes_confirmed_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            first = sample_audit(fixture.registry, count=1, seed="weekly-1")
            second = sample_audit(fixture.registry, count=1, seed="weekly-1")
            self.assertEqual(first, second)
            self.assertEqual([fixture.assessment_id], first["assessment_ids"])
            confirmed = record_outcome(
                fixture.registry,
                assessment_id=fixture.assessment_id,
                outcome_type="CONTROLLED_EVALUATION",
                verdict="SAFE",
                actor="evaluation-lab",
                occurred_at="2026-08-03T00:00:00Z",
            )
            self.assertEqual([], sample_audit(confirmed, count=1, seed="weekly-1")["assessment_ids"])

    def test_cli_end_to_end_uses_explicit_review_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            registry = Path(tmp) / "cli-registry.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = trust_main([
                    "init-comparison-registry", "--registry", str(registry),
                    "--project-id", "demo", "--created-at", "2026-08-02T00:00:00Z",
                ])
            self.assertEqual(0, code)
            with redirect_stdout(io.StringIO()):
                code = trust_main([
                    "capture-assessment", "--registry", str(registry),
                    "--trust-report", str(fixture.report), "--captured-at", "2026-08-02T00:01:00Z",
                ])
            self.assertEqual(0, code)
            _, loaded = load_registry(registry)
            assessment_id = loaded["assessments"][0]["assessment_id"]
            with redirect_stdout(io.StringIO()):
                code = trust_main([
                    "record-decision", "--registry", str(registry),
                    "--assessment-id", assessment_id, "--review-level", "WORKFLOW_ACCEPTED",
                    "--decision", "APPROVE", "--actor", "operator",
                    "--occurred-at", "2026-08-02T00:02:00Z",
                ])
            self.assertEqual(0, code)
            _, loaded = load_registry(registry)
            self.assertEqual("UNREVIEWED", loaded["comparisons"][0]["provisional_status"])
            with redirect_stdout(io.StringIO()):
                code = trust_main(["verify-comparison-registry", "--registry", str(registry)])
            self.assertEqual(0, code)


class TrustComparisonSafetyTests(unittest.TestCase):
    def test_event_before_assessment_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            with self.assertRaisesRegex(TrustComparisonError, "must not precede"):
                record_decision(
                    fixture.registry,
                    assessment_id=fixture.assessment_id,
                    review_level="REVIEWED",
                    decision="APPROVE",
                    actor="reviewer",
                    occurred_at="2026-08-01T00:00:00Z",
                )

    def test_symlink_registry_and_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ComparisonFixture(root)
            link = root / "registry-link.json"
            try:
                link.symlink_to(fixture.registry_path)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(TrustComparisonError, "symlink"):
                load_registry(link)
            output_link = root / "output-link.json"
            output_link.symlink_to(root / "missing.json")
            with self.assertRaisesRegex(TrustComparisonError, "symlink"):
                write_registry(output_link, fixture.registry)

    def test_atomic_replace_failure_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            original = fixture.registry_path.read_bytes()
            with patch("review_system.trust_comparison.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    write_registry(fixture.registry_path, fixture.registry)
            self.assertEqual(original, fixture.registry_path.read_bytes())

    def test_reclassify_requires_band_and_zero_denominators_stay_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ComparisonFixture(Path(tmp))
            with self.assertRaisesRegex(TrustComparisonError, "requires"):
                record_decision(
                    fixture.registry,
                    assessment_id=fixture.assessment_id,
                    review_level="REVIEWED",
                    decision="RECLASSIFY",
                    actor="reviewer",
                    occurred_at="2026-08-02T00:02:00Z",
                )
            metrics = fixture.registry["metrics"]["confirmed_outcomes"]
            self.assertIsNone(metrics["precision"])
            self.assertIsNone(metrics["recall"])
            self.assertIsNone(metrics["false_positive_rate"])
            self.assertIsNone(metrics["false_negative_rate"])
            self.assertIsNone(metrics["accuracy"])


if __name__ == "__main__":
    unittest.main()

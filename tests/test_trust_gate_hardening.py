import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

from review_system.identity import canonical_json_sha256
from review_system.io import dump_json
from review_system.trust import (
    TrustError,
    assess_trust,
    load_reground_observations,
    load_trust_request,
    verify_trust_report_data,
    verify_trust_report_sources,
    write_trust_report,
)
from test_trust_gate import TrustReadinessFixture


def rehash_report(report: dict) -> None:
    snapshot_payload = {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "mode": report.get("mode"),
        "automation_authorized": report.get("automation_authorized"),
        "maximum_automation_band": report.get("maximum_automation_band"),
        "request": deepcopy(report.get("request")),
        "profile": deepcopy(report.get("profile")),
        "risk": deepcopy(report.get("risk")),
        "hard_gates": deepcopy(report.get("hard_gates")),
        "evidence": deepcopy(report.get("evidence")),
        "readiness": deepcopy(report.get("readiness")),
        "task_advisory": deepcopy(report.get("task_advisory")),
    }
    report["snapshot_sha256"] = canonical_json_sha256(snapshot_payload)
    request = report["request"]
    report["report_id"] = "trust-" + canonical_json_sha256(
        {
            "project_id": report["project_id"],
            "task_id": request["task_id"],
            "source_revision": request["source_revision"],
            "snapshot_sha256": report["snapshot_sha256"],
        }
    )[:32]
    payload = deepcopy(report)
    payload.pop("report_sha256", None)
    report["report_sha256"] = canonical_json_sha256(payload)


class TrustInputHardeningTests(unittest.TestCase):
    def test_normalized_duplicate_changed_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            data = json.loads(fixture.request.read_text(encoding="utf-8"))
            data["changed_files"] = ["src/a.py", "src\\a.py"]
            dump_json(fixture.request, data)
            with self.assertRaisesRegex(TrustError, "normalized duplicates"):
                load_trust_request(fixture.request)

    def test_symbolic_source_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            data = json.loads(fixture.request.read_text(encoding="utf-8"))
            data["source_revision"] = "HEAD"
            dump_json(fixture.request, data)
            with self.assertRaisesRegex(TrustError, "symbolic revision"):
                load_trust_request(fixture.request)

    def test_duplicate_relation_observation_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            data = json.loads(fixture.observations.read_text(encoding="utf-8"))
            duplicate = dict(data["observations"][0])
            duplicate["observation_id"] = "obs-duplicate"
            data["observations"].append(duplicate)
            dump_json(fixture.observations, data)
            with self.assertRaisesRegex(TrustError, "duplicate Reground relation_id"):
                load_reground_observations(fixture.observations)

    def test_unknown_relation_observation_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            data = json.loads(fixture.observations.read_text(encoding="utf-8"))
            data["observations"][0]["relation_id"] = "relation-" + "0" * 32
            dump_json(fixture.observations, data)
            with self.assertRaisesRegex(TrustError, "unknown relation"):
                fixture.assess()

    def test_invalid_supplied_ledger_fails_instead_of_becoming_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            fixture.reground_fixture.ledger.write_bytes(b"not sqlite")
            with self.assertRaisesRegex(TrustError, "invalid Evidence Ledger"):
                fixture.assess()

    def test_symlink_inputs_and_broken_output_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = TrustReadinessFixture(root)
            request_link = root / "request-link.json"
            output_link = root / "output-link.json"
            try:
                request_link.symlink_to(fixture.request)
                output_link.symlink_to(root / "missing-target.json")
            except (OSError, NotImplementedError):
                return
            with self.assertRaisesRegex(TrustError, "symlink"):
                assess_trust(request_link, fixture.profile)
            with self.assertRaisesRegex(TrustError, "symlink"):
                write_trust_report(output_link, fixture.assess())


class TrustIntegrityHardeningTests(unittest.TestCase):
    def test_rehashed_risk_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            report = fixture.assess()
            report["risk"]["effective_band"] = "R0"
            report["task_advisory"]["risk_band"] = "R0"
            report["task_advisory"]["review_requirement"] = "HUMAN_CONFIRMATION_REQUIRED"
            rehash_report(report)
            errors = verify_trust_report_data(report)
            self.assertTrue(any("risk projection mismatch" in error for error in errors))

    def test_rehashed_readiness_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            report = assess_trust(
                fixture.request,
                fixture.profile,
                generated_at="2026-07-25T02:00:00Z",
            )
            report["readiness"] = {
                "status": "READY_FOR_HUMAN_COMPARISON",
                "conditions": {"forged": True},
                "failed_conditions": [],
                "next_step": "HUMAN_CONFIRMED_DECISION_COMPARISON",
            }
            rehash_report(report)
            errors = verify_trust_report_data(report)
            self.assertTrue(any("readiness projection mismatch" in error for error in errors))

    def test_missing_positive_or_negative_sample_cannot_claim_perfect_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            observations = json.loads(fixture.observations.read_text(encoding="utf-8"))
            current = next(
                item
                for item in observations["observations"]
                if item["expected_status"] == "CURRENT"
            )
            observations["observations"] = [current]
            dump_json(fixture.observations, observations)
            request = json.loads(fixture.request.read_text(encoding="utf-8"))
            request["readiness_policy"]["min_reground_coverage"] = 0.5
            dump_json(fixture.request, request)
            report = fixture.assess()
            self.assertIsNone(report["evidence"]["reground"]["precision"])
            self.assertIsNone(report["evidence"]["reground"]["recall"])
            self.assertEqual("NOT_READY", report["readiness"]["status"])
            self.assertIn("reground_precision_threshold", report["readiness"]["failed_conditions"])

    def test_policy_evaluation_mismatch_is_not_ready_and_hard_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            report = fixture.assess(evaluation_report=fixture.policy_fixture.report_ab)
            self.assertFalse(report["evidence"]["policy"]["active_evaluation_match"])
            self.assertEqual("NOT_READY", report["readiness"]["status"])
            self.assertIn(
                "POLICY_EVALUATION_MISSING",
                report["task_advisory"]["triggered_hard_gates"],
            )

    def test_source_replay_detects_changed_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            report = fixture.assess()
            fixture.write_request(changed_files=["docs/changed.md"])
            errors = verify_trust_report_sources(report, **fixture.source_args())
            self.assertTrue(any("source replay" in error for error in errors))

    def test_atomic_replace_failure_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            report = fixture.assess()
            output = Path(tmp) / "report.json"
            output.write_bytes(b"original\n")
            with patch("review_system.trust.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_trust_report(output, report)
            self.assertEqual(b"original\n", output.read_bytes())
            self.assertEqual([], list(output.parent.glob(output.name + ".*.tmp")))


if __name__ == "__main__":
    unittest.main()

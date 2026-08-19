from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from review_system.identity import canonical_json_sha256
from review_system.io import dump_json, load_data
from review_system.trust import write_trust_report
from review_system.trust_comparison import load_registry, new_registry, write_registry
from review_system.trust_prospective_evidence import (
    ProspectiveEvidenceError,
    campaign_progress,
    intake_prospective_case,
    record_case_outcome,
    snapshot_campaign,
    verify_campaign_report_data,
)
from test_trust_gate import TrustReadinessFixture
from test_trust_reconciliation import ReconciliationFixture


GENERATED_AT = "2026-08-18T01:00:00Z"
CAPTURED_AT = "2026-08-18T02:00:00Z"
REVIEWED_AT = "2026-08-18T03:00:00Z"


def policy() -> dict:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0.0",
        "mode": "REPORT_ONLY",
        "target_band": "R0",
        "thresholds": {
            "minimum_r0_assessment_count": 20,
            "minimum_r0_reviewed_count": 20,
            "minimum_r0_conclusive_outcome_count": 12,
            "minimum_r0_confirmed_safe_count": 12,
            "minimum_confirmed_unsafe_challenge_count": 8,
            "minimum_r0_independent_audit_count": 5,
            "minimum_r0_outcome_coverage": 0.6,
            "minimum_r0_evidence_span_days": 14,
            "maximum_r0_false_negatives": 0,
            "maximum_r0_false_negative_rate": 0.0,
        },
    }


def init_workspace(root: Path, project_id: str = "demo") -> Path:
    workspace = root / "campaign"
    workspace.mkdir()
    dump_json(
        workspace / "acquisition-attestation.json",
        {
            "schema_version": "1.0",
            "project_id": project_id,
            "evidence_origin": "RUNTIME_OBSERVED",
            "synthetic_evidence_used": False,
            "sample_evidence_used": False,
            "thresholds_relaxed": False,
            "attested_by": "campaign-owner",
            "attested_at": "2026-08-18T00:00:00Z",
        },
    )
    write_registry(
        workspace / "comparison-registry.json",
        new_registry(project_id, created_at="2026-08-18T00:00:00Z"),
    )
    dump_json(
        workspace / "reconciliation-sources.json",
        {
            "schema_version": "1.0",
            "project_id": project_id,
            "assessment_sources": [],
            "outcome_sources": [],
        },
    )
    dump_json(workspace / "observation-policy.json", policy())
    return workspace


def build_r0_case(root: Path, *, task_id: str = "TASK-R0-001", revision_char: str = "a", generated_at: str = GENERATED_AT):
    source_root = root / f"source-{task_id}-{generated_at.replace(':', '')}"
    source_root.mkdir()
    fixture = TrustReadinessFixture(source_root)
    fixture.write_request(task_class="formatting", changed_files=["reports/r0.report.json"])
    request = load_data(fixture.request)
    request["task_id"] = task_id
    request["source_revision"] = "git:" + revision_char * 40
    dump_json(fixture.request, request)
    report = fixture.assess(generated_at=generated_at)
    assert report["risk"]["effective_band"] == "R0", report["risk"]
    report_path = source_root / "trust-report.json"
    write_trust_report(report_path, report)
    return fixture, report, report_path


def intake(workspace: Path, fixture: TrustReadinessFixture, report_path: Path, *, captured_at: str = CAPTURED_AT):
    return intake_prospective_case(
        workspace,
        trust_report=report_path,
        request=fixture.request,
        profile=fixture.profile,
        ledger=fixture.reground_fixture.ledger,
        policy_registry=fixture.policy_registry,
        evaluation_report=fixture.evaluation_report,
        reground_report=fixture.reground_report,
        reground_observations=fixture.observations,
        captured_at=captured_at,
    )


class ProspectiveEvidenceTests(unittest.TestCase):
    def test_exact_trust_source_replay_intake_is_idempotent_and_progresses_without_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            fixture, _report, report_path = build_r0_case(root)
            first = intake(workspace, fixture, report_path)
            second = intake(workspace, fixture, report_path)
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(first["assessment_id"], second["assessment_id"])
            _, registry = load_registry(workspace / "comparison-registry.json")
            self.assertEqual(1, len(registry["assessments"]))
            progress = campaign_progress(workspace, generated_at="2026-08-18T04:00:00Z")
            self.assertEqual([], verify_campaign_report_data(progress))
            self.assertEqual("COLLECTING_EVIDENCE", progress["status"])
            self.assertEqual(1, progress["observation"]["r0_assessment_count"])
            self.assertEqual(0, progress["observation"]["r0_reviewed_count"])
            self.assertTrue(progress["reconciliation"]["source_reconciliation_complete"])
            self.assertFalse(progress["automation_authorized"])
            self.assertFalse(progress["pilot_authorized"])

    def test_same_task_revision_with_different_trust_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            fixture, _report, report_path = build_r0_case(root, task_id="TASK-R0-DUP")
            intake(workspace, fixture, report_path)
            second_report = fixture.assess(generated_at="2026-08-18T01:30:00Z")
            second_path = fixture.root / "trust-report-second.json"
            write_trust_report(second_path, second_report)
            with self.assertRaisesRegex(ProspectiveEvidenceError, "different Trust report"):
                intake(workspace, fixture, second_path, captured_at="2026-08-18T02:30:00Z")
            _, registry = load_registry(workspace / "comparison-registry.json")
            self.assertEqual(1, len(registry["assessments"]))

    def test_capture_before_trust_generation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            fixture, _report, report_path = build_r0_case(root)
            with self.assertRaisesRegex(ProspectiveEvidenceError, "must not precede"):
                intake(workspace, fixture, report_path, captured_at="2026-08-18T00:59:59Z")

    def test_non_exact_git_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            fixture, _report, _report_path = build_r0_case(root)
            request = load_data(fixture.request)
            request["source_revision"] = "git:abc1234"
            dump_json(fixture.request, request)
            report = fixture.assess(generated_at=GENERATED_AT)
            report_path = fixture.root / "trust-report-short-revision.json"
            write_trust_report(report_path, report)
            with self.assertRaisesRegex(ProspectiveEvidenceError, "exact 40-hex"):
                intake(workspace, fixture, report_path)


if __name__ == "__main__":
    unittest.main()

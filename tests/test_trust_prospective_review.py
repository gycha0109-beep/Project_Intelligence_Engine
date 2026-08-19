from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from review_system.github.source import refresh_source_hash
from review_system.github_prospective_capture import (
    build_github_prospective_capture_candidate,
    write_github_prospective_capture_candidate,
)
from review_system.io import dump_json, load_data
from review_system.trust import write_trust_report
from review_system.trust_comparison import load_registry
from review_system.trust_prospective_evidence import campaign_progress, intake_prospective_case
from review_system.trust_prospective_review import (
    ProspectiveReviewError,
    prepare_review_packet,
    submit_review_packet,
    verify_review_packet_data,
    write_review_packet,
)
from test_github_prospective_capture import HEAD, _source
from test_trust_gate import TrustReadinessFixture
from test_trust_prospective_evidence import init_workspace


PACKET_AT = "2026-08-19T02:00:00Z"
REVIEW_AT = "2026-08-19T02:10:00Z"
CHANGED_PATH = "reports/r0.report.json"


def github_source(*, head: str = HEAD, changed_path: str = CHANGED_PATH) -> dict:
    value = deepcopy(_source(head=head, local_head=head, dirty=False))
    value["pull_request"]["changed_files"] = [
        {"path": changed_path, "additions": 1, "deletions": 0}
    ]
    refresh_source_hash(value)
    return value


def build_governed_case(root: Path):
    fixture = TrustReadinessFixture(root / "sources")
    source = github_source()
    candidate = build_github_prospective_capture_candidate(
        source,
        fixture.profile,
        generated_at="2026-08-19T01:00:00Z",
    )
    request = load_data(fixture.request)
    request.update(
        {
            "task_id": candidate["task_id"],
            "source_revision": "git:" + HEAD,
            "task_class": "formatting",
            "changed_files": candidate["changed_files"],
            "required_scenarios": [],
            "completed_scenarios": [],
            "repository_match": True,
            "head_match": True,
            "rollback_evidence": False,
            "replay_evidence": False,
        }
    )
    dump_json(fixture.request, request)
    report = fixture.assess(generated_at="2026-08-19T01:10:00Z")
    report_path = fixture.root / "prospective-trust-report.json"
    write_trust_report(report_path, report)
    workspace = init_workspace(root)
    intake = intake_prospective_case(
        workspace,
        trust_report=report_path,
        request=fixture.request,
        profile=fixture.profile,
        ledger=fixture.reground_fixture.ledger,
        policy_registry=fixture.policy_registry,
        evaluation_report=fixture.evaluation_report,
        reground_report=fixture.reground_report,
        reground_observations=fixture.observations,
        captured_at="2026-08-19T01:20:00Z",
    )
    candidate_path = write_github_prospective_capture_candidate(
        root / "github-candidate.json",
        candidate,
    )
    return fixture, source, candidate, candidate_path, workspace, intake


def prepare(root: Path, workspace: Path, assessment_id: str, candidate_path: Path, source: dict):
    return prepare_review_packet(
        workspace,
        assessment_id=assessment_id,
        github_candidate=candidate_path,
        repository_root=root,
        github_cli=object(),
        generated_at=PACKET_AT,
        collect_pr=lambda *args, **kwargs: (deepcopy(source), None),
    )


class GovernedProspectiveReviewTests(unittest.TestCase):
    def test_prepare_packet_is_deterministic_and_does_not_mutate_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, source, candidate, candidate_path, workspace, intake = build_governed_case(root)
            registry_path = workspace / "comparison-registry.json"
            before = registry_path.read_bytes()
            first = prepare(root, workspace, intake["assessment_id"], candidate_path, source)
            second = prepare(root, workspace, intake["assessment_id"], candidate_path, source)
            self.assertEqual(before, registry_path.read_bytes())
            self.assertEqual([], verify_review_packet_data(first))
            self.assertEqual(first["packet_id"], second["packet_id"])
            self.assertEqual(first["packet_sha256"], second["packet_sha256"])
            self.assertEqual("git:" + HEAD, first["source_revision"])
            self.assertEqual(candidate["candidate_id"], first["github"]["candidate_id"])
            self.assertEqual("demo/repo", first["github"]["repository"])
            self.assertEqual(7, first["github"]["pr_number"])
            self.assertEqual([CHANGED_PATH], first["changed_files"])
            self.assertFalse(first["human_review_recorded"])
            self.assertFalse(first["outcome_recorded"])
            self.assertFalse(first["automation_authorized"])
            self.assertFalse(first["pilot_authorized"])

    def test_submit_binds_exact_packet_to_existing_stage10b_human_decision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, source, _candidate, candidate_path, workspace, intake = build_governed_case(root)
            packet = prepare(root, workspace, intake["assessment_id"], candidate_path, source)
            packet_path = write_review_packet(root / "review-packet.json", packet)
            result = submit_review_packet(
                packet_path,
                workspace_root=workspace,
                github_candidate=candidate_path,
                repository_root=root,
                github_cli=object(),
                review_level="REVIEWED",
                decision="APPROVE",
                actor="reviewer-a",
                occurred_at=REVIEW_AT,
                confirmed_risk_band="R0",
                collect_pr=lambda *args, **kwargs: (deepcopy(source), None),
            )
            _, registry = load_registry(workspace / "comparison-registry.json")
            event = registry["events"][-1]
            self.assertEqual("HUMAN_DECISION", event["event_type"])
            self.assertEqual("REVIEWED", event["payload"]["review_level"])
            self.assertEqual("APPROVE", event["payload"]["decision"])
            self.assertIn("REVIEW_PACKET_ID:" + packet["packet_id"], event["payload"]["reason_codes"])
            self.assertIn("REVIEW_PACKET_SHA256:" + packet["packet_sha256"], event["payload"]["reason_codes"])
            self.assertEqual(packet["packet_id"], result["review_packet_id"])
            archive = Path(result["review_packet_archive"])
            self.assertTrue((archive / "review-packet.json").is_file())
            self.assertTrue((archive / "github-capture-candidate.json").is_file())
            progress = campaign_progress(workspace, generated_at="2026-08-19T03:00:00Z")
            self.assertEqual(1, progress["observation"]["r0_reviewed_count"])
            self.assertTrue(progress["reconciliation"]["source_reconciliation_complete"])

    def test_duplicate_exact_packet_submission_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, source, _candidate, candidate_path, workspace, intake = build_governed_case(root)
            packet = prepare(root, workspace, intake["assessment_id"], candidate_path, source)
            packet_path = write_review_packet(root / "review-packet.json", packet)
            arguments = dict(
                workspace_root=workspace,
                github_candidate=candidate_path,
                repository_root=root,
                github_cli=object(),
                review_level="REVIEWED",
                decision="APPROVE",
                actor="reviewer-a",
                occurred_at=REVIEW_AT,
                confirmed_risk_band="R0",
                collect_pr=lambda *args, **kwargs: (deepcopy(source), None),
            )
            submit_review_packet(packet_path, **arguments)
            with self.assertRaisesRegex(ProspectiveReviewError, "review packet archive already exists|duplicate review submission"):
                submit_review_packet(packet_path, **arguments)
            _, registry = load_registry(workspace / "comparison-registry.json")
            self.assertEqual(1, len([event for event in registry["events"] if event["event_type"] == "HUMAN_DECISION"]))

    def test_audited_decision_does_not_create_independent_audit_outcome_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, source, _candidate, candidate_path, workspace, intake = build_governed_case(root)
            packet = prepare(root, workspace, intake["assessment_id"], candidate_path, source)
            packet_path = write_review_packet(root / "review-packet.json", packet)
            submit_review_packet(
                packet_path,
                workspace_root=workspace,
                github_candidate=candidate_path,
                repository_root=root,
                github_cli=object(),
                review_level="AUDITED",
                decision="APPROVE",
                actor="reviewer-a",
                occurred_at=REVIEW_AT,
                confirmed_risk_band="R0",
                collect_pr=lambda *args, **kwargs: (deepcopy(source), None),
            )
            _, registry = load_registry(workspace / "comparison-registry.json")
            self.assertEqual(1, registry["metrics"]["maturity"]["audited_decision_count"])
            self.assertEqual(0, registry["metrics"]["maturity"]["independent_audit_count"])
            self.assertEqual([], [event for event in registry["events"] if event["event_type"] == "OUTCOME"])


if __name__ == "__main__":
    unittest.main()

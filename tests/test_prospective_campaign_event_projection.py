from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from review_system.evaluation import load_evaluation_report, run_evaluation, write_evaluation_report
from review_system.identity import canonical_json_sha256
from review_system.io import dump_json, dump_yaml, load_data
from review_system.prospective_campaign_event_projection import (
    PROJECTION_SCHEMA_VERSION,
    ProspectiveCampaignEventProjectionError,
    project_governed_campaign_events,
)
from review_system.trust import write_trust_report
from review_system.trust_comparison import load_registry, record_decision, write_registry
from review_system.trust_outcome_declaration import build_outcome_declaration
from review_system.trust_prospective_mutation import record_case_outcome, record_case_review
from test_evaluation import EvaluationFixture
from test_trust_gate import TrustReadinessFixture
from test_trust_prospective_evidence import init_workspace, intake


PACKET_ID = "prospective-review-packet-" + "a" * 32
PACKET_GENERATED_AT = "2026-08-18T02:30:00Z"
REVIEWED_AT = "2026-08-18T03:00:00Z"
OUTCOME_AT = "2026-08-18T04:00:00Z"
REVIEW_ACTOR = "human:auto4c-reviewer@example.test"
OUTCOME_ACTOR = "human:auto4c-outcome@example.test"
HOLDOUT_REVISION = "git:" + "1" * 40


def _write_packet(workspace: Path, assessment_id: str) -> tuple[str, str]:
    packet = {
        "schema_version": "1.0",
        "packet_contract": "GOVERNED_PROSPECTIVE_REVIEW_PACKET_V1",
        "packet_id": PACKET_ID,
        "project_id": "demo",
        "assessment_id": assessment_id,
        "generated_at": PACKET_GENERATED_AT,
        "mode": "REPORT_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "human_review_recorded": False,
        "outcome_recorded": False,
    }
    packet_sha = canonical_json_sha256(packet)
    packet["packet_sha256"] = packet_sha
    archive = workspace / "cases" / assessment_id / "reviews" / PACKET_ID
    archive.mkdir(parents=True)
    (archive / "review-packet.json").write_text(
        json.dumps(packet, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (archive / "github-candidate.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "candidate_id": "github-candidate-auto4c",
                "assessment_id": assessment_id,
                "mode": "REPORT_ONLY",
                "automation_authorized": False,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return PACKET_ID, packet_sha


def _authority_bound_r0_case(root: Path) -> tuple[TrustReadinessFixture, dict, Path]:
    evaluation_root = root / "auto4c-evaluation"
    evaluation_root.mkdir()
    evaluation_fixture = EvaluationFixture(evaluation_root)
    dataset = load_data(evaluation_fixture.dataset)
    revisions = {
        "development": "git:" + "2" * 40,
        "validation": "git:" + "3" * 40,
        "holdout": HOLDOUT_REVISION,
    }
    for case in dataset["cases"]:
        case["source_revision"] = revisions[case["split"]]
    dump_yaml(evaluation_fixture.dataset, dataset)
    evaluation = run_evaluation(
        evaluation_fixture.dataset,
        evaluation_fixture.baseline,
        evaluation_fixture.challenger,
    )
    if evaluation["gate"]["decision"] != "PASS":
        raise AssertionError(evaluation["gate"])
    write_evaluation_report(evaluation_fixture.report, evaluation)

    trust_root = root / "auto4c-trust"
    trust_root.mkdir()
    trust_fixture = TrustReadinessFixture(trust_root)
    trust_fixture.evaluation_report = evaluation_fixture.report
    trust_fixture.write_request(task_class="formatting", changed_files=["reports/r0.report.json"])
    request = load_data(trust_fixture.request)
    request["task_id"] = "TASK-AUTO4C-001"
    request["source_revision"] = HOLDOUT_REVISION
    dump_json(trust_fixture.request, request)
    report = trust_fixture.assess(
        generated_at="2026-08-18T01:00:00Z",
        evaluation_report=evaluation_fixture.report,
    )
    if report["risk"]["effective_band"] != "R0":
        raise AssertionError(report["risk"])
    report_path = trust_root / "trust-report-auto4c.json"
    write_trust_report(report_path, report)
    return trust_fixture, report, report_path


def _fixture(root: Path, *, with_outcome: bool) -> dict:
    base_root = root / "base"
    base_root.mkdir()
    base = init_workspace(base_root, project_id="demo")
    trust_fixture, _report, report_path = _authority_bound_r0_case(base_root)
    intake(base, trust_fixture, report_path, captured_at="2026-08-18T02:00:00Z")

    source = root / "source-campaign"
    destination = root / "destination-campaign"
    shutil.copytree(base, source, copy_function=shutil.copy2)
    shutil.copytree(base, destination, copy_function=shutil.copy2)

    _, registry = load_registry(source / "comparison-registry.json")
    assessment = registry["assessments"][0]
    packet_id, packet_sha = _write_packet(source, assessment["assessment_id"])
    record_case_review(
        source,
        assessment_id=assessment["assessment_id"],
        review_level="REVIEWED",
        decision="APPROVE",
        actor=REVIEW_ACTOR,
        review_packet_id=packet_id,
        review_packet_sha256=packet_sha,
        occurred_at=REVIEWED_AT,
        confirmed_risk_band="R0",
        reason_codes=["AUTO4C_FIXTURE_REVIEW"],
    )
    _, registry = load_registry(source / "comparison-registry.json")
    review_event = registry["events"][0]

    declaration_path = None
    if with_outcome:
        record_case_outcome(
            source,
            assessment_id=assessment["assessment_id"],
            outcome_type="CONTROLLED_EVALUATION",
            verdict="SAFE",
            actor=OUTCOME_ACTOR,
            occurred_at=OUTCOME_AT,
            evaluation_report=trust_fixture.evaluation_report,
        )
        _, registry = load_registry(source / "comparison-registry.json")
        outcome_event = registry["events"][1]
        if outcome_event["payload"]["outcome_type"] != "CONTROLLED_EVALUATION":
            raise AssertionError(outcome_event)
        _, evaluation = load_evaluation_report(trust_fixture.evaluation_report)
        declaration = build_outcome_declaration(
            actor=OUTCOME_ACTOR,
            project_id="demo",
            assessment_id=assessment["assessment_id"],
            source_revision=assessment["source_revision"],
            trust_report_id=assessment["trust_report_id"],
            trust_report_sha256=assessment["trust_report_sha256"],
            review_event_id=review_event["event_id"],
            review_event_sha256=review_event["event_sha256"],
            review_level=review_event["payload"]["review_level"],
            decision=review_event["payload"]["decision"],
            review_packet_id=packet_id,
            review_packet_sha256=packet_sha,
            authority_type="CONTROLLED_EVALUATION",
            verdict="SAFE",
            declared_at=OUTCOME_AT,
            evaluation_id=evaluation["evaluation_id"],
            evaluation_report_sha256=evaluation["report_sha256"],
        )
        declaration_path = root / "outcome-declaration.json"
        dump_json(declaration_path, declaration)

    return {
        "source": source,
        "destination": destination,
        "assessment": assessment,
        "declaration": declaration_path,
    }


class ProspectiveCampaignEventProjectionTests(unittest.TestCase):
    def test_review_projection_reproduces_exact_governed_event_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _fixture(root, with_outcome=False)

            initial = project_governed_campaign_events(
                fixture["destination"],
                source_workspace=fixture["source"],
                generated_at="2026-08-18T05:00:00Z",
            )
            self.assertEqual(PROJECTION_SCHEMA_VERSION, initial["schema_version"])
            self.assertEqual("AUTO-4C", initial["stage"])
            self.assertEqual("GOVERNED_EVENTS_PROJECTED", initial["status"])
            self.assertEqual(1, initial["projected_review_count"])
            self.assertEqual(0, initial["projected_outcome_count"])
            self.assertTrue(initial["human_review_projected"])
            self.assertFalse(initial["outcome_projected"])
            self.assertFalse(initial["automatic_human_review_inference"])
            self.assertFalse(initial["automatic_outcome_inference"])
            self.assertFalse(initial["automation_authorized"])
            self.assertFalse(initial["pilot_authorized"])
            self.assertFalse(initial["merge_authorized"])
            self.assertFalse(initial["deploy_authorized"])
            self.assertFalse(initial["production_effect_authorized"])

            _, source_registry = load_registry(fixture["source"] / "comparison-registry.json")
            _, destination_registry = load_registry(fixture["destination"] / "comparison-registry.json")
            self.assertEqual(source_registry["events"], destination_registry["events"])

            replay = project_governed_campaign_events(
                fixture["destination"],
                source_workspace=fixture["source"],
                generated_at="2026-08-18T05:00:00Z",
            )
            self.assertEqual(0, replay["projected_review_count"])
            self.assertEqual(1, replay["idempotent_review_count"])
            self.assertFalse(replay["workspace_mutation_performed"])
            self.assertEqual(initial["registry_sha256"], replay["registry_sha256"])
            self.assertEqual(initial["campaign_evidence_snapshot_sha256"], replay["campaign_evidence_snapshot_sha256"])

    def test_outcome_requires_explicit_declaration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _fixture(root, with_outcome=True)
            with self.assertRaises(ProspectiveCampaignEventProjectionError) as caught:
                project_governed_campaign_events(
                    fixture["destination"],
                    source_workspace=fixture["source"],
                    generated_at="2026-08-18T05:00:00Z",
                )
            self.assertEqual("DECLARATION_REQUIRED", caught.exception.code)
            _, destination_registry = load_registry(fixture["destination"] / "comparison-registry.json")
            self.assertEqual([], destination_registry["events"])

    def test_declaration_bound_outcome_projection_reproduces_exact_event_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _fixture(root, with_outcome=True)
            report = project_governed_campaign_events(
                fixture["destination"],
                source_workspace=fixture["source"],
                declarations=[fixture["declaration"]],
                generated_at="2026-08-18T05:00:00Z",
            )
            self.assertEqual(1, report["projected_review_count"])
            self.assertEqual(1, report["projected_outcome_count"])
            self.assertTrue(report["human_review_projected"])
            self.assertTrue(report["outcome_projected"])
            self.assertFalse(report["automatic_outcome_inference"])
            self.assertEqual(1, report["r0_reviewed_count"])
            self.assertEqual(1, report["r0_conclusive_outcome_count"])

            _, source_registry = load_registry(fixture["source"] / "comparison-registry.json")
            _, destination_registry = load_registry(fixture["destination"] / "comparison-registry.json")
            self.assertEqual(source_registry["events"], destination_registry["events"])

            replay = project_governed_campaign_events(
                fixture["destination"],
                source_workspace=fixture["source"],
                declarations=[fixture["declaration"]],
                generated_at="2026-08-18T05:00:00Z",
            )
            self.assertEqual(0, replay["projected_review_count"])
            self.assertEqual(1, replay["idempotent_review_count"])
            self.assertEqual(0, replay["projected_outcome_count"])
            self.assertEqual(1, replay["idempotent_outcome_count"])
            self.assertFalse(replay["workspace_mutation_performed"])

    def test_divergent_destination_event_chain_is_rejected_before_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _fixture(root, with_outcome=False)
            registry_path = fixture["destination"] / "comparison-registry.json"
            _, registry = load_registry(registry_path)
            changed = record_decision(
                registry,
                assessment_id=fixture["assessment"]["assessment_id"],
                review_level="WORKFLOW_ACCEPTED",
                decision="HOLD",
                actor="workflow:other",
                occurred_at=REVIEWED_AT,
                reason_codes=["DIFFERENT_LINEAGE"],
            )
            write_registry(registry_path, changed)

            with self.assertRaises(ProspectiveCampaignEventProjectionError) as caught:
                project_governed_campaign_events(
                    fixture["destination"],
                    source_workspace=fixture["source"],
                    generated_at="2026-08-18T05:00:00Z",
                )
            self.assertEqual("LINEAGE_MISMATCH", caught.exception.code)
            _, after = load_registry(registry_path)
            self.assertEqual(changed["registry_sha256"], after["registry_sha256"])

    def test_destination_cannot_extend_beyond_governed_source_event_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _fixture(root, with_outcome=False)
            project_governed_campaign_events(
                fixture["destination"],
                source_workspace=fixture["source"],
                generated_at="2026-08-18T05:00:00Z",
            )
            registry_path = fixture["destination"] / "comparison-registry.json"
            _, registry = load_registry(registry_path)
            extended = record_decision(
                registry,
                assessment_id=fixture["assessment"]["assessment_id"],
                review_level="WORKFLOW_ACCEPTED",
                decision="HOLD",
                actor="workflow:destination-only",
                occurred_at="2026-08-18T03:30:00Z",
                reason_codes=["DESTINATION_ONLY_EVENT"],
            )
            write_registry(registry_path, extended)

            with self.assertRaises(ProspectiveCampaignEventProjectionError) as caught:
                project_governed_campaign_events(
                    fixture["destination"],
                    source_workspace=fixture["source"],
                    generated_at="2026-08-18T05:00:00Z",
                )
            self.assertEqual("LINEAGE_MISMATCH", caught.exception.code)
            _, after = load_registry(registry_path)
            self.assertEqual(extended["registry_sha256"], after["registry_sha256"])


if __name__ == "__main__":
    unittest.main()

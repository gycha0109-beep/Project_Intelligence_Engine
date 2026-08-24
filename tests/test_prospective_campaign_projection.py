from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.identity import file_sha256
from review_system.io import load_data
from review_system.prospective_campaign_projection import (
    PROJECTION_SCHEMA_VERSION,
    ProspectiveCampaignProjectionError,
    project_auto2_artifacts_to_campaign,
)
from review_system.prospective_evidence_bundle import write_evidence_bundle
from review_system.prospective_execution_identity import build_prospective_execution_identity
from review_system.prospective_trust_bridge import build_bridge_result_projection
from review_system.prospective_trust_bridge_result import stabilize_trusted_bridge_result
from review_system.trust_comparison import load_registry
from test_trust_prospective_evidence import build_r0_case, init_workspace, intake


REPOSITORY = "demo/repo"
HEAD = "c" * 40
BASE = "d" * 40
PIE_REVISION = "a" * 40
GENERATED_AT = "2026-08-18T04:00:00Z"


def _packet(*, assessment: dict, transport: str) -> dict:
    return {
        "schema_version": "1.0",
        "packet_contract": "GOVERNED_PROSPECTIVE_REVIEW_PACKET_V1",
        "packet_id": "prospective-review-packet-" + transport[:32],
        "packet_sha256": transport * 2,
        "project_id": "demo",
        "assessment_id": assessment["assessment_id"],
        "assessment_sha256": assessment["assessment_sha256"],
        "task_id": assessment["task_id"],
        "source_revision": assessment["source_revision"],
        "trust_report_id": assessment["trust_report_id"],
        "trust_report_sha256": assessment["trust_report_sha256"],
        "github": {
            "candidate_id": "github-capture-stable",
            "candidate_evidence_snapshot_sha256": transport * 2,
            "candidate_report_sha256": transport[::-1] * 2,
            "hostname": "github.com",
            "repository": REPOSITORY,
            "pr_number": 7,
            "pr_url": "https://github.com/demo/repo/pull/7",
            "base_oid": BASE,
            "head_oid": HEAD,
        },
        "predicted_risk_band": assessment["predicted_risk_band"],
        "changed_files": ["reports/r0.report.json"],
        "hard_gates": [],
        "review_requirement": "REVIEWED",
        "evidence_references": {"trust_evidence_fingerprint_sha256": "4" * 64},
        "source_replay_state": {
            "trust_sources_verified": True,
            "assessment_source_sha256": "5" * 64,
            "assessment_reconciled": True,
            "assessment_reconciliation_status": "RECONCILED",
        },
        "reconciliation_state": {"status": "RECONCILED", "source_reconciliation_complete": True},
        "generated_at": "2026-08-18T03:00:00Z" if transport[0] == "6" else "2026-08-18T03:10:00Z",
        "mode": "REPORT_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "human_review_recorded": False,
        "outcome_recorded": False,
        "evidence_snapshot_sha256": transport[::-1] * 2,
    }


def _artifact(root: Path, name: str, *, transport: str) -> Path:
    artifact = root / name
    bridge = artifact / "bridge"
    bridge.mkdir(parents=True)

    workspace = init_workspace(bridge, project_id="demo")
    fixture, report, report_path = build_r0_case(
        bridge,
        task_id="TASK-AUTO4B-001",
        revision_char="c",
        generated_at="2026-08-18T01:00:00Z",
    )
    result = intake(workspace, fixture, report_path, captured_at="2026-08-18T02:00:00Z")
    workspace.rename(bridge / "workspace")
    workspace = bridge / "workspace"
    _, registry = load_registry(workspace / "comparison-registry.json")
    assessment = registry["assessments"][0]
    request = load_data(fixture.request)

    source_dir = bridge / "source"
    source_dir.mkdir()
    trust_request_path = source_dir / "trust-request.json"
    trust_request_path.write_bytes(fixture.request.read_bytes())
    request_sha256 = file_sha256(trust_request_path)
    source_evidence = {
        "schema_version": "1.0",
        "source_contract": "PIE_AUTO2_TRUST_REQUEST_SOURCE_V1",
        "bridge_contract": "PIE_AUTO2_HUMAN_REVIEW_BRIDGE_V1",
        "mode": "REPORT_ONLY",
        "authority": {
            "repository": "gycha0109-beep/Project_Intelligence_Engine",
            "revision": PIE_REVISION,
            "committed_at": "2026-08-18T01:00:00Z",
            "path": "evidence/trust/requests/auto4b-test.json",
            "provider_blob_sha": "b" * 40,
            "content_sha256": request_sha256,
        },
        "target": {
            "repository": REPOSITORY,
            "pull_request": 7,
            "head_sha": HEAD,
            "base_sha": BASE,
            "changed_files": request["changed_files"],
            "project_id": "demo",
        },
        "trust_request": {"task_id": request["task_id"], "source_revision": request["source_revision"]},
        "human_review_recorded": False,
        "outcome_recorded": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
    }
    (source_dir / "trust-request-source.json").write_text(
        json.dumps(source_evidence, indent=2) + "\n",
        encoding="utf-8",
    )

    packet = _packet(assessment=assessment, transport=transport)
    packet_source = bridge / "packet-source.json"
    packet_source.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    identity = build_prospective_execution_identity(
        repository=REPOSITORY,
        pull_request=7,
        source_revision=HEAD,
        pie_revision=PIE_REVISION,
        profile_sha256="1" * 64,
        config_sha256="2" * 64,
        trust_request_sha256=request_sha256,
    ).to_dict()
    summary = {
        "schema_version": "PIE_PR_PROSPECTIVE_RUN_V1",
        "execution_id": identity["execution_id"],
        "repository": REPOSITORY,
        "pull_request": 7,
        "source_revision": HEAD,
        "pie_revision": PIE_REVISION,
        "status": "READY_FOR_HUMAN_REVIEW",
        "assessment_id": assessment["assessment_id"],
        "packet_id": packet["packet_id"],
        "risk_band": report["risk"]["effective_band"],
        "human_review_recorded": False,
        "outcome_recorded": False,
        "automation_authorized": False,
        "pilot_authorized": False,
    }
    bundle = bridge / "automation" / "bundles" / identity["execution_id"]
    write_evidence_bundle(
        bundle,
        summary=summary,
        identity=identity,
        evidence_files={
            "trust/request.json": trust_request_path,
            "trust/assessment.json": report_path,
            "review/packet.json": packet_source,
        },
    )

    run_result = {
        "status": "READY_FOR_HUMAN_REVIEW",
        "assessment_id": result["assessment_id"],
        "risk_band": report["risk"]["effective_band"],
        "readiness": None,
    }
    projection = build_bridge_result_projection(
        source_evidence=source_evidence,
        run_result=run_result,
        packet=packet,
        request_sha256=request_sha256,
    )
    result_file = bridge / "result.json"
    raw = {
        **projection,
        "deterministic_result_sha256": "0" * 64,
        "bundle": str(bundle),
        "result_file": str(result_file),
    }
    result_file.write_text(json.dumps(projection), encoding="utf-8")
    stabilize_trusted_bridge_result(raw)
    packet_source.unlink()
    return artifact


class ProspectiveCampaignProjectionTests(unittest.TestCase):
    def test_auto2_semantic_replays_project_one_assessment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = _artifact(root, "first", transport="6" * 32)
            second = _artifact(root, "second", transport="7" * 32)
            workspace = root / "project-campaign"

            report = project_auto2_artifacts_to_campaign(
                workspace,
                [first, second],
                generated_at=GENERATED_AT,
            )

            self.assertEqual(PROJECTION_SCHEMA_VERSION, report["schema_version"])
            self.assertEqual("AUTO-4B", report["stage"])
            self.assertEqual("PROJECT_CAMPAIGN_PROJECTED", report["status"])
            self.assertEqual("demo", report["project_id"])
            self.assertEqual(2, report["source_artifact_count"])
            self.assertEqual(1, report["unique_assessment_count"])
            self.assertEqual(1, report["projected_assessment_count"])
            self.assertEqual(1, report["idempotent_assessment_input_count"])
            self.assertEqual(1, report["r0_assessment_count"])
            self.assertEqual(0, report["r0_reviewed_count"])
            self.assertEqual(0, report["r0_conclusive_outcome_count"])
            self.assertTrue(report["source_reconciliation_complete"])
            self.assertTrue(report["workspace_mutation_performed"])
            self.assertTrue(report["campaign_thresholds_evaluated"])
            self.assertFalse(report["human_review_projected"])
            self.assertFalse(report["outcome_projected"])
            self.assertFalse(report["automation_authorized"])
            self.assertFalse(report["pilot_authorized"])
            self.assertFalse(report["merge_authorized"])
            self.assertFalse(report["deploy_authorized"])
            self.assertFalse(report["production_effect_authorized"])

    def test_reprojection_is_idempotent_and_preserves_semantic_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = _artifact(root, "first", transport="6" * 32)
            second = _artifact(root, "second", transport="7" * 32)
            workspace = root / "project-campaign"
            initial = project_auto2_artifacts_to_campaign(workspace, [first, second], generated_at=GENERATED_AT)
            replay = project_auto2_artifacts_to_campaign(workspace, [second, first], generated_at=GENERATED_AT)

            self.assertEqual(0, replay["projected_assessment_count"])
            self.assertEqual(2, replay["idempotent_assessment_input_count"])
            self.assertFalse(replay["workspace_mutation_performed"])
            self.assertEqual(initial["registry_sha256"], replay["registry_sha256"])
            self.assertEqual(initial["campaign_evidence_snapshot_sha256"], replay["campaign_evidence_snapshot_sha256"])
            self.assertEqual(initial["projection_sha256"], replay["projection_sha256"])

    def test_tampered_auto2_deterministic_result_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = _artifact(root, "one", transport="6" * 32)
            result_path = artifact / "bridge" / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["deterministic_result_sha256"] = "0" * 64
            result_path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaises(ProspectiveCampaignProjectionError) as caught:
                project_auto2_artifacts_to_campaign(root / "campaign", [artifact], generated_at=GENERATED_AT)
            self.assertEqual("NON_DETERMINISTIC_REPLAY", caught.exception.code)

    def test_auto2_authority_elevation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = _artifact(root, "one", transport="6" * 32)
            result_path = artifact / "bridge" / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["merge_authorized"] = True
            result_path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaises(ProspectiveCampaignProjectionError) as caught:
                project_auto2_artifacts_to_campaign(root / "campaign", [artifact], generated_at=GENERATED_AT)
            self.assertEqual("AUTHORITY_VIOLATION", caught.exception.code)

    def test_different_source_observation_policies_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = _artifact(root, "first", transport="6" * 32)
            second = _artifact(root, "second", transport="7" * 32)
            policy_path = second / "bridge" / "workspace" / "observation-policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["thresholds"]["minimum_r0_assessment_count"] = 21
            policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")

            with self.assertRaises(ProspectiveCampaignProjectionError) as caught:
                project_auto2_artifacts_to_campaign(root / "campaign", [first, second], generated_at=GENERATED_AT)
            self.assertEqual("POLICY_MISMATCH", caught.exception.code)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from review_system.identity import canonical_json_sha256
from review_system.prospective_campaign_aggregator import (
    AGGREGATION_SCHEMA_VERSION,
    ProspectiveCampaignAggregationError,
    aggregate_prospective_artifacts,
)
from review_system.prospective_evidence_bundle import write_evidence_bundle
from review_system.prospective_execution_identity import build_prospective_execution_identity
from review_system.prospective_replay import REPLAY_SCHEMA_VERSION


REPOSITORY = "example/project"
SOURCE_REVISION = "a" * 40
PIE_REVISION = "b" * 40


def _artifact(
    root: Path,
    name: str,
    *,
    evidence_text: str,
    run_id: str,
    deterministic_marker: str = "stable",
    context_override: dict | None = None,
    authority_override: dict | None = None,
) -> Path:
    artifact_root = root / name
    bundle_root = artifact_root / "bundle"
    source = root / f"{name}-evidence.txt"
    source.write_text(evidence_text, encoding="utf-8")

    identity = build_prospective_execution_identity(
        repository=REPOSITORY,
        pull_request=12,
        source_revision=SOURCE_REVISION,
        pie_revision=PIE_REVISION,
        profile_sha256="1" * 64,
        config_sha256="2" * 64,
        trust_request_sha256=None,
    ).to_dict()
    deterministic_body = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "execution_identity": deepcopy(identity),
        "result": {"status": "WAITING_FOR_TRUST_INPUT"},
        "marker": deterministic_marker,
    }
    deterministic = deepcopy(deterministic_body)
    deterministic["deterministic_result_sha256"] = canonical_json_sha256(deterministic_body)
    summary = {
        "schema_version": "PIE_PR_PROSPECTIVE_RUN_V1",
        "execution_id": identity["execution_id"],
        "repository": REPOSITORY,
        "pull_request": 12,
        "source_revision": SOURCE_REVISION,
        "pie_revision": PIE_REVISION,
        "status": "WAITING_FOR_TRUST_INPUT",
        "deterministic_result_sha256": deterministic["deterministic_result_sha256"],
        "human_review_recorded": False,
        "outcome_recorded": False,
        "automation_authorized": False,
        "pilot_authorized": False,
    }
    manifest = write_evidence_bundle(
        bundle_root,
        summary=summary,
        identity=identity,
        evidence_files={"analysis/evidence.txt": source},
        deterministic_result=deterministic,
    )

    authority = {
        "human_review_recorded": False,
        "outcome_recorded": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
    }
    if authority_override:
        authority.update(authority_override)
    context = {
        "schema_version": "PIE_PROSPECTIVE_WORKFLOW_CONTEXT_V1",
        "workflow_run_id": run_id,
        "workflow_run_attempt": "1",
        "workflow_ref": "example/workflow@refs/heads/main",
        "repository": REPOSITORY,
        "pull_request": 12,
        "source_revision": SOURCE_REVISION,
        "pie_revision": PIE_REVISION,
        "execution_id": identity["execution_id"],
        "deterministic_result_sha256": deterministic["deterministic_result_sha256"],
        "raw_observation_manifest_sha256": manifest["manifest_sha256"],
        "authority": authority,
    }
    if context_override:
        context.update(context_override)
    artifact_root.mkdir(parents=True, exist_ok=True)
    (artifact_root / "workflow-context.json").write_text(
        json.dumps(context, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact_root


class ProspectiveCampaignAggregatorTests(unittest.TestCase):
    def test_same_execution_allows_distinct_raw_provider_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = _artifact(root, "first", evidence_text="raw observation A", run_id="100")
            second = _artifact(root, "second", evidence_text="raw observation B", run_id="101")
            report = aggregate_prospective_artifacts([first, second])

            self.assertEqual(AGGREGATION_SCHEMA_VERSION, report["schema_version"])
            self.assertEqual("AUTO-4A", report["stage"])
            self.assertEqual("ARTIFACT_AGGREGATION_READY", report["status"])
            self.assertEqual(2, report["input_artifact_count"])
            self.assertEqual(2, report["unique_observation_count"])
            self.assertEqual(0, report["duplicate_observation_count"])
            self.assertEqual(1, report["unique_execution_count"])
            self.assertEqual(2, report["executions"][0]["raw_observation_count"])
            self.assertEqual(2, len(report["executions"][0]["raw_observation_manifest_sha256s"]))
            self.assertFalse(report["workspace_mutation_performed"])
            self.assertFalse(report["campaign_thresholds_evaluated"])
            self.assertFalse(report["automation_authorized"])
            self.assertFalse(report["pilot_authorized"])
            self.assertFalse(report["merge_authorized"])
            self.assertFalse(report["deploy_authorized"])
            self.assertFalse(report["production_effect_authorized"])

    def test_duplicate_artifact_input_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = _artifact(root, "one", evidence_text="same", run_id="100")
            report = aggregate_prospective_artifacts([artifact, artifact])
            self.assertEqual(2, report["input_artifact_count"])
            self.assertEqual(1, report["unique_observation_count"])
            self.assertEqual(1, report["duplicate_observation_count"])
            self.assertEqual(1, report["unique_execution_count"])
            self.assertEqual(1, report["executions"][0]["raw_observation_count"])

    def test_conflicting_deterministic_result_for_same_execution_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = _artifact(root, "first", evidence_text="raw A", run_id="100", deterministic_marker="A")
            second = _artifact(root, "second", evidence_text="raw B", run_id="101", deterministic_marker="B")
            with self.assertRaises(ProspectiveCampaignAggregationError) as caught:
                aggregate_prospective_artifacts([first, second])
            self.assertEqual("NON_DETERMINISTIC_REPLAY", caught.exception.code)

    def test_tampered_bundle_fails_integrity_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = _artifact(root, "one", evidence_text="original", run_id="100")
            evidence = artifact / "bundle" / "analysis" / "evidence.txt"
            evidence.write_text("tampered", encoding="utf-8")
            with self.assertRaises(ProspectiveCampaignAggregationError) as caught:
                aggregate_prospective_artifacts([artifact])
            self.assertEqual("EVIDENCE_HASH_MISMATCH", caught.exception.code)

    def test_workflow_context_source_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = _artifact(
                root,
                "one",
                evidence_text="source",
                run_id="100",
                context_override={"source_revision": "c" * 40},
            )
            with self.assertRaises(ProspectiveCampaignAggregationError) as caught:
                aggregate_prospective_artifacts([artifact])
            self.assertEqual("SOURCE_MISMATCH", caught.exception.code)

    def test_workflow_context_cannot_elevate_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = _artifact(
                root,
                "one",
                evidence_text="source",
                run_id="100",
                authority_override={"merge_authorized": True},
            )
            with self.assertRaises(ProspectiveCampaignAggregationError) as caught:
                aggregate_prospective_artifacts([artifact])
            self.assertEqual("AUTHORITY_VIOLATION", caught.exception.code)

    def test_aggregation_semantic_hash_is_input_order_invariant(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = _artifact(root, "first", evidence_text="raw A", run_id="100")
            second = _artifact(root, "second", evidence_text="raw B", run_id="101")
            forward = aggregate_prospective_artifacts([first, second])
            reverse = aggregate_prospective_artifacts([second, first])
            self.assertEqual(forward["aggregation_sha256"], reverse["aggregation_sha256"])
            self.assertEqual(forward["executions"], reverse["executions"])
            self.assertEqual(forward["repositories"], reverse["repositories"])


if __name__ == "__main__":
    unittest.main()

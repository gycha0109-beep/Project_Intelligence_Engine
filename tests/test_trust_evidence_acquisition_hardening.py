from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.trust_comparison import new_registry, write_registry
from review_system.trust_evidence_acquisition import (
    EvidenceAcquisitionError,
    EvidenceAcquisitionVerificationError,
    inspect_acquisition_workspace,
    populate_r0_evidence_package,
    verify_acquisition_report_sources,
)


GENERATED_AT = "2026-08-18T05:00:00Z"


def attestation(*, sample: bool = False) -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "project-x",
        "evidence_origin": "RUNTIME_OBSERVED",
        "synthetic_evidence_used": False,
        "sample_evidence_used": sample,
        "thresholds_relaxed": False,
        "attested_by": "operator@example",
        "attested_at": "2026-08-18T04:00:00Z",
    }


def manifest() -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "project-x",
        "assessment_sources": [{
            "assessment_id": "assessment-1",
            "trust_report": "trust/report.json",
            "request": "trust/request.json",
            "profile": "trust/profile.yml",
            "ledger": None,
            "policy_registry": None,
            "evaluation_report": None,
            "reground_report": None,
            "reground_observations": None,
        }],
        "outcome_sources": [],
    }


def write_workspace(root: Path, *, sample: bool = False) -> None:
    (root / "acquisition-attestation.json").write_text(json.dumps(attestation(sample=sample)), encoding="utf-8")
    (root / "comparison-registry.json").write_text("{}\n", encoding="utf-8")
    (root / "reconciliation-sources.json").write_text("{}\n", encoding="utf-8")
    (root / "observation-policy.json").write_text("{}\n", encoding="utf-8")
    (root / "trust").mkdir(parents=True, exist_ok=True)
    (root / "trust" / "report.json").write_text("{}\n", encoding="utf-8")
    (root / "trust" / "request.json").write_text("{}\n", encoding="utf-8")
    (root / "trust" / "profile.yml").write_text("project: x\n", encoding="utf-8")


class EvidenceAcquisitionHardeningTests(unittest.TestCase):
    @patch("review_system.trust_evidence_acquisition.load_policy")
    @patch("review_system.trust_evidence_acquisition.load_source_manifest")
    @patch("review_system.trust_evidence_acquisition.load_registry")
    def test_sample_attestation_is_rejected(self, load_registry_mock, load_manifest_mock, load_policy_mock) -> None:
        load_registry_mock.return_value = (Path("registry"), {"project_id": "project-x"})
        load_manifest_mock.return_value = (Path("manifest"), manifest())
        load_policy_mock.return_value = (Path("policy"), {})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_workspace(root, sample=True)
            with self.assertRaises(EvidenceAcquisitionVerificationError):
                inspect_acquisition_workspace(root, generated_at=GENERATED_AT)

    @patch("review_system.trust_evidence_acquisition.load_policy")
    @patch("review_system.trust_evidence_acquisition.load_source_manifest")
    @patch("review_system.trust_evidence_acquisition.load_registry")
    def test_symlinked_source_closure_is_rejected(self, load_registry_mock, load_manifest_mock, load_policy_mock) -> None:
        load_registry_mock.return_value = (Path("registry"), {"project_id": "project-x"})
        load_manifest_mock.return_value = (Path("manifest"), manifest())
        load_policy_mock.return_value = (Path("policy"), {})
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "workspace"
            root.mkdir()
            write_workspace(root)
            external = base / "external.json"
            external.write_text("{}\n", encoding="utf-8")
            (root / "trust" / "report.json").unlink()
            (root / "trust" / "report.json").symlink_to(external)
            with self.assertRaises(EvidenceAcquisitionError):
                inspect_acquisition_workspace(root, generated_at=GENERATED_AT)

    @patch("review_system.trust_evidence_acquisition._finalize", side_effect=EvidenceAcquisitionVerificationError(["forced"]))
    @patch("review_system.trust_evidence_acquisition.run_r0_pilot_evidence")
    @patch("review_system.trust_evidence_acquisition.write_observation_report")
    @patch("review_system.trust_evidence_acquisition.assess_observation")
    @patch("review_system.trust_evidence_acquisition.write_reconciliation_report")
    @patch("review_system.trust_evidence_acquisition.reconcile_sources")
    @patch("review_system.trust_evidence_acquisition.load_policy")
    @patch("review_system.trust_evidence_acquisition.load_source_manifest")
    @patch("review_system.trust_evidence_acquisition.load_registry")
    def test_report_finalize_failure_leaves_no_published_target(
        self,
        load_registry_mock,
        load_manifest_mock,
        load_policy_mock,
        reconcile_mock,
        write_reconcile_mock,
        observe_mock,
        write_observe_mock,
        pilot_mock,
        _finalize_mock,
    ) -> None:
        load_registry_mock.return_value = (Path("registry"), {"project_id": "project-x"})
        load_manifest_mock.return_value = (Path("manifest"), manifest())
        load_policy_mock.return_value = (Path("policy"), {})
        reconcile_mock.return_value = {"report_id": "reconciliation-1"}
        observe_mock.return_value = {"report_id": "observation-1"}
        write_reconcile_mock.side_effect = lambda path, _value: Path(path).write_text("{}\n", encoding="utf-8")
        write_observe_mock.side_effect = lambda path, _value: Path(path).write_text("{}\n", encoding="utf-8")
        pilot_mock.return_value = {
            "run_id": "r0-pilot-evidence-run-" + "1" * 32,
            "status": "NOT_ELIGIBLE",
            "next_step": "COLLECT_MORE_CONFIRMED_OBSERVATION",
            "blockers": ["MINIMUM_R0_ASSESSMENT_COUNT"],
            "source_replay": {"verified": True},
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workspace = base / "workspace"
            workspace.mkdir()
            write_workspace(workspace)
            target = base / "package"
            with self.assertRaises(EvidenceAcquisitionVerificationError):
                populate_r0_evidence_package(workspace, target, generated_at=GENERATED_AT)
            self.assertFalse(target.exists())
            self.assertEqual(list(base.glob(".package.*.tmp")), [])

    def test_published_empty_runtime_package_replays_after_atomic_rename(self) -> None:
        policy = {
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
        empty_manifest = {
            "schema_version": "1.0",
            "project_id": "project-x",
            "assessment_sources": [],
            "outcome_sources": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workspace = base / "workspace"
            workspace.mkdir()
            (workspace / "acquisition-attestation.json").write_text(
                json.dumps(attestation()), encoding="utf-8"
            )
            write_registry(
                workspace / "comparison-registry.json",
                new_registry("project-x", created_at="2026-08-18T04:00:00Z"),
            )
            (workspace / "reconciliation-sources.json").write_text(
                json.dumps(empty_manifest), encoding="utf-8"
            )
            (workspace / "observation-policy.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )
            target = base / "r0-pilot-evidence"
            report = populate_r0_evidence_package(workspace, target, generated_at=GENERATED_AT)
            self.assertTrue(target.is_dir())
            self.assertTrue(report["package"]["published"])
            self.assertEqual(
                verify_acquisition_report_sources(
                    report, workspace_root=workspace, package_root=target
                ),
                [],
            )

    @patch("review_system.trust_evidence_acquisition.run_r0_pilot_evidence")
    @patch("review_system.trust_evidence_acquisition.write_observation_report")
    @patch("review_system.trust_evidence_acquisition.assess_observation")
    @patch("review_system.trust_evidence_acquisition.write_reconciliation_report")
    @patch("review_system.trust_evidence_acquisition.reconcile_sources")
    @patch("review_system.trust_evidence_acquisition.load_policy")
    @patch("review_system.trust_evidence_acquisition.load_source_manifest")
    @patch("review_system.trust_evidence_acquisition.load_registry")
    def test_published_package_byte_mutation_is_detected(
        self,
        load_registry_mock,
        load_manifest_mock,
        load_policy_mock,
        reconcile_mock,
        write_reconcile_mock,
        observe_mock,
        write_observe_mock,
        pilot_mock,
    ) -> None:
        load_registry_mock.return_value = (Path("registry"), {"project_id": "project-x"})
        load_manifest_mock.return_value = (Path("manifest"), manifest())
        load_policy_mock.return_value = (Path("policy"), {})
        reconcile_mock.return_value = {"report_id": "reconciliation-1"}
        observe_mock.return_value = {"report_id": "observation-1"}
        write_reconcile_mock.side_effect = lambda path, _value: Path(path).write_text("{}\n", encoding="utf-8")
        write_observe_mock.side_effect = lambda path, _value: Path(path).write_text("{}\n", encoding="utf-8")
        pilot_result = {
            "run_id": "r0-pilot-evidence-run-" + "2" * 32,
            "status": "NOT_ELIGIBLE",
            "next_step": "COLLECT_MORE_CONFIRMED_OBSERVATION",
            "blockers": ["MINIMUM_R0_ASSESSMENT_COUNT"],
            "source_replay": {"verified": True},
        }
        pilot_mock.return_value = pilot_result
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workspace = base / "workspace"
            workspace.mkdir()
            write_workspace(workspace)
            target = base / "package"
            report = populate_r0_evidence_package(workspace, target, generated_at=GENERATED_AT)
            self.assertTrue(report["package"]["published"])
            (target / "acquisition-attestation.json").write_text("{}\n", encoding="utf-8")
            errors = verify_acquisition_report_sources(report, package_root=target)
        self.assertIn("package byte manifest mismatch", errors)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.identity import canonical_json_sha256
from review_system.trust_evidence_acquisition import (
    EvidenceAcquisitionError,
    _report_id,
    _report_payload,
    _snapshot_payload,
    inspect_acquisition_workspace,
    populate_r0_evidence_package,
    verify_acquisition_report_data,
)


GENERATED_AT = "2026-08-18T05:00:00Z"


def attestation(project_id: str = "project-x") -> dict:
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "evidence_origin": "RUNTIME_OBSERVED",
        "synthetic_evidence_used": False,
        "sample_evidence_used": False,
        "thresholds_relaxed": False,
        "attested_by": "operator@example",
        "attested_at": "2026-08-18T04:00:00Z",
    }


def manifest() -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "project-x",
        "assessment_sources": [
            {
                "assessment_id": "assessment-1",
                "trust_report": "trust/report.json",
                "request": "trust/request.json",
                "profile": "trust/profile.yml",
                "ledger": None,
                "policy_registry": None,
                "evaluation_report": None,
                "reground_report": None,
                "reground_observations": None,
            }
        ],
        "outcome_sources": [],
    }


def write_required(root: Path) -> None:
    (root / "acquisition-attestation.json").write_text(json.dumps(attestation()), encoding="utf-8")
    (root / "comparison-registry.json").write_text("{}\n", encoding="utf-8")
    (root / "reconciliation-sources.json").write_text("{}\n", encoding="utf-8")
    (root / "observation-policy.json").write_text("{}\n", encoding="utf-8")


def make_closure(root: Path) -> None:
    (root / "trust").mkdir(parents=True, exist_ok=True)
    (root / "trust" / "report.json").write_text("{}\n", encoding="utf-8")
    (root / "trust" / "request.json").write_text("{}\n", encoding="utf-8")
    (root / "trust" / "profile.yml").write_text("project: x\n", encoding="utf-8")


class EvidenceAcquisitionTests(unittest.TestCase):
    def test_missing_required_inputs_are_blocked_without_fabrication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = inspect_acquisition_workspace(temporary, generated_at=GENERATED_AT)
        self.assertEqual(report["status"], "BLOCKED_MISSING_INPUT")
        self.assertFalse(report["workspace_complete"])
        self.assertFalse(report["package"]["published"])
        self.assertFalse(report["automation_authorized"])
        self.assertFalse(report["pilot_authorized"])
        self.assertEqual(verify_acquisition_report_data(report), [])

    @patch("review_system.trust_evidence_acquisition.load_policy")
    @patch("review_system.trust_evidence_acquisition.load_source_manifest")
    @patch("review_system.trust_evidence_acquisition.load_registry")
    def test_missing_source_closure_is_blocked(self, load_registry_mock, load_manifest_mock, load_policy_mock) -> None:
        load_registry_mock.return_value = (Path("registry"), {"project_id": "project-x"})
        load_manifest_mock.return_value = (Path("manifest"), manifest())
        load_policy_mock.return_value = (Path("policy"), {})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_required(root)
            report = inspect_acquisition_workspace(root, generated_at=GENERATED_AT)
        self.assertEqual(report["status"], "BLOCKED_MISSING_SOURCE_CLOSURE")
        self.assertIn("MISSING_SOURCE_CLOSURE:trust/report.json", report["blockers"])
        self.assertFalse(report["workspace_complete"])
        self.assertEqual(verify_acquisition_report_data(report), [])

    @patch("review_system.trust_evidence_acquisition.load_policy")
    @patch("review_system.trust_evidence_acquisition.load_source_manifest")
    @patch("review_system.trust_evidence_acquisition.load_registry")
    def test_complete_workspace_is_ready_not_eligible(self, load_registry_mock, load_manifest_mock, load_policy_mock) -> None:
        load_registry_mock.return_value = (Path("registry"), {"project_id": "project-x"})
        load_manifest_mock.return_value = (Path("manifest"), manifest())
        load_policy_mock.return_value = (Path("policy"), {})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_required(root)
            make_closure(root)
            report = inspect_acquisition_workspace(root, generated_at=GENERATED_AT)
        self.assertEqual(report["status"], "READY_TO_POPULATE")
        self.assertTrue(report["workspace_complete"])
        self.assertFalse(report["package"]["attempted"])
        self.assertEqual(report["next_step"], "POPULATE_R0_EVIDENCE_PACKAGE")
        self.assertEqual(verify_acquisition_report_data(report), [])

    @patch("review_system.trust_evidence_acquisition.run_r0_pilot_evidence")
    @patch("review_system.trust_evidence_acquisition.write_observation_report")
    @patch("review_system.trust_evidence_acquisition.assess_observation")
    @patch("review_system.trust_evidence_acquisition.write_reconciliation_report")
    @patch("review_system.trust_evidence_acquisition.reconcile_sources")
    @patch("review_system.trust_evidence_acquisition.load_policy")
    @patch("review_system.trust_evidence_acquisition.load_source_manifest")
    @patch("review_system.trust_evidence_acquisition.load_registry")
    def test_verified_not_eligible_package_is_published(
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
            write_required(workspace)
            make_closure(workspace)
            target = base / "package"
            report = populate_r0_evidence_package(workspace, target, generated_at=GENERATED_AT)
            self.assertTrue(target.is_dir())
            self.assertTrue((target / "reconciliation-report.json").is_file())
            self.assertTrue((target / "observation-report.json").is_file())
            self.assertTrue((target / "trust" / "report.json").is_file())
        self.assertEqual(report["status"], "PACKAGE_POPULATED_NOT_ELIGIBLE")
        self.assertTrue(report["package"]["published"])
        self.assertTrue(report["generated"]["source_replay_verified"])
        self.assertEqual(verify_acquisition_report_data(report), [])

    @patch("review_system.trust_evidence_acquisition.run_r0_pilot_evidence")
    @patch("review_system.trust_evidence_acquisition.write_observation_report")
    @patch("review_system.trust_evidence_acquisition.assess_observation")
    @patch("review_system.trust_evidence_acquisition.write_reconciliation_report")
    @patch("review_system.trust_evidence_acquisition.reconcile_sources")
    @patch("review_system.trust_evidence_acquisition.load_policy")
    @patch("review_system.trust_evidence_acquisition.load_source_manifest")
    @patch("review_system.trust_evidence_acquisition.load_registry")
    def test_source_replay_failure_never_publishes(
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
        pilot_mock.return_value = {
            "run_id": "r0-pilot-evidence-run-" + "2" * 32,
            "status": "NOT_ELIGIBLE",
            "next_step": "REPAIR_AND_REPLAY_SOURCE_EVIDENCE",
            "blockers": ["RECONCILIATION_SOURCE_REPLAY"],
            "source_replay": {"verified": False},
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workspace = base / "workspace"
            workspace.mkdir()
            write_required(workspace)
            make_closure(workspace)
            target = base / "package"
            report = populate_r0_evidence_package(workspace, target, generated_at=GENERATED_AT)
            self.assertFalse(target.exists())
        self.assertEqual(report["status"], "BLOCKED_SOURCE_REPLAY")
        self.assertFalse(report["package"]["published"])
        self.assertIn("SOURCE_REPLAY_FAILED", report["blockers"])
        self.assertEqual(verify_acquisition_report_data(report), [])

    @patch("review_system.trust_evidence_acquisition.load_policy")
    @patch("review_system.trust_evidence_acquisition.load_source_manifest")
    @patch("review_system.trust_evidence_acquisition.load_registry")
    def test_existing_package_target_is_rejected(self, load_registry_mock, load_manifest_mock, load_policy_mock) -> None:
        load_registry_mock.return_value = (Path("registry"), {"project_id": "project-x"})
        load_manifest_mock.return_value = (Path("manifest"), manifest())
        load_policy_mock.return_value = (Path("policy"), {})
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workspace = base / "workspace"
            workspace.mkdir()
            write_required(workspace)
            make_closure(workspace)
            target = base / "package"
            target.mkdir()
            with self.assertRaises(EvidenceAcquisitionError):
                populate_r0_evidence_package(workspace, target, generated_at=GENERATED_AT)

    def test_semantic_rehash_cannot_enable_pilot_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = inspect_acquisition_workspace(temporary, generated_at=GENERATED_AT)
        forged = deepcopy(report)
        forged["pilot_authorized"] = True
        forged["evidence_snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(forged))
        forged["report_id"] = _report_id(forged["project_id"], forged["evidence_snapshot_sha256"])
        forged["report_sha256"] = canonical_json_sha256(_report_payload(forged))
        errors = verify_acquisition_report_data(forged)
        self.assertTrue(any("pilot_authorized" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

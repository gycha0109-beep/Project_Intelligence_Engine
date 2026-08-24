from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from review_system.prospective_automation import RunGitHubPRRequest, run_github_pr
from review_system.prospective_evidence_bundle import verify_evidence_bundle


HEAD = "a" * 40
PIE = "b" * 40
BASE = "d" * 40


class _CLI:
    pass


def _candidate() -> dict:
    return {
        "candidate_id": "candidate-1",
        "project_id": "demo",
        "task_id": "github-pr:demo",
        "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
        "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
        "changed_files": ["src/core.py"],
        "status": "BLOCKED_OPERATOR_INPUT_REQUIRED",
    }


def _analysis(root: Path):
    output = root / "analysis-result"
    output.mkdir(parents=True, exist_ok=True)
    for name, value in {
        "github-source.json": {"source": True},
        "impact.json": {"impact": True},
        "identity.json": {"identity": True},
    }.items():
        (output / name).write_text(json.dumps(value), encoding="utf-8")
    (output / "REPORT.md").write_text("report\n", encoding="utf-8")
    (output / "pull-request.diff").write_text("diff --git a/a b/a\n", encoding="utf-8")
    candidate = output / "prospective-capture.json"
    candidate.write_text(json.dumps(_candidate()), encoding="utf-8")
    source = {
        "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
        "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
        "local_project_state": {"head_revision": HEAD},
    }
    return SimpleNamespace(
        source=source,
        impact={
            "direct": {"components": ["core"]},
            "impact": {"dependent_files": []},
            "review": {"selected_packs": ["universal.test-completeness"], "required_tests": ["tests/test_core.py"]},
            "limitations": ["review signal only"],
            "source_evidence_sha256": "1" * 64,
        },
        output_dir=output,
        source_path=output / "github-source.json",
        impact_path=output / "impact.json",
        report_path=output / "REPORT.md",
        diff_path=output / "pull-request.diff",
        changed_files=("src/core.py",),
        prospective_candidate_path=candidate,
        workflow_semantics_path=None,
    )


def _binding(*, materialized: bool) -> dict:
    return {
        "project_id": "demo",
        "candidate_id": "candidate-1",
        "source_revision": "git:" + HEAD,
        "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
        "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
        "changed_files": ["src/core.py"],
        "status": "TRUST_REQUEST_MATERIALIZED" if materialized else "MISSING_TRUST_FIELDS",
        "match_status": "UNIQUE_POLICY_MATCH",
        "selected_operational_class": "core-runtime",
        "requirements": {
            "trust_task_class": "routine_code",
            "required_scenarios": ["core-test"],
            "required_evidence": ["ci"],
        },
        "binding_sha256": "2" * 64,
        "policy": {
            "policy_revision": "git:" + BASE,
            "policy_blob_sha": "5" * 40,
            "policy_content_sha256": "6" * 64,
            "policy_sha256": "3" * 64,
        },
        "missing_inputs": [] if materialized else ["rollback_evidence"],
        "trust_request": {
            "materialized": materialized,
            "request_sha256": "4" * 64 if materialized else None,
        },
    }


def _packet() -> dict:
    return {
        "project_id": "demo",
        "packet_id": "packet-1",
        "packet_sha256": "7" * 64,
        "assessment_id": "assessment-1",
        "assessment_sha256": "8" * 64,
        "task_id": "github-pr:demo",
        "source_revision": "git:" + HEAD,
        "trust_report_id": "trust-report-1",
        "trust_report_sha256": "9" * 64,
        "github": {
            "candidate_id": "candidate-1",
            "hostname": "github.com",
            "repository": "demo/repo",
            "pr_number": 7,
            "base_oid": BASE,
            "head_oid": HEAD,
        },
        "predicted_risk_band": "R2",
        "changed_files": ["src/core.py"],
        "hard_gates": [],
        "review_requirement": "HUMAN_APPROVAL_REQUIRED",
    }


class ProspectiveAutomationORL2Tests(unittest.TestCase):
    def _root(self, tmp: str) -> Path:
        root = Path(tmp)
        (root / ".review" / "intelligence").mkdir(parents=True)
        (root / ".review" / "project.yml").write_text("project: demo\n", encoding="utf-8")
        (root / ".review" / "intelligence" / "config.yml").write_text("components: []\n", encoding="utf-8")
        return root

    @staticmethod
    def _write_binding(path, value):
        target = Path(path)
        target.write_text(json.dumps(value), encoding="utf-8")
        return target

    def test_missing_operational_facts_stays_waiting_and_binds_replay_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            with (
                patch("review_system.prospective_automation.analyze_pull_request", return_value=_analysis(root)),
                patch("review_system.prospective_automation.bind_operational_policy", return_value=_binding(materialized=False)),
                patch("review_system.prospective_automation.write_operational_policy_binding", side_effect=self._write_binding),
            ):
                result = run_github_pr(
                    RunGitHubPRRequest(
                        pull_request="7", event_head_sha=HEAD, pie_revision=PIE,
                        repository_root=root, repository="demo/repo",
                        operational_policy=".review/operational/policy.yml",
                    ),
                    github_cli=_CLI(),
                )
            self.assertEqual("WAITING_FOR_TRUST_INPUT", result["status"])
            self.assertEqual("MISSING_TRUST_FIELDS", result["operational_binding_status"])
            self.assertEqual("UNIQUE_POLICY_MATCH", result["operational_match_status"])
            self.assertEqual(["rollback_evidence"], result["operational_missing_inputs"])
            self.assertTrue(result["deterministic_replay_bound"])
            bundle = Path(result["bundle"])
            self.assertTrue((bundle / "operational" / "binding.json").is_file())
            self.assertTrue((bundle / "review" / "brief.json").is_file())
            deterministic = json.loads((bundle / "deterministic-result.json").read_text(encoding="utf-8"))
            self.assertEqual("2" * 64, deterministic["result"]["operational_binding_sha256"])
            brief = json.loads((bundle / "review" / "brief.json").read_text(encoding="utf-8"))
            self.assertEqual("core-runtime", brief["required_verification"]["operational_class"])
            self.assertEqual([], verify_evidence_bundle(bundle))

    def test_materialized_policy_request_reuses_existing_auto2_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            facts = root / "facts.yml"
            facts.write_text("explicit: true\n", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()

            def bind_with_request(*args, **kwargs):
                Path(kwargs["trust_request_output"]).write_text('{"request":true}\n', encoding="utf-8")
                return _binding(materialized=True)

            def materialize(*args, **kwargs):
                Path(kwargs["trust_report_output"]).write_text('{"report":true}\n', encoding="utf-8")
                return {"assessment_id": "assessment-1", "predicted_risk_band": "R2"}

            def write_packet(path, packet):
                target = Path(path)
                target.write_text(json.dumps(packet), encoding="utf-8")
                return target

            with (
                patch("review_system.prospective_automation.analyze_pull_request", return_value=_analysis(root)),
                patch("review_system.prospective_automation.bind_operational_policy", side_effect=bind_with_request),
                patch("review_system.prospective_automation.write_operational_policy_binding", side_effect=self._write_binding),
                patch("review_system.prospective_automation.materialize_github_prospective_capture", side_effect=materialize),
                patch("review_system.prospective_automation.prepare_review_packet", return_value=_packet()),
                patch("review_system.prospective_automation.write_review_packet", side_effect=write_packet),
            ):
                result = run_github_pr(
                    RunGitHubPRRequest(
                        pull_request="7", event_head_sha=HEAD, pie_revision=PIE,
                        repository_root=root, repository="demo/repo",
                        operational_policy=".review/operational/policy.yml",
                        operational_trust_facts=facts, workspace=workspace,
                    ),
                    github_cli=_CLI(),
                )
            self.assertEqual("READY_FOR_HUMAN_REVIEW", result["status"])
            self.assertEqual("TRUST_REQUEST_MATERIALIZED", result["operational_binding_status"])
            self.assertEqual("assessment-1", result["assessment_id"])
            self.assertEqual("packet-1", result["packet_id"])
            self.assertTrue(result["auto_trust_assessment"])
            self.assertTrue(result["auto_packet_prepare"])
            self.assertFalse(result["human_review_recorded"])
            self.assertFalse(result["outcome_recorded"])
            self.assertFalse(result["automation_authorized"])
            self.assertFalse(result["pilot_authorized"])
            bundle = Path(result["bundle"])
            self.assertTrue((bundle / "operational" / "binding.json").is_file())
            self.assertTrue((bundle / "operational" / "trust-facts.yml").is_file())
            self.assertTrue((bundle / "trust" / "request.json").is_file())
            self.assertTrue((bundle / "review" / "BRIEF.md").is_file())
            self.assertEqual([], verify_evidence_bundle(bundle))


if __name__ == "__main__":
    unittest.main()

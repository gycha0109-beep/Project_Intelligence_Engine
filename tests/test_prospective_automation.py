from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from review_system.prospective_automation import (
    ProspectiveAutomationError,
    RunGitHubPRRequest,
    run_github_pr,
)
from review_system.prospective_evidence_bundle import verify_evidence_bundle


HEAD = "a" * 40
PIE = "b" * 40


class _CLI:
    pass


def _analysis(root: Path, *, live_head: str = HEAD, local_head: str = HEAD):
    output = root / "analysis-result"
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "github-source.json": {"source": True},
        "impact.json": {"impact": True},
        "identity.json": {"identity": True},
    }
    for name, value in files.items():
        (output / name).write_text(json.dumps(value), encoding="utf-8")
    (output / "REPORT.md").write_text("report\n", encoding="utf-8")
    (output / "pull-request.diff").write_text("diff --git a/a b/a\n", encoding="utf-8")
    candidate = output / "prospective-capture.json"
    candidate.write_text(
        json.dumps(
            {
                "candidate_id": "candidate-1",
                "generated_at": "2026-08-24T00:00:00Z",
                "source_evidence_sha256": "1" * 64,
                "evidence_snapshot_sha256": "2" * 64,
                "report_sha256": "3" * 64,
                "status": "BLOCKED_OPERATOR_INPUT_REQUIRED",
            }
        ),
        encoding="utf-8",
    )
    source = {
        "repository": {"name_with_owner": "demo/repo"},
        "pull_request": {"number": 7, "base_oid": "d" * 40, "head_oid": live_head},
        "local_project_state": {"head_revision": local_head},
    }
    return SimpleNamespace(
        source=source,
        impact={"impact": True, "source_evidence_sha256": "1" * 64},
        output_dir=output,
        source_path=output / "github-source.json",
        impact_path=output / "impact.json",
        report_path=output / "REPORT.md",
        diff_path=output / "pull-request.diff",
        changed_files=("src/core.py",),
        prospective_candidate_path=candidate,
        workflow_semantics_path=None,
    )


class ProspectiveAutomationTests(unittest.TestCase):
    def _root(self, tmp: str) -> Path:
        root = Path(tmp)
        (root / ".review" / "intelligence").mkdir(parents=True)
        (root / ".review" / "project.yml").write_text("project: demo\n", encoding="utf-8")
        (root / ".review" / "intelligence" / "config.yml").write_text("components: []\n", encoding="utf-8")
        return root

    def test_no_trust_request_stops_at_waiting_and_emits_replay_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            with patch("review_system.prospective_automation.analyze_pull_request", return_value=_analysis(root)):
                result = run_github_pr(
                    RunGitHubPRRequest(
                        pull_request="https://github.com/demo/repo/pull/7",
                        event_head_sha=HEAD,
                        pie_revision=PIE,
                        repository_root=root,
                        repository="demo/repo",
                    ),
                    github_cli=_CLI(),
                )
            self.assertEqual("WAITING_FOR_TRUST_INPUT", result["status"])
            self.assertTrue(result["auto_capture"])
            self.assertTrue(result["auto_analysis"])
            self.assertFalse(result["auto_trust_assessment"])
            self.assertFalse(result["auto_packet_prepare"])
            self.assertFalse(result["human_review_recorded"])
            self.assertFalse(result["outcome_recorded"])
            self.assertFalse(result["automation_authorized"])
            self.assertFalse(result["pilot_authorized"])
            self.assertTrue(result["deterministic_replay_bound"])
            self.assertRegex(result["deterministic_result_sha256"], r"^[0-9a-f]{64}$")
            bundle = Path(result["bundle"])
            self.assertTrue((bundle / "manifest.json").is_file())
            self.assertTrue((bundle / "deterministic-result.json").is_file())
            self.assertEqual([], verify_evidence_bundle(bundle))
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result["deterministic_result_sha256"], manifest["deterministic_result_sha256"])

    def test_same_semantics_replay_to_same_deterministic_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            first_analysis = _analysis(root)
            first_candidate = json.loads(first_analysis.prospective_candidate_path.read_text(encoding="utf-8"))
            with patch("review_system.prospective_automation.analyze_pull_request", return_value=first_analysis):
                first = run_github_pr(
                    RunGitHubPRRequest(
                        pull_request="7",
                        event_head_sha=HEAD,
                        pie_revision=PIE,
                        repository_root=root,
                        repository="demo/repo",
                        output_root=".pie/first",
                    ),
                    github_cli=_CLI(),
                )

            second_analysis = _analysis(root)
            second_candidate = dict(first_candidate)
            second_candidate.update({
                "generated_at": "2026-08-24T00:30:00Z",
                "source_evidence_sha256": "4" * 64,
                "evidence_snapshot_sha256": "5" * 64,
                "report_sha256": "6" * 64,
            })
            second_analysis.prospective_candidate_path.write_text(json.dumps(second_candidate), encoding="utf-8")
            second_analysis.impact["source_evidence_sha256"] = "4" * 64
            with patch("review_system.prospective_automation.analyze_pull_request", return_value=second_analysis):
                second = run_github_pr(
                    RunGitHubPRRequest(
                        pull_request="7",
                        event_head_sha=HEAD,
                        pie_revision=PIE,
                        repository_root=root,
                        repository="demo/repo",
                        output_root=".pie/second",
                    ),
                    github_cli=_CLI(),
                )
            self.assertEqual(first["execution_id"], second["execution_id"])
            self.assertEqual(first["deterministic_result_sha256"], second["deterministic_result_sha256"])

    def test_event_live_local_head_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            with patch(
                "review_system.prospective_automation.analyze_pull_request",
                return_value=_analysis(root, live_head=HEAD, local_head="c" * 40),
            ):
                with self.assertRaises(ProspectiveAutomationError) as caught:
                    run_github_pr(
                        RunGitHubPRRequest(
                            pull_request="7",
                            event_head_sha=HEAD,
                            pie_revision=PIE,
                            repository_root=root,
                            repository="demo/repo",
                        ),
                        github_cli=_CLI(),
                    )
            self.assertEqual("STALE_SOURCE_REVISION", caught.exception.code)

    def test_explicit_request_can_prepare_packet_without_recording_human_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            request_path = root / "request.json"
            request_path.write_text('{"request": true}\n', encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()

            def write_packet(path, packet):
                target = Path(path)
                target.write_text(json.dumps(packet), encoding="utf-8")
                return target

            def materialize_with_report(*args, **kwargs):
                Path(kwargs["trust_report_output"]).write_text('{"risk_band":"R4"}\n', encoding="utf-8")
                return {"assessment_id": "assessment-1", "predicted_risk_band": "R4", "source_revision": HEAD}

            with (
                patch("review_system.prospective_automation.analyze_pull_request", return_value=_analysis(root)),
                patch(
                    "review_system.prospective_automation.materialize_github_prospective_capture",
                    side_effect=materialize_with_report,
                ),
                patch(
                    "review_system.prospective_automation.prepare_review_packet",
                    return_value={"packet_id": "packet-1"},
                ),
                patch("review_system.prospective_automation.write_review_packet", side_effect=write_packet),
            ):
                result = run_github_pr(
                    RunGitHubPRRequest(
                        pull_request="7",
                        event_head_sha=HEAD,
                        pie_revision=PIE,
                        repository_root=root,
                        repository="demo/repo",
                        trust_request=request_path,
                        workspace=workspace,
                    ),
                    github_cli=_CLI(),
                )
            self.assertEqual("READY_FOR_HUMAN_REVIEW", result["status"])
            self.assertEqual("assessment-1", result["assessment_id"])
            self.assertEqual("packet-1", result["packet_id"])
            self.assertEqual("R4", result["risk_band"])
            self.assertFalse(result["human_review_recorded"])
            self.assertFalse(result["outcome_recorded"])
            self.assertFalse(result["automation_authorized"])
            self.assertFalse(result["pilot_authorized"])
            self.assertFalse(result["deterministic_replay_bound"])
            self.assertIsNone(result["deterministic_result_sha256"])


if __name__ == "__main__":
    unittest.main()

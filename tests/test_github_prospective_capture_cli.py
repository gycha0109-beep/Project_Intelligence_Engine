from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from review_system.github.source import refresh_source_hash
from review_system.github_prospective_capture import (
    GitHubProspectiveCaptureError,
    build_github_prospective_capture_candidate,
    write_github_prospective_capture_candidate,
)
from review_system.project_init import initialize_project
from review_system.trust_cli import main as trust_main
from review_system.trust_prospective_evidence_cli import main as prospective_main


HEAD = "a" * 40
BASE = "b" * 40


def _candidate(root: Path) -> Path:
    initialize_project(root, preset="generic-webapp")
    source = {
        "schema_version": "1.0",
        "source": "github-cli",
        "retrieved_at": "2026-08-19T00:00:00Z",
        "repository": {"hostname": "github.com", "name_with_owner": "demo/repo", "gh_repo_argument": "demo/repo"},
        "pull_request": {
            "number": 7,
            "url": "https://github.com/demo/repo/pull/7",
            "base_oid": BASE,
            "head_oid": HEAD,
            "changed_files": [{"path": "src/core.py"}],
        },
        "diff": {"requested": False, "available": False},
        "discussion": {"requested": False, "complete": True},
        "warnings": [],
        "local_repository_verification": {"status": "matched"},
        "local_project_state": {"head_revision": HEAD, "working_tree_dirty": False},
    }
    refresh_source_hash(source)
    candidate = build_github_prospective_capture_candidate(source, root / ".review" / "project.yml")
    return write_github_prospective_capture_candidate(root / "candidate.json", candidate)


class GitHubProspectiveCaptureCLITests(unittest.TestCase):
    def test_standalone_and_pie_trust_verify_delegate_to_same_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _candidate(Path(tmp))
            for entry in (prospective_main, trust_main):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = entry(["verify-github-prospective-capture", "--candidate", str(path)])
                self.assertEqual(0, code)
                payload = json.loads(output.getvalue())
                self.assertTrue(payload["valid"])
                self.assertEqual("BLOCKED_OPERATOR_INPUT_REQUIRED", payload["status"])
                self.assertFalse(payload["automation_authorized"])
                self.assertFalse(payload["pilot_authorized"])

    def test_materialize_cli_maps_arguments_without_creating_review_or_outcome(self):
        result = {
            "candidate_id": "github-capture-" + "a" * 32,
            "assessment_id": "assessment-test",
            "predicted_risk_band": "R2",
            "source_revision": HEAD,
            "idempotent": False,
            "trust_report": "/tmp/report.json",
            "mode": "REPORT_ONLY",
            "automation_authorized": False,
            "pilot_authorized": False,
            "human_review_recorded": False,
            "outcome_recorded": False,
        }
        output = io.StringIO()
        with (
            patch("review_system.trust_prospective_evidence_cli.GitHubCLI") as cli_type,
            patch("review_system.trust_prospective_evidence_cli.materialize_github_prospective_capture", return_value=result) as materialize,
            redirect_stdout(output),
        ):
            code = prospective_main([
                "materialize-github-prospective-capture",
                "--candidate", "candidate.json",
                "--request", "request.json",
                "--workspace", "workspace",
                "--profile", "project.yml",
                "--repository-root", ".",
                "--repo", "demo/repo",
                "--trust-report-output", "report.json",
                "--generated-at", "2026-08-19T00:10:00Z",
                "--captured-at", "2026-08-19T00:11:00Z",
                "--timeout", "45",
                "--gh-executable", "gh-test",
            ])
        self.assertEqual(0, code)
        self.assertTrue(json.loads(output.getvalue())["valid"])
        self.assertEqual("candidate.json", materialize.call_args.args[0])
        self.assertEqual("request.json", materialize.call_args.kwargs["request"])
        self.assertEqual("workspace", materialize.call_args.kwargs["workspace"])
        self.assertEqual("demo/repo", materialize.call_args.kwargs["repository"])
        cli_type.assert_called_once_with(executable="gh-test", timeout_seconds=45)

    def test_pie_trust_normalizes_stage10j_errors(self):
        error = GitHubProspectiveCaptureError("live GitHub PR head moved")
        stderr = io.StringIO()
        with (
            patch("review_system.trust_prospective_evidence_cli.materialize_github_prospective_capture", side_effect=error),
            patch("review_system.trust_prospective_evidence_cli.GitHubCLI"),
            redirect_stderr(stderr),
        ):
            code = trust_main([
                "materialize-github-prospective-capture",
                "--candidate", "candidate.json",
                "--request", "request.json",
                "--workspace", "workspace",
                "--profile", "project.yml",
                "--repository-root", ".",
            ])
        self.assertEqual(3, code)
        payload = json.loads(stderr.getvalue())
        self.assertFalse(payload["valid"])
        self.assertIn("head moved", payload["error"])


if __name__ == "__main__":
    unittest.main()

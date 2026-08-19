from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.application import AnalyzePullRequestRequest, analyze_pull_request
from review_system.github.source import refresh_source_hash
from review_system.github_prospective_capture import (
    GitHubProspectiveCaptureError,
    build_github_prospective_capture_candidate,
    candidate_filename,
    load_github_prospective_capture_candidate,
    materialize_github_prospective_capture,
    verify_github_prospective_capture_candidate,
    write_github_prospective_capture_candidate,
)
from review_system.identity import canonical_json_sha256
from review_system.project_init import initialize_project
from tests.test_github_connector import StubGitHubCLI


HEAD = "a" * 40
BASE = "b" * 40
MOVED = "c" * 40


def _profile(root: Path) -> Path:
    initialize_project(root, preset="generic-webapp")
    return root / ".review" / "project.yml"


def _source(*, head: str = HEAD, base: str = BASE, local_head: str | None = HEAD, dirty: bool = False) -> dict:
    value = {
        "schema_version": "1.0",
        "source": "github-cli",
        "retrieved_at": "2026-08-19T00:00:00Z",
        "repository": {
            "hostname": "github.com",
            "name_with_owner": "demo/repo",
            "gh_repo_argument": "demo/repo",
        },
        "pull_request": {
            "number": 7,
            "url": "https://github.com/demo/repo/pull/7",
            "title": "Prospective capture",
            "body": "",
            "state": "OPEN",
            "is_draft": False,
            "is_cross_repository": False,
            "author": {"login": "dev"},
            "base_ref": "main",
            "base_oid": base,
            "head_ref": "feature",
            "head_oid": head,
            "created_at": "2026-08-18T00:00:00Z",
            "updated_at": "2026-08-19T00:00:00Z",
            "merged_at": None,
            "merged_by": None,
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
            "review_decision": None,
            "additions": 1,
            "deletions": 0,
            "changed_files": [{"path": "src/core.py", "additions": 1, "deletions": 0}],
            "commits": [],
            "labels": [],
            "reviews": [],
            "latest_reviews": [],
            "review_requests": [],
            "comments": [],
            "inline_review_comments": [],
            "checks": [],
        },
        "diff": {"requested": False, "available": False},
        "discussion": {"requested": False, "complete": True},
        "warnings": [],
        "local_repository_verification": {
            "status": "matched",
            "expected_repository": "demo/repo",
            "expected_hostname": "github.com",
            "local_repository": {"name_with_owner": "demo/repo", "hostname": "github.com", "url": "https://github.com/demo/repo"},
        },
        "local_project_state": {
            "root": ".",
            "branch": "feature",
            "head_revision": local_head,
            "baseline_revision": None,
            "working_tree_dirty": dirty,
            "working_tree_entries": [],
        },
    }
    refresh_source_hash(value)
    return value


def _request(candidate: dict) -> dict:
    return {
        "schema_version": "1.0",
        "task_id": candidate["task_id"],
        "source_revision": candidate["pull_request"]["head_oid"],
        "task_class": "routine_code",
        "changed_files": candidate["changed_files"],
        "required_scenarios": [],
        "completed_scenarios": [],
        "repository_match": True,
        "head_match": True,
        "rollback_evidence": False,
        "replay_evidence": False,
        "readiness_policy": {
            "policy_id": "prospective-test",
            "policy_version": "1.0.0",
            "min_ledger_runs": 1,
            "min_ledger_decisions": 1,
            "min_defects": 1,
            "min_closed_defects": 0,
            "min_reground_observations": 1,
            "min_reground_coverage": 0.5,
            "min_reground_precision": 0.5,
            "min_reground_recall": 0.5,
            "max_reground_false_positive_rate": 0.5,
            "require_active_policy": True,
            "require_pass_evaluation": True,
            "require_holdout": True,
            "require_repeatability": True,
            "require_zero_protected_negative_regressions": True,
        },
    }


class _MaterializeCLI:
    def current_repository(self, cwd):
        return {"name_with_owner": "demo/repo", "hostname": "github.com", "url": "https://github.com/demo/repo"}


class GitHubProspectiveCaptureTests(unittest.TestCase):
    def test_candidate_binds_known_evidence_without_inventing_operator_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _profile(root)
            first = build_github_prospective_capture_candidate(_source(), profile, generated_at="2026-08-19T00:01:00Z")
            second = build_github_prospective_capture_candidate(_source(), profile, generated_at="2026-08-19T00:02:00Z")

            self.assertEqual("BLOCKED_OPERATOR_INPUT_REQUIRED", first["status"])
            self.assertEqual("COMPLETE_TRUST_REQUEST_AND_MATERIALIZE", first["next_step"])
            self.assertEqual(HEAD, first["request_scaffold"]["source_revision"])
            self.assertIsNone(first["request_scaffold"]["task_class"])
            self.assertIsNone(first["request_scaffold"]["required_scenarios"])
            self.assertIsNone(first["request_scaffold"]["rollback_evidence"])
            self.assertIsNone(first["request_scaffold"]["readiness_policy"])
            self.assertFalse(first["automation_authorized"])
            self.assertFalse(first["pilot_authorized"])
            self.assertFalse(first["human_review_recorded"])
            self.assertFalse(first["outcome_recorded"])
            self.assertEqual(first["candidate_id"], second["candidate_id"])
            self.assertEqual(first["evidence_snapshot_sha256"], second["evidence_snapshot_sha256"])
            self.assertNotEqual(first["report_sha256"], second["report_sha256"])

    def test_degraded_analysis_candidate_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _profile(root)
            candidate = build_github_prospective_capture_candidate(
                _source(head="head123", local_head=None, dirty=True),
                profile,
            )
            self.assertEqual("BLOCKED_EXACT_HEAD_REANALYSIS_REQUIRED", candidate["status"])
            self.assertIn("EXACT_REMOTE_HEAD_REQUIRED", candidate["blockers"])
            self.assertIn("EXACT_LOCAL_HEAD_REQUIRED", candidate["blockers"])
            self.assertIn("CLEAN_WORKTREE_REQUIRED", candidate["blockers"])
            self.assertIsNone(candidate["request_scaffold"]["source_revision"])

    def test_semantic_rehash_cannot_remove_required_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = build_github_prospective_capture_candidate(_source(), _profile(root))
            forged = deepcopy(candidate)
            forged["blockers"].remove("TRUST_TASK_CLASS_REQUIRED")
            snapshot = deepcopy(forged)
            snapshot.pop("generated_at", None)
            snapshot.pop("evidence_snapshot_sha256", None)
            snapshot.pop("report_sha256", None)
            forged["evidence_snapshot_sha256"] = canonical_json_sha256(snapshot)
            report_payload = deepcopy(forged)
            report_payload.pop("report_sha256", None)
            forged["report_sha256"] = canonical_json_sha256(report_payload)
            errors = verify_github_prospective_capture_candidate(forged)
            self.assertIn("blockers projection mismatch", errors)

    def test_candidate_write_load_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = build_github_prospective_capture_candidate(_source(), _profile(root))
            target = write_github_prospective_capture_candidate(root / candidate_filename(candidate), candidate)
            _, loaded = load_github_prospective_capture_candidate(target)
            self.assertEqual(candidate, loaded)
            link = root / "candidate-link.json"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            with self.assertRaisesRegex(GitHubProspectiveCaptureError, "symlinks"):
                load_github_prospective_capture_candidate(link)

    def test_materialization_rejects_live_head_drift_before_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _profile(root)
            candidate = build_github_prospective_capture_candidate(_source(), profile)
            candidate_path = write_github_prospective_capture_candidate(root / "candidate.json", candidate)
            request_path = root / "request.json"
            request_path.write_text(json.dumps(_request(candidate)), encoding="utf-8")

            def moved_collect(*args, **kwargs):
                return _source(head=MOVED, local_head=MOVED), None

            with patch("review_system.github_prospective_capture.intake_prospective_case") as intake:
                with self.assertRaisesRegex(GitHubProspectiveCaptureError, "head moved"):
                    materialize_github_prospective_capture(
                        candidate_path,
                        request=request_path,
                        workspace=root / "workspace",
                        profile=profile,
                        repository_root=root,
                        github_cli=_MaterializeCLI(),
                        collect_pr=moved_collect,
                        capture_state=lambda *args, **kwargs: {"repository": {"head_revision": HEAD, "working_tree_dirty": False}},
                    )
                intake.assert_not_called()

    def test_materialization_rejects_base_or_diff_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _profile(root)
            candidate = build_github_prospective_capture_candidate(_source(), profile)
            candidate_path = write_github_prospective_capture_candidate(root / "candidate.json", candidate)
            request_path = root / "request.json"
            request_path.write_text(json.dumps(_request(candidate)), encoding="utf-8")

            with self.assertRaisesRegex(GitHubProspectiveCaptureError, "base moved"):
                materialize_github_prospective_capture(
                    candidate_path,
                    request=request_path,
                    workspace=root / "workspace",
                    profile=profile,
                    repository_root=root,
                    github_cli=_MaterializeCLI(),
                    collect_pr=lambda *args, **kwargs: (_source(base=MOVED), None),
                    capture_state=lambda *args, **kwargs: {"repository": {"head_revision": HEAD, "working_tree_dirty": False}},
                )

            changed = _source()
            changed["pull_request"]["changed_files"] = [{"path": "src/other.py", "additions": 1, "deletions": 0}]
            refresh_source_hash(changed)
            with self.assertRaisesRegex(GitHubProspectiveCaptureError, "changed-file set"):
                materialize_github_prospective_capture(
                    candidate_path,
                    request=request_path,
                    workspace=root / "workspace",
                    profile=profile,
                    repository_root=root,
                    github_cli=_MaterializeCLI(),
                    collect_pr=lambda *args, **kwargs: (changed, None),
                    capture_state=lambda *args, **kwargs: {"repository": {"head_revision": HEAD, "working_tree_dirty": False}},
                )

    def test_materialization_creates_stage10a_report_then_calls_stage10i_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _profile(root)
            candidate = build_github_prospective_capture_candidate(_source(), profile)
            candidate_path = write_github_prospective_capture_candidate(root / "candidate.json", candidate)
            request_path = root / "request.json"
            request_path.write_text(json.dumps(_request(candidate)), encoding="utf-8")
            report_path = root / ".pie" / "prospective-trust-report.json"

            with patch(
                "review_system.github_prospective_capture.intake_prospective_case",
                return_value={
                    "assessment_id": "assessment-test",
                    "predicted_risk_band": "R2",
                    "source_revision": HEAD,
                    "idempotent": False,
                    "registry_sha256": "d" * 64,
                },
            ) as intake:
                result = materialize_github_prospective_capture(
                    candidate_path,
                    request=request_path,
                    workspace=root / "workspace",
                    profile=profile,
                    repository_root=root,
                    github_cli=_MaterializeCLI(),
                    collect_pr=lambda *args, **kwargs: (_source(), None),
                    capture_state=lambda *args, **kwargs: {"repository": {"head_revision": HEAD, "working_tree_dirty": False}},
                    trust_report_output=report_path,
                    generated_at="2026-08-19T00:10:00Z",
                    captured_at="2026-08-19T00:11:00Z",
                )

            self.assertTrue(report_path.is_file())
            self.assertEqual("assessment-test", result["assessment_id"])
            self.assertEqual(HEAD, result["source_revision"])
            self.assertFalse(result["automation_authorized"])
            self.assertFalse(result["pilot_authorized"])
            self.assertFalse(result["human_review_recorded"])
            self.assertFalse(result["outcome_recorded"])
            intake.assert_called_once()

    def test_materialization_rejects_request_identity_mismatch_before_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _profile(root)
            candidate = build_github_prospective_capture_candidate(_source(), profile)
            candidate_path = write_github_prospective_capture_candidate(root / "candidate.json", candidate)
            request_value = _request(candidate)
            request_value["task_id"] = "different-task"
            request_path = root / "request.json"
            request_path.write_text(json.dumps(request_value), encoding="utf-8")

            with patch("review_system.github_prospective_capture.intake_prospective_case") as intake:
                with self.assertRaisesRegex(GitHubProspectiveCaptureError, "task_id"):
                    materialize_github_prospective_capture(
                        candidate_path,
                        request=request_path,
                        workspace=root / "workspace",
                        profile=profile,
                        repository_root=root,
                        github_cli=_MaterializeCLI(),
                        collect_pr=lambda *args, **kwargs: (_source(), None),
                        capture_state=lambda *args, **kwargs: {"repository": {"head_revision": HEAD, "working_tree_dirty": False}},
                    )
                intake.assert_not_called()

    def test_analyze_pr_always_emits_capture_candidate_without_mutating_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "app").mkdir()
            (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
            (root / "app" / "api.ts").write_text("import { score } from '../src/core'\n", encoding="utf-8")
            _profile(root)
            output = root / "analysis"

            with patch("review_system.github_prospective_capture.intake_prospective_case") as intake:
                result = analyze_pull_request(
                    AnalyzePullRequestRequest(
                        pull_request="https://github.com/demo/repo/pull/7",
                        repository_root=root,
                        output_dir=output,
                    ),
                    github_cli=StubGitHubCLI(),
                )
                intake.assert_not_called()

            self.assertIsNotNone(result.prospective_candidate_path)
            self.assertTrue(result.prospective_candidate_path.is_file())
            _, candidate = load_github_prospective_capture_candidate(result.prospective_candidate_path)
            self.assertEqual("BLOCKED_EXACT_HEAD_REANALYSIS_REQUIRED", candidate["status"])
            self.assertFalse(candidate["human_review_recorded"])
            self.assertFalse(candidate["outcome_recorded"])


if __name__ == "__main__":
    unittest.main()

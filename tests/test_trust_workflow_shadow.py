from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from review_system.application import AnalyzePullRequestRequest, analyze_pull_request
from review_system.github_connector import CommandResult, collect_pull_request
from review_system.io import dump_json, load_data
from review_system.project_init import initialize_project
from review_system.trust import _profile_descriptor
from review_system.trust_workflow_shadow import (
    TrustWorkflowShadowError,
    build_workflow_semantic_shadow,
    build_workflow_semantic_shadow_from_files,
    verify_workflow_semantic_shadow_sources,
)
from review_system.workflow_semantics import build_workflow_diff_evidence
from tests.test_github_connector import PR_DATA, StubGitHubCLI


HEAD = "a" * 40
BASE = "b" * 40
WORKFLOW = ".github/workflows/ci.yml"
TEST_DIFF = (
    f"diff --git a/{WORKFLOW} b/{WORKFLOW}\n"
    f"--- a/{WORKFLOW}\n"
    f"+++ b/{WORKFLOW}\n"
    "@@ -10,2 +10,3 @@ jobs:\n"
    "       - run: npm run verify:old\n"
    "+      - run: npm run verify:new\n"
)
AUTHORITY_DIFF = (
    f"diff --git a/{WORKFLOW} b/{WORKFLOW}\n"
    f"--- a/{WORKFLOW}\n"
    f"+++ b/{WORKFLOW}\n"
    "@@ -1,3 +1,4 @@\n"
    " permissions:\n"
    "   contents: read\n"
    "+  statuses: write\n"
)


class ExactWorkflowCLI(StubGitHubCLI):
    def __init__(self, diff_text: str = TEST_DIFF):
        pr_data = deepcopy(PR_DATA)
        pr_data["baseRefOid"] = BASE
        pr_data["headRefOid"] = HEAD
        pr_data["changedFiles"] = 1
        pr_data["files"] = [{"path": WORKFLOW, "additions": 1, "deletions": 0}]
        super().__init__(
            pr_data=pr_data,
            api_files=[{"filename": WORKFLOW, "additions": 1, "deletions": 0}],
        )
        self.diff_text = diff_text

    def run(self, arguments, *, cwd=None, check=True, timeout_seconds=None):
        args = tuple(arguments)
        if args[:2] == ("pr", "diff"):
            return CommandResult(("gh", *args), 0, self.diff_text, "")
        return super().run(
            arguments,
            cwd=cwd,
            check=check,
            timeout_seconds=timeout_seconds,
        )


def _profile(root: Path) -> Path:
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "core.ts").write_text("export const score = 1\n", encoding="utf-8")
    initialize_project(root, preset="generic-webapp")
    return root / ".review" / "project.yml"


def _request_value() -> dict:
    return {
        "schema_version": "1.0",
        "task_id": "workflow-shadow-test",
        "source_revision": HEAD,
        "task_class": "routine_code",
        "changed_files": [WORKFLOW],
        "required_scenarios": [],
        "completed_scenarios": [],
        "repository_match": True,
        "head_match": True,
        "rollback_evidence": False,
        "replay_evidence": False,
        "readiness_policy": {
            "policy_id": "workflow-shadow-test",
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


def _source(diff_text: str) -> dict:
    source, observed = collect_pull_request(
        ExactWorkflowCLI(diff_text),
        "https://github.com/demo/repo/pull/7",
        cwd=".",
        include_diff=True,
        include_discussion=False,
    )
    assert observed == diff_text
    return source


class TrustWorkflowShadowTests(unittest.TestCase):
    def test_analyze_pr_emits_exact_workflow_semantics_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _profile(root)
            result = analyze_pull_request(
                AnalyzePullRequestRequest(
                    pull_request="https://github.com/demo/repo/pull/7",
                    repository_root=root,
                    output_dir=root / "analysis",
                    skip_discussion=True,
                ),
                github_cli=ExactWorkflowCLI(),
                capture_state=lambda *args, **kwargs: {
                    "repository": {
                        "root": str(root),
                        "branch": "feature",
                        "head_revision": HEAD,
                        "baseline_revision": None,
                        "working_tree_dirty": False,
                        "working_tree_entries": [],
                    }
                },
            )
            self.assertIsNotNone(result.workflow_semantics_path)
            self.assertTrue(result.workflow_semantics_path.is_file())
            evidence = load_data(result.workflow_semantics_path)
            self.assertEqual(evidence["source_revision"], "git:" + HEAD)
            self.assertEqual(evidence["source_evidence_sha256"], result.source["source_sha256"])
            self.assertEqual(evidence["diff_sha256"], result.source["diff"]["sha256"])
            self.assertEqual(evidence["workflows"][0]["classification"], "CI_TEST_WIRING_ONLY")
            self.assertTrue(profile.is_file())

    def test_analyze_pr_skip_diff_removes_stale_workflow_semantics_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _profile(root)
            output = root / "analysis"
            output.mkdir()
            stale = output / "workflow-semantics.json"
            stale.write_text("{}\n", encoding="utf-8")
            result = analyze_pull_request(
                AnalyzePullRequestRequest(
                    pull_request="https://github.com/demo/repo/pull/7",
                    repository_root=root,
                    output_dir=output,
                    skip_diff=True,
                    skip_discussion=True,
                ),
                github_cli=ExactWorkflowCLI(),
                capture_state=lambda *args, **kwargs: {
                    "repository": {
                        "root": str(root),
                        "branch": "feature",
                        "head_revision": HEAD,
                        "baseline_revision": None,
                        "working_tree_dirty": False,
                        "working_tree_entries": [],
                    }
                },
            )
            self.assertIsNone(result.workflow_semantics_path)
            self.assertFalse(stale.exists())

    def test_shadow_test_wiring_is_r3_authoritative_r2_candidate_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = _profile(root)
            _, profile = _profile_descriptor(profile_path)
            source = _source(TEST_DIFF)
            request = _request_value()
            request["source_revision"] = "git:" + HEAD
            shadow = build_workflow_semantic_shadow(
                request=request,
                profile=profile,
                github_source=source,
                diff_text=TEST_DIFF,
            )
            self.assertEqual(shadow["authority"], "SHADOW_ONLY")
            self.assertFalse(shadow["automation_authorized"])
            self.assertFalse(shadow["pilot_authorized"])
            self.assertEqual(shadow["authoritative_risk_band"], "R3")
            self.assertEqual(shadow["candidate_risk_band"], "R2")
            self.assertEqual(shadow["band_delta"], -1)
            self.assertTrue(shadow["band_changed"])
            self.assertEqual(
                shadow["workflow_semantics"]["workflows"][0]["classification"],
                "CI_TEST_WIRING_ONLY",
            )

    def test_shadow_authority_mutation_stays_r3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = _profile(root)
            _, profile = _profile_descriptor(profile_path)
            source = _source(AUTHORITY_DIFF)
            request = _request_value()
            request["source_revision"] = "git:" + HEAD
            shadow = build_workflow_semantic_shadow(
                request=request,
                profile=profile,
                github_source=source,
                diff_text=AUTHORITY_DIFF,
            )
            self.assertEqual(shadow["authoritative_risk_band"], "R3")
            self.assertEqual(shadow["candidate_risk_band"], "R3")
            self.assertEqual(shadow["band_delta"], 0)
            self.assertFalse(shadow["band_changed"])
            self.assertEqual(
                shadow["workflow_semantics"]["workflows"][0]["classification"],
                "AUTHORITY_MUTATION",
            )

    def test_shadow_fails_closed_on_request_or_diff_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = _profile(root)
            _, profile = _profile_descriptor(profile_path)
            source = _source(TEST_DIFF)
            request = _request_value()
            request["source_revision"] = "git:" + ("c" * 40)
            with self.assertRaisesRegex(TrustWorkflowShadowError, "source_revision"):
                build_workflow_semantic_shadow(
                    request=request,
                    profile=profile,
                    github_source=source,
                    diff_text=TEST_DIFF,
                )
            request["source_revision"] = "git:" + HEAD
            with self.assertRaisesRegex(TrustWorkflowShadowError, "diff SHA-256"):
                build_workflow_semantic_shadow(
                    request=request,
                    profile=profile,
                    github_source=source,
                    diff_text=TEST_DIFF + "\n",
                )

    def test_shadow_file_source_replay_is_deterministic_and_detects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = _profile(root)
            source = _source(TEST_DIFF)
            source_path = root / "github-source.json"
            diff_path = root / "pull-request.diff"
            request_path = root / "request.json"
            dump_json(source_path, source)
            diff_path.write_text(TEST_DIFF, encoding="utf-8")
            request_path.write_text(json.dumps(_request_value()), encoding="utf-8")

            first = build_workflow_semantic_shadow_from_files(
                request=request_path,
                profile=profile_path,
                github_source=source_path,
                diff=diff_path,
            )
            second = build_workflow_semantic_shadow_from_files(
                request=request_path,
                profile=profile_path,
                github_source=source_path,
                diff=diff_path,
            )
            self.assertEqual(first, second)
            self.assertRegex(first["shadow_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                verify_workflow_semantic_shadow_sources(
                    first,
                    request=request_path,
                    profile=profile_path,
                    github_source=source_path,
                    diff=diff_path,
                ),
                [],
            )
            diff_path.write_text(TEST_DIFF + "\n", encoding="utf-8")
            errors = verify_workflow_semantic_shadow_sources(
                first,
                request=request_path,
                profile=profile_path,
                github_source=source_path,
                diff=diff_path,
            )
            self.assertTrue(errors)

    def test_multi_commit_repeated_workflow_sections_are_aggregated_conservatively(self) -> None:
        repeated = (
            TEST_DIFF
            + "From deadbeef Mon Sep 17 00:00:00 2001\n"
            + f"diff --git a/{WORKFLOW} b/{WORKFLOW}\n"
            + f"--- a/{WORKFLOW}\n"
            + f"+++ b/{WORKFLOW}\n"
            + "@@ -20,2 +20,3 @@ jobs:\n"
            + "       - run: npm run test:old\n"
            + "+      - run: npm run test:new\n"
        )
        evidence = build_workflow_diff_evidence(
            source_revision=HEAD,
            source_evidence_sha256="f" * 64,
            changed_files=[WORKFLOW],
            diff_text=repeated,
        )
        self.assertEqual(evidence["workflow_count"], 1)
        self.assertEqual(evidence["workflows"][0]["classification"], "CI_TEST_WIRING_ONLY")
        self.assertEqual(evidence["workflows"][0]["changed_line_count"], 2)


if __name__ == "__main__":
    unittest.main()

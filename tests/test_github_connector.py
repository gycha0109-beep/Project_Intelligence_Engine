import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from review_system.github_connector import (
    CommandResult,
    GitHubCLI,
    GitHubCLIError,
    collect_pull_request,
    normalize_repository,
    parse_pr_target,
    refresh_source_hash,
    validate_pull_request_source,
)


PR_DATA = {
    "number": 7,
    "url": "https://github.com/demo/repo/pull/7",
    "title": "Change scoring",
    "body": "Body",
    "state": "OPEN",
    "isDraft": False,
    "isCrossRepository": False,
    "author": {"login": "dev"},
    "baseRefName": "main",
    "baseRefOid": "base123",
    "headRefName": "feature",
    "headRefOid": "head123",
    "createdAt": "2026-07-01T00:00:00Z",
    "updatedAt": "2026-07-02T00:00:00Z",
    "mergedAt": None,
    "mergedBy": None,
    "mergeable": "MERGEABLE",
    "mergeStateStatus": "CLEAN",
    "reviewDecision": "APPROVED",
    "additions": 4,
    "deletions": 1,
    "changedFiles": 1,
    "files": [{"path": "src/core.ts", "additions": 4, "deletions": 1}],
    "commits": [],
    "labels": [],
    "reviews": [],
    "latestReviews": [],
    "reviewRequests": [],
    "comments": [],
    "statusCheckRollup": [{"name": "test", "conclusion": "SUCCESS", "status": "COMPLETED"}],
}


class StubGitHubCLI:
    installed = True
    executable = "gh-stub"

    def __init__(self, *, authenticated=True, repository="demo/repo", diff_failure=False, pr_data=None, api_files=None):
        self.authenticated = authenticated
        self.repository = repository
        self.diff_failure = diff_failure
        self.pr_data = pr_data or PR_DATA
        self.api_files = api_files or [{"filename": "src/core.ts", "additions": 4, "deletions": 1}]

    def version(self):
        return "gh version 2.99.0-test"

    def auth_status(self, hostname="github.com"):
        return {"hostname": hostname, "authenticated": self.authenticated, "detail": "stub"}

    def current_repository(self, cwd):
        return {"name_with_owner": self.repository, "url": f"https://github.com/{self.repository}", "hostname": "github.com"}

    def run(self, arguments, *, cwd=None, check=True, timeout_seconds=None):
        args = tuple(arguments)
        if args[:2] == ("pr", "view"):
            return CommandResult(("gh", *args), 0, json.dumps(self.pr_data), "")
        if args[:2] == ("pr", "diff"):
            if self.diff_failure:
                return CommandResult(("gh", *args), 1, "", "diff too large")
            return CommandResult(("gh", *args), 0, "diff --git a/src/core.ts b/src/core.ts\n+export const score = 2\n", "")
        if args[:1] == ("api",):
            endpoint = next((value for value in args if value.startswith("repos/")), "")
            if endpoint.endswith("/files?per_page=100"):
                payload = [self.api_files]
            elif endpoint.endswith("/reviews?per_page=100"):
                payload = [[{"id": 21, "body": "approved", "state": "APPROVED", "user": {"login": "reviewer"}}]]
            elif endpoint.endswith("/pulls/7/comments?per_page=100"):
                payload = [[{"id": 31, "body": "inline", "path": "src/core.ts", "line": 1, "side": "RIGHT", "user": {"login": "reviewer"}}]]
            else:
                payload = [[{"id": 11, "body": "discussion", "user": {"login": "dev"}}]]
            return CommandResult(("gh", *args), 0, json.dumps(payload), "")
        raise AssertionError(f"unexpected command: {args}")


class GitHubTargetTests(unittest.TestCase):
    def test_parse_number_and_url(self):
        number = parse_pr_target("17")
        self.assertEqual(17, number.number)
        self.assertIsNone(number.repository)
        url = parse_pr_target("https://github.com/acme/widget/pull/22")
        self.assertEqual("acme/widget", url.repository)
        self.assertEqual("github.com", url.hostname)

    def test_rejects_unsafe_or_ambiguous_target(self):
        for value in ("", "0", "http://github.com/a/b/pull/1", "https://github.com/a/b/issues/1", "7; rm -rf /"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_pr_target(value)

    def test_normalize_repository(self):
        self.assertEqual(("github.com", "acme/widget"), normalize_repository("acme/widget"))
        self.assertEqual(("git.example.com", "acme/widget"), normalize_repository("git.example.com/acme/widget"))
        self.assertEqual(("github.com", "acme/widget"), normalize_repository("https://github.com/acme/widget.git"))


class GitHubCollectionTests(unittest.TestCase):
    def test_collects_metadata_diff_and_inline_review_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, diff = collect_pull_request(
                StubGitHubCLI(),
                "https://github.com/demo/repo/pull/7",
                cwd=tmp,
            )
            self.assertEqual(7, source["pull_request"]["number"])
            self.assertEqual([{"path": "src/core.ts", "additions": 4, "deletions": 1}], source["pull_request"]["changed_files"])
            self.assertTrue(source["diff"]["available"])
            self.assertTrue(source["discussion"]["complete"])
            self.assertEqual("inline", source["pull_request"]["inline_review_comments"][0]["body"])
            self.assertIn("src/core.ts", diff)
            self.assertEqual([], validate_pull_request_source(source))
            old_hash = source["source_sha256"]
            source["extra"] = "context"
            self.assertIn("source_sha256 mismatch", validate_pull_request_source(source))
            self.assertNotEqual(old_hash, refresh_source_hash(source))
            self.assertEqual([], validate_pull_request_source(source))

    def test_diff_failure_is_warning_not_metadata_failure(self):
        source, diff = collect_pull_request(StubGitHubCLI(diff_failure=True), "7", cwd=".")
        self.assertIsNone(diff)
        self.assertFalse(source["diff"]["available"])
        self.assertTrue(any("diff" in warning.lower() for warning in source["warnings"]))

    def test_collects_all_files_from_paginated_api(self):
        pr_data = dict(PR_DATA)
        pr_data["changedFiles"] = 101
        pr_data["files"] = [
            {"path": f"src/file-{index}.ts", "additions": 1, "deletions": 0}
            for index in range(100)
        ]
        api_files = [
            {"filename": f"src/file-{index}.ts", "additions": 1, "deletions": 0}
            for index in range(101)
        ]
        source, _ = collect_pull_request(
            StubGitHubCLI(pr_data=pr_data, api_files=api_files),
            "7",
            cwd=".",
        )
        self.assertEqual(101, len(source["pull_request"]["changed_files"]))
        self.assertIn("src/file-100.ts", {item["path"] for item in source["pull_request"]["changed_files"]})

    def test_authentication_failure_is_actionable(self):
        with self.assertRaisesRegex(GitHubCLIError, "gh auth login"):
            collect_pull_request(StubGitHubCLI(authenticated=False), "7", cwd=".")

    def test_real_runner_uses_argument_vector(self):
        completed = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        with patch("review_system.github.runner.subprocess.run", return_value=completed) as runner:
            result = GitHubCLI("gh-test").run(["literal;not-shell", "$(echo nope)"])
        self.assertEqual(0, result.returncode)
        self.assertEqual(("gh-test", "literal;not-shell", "$(echo nope)"), runner.call_args.args[0])
        self.assertNotIn("shell", runner.call_args.kwargs)

    def test_rate_limit_is_retried_and_actionable(self):
        limited = SimpleNamespace(returncode=1, stdout="", stderr="HTTP 429: API rate limit exceeded")
        with (
            patch("review_system.github.runner.subprocess.run", return_value=limited) as runner,
            patch("review_system.github.runner.time.sleep"),
        ):
            with self.assertRaisesRegex(GitHubCLIError, "gh api rate_limit"):
                GitHubCLI("gh-test").run(["api", "repos/demo/repo"])
        self.assertEqual(3, runner.call_count)


if __name__ == "__main__":
    unittest.main()

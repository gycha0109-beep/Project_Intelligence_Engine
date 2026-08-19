import json
import unittest
from dataclasses import FrozenInstanceError

from review_system.github.binding import RepositoryBinding
from review_system.github.discussion import DiscussionEvidence, collect_discussion
from review_system.github.pagination import collect_paginated_list, flatten_paginated_arrays
from review_system.github.runner import CommandResult, GitHubCLIError
from review_system.github.source import (
    assemble_pull_request_source,
    refresh_source_hash,
    validate_pull_request_source,
)


class APIStub:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def run(self, arguments, *, cwd=None, check=True, timeout_seconds=None):
        args = tuple(arguments)
        self.calls.append(args)
        endpoint = next((value for value in args if value.startswith("repos/")), "")
        response = self.responses[endpoint]
        if isinstance(response, CommandResult):
            return response
        return CommandResult(("gh", *args), 0, json.dumps(response), "")


class PaginationBoundaryTests(unittest.TestCase):
    def test_flattens_direct_and_slurped_arrays(self):
        self.assertEqual([{"id": 1}], flatten_paginated_arrays('[{"id": 1}]', label="direct"))
        self.assertEqual(
            [{"id": 1}, {"id": 2}],
            flatten_paginated_arrays('[[{"id": 1}], [{"id": 2}]]', label="slurped"),
        )

    def test_invalid_json_is_actionable(self):
        with self.assertRaisesRegex(GitHubCLIError, "returned invalid JSON"):
            flatten_paginated_arrays("not-json", label="example")

    def test_api_failure_returns_detail_without_raising(self):
        endpoint = "repos/demo/repo/pulls/7/files?per_page=100"
        cli = APIStub({endpoint: CommandResult(("gh", "api"), 1, "", "forbidden")})
        items, error = collect_paginated_list(cli, endpoint, hostname="github.com", cwd=".")
        self.assertIsNone(items)
        self.assertEqual("forbidden", error)
        self.assertEqual(
            (
                "api",
                "--hostname",
                "github.com",
                endpoint,
                "--paginate",
                "--slurp",
            ),
            cli.calls[0],
        )


class DiscussionBoundaryTests(unittest.TestCase):
    def test_collects_and_compacts_complete_discussion(self):
        base = "repos/demo/repo"
        cli = APIStub(
            {
                f"{base}/issues/7/comments?per_page=100": [[{"id": 1, "body": "issue", "user": {"login": "dev", "avatar": "ignored"}}]],
                f"{base}/pulls/7/reviews?per_page=100": [[{"id": 2, "body": "review", "state": "APPROVED", "user": {"login": "reviewer"}}]],
                f"{base}/pulls/7/comments?per_page=100": [[{"id": 3, "body": "inline", "path": "src/a.py", "line": 4, "user": {"login": "reviewer"}}]],
            }
        )
        result = collect_discussion(
            cli,
            endpoint_base=base,
            pr_number=7,
            hostname="github.com",
            cwd=".",
            initial_issue_comments=[],
            initial_reviews=[],
            include_discussion=True,
        )
        self.assertIsInstance(result, DiscussionEvidence)
        self.assertTrue(result.metadata["complete"])
        self.assertEqual({"login": "dev"}, result.issue_comments[0]["user"])
        self.assertEqual("src/a.py", result.inline_review_comments[0]["path"])
        self.assertEqual((), result.warnings)
        with self.assertRaises(FrozenInstanceError):
            result.metadata = {}

    def test_partial_failure_preserves_fallback_and_warning(self):
        base = "repos/demo/repo"
        cli = APIStub(
            {
                f"{base}/issues/7/comments?per_page=100": CommandResult(("gh", "api"), 1, "", "issue failure"),
                f"{base}/pulls/7/reviews?per_page=100": [[]],
                f"{base}/pulls/7/comments?per_page=100": [[]],
            }
        )
        result = collect_discussion(
            cli,
            endpoint_base=base,
            pr_number=7,
            hostname="github.com",
            cwd=".",
            initial_issue_comments=[{"body": "fallback"}],
            initial_reviews=[],
            include_discussion=True,
        )
        self.assertFalse(result.metadata["complete"])
        self.assertEqual("fallback", result.issue_comments[0]["body"])
        self.assertIn("issue failure", result.warnings[0])

    def test_disabled_discussion_uses_view_data_without_api_calls(self):
        cli = APIStub({})
        result = collect_discussion(
            cli,
            endpoint_base="repos/demo/repo",
            pr_number=7,
            hostname="github.com",
            cwd=".",
            initial_issue_comments=[{"body": "view"}],
            initial_reviews=[{"body": "view review"}],
            include_discussion=False,
        )
        self.assertEqual([], cli.calls)
        self.assertEqual({"requested": False, "complete": False}, result.metadata)
        self.assertEqual("view", result.issue_comments[0]["body"])


class SourceBoundaryTests(unittest.TestCase):
    def test_assembles_valid_deterministic_source(self):
        raw = {
            "number": 7,
            "url": "https://github.com/demo/repo/pull/7",
            "title": "Change",
            "comments": [],
            "reviews": [],
        }
        binding = RepositoryBinding("github.com", "demo/repo", "demo/repo")
        kwargs = {
            "raw": raw,
            "binding": binding,
            "pr_number": 7,
            "changed_files": [{"path": "src/a.py"}],
            "reviews": [],
            "issue_comments": [],
            "inline_review_comments": [],
            "diff_metadata": {"requested": False, "available": False},
            "discussion_metadata": {"requested": False, "complete": False},
            "warnings": [],
            "retrieved_at": "2026-07-24T00:00:00Z",
        }
        first = assemble_pull_request_source(**kwargs)
        second = assemble_pull_request_source(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual([], validate_pull_request_source(first))
        original = first["source_sha256"]
        first["extra"] = "tamper"
        self.assertIn("source_sha256 mismatch", validate_pull_request_source(first))
        self.assertNotEqual(original, refresh_source_hash(first))
        self.assertEqual([], validate_pull_request_source(first))


if __name__ == "__main__":
    unittest.main()

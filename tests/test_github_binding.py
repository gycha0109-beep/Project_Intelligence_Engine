import unittest
from dataclasses import FrozenInstanceError

from review_system.github.binding import RepositoryBinding, resolve_repository_binding
from review_system.github.runner import GitHubCLIError
from review_system.github.target import parse_pr_target


class StubCLI:
    def __init__(self, current=None):
        self.current = current
        self.calls = []

    def current_repository(self, cwd):
        self.calls.append(cwd)
        return self.current


class RepositoryBindingTests(unittest.TestCase):
    def test_explicit_repository_matching_url_is_normalized(self):
        target = parse_pr_target("https://github.com/Acme/Widget/pull/7")
        result = resolve_repository_binding(
            StubCLI(),
            target,
            cwd=".",
            repository="https://github.com/acme/widget.git",
        )
        self.assertEqual("github.com", result.hostname)
        self.assertEqual("acme/widget", result.name_with_owner)
        self.assertEqual("acme/widget", result.gh_repo_argument)

    def test_repository_mismatch_preserves_failure(self):
        target = parse_pr_target("https://github.com/acme/widget/pull/7")
        with self.assertRaisesRegex(ValueError, "PR URL repository acme/widget does not match --repo acme/other"):
            resolve_repository_binding(StubCLI(), target, cwd=".", repository="acme/other")

    def test_hostname_mismatch_preserves_failure(self):
        target = parse_pr_target("https://github.com/acme/widget/pull/7")
        with self.assertRaisesRegex(ValueError, "PR URL hostname github.com does not match --repo hostname git.example.com"):
            resolve_repository_binding(
                StubCLI(),
                target,
                cwd=".",
                repository="git.example.com/acme/widget",
            )

    def test_url_target_supplies_repository_without_current_lookup(self):
        cli = StubCLI(current={"hostname": "ignored", "name_with_owner": "ignored/repo"})
        result = resolve_repository_binding(
            cli,
            parse_pr_target("https://git.example.com/acme/widget/pull/7"),
            cwd="workspace",
        )
        self.assertEqual([], cli.calls)
        self.assertEqual("git.example.com", result.hostname)
        self.assertEqual("acme/widget", result.name_with_owner)
        self.assertEqual("git.example.com/acme/widget", result.gh_repo_argument)

    def test_numeric_target_uses_current_repository(self):
        cli = StubCLI(current={
            "hostname": "github.com",
            "name_with_owner": "demo/repo",
            "url": "https://github.com/demo/repo",
        })
        result = resolve_repository_binding(cli, parse_pr_target("7"), cwd="workspace")
        self.assertEqual(["workspace"], cli.calls)
        self.assertEqual("github.com", result.hostname)
        self.assertEqual("demo/repo", result.name_with_owner)
        self.assertEqual("demo/repo", result.gh_repo_argument)

    def test_numeric_target_without_current_repository_fails_closed(self):
        with self.assertRaisesRegex(GitHubCLIError, "cannot determine repository for a PR number"):
            resolve_repository_binding(StubCLI(), parse_pr_target("7"), cwd=".")

    def test_binding_is_frozen(self):
        binding = RepositoryBinding("github.com", "demo/repo", "demo/repo")
        with self.assertRaises(FrozenInstanceError):
            binding.hostname = "git.example.com"


if __name__ == "__main__":
    unittest.main()

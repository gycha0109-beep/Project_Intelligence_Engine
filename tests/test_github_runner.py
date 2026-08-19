import json
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import review_system.github.runner as extracted
import review_system.github_connector as legacy


class GitHubRunnerExtractionTests(unittest.TestCase):
    def test_legacy_exports_are_extracted_implementations(self):
        self.assertIs(legacy.GitHubCLI, extracted.GitHubCLI)
        self.assertIs(legacy.GitHubCLIError, extracted.GitHubCLIError)
        self.assertIs(legacy.CommandResult, extracted.CommandResult)

    def test_runner_uses_argument_vector_environment_cwd_and_timeout(self):
        completed = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            with patch("review_system.github.runner.subprocess.run", return_value=completed) as runner:
                result = extracted.GitHubCLI("gh-test", timeout_seconds=99).run(
                    ["literal;not-shell", "$(echo nope)"],
                    cwd=tmp,
                    timeout_seconds=7,
                )
        self.assertEqual(0, result.returncode)
        self.assertEqual(("gh-test", "literal;not-shell", "$(echo nope)"), runner.call_args.args[0])
        self.assertEqual(7, runner.call_args.kwargs["timeout"])
        self.assertEqual("cat", runner.call_args.kwargs["env"]["GH_PAGER"])
        self.assertEqual("cat", runner.call_args.kwargs["env"]["PAGER"])
        self.assertEqual("1", runner.call_args.kwargs["env"]["NO_COLOR"])
        self.assertNotIn("shell", runner.call_args.kwargs)

    def test_transient_server_error_retries_then_returns_success(self):
        responses = [
            SimpleNamespace(returncode=1, stdout="", stderr="HTTP 502"),
            SimpleNamespace(returncode=1, stdout="", stderr="HTTP 503"),
            SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        ]
        with (
            patch("review_system.github.runner.subprocess.run", side_effect=responses) as runner,
            patch("review_system.github.runner.time.sleep") as sleeper,
        ):
            result = extracted.GitHubCLI("gh-test").run(["api", "repos/demo/repo"])
        self.assertEqual(0, result.returncode)
        self.assertEqual(3, runner.call_count)
        self.assertEqual([unittest.mock.call(1), unittest.mock.call(2)], sleeper.call_args_list)

    def test_rate_limit_is_retried_three_times_and_actionable(self):
        limited = SimpleNamespace(returncode=1, stdout="", stderr="HTTP 429: API rate limit exceeded")
        with (
            patch("review_system.github.runner.subprocess.run", return_value=limited) as runner,
            patch("review_system.github.runner.time.sleep") as sleeper,
        ):
            with self.assertRaisesRegex(extracted.GitHubCLIError, "gh api rate_limit"):
                extracted.GitHubCLI("gh-test").run(["api", "repos/demo/repo"])
        self.assertEqual(3, runner.call_count)
        self.assertEqual([unittest.mock.call(1), unittest.mock.call(2)], sleeper.call_args_list)

    def test_non_retryable_failure_runs_once(self):
        denied = SimpleNamespace(returncode=1, stdout="", stderr="permission denied")
        with (
            patch("review_system.github.runner.subprocess.run", return_value=denied) as runner,
            patch("review_system.github.runner.time.sleep") as sleeper,
        ):
            with self.assertRaisesRegex(extracted.GitHubCLIError, "permission denied"):
                extracted.GitHubCLI("gh-test").run(["repo", "view"])
        self.assertEqual(1, runner.call_count)
        sleeper.assert_not_called()

    def test_check_false_returns_failure_result(self):
        denied = SimpleNamespace(returncode=2, stdout="out", stderr="err")
        with patch("review_system.github.runner.subprocess.run", return_value=denied):
            result = extracted.GitHubCLI("gh-test").run(["repo", "view"], check=False)
        self.assertEqual(2, result.returncode)
        self.assertEqual("out", result.stdout)
        self.assertEqual("err", result.stderr)

    def test_timeout_and_os_error_are_wrapped(self):
        with patch(
            "review_system.github.runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["gh-test"], timeout=4),
        ):
            with self.assertRaisesRegex(extracted.GitHubCLIError, "timed out after 4 seconds"):
                extracted.GitHubCLI("gh-test").run(["repo", "view"])
        with patch("review_system.github.runner.subprocess.run", side_effect=OSError("boom")):
            with self.assertRaisesRegex(extracted.GitHubCLIError, "failed to execute GitHub CLI: boom"):
                extracted.GitHubCLI("gh-test").run(["repo", "view"])

    def test_version_auth_and_current_repository_contracts(self):
        cli = extracted.GitHubCLI("gh-test")
        results = [
            extracted.CommandResult(("gh-test", "--version"), 0, "gh version 2.99.0\nextra", ""),
            extracted.CommandResult(("gh-test", "auth"), 1, "", "not logged in\r\nnext"),
            extracted.CommandResult(
                ("gh-test", "repo"),
                0,
                json.dumps({"nameWithOwner": "demo/repo", "url": "https://git.example.com/demo/repo"}),
                "",
            ),
        ]
        with patch.object(cli, "run", side_effect=results):
            self.assertEqual("gh version 2.99.0", cli.version())
            self.assertEqual(
                {"hostname": "git.example.com", "authenticated": False, "detail": "not logged in\nnext"},
                cli.auth_status("git.example.com"),
            )
            self.assertEqual(
                {
                    "name_with_owner": "demo/repo",
                    "url": "https://git.example.com/demo/repo",
                    "hostname": "git.example.com",
                },
                cli.current_repository("."),
            )

    def test_missing_executable_contracts(self):
        with patch("review_system.github.runner.shutil.which", return_value=None):
            cli = extracted.GitHubCLI()
        self.assertFalse(cli.installed)
        self.assertIsNone(cli.version())
        self.assertEqual(
            {"hostname": "github.com", "authenticated": False, "detail": "gh is not installed"},
            cli.auth_status(),
        )
        with self.assertRaisesRegex(extracted.GitHubCLIError, "not installed"):
            cli.run(["--version"])


if __name__ == "__main__":
    unittest.main()

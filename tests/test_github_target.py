import unittest

import review_system.github.target as extracted
import review_system.github_connector as legacy


class GitHubTargetExtractionTests(unittest.TestCase):
    def test_legacy_exports_are_the_extracted_implementations(self):
        self.assertIs(legacy.PullRequestTarget, extracted.PullRequestTarget)
        self.assertIs(legacy.parse_pr_target, extracted.parse_pr_target)
        self.assertIs(legacy.normalize_repository, extracted.normalize_repository)

    def test_numeric_target_preserves_whitespace_and_default_host_behavior(self):
        target = extracted.parse_pr_target(" 17 ")
        self.assertEqual("17", target.raw)
        self.assertEqual(17, target.number)
        self.assertEqual("github.com", target.hostname)
        self.assertIsNone(target.repository)
        self.assertEqual("17", target.gh_target)

    def test_https_pr_url_preserves_enterprise_and_trailing_path_behavior(self):
        raw = "https://Git.Example.com/acme/widget/pull/22/files"
        target = extracted.parse_pr_target(raw)
        self.assertEqual(22, target.number)
        self.assertEqual("git.example.com", target.hostname)
        self.assertEqual("acme/widget", target.repository)
        self.assertEqual(raw, target.gh_target)

    def test_rejects_existing_unsafe_and_ambiguous_inputs(self):
        values = (
            "",
            "0",
            "http://github.com/a/b/pull/1",
            "https://github.com/a/b/issues/1",
            "7; rm -rf /",
        )
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    extracted.parse_pr_target(value)

    def test_repository_normalization_preserves_supported_forms(self):
        self.assertEqual(("github.com", "acme/widget"), extracted.normalize_repository(" acme/widget "))
        self.assertEqual(("git.example.com", "acme/widget"), extracted.normalize_repository("git.example.com/acme/widget"))
        self.assertEqual(("github.com", "acme/widget"), extracted.normalize_repository("https://github.com/acme/widget.git/"))
        self.assertEqual(("enterprise.local", "acme/widget"), extracted.normalize_repository("acme/widget", default_hostname="enterprise.local"))

    def test_repository_argument_preserves_public_and_enterprise_forms(self):
        self.assertEqual("acme/widget", extracted.repository_argument("github.com", "acme/widget"))
        self.assertEqual("git.example.com/acme/widget", extracted.repository_argument("git.example.com", "acme/widget"))


if __name__ == "__main__":
    unittest.main()

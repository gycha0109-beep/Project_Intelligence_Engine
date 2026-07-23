from pathlib import Path


TARGET_MODULE = '''from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


_GITHUB_PR_RE = re.compile(r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>[1-9][0-9]*)(?:/.*)?$")
_REPOSITORY_RE = re.compile(r"^(?:(?P<host>[A-Za-z0-9.-]+)/)?(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)$")


@dataclass(frozen=True)
class PullRequestTarget:
    raw: str
    number: int
    hostname: str
    repository: str | None
    gh_target: str


def parse_pr_target(value: str) -> PullRequestTarget:
    raw = value.strip()
    if not raw:
        raise ValueError("pull request target is empty")
    if raw.isdigit():
        number = int(raw)
        if number < 1:
            raise ValueError("pull request number must be positive")
        return PullRequestTarget(raw=raw, number=number, hostname="github.com", repository=None, gh_target=raw)

    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("pull request target must be a positive PR number or an https GitHub PR URL")
    match = _GITHUB_PR_RE.fullmatch(parsed.path)
    if not match:
        raise ValueError("pull request URL must match https://HOST/OWNER/REPO/pull/NUMBER")
    repository = f"{match.group('owner')}/{match.group('repo')}"
    return PullRequestTarget(
        raw=raw,
        number=int(match.group("number")),
        hostname=parsed.hostname.lower(),
        repository=repository,
        gh_target=raw,
    )


def normalize_repository(value: str, *, default_hostname: str = "github.com") -> tuple[str, str]:
    raw = value.strip().rstrip("/")
    if raw.startswith("https://"):
        parsed = urlparse(raw)
        if not parsed.hostname:
            raise ValueError("repository URL has no hostname")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2:
            raise ValueError("repository URL must match https://HOST/OWNER/REPO")
        repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
        return parsed.hostname.lower(), f"{parts[0]}/{repo}"
    match = _REPOSITORY_RE.fullmatch(raw)
    if not match:
        raise ValueError("repository must use OWNER/REPO, HOST/OWNER/REPO, or an https repository URL")
    hostname = (match.group("host") or default_hostname).lower()
    return hostname, f"{match.group('owner')}/{match.group('repo')}"


def repository_argument(hostname: str, repository: str) -> str:
    return repository if hostname == "github.com" else f"{hostname}/{repository}"
'''

PACKAGE_INIT = '''"""GitHub integration internals with compatibility exports."""

from .target import PullRequestTarget, normalize_repository, parse_pr_target, repository_argument

__all__ = [
    "PullRequestTarget",
    "normalize_repository",
    "parse_pr_target",
    "repository_argument",
]
'''

TARGET_TEST = '''import unittest

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
'''

root = Path("src/review_system/github")
root.mkdir(parents=True, exist_ok=True)
(root / "target.py").write_text(TARGET_MODULE, encoding="utf-8")
(root / "__init__.py").write_text(PACKAGE_INIT, encoding="utf-8")
Path("tests/test_github_target.py").write_text(TARGET_TEST, encoding="utf-8")

connector_path = Path("src/review_system/github_connector.py")
text = connector_path.read_text(encoding="utf-8")

constants = '''_GITHUB_PR_RE = re.compile(r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>[1-9][0-9]*)(?:/.*)?$")
_REPOSITORY_RE = re.compile(r"^(?:(?P<host>[A-Za-z0-9.-]+)/)?(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)$")
'''
text = text.replace(constants + "\n", "", 1)

import_anchor = "from urllib.parse import urlparse\n"
import_block = '''from urllib.parse import urlparse

from .github.target import (
    PullRequestTarget,
    normalize_repository,
    parse_pr_target,
    repository_argument as _repo_argument,
)
'''
if import_block not in text:
    if import_anchor not in text:
        raise SystemExit("urlparse import anchor not found")
    text = text.replace(import_anchor, import_block, 1)

class_block = '''@dataclass(frozen=True)
class PullRequestTarget:
    raw: str
    number: int
    hostname: str
    repository: str | None
    gh_target: str


'''
text = text.replace(class_block, "", 1)

function_block = '''def parse_pr_target(value: str) -> PullRequestTarget:
    raw = value.strip()
    if not raw:
        raise ValueError("pull request target is empty")
    if raw.isdigit():
        number = int(raw)
        if number < 1:
            raise ValueError("pull request number must be positive")
        return PullRequestTarget(raw=raw, number=number, hostname="github.com", repository=None, gh_target=raw)

    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("pull request target must be a positive PR number or an https GitHub PR URL")
    match = _GITHUB_PR_RE.fullmatch(parsed.path)
    if not match:
        raise ValueError("pull request URL must match https://HOST/OWNER/REPO/pull/NUMBER")
    repository = f"{match.group('owner')}/{match.group('repo')}"
    return PullRequestTarget(
        raw=raw,
        number=int(match.group("number")),
        hostname=parsed.hostname.lower(),
        repository=repository,
        gh_target=raw,
    )


def normalize_repository(value: str, *, default_hostname: str = "github.com") -> tuple[str, str]:
    raw = value.strip().rstrip("/")
    if raw.startswith("https://"):
        parsed = urlparse(raw)
        if not parsed.hostname:
            raise ValueError("repository URL has no hostname")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2:
            raise ValueError("repository URL must match https://HOST/OWNER/REPO")
        repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
        return parsed.hostname.lower(), f"{parts[0]}/{repo}"
    match = _REPOSITORY_RE.fullmatch(raw)
    if not match:
        raise ValueError("repository must use OWNER/REPO, HOST/OWNER/REPO, or an https repository URL")
    hostname = (match.group("host") or default_hostname).lower()
    return hostname, f"{match.group('owner')}/{match.group('repo')}"


def _repo_argument(hostname: str, repository: str) -> str:
    return repository if hostname == "github.com" else f"{hostname}/{repository}"


'''
if function_block not in text:
    raise SystemExit("target parsing block not found")
text = text.replace(function_block, "", 1)
connector_path.write_text(text, encoding="utf-8")

readme_path = Path("docs/architecture/README.md")
readme = readme_path.read_text(encoding="utf-8")
readme = readme.replace(
    "7. [STAGE-1B-INDEX-ANALYZE-BOUNDARY.md](STAGE-1B-INDEX-ANALYZE-BOUNDARY.md) — IndexProject·AnalyzeChange application boundary 설계·리뷰·검증\n8. [STAGE-1C-RULE-GATE-BOUNDARY.md](STAGE-1C-RULE-GATE-BOUNDARY.md) — ApproveRule·CalculateGate application boundary 설계·리뷰·검증\n",
    "7. [STAGE-1B-INDEX-ANALYZE-BOUNDARY.md](STAGE-1B-INDEX-ANALYZE-BOUNDARY.md) — IndexProject·AnalyzeChange application boundary 설계·리뷰·검증\n8. [STAGE-1C-RULE-GATE-BOUNDARY.md](STAGE-1C-RULE-GATE-BOUNDARY.md) — ApproveRule·CalculateGate application boundary 설계·리뷰·검증\n9. [STAGE-2A-GITHUB-TARGET-EXTRACTION.md](STAGE-2A-GITHUB-TARGET-EXTRACTION.md) — GitHub target·repository parser 분리 설계·리뷰·검증\n",
    1,
)
readme = readme.replace(
    "- Stage 1C — ApproveRule / CalculateGate Application Boundaries: `PASS`, PR #6 검토 대기\n\n## 다음 단계\n\n남은 CLI orchestration을 점검해 Application Boundary Extraction을 동결한 뒤 Evidence Ledger 단계로 진입한다.\n",
    "- Stage 1C — ApproveRule / CalculateGate Application Boundaries: `PASS`, PR #6 검토 대기\n- Stage 2A — GitHub Target Parsing Extraction: 구현 리뷰 진행\n\n## 다음 단계\n\nStage 2A 승인 후 GitHub CLI command runner와 retry 책임을 별도 모듈로 추출한다.\n",
    1,
)
readme_path.write_text(readme, encoding="utf-8")

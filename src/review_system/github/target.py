from __future__ import annotations

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

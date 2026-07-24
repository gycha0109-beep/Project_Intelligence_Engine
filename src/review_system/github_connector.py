from __future__ import annotations

from pathlib import Path
from typing import Any

from .github.collector import collect_pull_request
from .github.runner import CommandResult, GitHubCLI, GitHubCLIError
from .github.source import refresh_source_hash, validate_pull_request_source
from .github.target import PullRequestTarget, normalize_repository, parse_pr_target


__all__ = [
    "CommandResult",
    "GitHubCLI",
    "GitHubCLIError",
    "PullRequestTarget",
    "collect_pull_request",
    "doctor",
    "normalize_repository",
    "parse_pr_target",
    "refresh_source_hash",
    "validate_pull_request_source",
]


def doctor(cli: GitHubCLI, *, cwd: str | Path, hostname: str = "github.com") -> dict[str, Any]:
    version = cli.version()
    auth = cli.auth_status(hostname)
    current_repo = cli.current_repository(cwd) if cli.installed else None
    return {
        "schema_version": "1.0",
        "ready": bool(cli.installed and version and auth["authenticated"]),
        "gh": {"installed": cli.installed, "executable": cli.executable, "version": version},
        "authentication": auth,
        "current_repository": current_repo,
    }

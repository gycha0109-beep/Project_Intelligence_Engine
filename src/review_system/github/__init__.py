"""GitHub integration internals with compatibility exports."""

from .runner import CommandResult, GitHubCLI, GitHubCLIError
from .target import PullRequestTarget, normalize_repository, parse_pr_target, repository_argument

__all__ = [
    "CommandResult",
    "GitHubCLI",
    "GitHubCLIError",
    "PullRequestTarget",
    "normalize_repository",
    "parse_pr_target",
    "repository_argument",
]

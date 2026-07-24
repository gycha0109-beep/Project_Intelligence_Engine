"""GitHub integration internals with compatibility exports."""

from .binding import RepositoryBinding, resolve_repository_binding
from .runner import CommandResult, GitHubCLI, GitHubCLIError
from .target import PullRequestTarget, normalize_repository, parse_pr_target, repository_argument

__all__ = [
    "CommandResult",
    "GitHubCLI",
    "GitHubCLIError",
    "PullRequestTarget",
    "RepositoryBinding",
    "normalize_repository",
    "parse_pr_target",
    "repository_argument",
    "resolve_repository_binding",
]

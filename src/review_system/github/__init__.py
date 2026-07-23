"""GitHub integration internals with compatibility exports."""

from .target import PullRequestTarget, normalize_repository, parse_pr_target, repository_argument

__all__ = [
    "PullRequestTarget",
    "normalize_repository",
    "parse_pr_target",
    "repository_argument",
]

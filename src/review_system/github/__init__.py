"""GitHub integration internals with compatibility exports."""

from .binding import RepositoryBinding, resolve_repository_binding
from .collector import collect_pull_request, normalize_changed_files
from .discussion import DiscussionEvidence, collect_discussion
from .pagination import collect_paginated_list, flatten_paginated_arrays
from .runner import CommandResult, GitHubCLI, GitHubCLIError
from .source import assemble_pull_request_source, refresh_source_hash, validate_pull_request_source
from .target import PullRequestTarget, normalize_repository, parse_pr_target, repository_argument

__all__ = [
    "CommandResult",
    "DiscussionEvidence",
    "GitHubCLI",
    "GitHubCLIError",
    "PullRequestTarget",
    "RepositoryBinding",
    "assemble_pull_request_source",
    "collect_discussion",
    "collect_paginated_list",
    "collect_pull_request",
    "flatten_paginated_arrays",
    "normalize_changed_files",
    "normalize_repository",
    "parse_pr_target",
    "refresh_source_hash",
    "repository_argument",
    "resolve_repository_binding",
    "validate_pull_request_source",
]

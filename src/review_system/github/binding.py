from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .runner import GitHubCLI, GitHubCLIError
from .target import PullRequestTarget, normalize_repository, repository_argument


@dataclass(frozen=True)
class RepositoryBinding:
    hostname: str
    name_with_owner: str
    gh_repo_argument: str


def resolve_repository_binding(
    cli: GitHubCLI,
    target: PullRequestTarget,
    *,
    cwd: str | Path,
    repository: str | None = None,
) -> RepositoryBinding:
    if repository:
        repo_hostname, repo_name = normalize_repository(repository, default_hostname=target.hostname)
        if target.repository and target.repository.lower() != repo_name.lower():
            raise ValueError(f"PR URL repository {target.repository} does not match --repo {repo_name}")
        if target.hostname != repo_hostname and target.repository:
            raise ValueError(f"PR URL hostname {target.hostname} does not match --repo hostname {repo_hostname}")
    elif target.repository:
        repo_hostname, repo_name = target.hostname, target.repository
    else:
        current = cli.current_repository(cwd)
        if not current:
            raise GitHubCLIError(
                "cannot determine repository for a PR number; run inside a Git repository or provide --repo OWNER/REPO"
            )
        repo_hostname, repo_name = current["hostname"], current["name_with_owner"]

    return RepositoryBinding(
        hostname=repo_hostname,
        name_with_owner=repo_name,
        gh_repo_argument=repository_argument(repo_hostname, repo_name),
    )

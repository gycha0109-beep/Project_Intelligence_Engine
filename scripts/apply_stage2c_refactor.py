from pathlib import Path

connector_path = Path("src/review_system/github_connector.py")
text = connector_path.read_text(encoding="utf-8")

old_imports = '''from .github.runner import CommandResult, GitHubCLI, GitHubCLIError
from .github.target import (
    PullRequestTarget,
    normalize_repository,
    parse_pr_target,
    repository_argument as _repo_argument,
)
'''
new_imports = '''from .github.binding import resolve_repository_binding
from .github.runner import CommandResult, GitHubCLI, GitHubCLIError
from .github.target import PullRequestTarget, normalize_repository, parse_pr_target
'''
if old_imports not in text:
    raise SystemExit("connector import block not found")
text = text.replace(old_imports, new_imports, 1)

old_binding = '''    target = parse_pr_target(target_value)
    repo_hostname: str
    repo_name: str

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
            raise GitHubCLIError("cannot determine repository for a PR number; run inside a Git repository or provide --repo OWNER/REPO")
        repo_hostname, repo_name = current["hostname"], current["name_with_owner"]

    auth = cli.auth_status(repo_hostname)
'''
new_binding = '''    target = parse_pr_target(target_value)
    binding = resolve_repository_binding(
        cli,
        target,
        cwd=cwd,
        repository=repository,
    )
    repo_hostname = binding.hostname
    repo_name = binding.name_with_owner

    auth = cli.auth_status(repo_hostname)
'''
if old_binding not in text:
    raise SystemExit("repository binding block not found")
text = text.replace(old_binding, new_binding, 1)

old_repo_arg = "    repo_arg = _repo_argument(repo_hostname, repo_name)\n"
new_repo_arg = "    repo_arg = binding.gh_repo_argument\n"
if old_repo_arg not in text:
    raise SystemExit("repo argument line not found")
text = text.replace(old_repo_arg, new_repo_arg, 1)
connector_path.write_text(text, encoding="utf-8")

Path("src/review_system/github/__init__.py").write_text(
    '''"""GitHub integration internals with compatibility exports."""

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
''',
    encoding="utf-8",
)

readme_path = Path("docs/architecture/README.md")
readme = readme_path.read_text(encoding="utf-8")
readme = readme.replace(
    "10. [STAGE-2B-GITHUB-RUNNER-EXTRACTION.md](STAGE-2B-GITHUB-RUNNER-EXTRACTION.md) — GitHub CLI runner·retry policy 분리 설계·리뷰·검증\n",
    "10. [STAGE-2B-GITHUB-RUNNER-EXTRACTION.md](STAGE-2B-GITHUB-RUNNER-EXTRACTION.md) — GitHub CLI runner·retry policy 분리 설계·리뷰·검증\n11. [STAGE-2C-REPOSITORY-BINDING.md](STAGE-2C-REPOSITORY-BINDING.md) — PR target·repository binding 분리 설계·리뷰·검증\n",
    1,
)
readme = readme.replace(
    "- Stage 2B — GitHub CLI Runner Extraction: `PASS`, PR #8 검토 대기\n\n## 다음 단계\n\nStage 2C에서 repository binding과 PR collector 책임의 경계를 먼저 설계하고 characterisation 범위를 고정한다.\n",
    "- Stage 2B — GitHub CLI Runner Extraction: `PASS`, PR #8 검토 대기\n- Stage 2C — Repository Binding Extraction: 구현 리뷰 진행\n\n## 다음 단계\n\nStage 2C 승인 후 PR collector의 pagination·discussion·artifact 조립 책임을 별도 모듈로 분리한다.\n",
    1,
)
readme_path.write_text(readme, encoding="utf-8")

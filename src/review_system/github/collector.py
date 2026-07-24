from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .binding import resolve_repository_binding
from .discussion import collect_discussion
from .pagination import collect_paginated_list
from .runner import GitHubCLI, GitHubCLIError
from .source import assemble_pull_request_source
from .target import parse_pr_target


_PR_JSON_FIELDS = (
    "additions",
    "author",
    "baseRefName",
    "baseRefOid",
    "body",
    "changedFiles",
    "comments",
    "commits",
    "createdAt",
    "deletions",
    "files",
    "headRefName",
    "headRefOid",
    "isCrossRepository",
    "isDraft",
    "labels",
    "latestReviews",
    "mergeStateStatus",
    "mergeable",
    "mergedAt",
    "mergedBy",
    "number",
    "reviewDecision",
    "reviewRequests",
    "reviews",
    "state",
    "statusCheckRollup",
    "title",
    "updatedAt",
    "url",
)


def _load_json_object(text: str, *, label: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GitHubCLIError(f"{label} returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise GitHubCLIError(f"{label} must return a JSON object")
    return data


def normalize_changed_files(files: Any) -> list[dict[str, Any]]:
    if not isinstance(files, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or item.get("filename")
        if not isinstance(path, str) or not path.strip():
            continue
        record: dict[str, Any] = {"path": path.replace("\\", "/")}
        for field in ("additions", "deletions"):
            value = item.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                record[field] = value
        normalized.append(record)
    return sorted(normalized, key=lambda item: item["path"])


def collect_pull_request(
    cli: GitHubCLI,
    target_value: str,
    *,
    cwd: str | Path,
    repository: str | None = None,
    include_diff: bool = True,
    include_discussion: bool = True,
) -> tuple[dict[str, Any], str | None]:
    target = parse_pr_target(target_value)
    binding = resolve_repository_binding(
        cli,
        target,
        cwd=cwd,
        repository=repository,
    )

    auth = cli.auth_status(binding.hostname)
    if not auth["authenticated"]:
        raise GitHubCLIError(
            f"GitHub CLI is not authenticated for {binding.hostname}; "
            f"run 'gh auth login --hostname {binding.hostname}'"
        )

    view_result = cli.run(
        [
            "pr",
            "view",
            target.gh_target,
            "--repo",
            binding.gh_repo_argument,
            "--json",
            ",".join(_PR_JSON_FIELDS),
        ],
        cwd=cwd,
    )
    raw = _load_json_object(view_result.stdout, label="gh pr view")
    files = normalize_changed_files(raw.get("files"))
    warnings: list[str] = []
    declared_count = raw.get("changedFiles")

    owner, repository_name = binding.name_with_owner.split("/", 1)
    endpoint_base = f"repos/{owner}/{repository_name}"
    collected_files, files_error = collect_paginated_list(
        cli,
        f"{endpoint_base}/pulls/{target.number}/files?per_page=100",
        hostname=binding.hostname,
        cwd=cwd,
    )
    if collected_files is not None:
        files = normalize_changed_files(collected_files)
    elif isinstance(declared_count, int) and declared_count != len(files):
        raise GitHubCLIError(
            f"could not collect all changed files: GitHub declared {declared_count}, "
            f"gh pr view returned {len(files)}, and the paginated API failed: {files_error}"
        )
    elif files_error:
        warnings.append(f"paginated changed files could not be collected: {files_error}")
    if isinstance(declared_count, int) and declared_count != len(files):
        raise GitHubCLIError(
            f"incomplete changed-file evidence: GitHub declared {declared_count} but collected {len(files)}"
        )

    diff_text: str | None = None
    diff_metadata: dict[str, Any] = {"requested": include_diff, "available": False}
    if include_diff:
        diff_result = cli.run(
            ["pr", "diff", target.gh_target, "--repo", binding.gh_repo_argument, "--patch"],
            cwd=cwd,
            check=False,
        )
        if diff_result.returncode == 0:
            diff_text = diff_result.stdout
            encoded = diff_text.encode("utf-8")
            diff_metadata.update(
                {
                    "available": True,
                    "bytes": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                }
            )
        else:
            detail = diff_result.stderr.strip() or diff_result.stdout.strip() or "unknown failure"
            warnings.append(f"PR diff could not be collected: {detail}")
            diff_metadata["error"] = detail

    pr_number = raw.get("number")
    if not isinstance(pr_number, int) or pr_number < 1:
        raise GitHubCLIError("gh pr view response has no valid PR number")
    if pr_number != target.number:
        raise GitHubCLIError(f"gh pr view returned PR #{pr_number}, expected #{target.number}")
    response_url = raw.get("url")
    if isinstance(response_url, str) and response_url:
        response_target = parse_pr_target(response_url)
        if (
            response_target.hostname != binding.hostname
            or response_target.repository.lower() != binding.name_with_owner.lower()
        ):
            raise GitHubCLIError("gh pr view response repository does not match the requested repository")

    initial_issue_comments = raw.get("comments") if isinstance(raw.get("comments"), list) else []
    initial_reviews = raw.get("reviews") if isinstance(raw.get("reviews"), list) else []
    discussion = collect_discussion(
        cli,
        endpoint_base=endpoint_base,
        pr_number=pr_number,
        hostname=binding.hostname,
        cwd=cwd,
        initial_issue_comments=initial_issue_comments,
        initial_reviews=initial_reviews,
        include_discussion=include_discussion,
    )
    warnings.extend(discussion.warnings)

    source = assemble_pull_request_source(
        raw=raw,
        binding=binding,
        pr_number=pr_number,
        changed_files=files,
        reviews=list(discussion.reviews),
        issue_comments=list(discussion.issue_comments),
        inline_review_comments=list(discussion.inline_review_comments),
        diff_metadata=diff_metadata,
        discussion_metadata=discussion.metadata,
        warnings=warnings,
    )
    return source, diff_text

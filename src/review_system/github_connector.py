from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .github.binding import resolve_repository_binding
from .github.runner import CommandResult, GitHubCLI, GitHubCLIError
from .github.target import PullRequestTarget, normalize_repository, parse_pr_target


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


def _canonical_sha256(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_files(files: Any) -> list[dict[str, Any]]:
    if not isinstance(files, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        # `gh pr view --json files` uses `path`, while the paginated REST
        # endpoint uses `filename`. Supporting both lets us avoid GraphQL's
        # 100-file truncation for large pull requests.
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



def _flatten_paginated_arrays(text: str, *, label: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GitHubCLIError(f"{label} returned invalid JSON: {exc}") from exc
    pages = data if isinstance(data, list) else []
    if pages and all(isinstance(item, dict) for item in pages):
        return [item for item in pages if isinstance(item, dict)]
    result: list[dict[str, Any]] = []
    for page in pages:
        if isinstance(page, list):
            result.extend(item for item in page if isinstance(item, dict))
    return result


def _api_list(
    cli: GitHubCLI,
    endpoint: str,
    *,
    hostname: str,
    cwd: str | Path,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    response = cli.run(
        ["api", "--hostname", hostname, endpoint, "--paginate", "--slurp"],
        cwd=cwd,
        check=False,
    )
    if response.returncode != 0:
        detail = response.stderr.strip() or response.stdout.strip() or "unknown failure"
        return None, detail
    try:
        return _flatten_paginated_arrays(response.stdout, label=f"gh api {endpoint}"), None
    except GitHubCLIError as exc:
        return None, str(exc)


def _compact_actor(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = {key: value.get(key) for key in ("login", "id", "type") if value.get(key) is not None}
    return result or None


def _compact_comments(items: list[dict[str, Any]], *, review_comment: bool = False) -> list[dict[str, Any]]:
    common = ("id", "body", "created_at", "updated_at", "html_url", "author_association")
    review_fields = (
        "path", "line", "side", "start_line", "start_side", "commit_id",
        "original_commit_id", "in_reply_to_id", "pull_request_review_id", "subject_type",
    )
    result: list[dict[str, Any]] = []
    for item in items:
        compact = {key: item.get(key) for key in common if item.get(key) is not None}
        actor = _compact_actor(item.get("user"))
        if actor:
            compact["user"] = actor
        if review_comment:
            compact.update({key: item.get(key) for key in review_fields if item.get(key) is not None})
        result.append(compact)
    return result


def _compact_reviews(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ("id", "body", "state", "html_url", "submitted_at", "commit_id", "author_association")
    result: list[dict[str, Any]] = []
    for item in items:
        compact = {key: item.get(key) for key in fields if item.get(key) is not None}
        actor = _compact_actor(item.get("user"))
        if actor:
            compact["user"] = actor
        result.append(compact)
    return result


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
    repo_hostname = binding.hostname
    repo_name = binding.name_with_owner

    auth = cli.auth_status(repo_hostname)
    if not auth["authenticated"]:
        raise GitHubCLIError(
            f"GitHub CLI is not authenticated for {repo_hostname}; run 'gh auth login --hostname {repo_hostname}'"
        )

    repo_arg = binding.gh_repo_argument
    view_result = cli.run(
        ["pr", "view", target.gh_target, "--repo", repo_arg, "--json", ",".join(_PR_JSON_FIELDS)],
        cwd=cwd,
    )
    raw = _load_json_object(view_result.stdout, label="gh pr view")
    files = _normalize_files(raw.get("files"))
    warnings: list[str] = []
    declared_count = raw.get("changedFiles")

    owner, repository_name = repo_name.split("/", 1)
    endpoint_base = f"repos/{owner}/{repository_name}"
    collected_files, files_error = _api_list(
        cli,
        f"{endpoint_base}/pulls/{target.number}/files?per_page=100",
        hostname=repo_hostname,
        cwd=cwd,
    )
    if collected_files is not None:
        files = _normalize_files(collected_files)
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
        diff_result = cli.run(["pr", "diff", target.gh_target, "--repo", repo_arg, "--patch"], cwd=cwd, check=False)
        if diff_result.returncode == 0:
            diff_text = diff_result.stdout
            encoded = diff_text.encode("utf-8")
            diff_metadata.update({
                "available": True,
                "bytes": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            })
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
        if response_target.hostname != repo_hostname or response_target.repository.lower() != repo_name.lower():
            raise GitHubCLIError("gh pr view response repository does not match the requested repository")

    issue_comments = raw.get("comments") if isinstance(raw.get("comments"), list) else []
    reviews = raw.get("reviews") if isinstance(raw.get("reviews"), list) else []
    review_comments: list[dict[str, Any]] = []
    discussion_metadata: dict[str, Any] = {"requested": include_discussion, "complete": False}
    if include_discussion:
        collected_issue_comments, issue_error = _api_list(
            cli,
            f"{endpoint_base}/issues/{pr_number}/comments?per_page=100",
            hostname=repo_hostname,
            cwd=cwd,
        )
        collected_reviews, reviews_error = _api_list(
            cli,
            f"{endpoint_base}/pulls/{pr_number}/reviews?per_page=100",
            hostname=repo_hostname,
            cwd=cwd,
        )
        collected_review_comments, review_comments_error = _api_list(
            cli,
            f"{endpoint_base}/pulls/{pr_number}/comments?per_page=100",
            hostname=repo_hostname,
            cwd=cwd,
        )
        if collected_issue_comments is not None:
            issue_comments = _compact_comments(collected_issue_comments)
        else:
            warnings.append(f"issue comments could not be fully collected: {issue_error}")
        if collected_reviews is not None:
            reviews = _compact_reviews(collected_reviews)
        else:
            warnings.append(f"reviews could not be fully collected: {reviews_error}")
        if collected_review_comments is not None:
            review_comments = _compact_comments(collected_review_comments, review_comment=True)
        else:
            warnings.append(f"inline review comments could not be collected: {review_comments_error}")
        discussion_metadata = {
            "requested": True,
            "complete": all(value is not None for value in (collected_issue_comments, collected_reviews, collected_review_comments)),
            "issue_comments": len(issue_comments),
            "reviews": len(reviews),
            "inline_review_comments": len(review_comments),
        }

    source = {
        "schema_version": "1.0",
        "source": "github-cli",
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repository": {
            "hostname": repo_hostname,
            "name_with_owner": repo_name,
            "gh_repo_argument": repo_arg,
        },
        "pull_request": {
            "number": pr_number,
            "url": raw.get("url"),
            "title": raw.get("title"),
            "body": raw.get("body"),
            "state": raw.get("state"),
            "is_draft": raw.get("isDraft"),
            "is_cross_repository": raw.get("isCrossRepository"),
            "author": raw.get("author"),
            "base_ref": raw.get("baseRefName"),
            "base_oid": raw.get("baseRefOid"),
            "head_ref": raw.get("headRefName"),
            "head_oid": raw.get("headRefOid"),
            "created_at": raw.get("createdAt"),
            "updated_at": raw.get("updatedAt"),
            "merged_at": raw.get("mergedAt"),
            "merged_by": raw.get("mergedBy"),
            "mergeable": raw.get("mergeable"),
            "merge_state_status": raw.get("mergeStateStatus"),
            "review_decision": raw.get("reviewDecision"),
            "additions": raw.get("additions"),
            "deletions": raw.get("deletions"),
            "changed_files": files,
            "commits": raw.get("commits") if isinstance(raw.get("commits"), list) else [],
            "labels": raw.get("labels") if isinstance(raw.get("labels"), list) else [],
            "reviews": reviews,
            "latest_reviews": raw.get("latestReviews") if isinstance(raw.get("latestReviews"), list) else [],
            "review_requests": raw.get("reviewRequests") if isinstance(raw.get("reviewRequests"), list) else [],
            "comments": issue_comments,
            "inline_review_comments": review_comments,
            "checks": raw.get("statusCheckRollup") if isinstance(raw.get("statusCheckRollup"), list) else [],
        },
        "diff": diff_metadata,
        "discussion": discussion_metadata,
        "warnings": warnings,
    }
    source["source_sha256"] = _canonical_sha256(source)
    return source, diff_text


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


def refresh_source_hash(source: dict[str, Any]) -> str:
    source.pop("source_sha256", None)
    digest = _canonical_sha256(source)
    source["source_sha256"] = digest
    return digest


def validate_pull_request_source(source: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if source.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if source.get("source") != "github-cli":
        errors.append("source must be 'github-cli'")
    repository = source.get("repository")
    if not isinstance(repository, dict):
        errors.append("repository must be an object")
    else:
        for field in ("hostname", "name_with_owner"):
            if not isinstance(repository.get(field), str) or not repository.get(field):
                errors.append(f"repository.{field} must be a non-empty string")
    pull_request = source.get("pull_request")
    if not isinstance(pull_request, dict):
        errors.append("pull_request must be an object")
    else:
        number = pull_request.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            errors.append("pull_request.number must be a positive integer")
        files = pull_request.get("changed_files")
        if not isinstance(files, list):
            errors.append("pull_request.changed_files must be an array")
        else:
            seen: set[str] = set()
            for index, item in enumerate(files):
                if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item.get("path"):
                    errors.append(f"pull_request.changed_files[{index}].path must be a non-empty string")
                    continue
                path = item["path"]
                if path in seen:
                    errors.append(f"duplicate changed file path: {path}")
                seen.add(path)
    digest = source.get("source_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append("source_sha256 must be a lowercase SHA-256 digest")
    else:
        candidate = dict(source)
        candidate.pop("source_sha256", None)
        if _canonical_sha256(candidate) != digest:
            errors.append("source_sha256 mismatch")
    return errors

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from .binding import RepositoryBinding


def canonical_sha256(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assemble_pull_request_source(
    *,
    raw: dict[str, Any],
    binding: RepositoryBinding,
    pr_number: int,
    changed_files: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    issue_comments: list[dict[str, Any]],
    inline_review_comments: list[dict[str, Any]],
    diff_metadata: dict[str, Any],
    discussion_metadata: dict[str, Any],
    warnings: list[str],
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    source = {
        "schema_version": "1.0",
        "source": "github-cli",
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repository": {
            "hostname": binding.hostname,
            "name_with_owner": binding.name_with_owner,
            "gh_repo_argument": binding.gh_repo_argument,
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
            "changed_files": changed_files,
            "commits": raw.get("commits") if isinstance(raw.get("commits"), list) else [],
            "labels": raw.get("labels") if isinstance(raw.get("labels"), list) else [],
            "reviews": reviews,
            "latest_reviews": raw.get("latestReviews") if isinstance(raw.get("latestReviews"), list) else [],
            "review_requests": raw.get("reviewRequests") if isinstance(raw.get("reviewRequests"), list) else [],
            "comments": issue_comments,
            "inline_review_comments": inline_review_comments,
            "checks": raw.get("statusCheckRollup") if isinstance(raw.get("statusCheckRollup"), list) else [],
        },
        "diff": diff_metadata,
        "discussion": discussion_metadata,
        "warnings": warnings,
    }
    source["source_sha256"] = canonical_sha256(source)
    return source


def refresh_source_hash(source: dict[str, Any]) -> str:
    source.pop("source_sha256", None)
    digest = canonical_sha256(source)
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
        if canonical_sha256(candidate) != digest:
            errors.append("source_sha256 mismatch")
    return errors

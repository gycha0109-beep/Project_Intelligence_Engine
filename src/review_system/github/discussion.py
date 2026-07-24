from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .pagination import collect_paginated_list
from .runner import GitHubCLI


@dataclass(frozen=True)
class DiscussionEvidence:
    issue_comments: tuple[dict[str, Any], ...]
    reviews: tuple[dict[str, Any], ...]
    inline_review_comments: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    warnings: tuple[str, ...]


def _compact_actor(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = {key: value.get(key) for key in ("login", "id", "type") if value.get(key) is not None}
    return result or None


def _compact_comments(items: list[dict[str, Any]], *, review_comment: bool = False) -> list[dict[str, Any]]:
    common = ("id", "body", "created_at", "updated_at", "html_url", "author_association")
    review_fields = (
        "path",
        "line",
        "side",
        "start_line",
        "start_side",
        "commit_id",
        "original_commit_id",
        "in_reply_to_id",
        "pull_request_review_id",
        "subject_type",
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


def collect_discussion(
    cli: GitHubCLI,
    *,
    endpoint_base: str,
    pr_number: int,
    hostname: str,
    cwd: str | Path,
    initial_issue_comments: list[dict[str, Any]],
    initial_reviews: list[dict[str, Any]],
    include_discussion: bool,
) -> DiscussionEvidence:
    issue_comments = initial_issue_comments
    reviews = initial_reviews
    inline_review_comments: list[dict[str, Any]] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {"requested": include_discussion, "complete": False}

    if include_discussion:
        collected_issue_comments, issue_error = collect_paginated_list(
            cli,
            f"{endpoint_base}/issues/{pr_number}/comments?per_page=100",
            hostname=hostname,
            cwd=cwd,
        )
        collected_reviews, reviews_error = collect_paginated_list(
            cli,
            f"{endpoint_base}/pulls/{pr_number}/reviews?per_page=100",
            hostname=hostname,
            cwd=cwd,
        )
        collected_review_comments, review_comments_error = collect_paginated_list(
            cli,
            f"{endpoint_base}/pulls/{pr_number}/comments?per_page=100",
            hostname=hostname,
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
            inline_review_comments = _compact_comments(collected_review_comments, review_comment=True)
        else:
            warnings.append(f"inline review comments could not be collected: {review_comments_error}")
        metadata = {
            "requested": True,
            "complete": all(
                value is not None
                for value in (collected_issue_comments, collected_reviews, collected_review_comments)
            ),
            "issue_comments": len(issue_comments),
            "reviews": len(reviews),
            "inline_review_comments": len(inline_review_comments),
        }

    return DiscussionEvidence(
        issue_comments=tuple(issue_comments),
        reviews=tuple(reviews),
        inline_review_comments=tuple(inline_review_comments),
        metadata=metadata,
        warnings=tuple(warnings),
    )

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runner import GitHubCLI, GitHubCLIError


def flatten_paginated_arrays(text: str, *, label: str) -> list[dict[str, Any]]:
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


def collect_paginated_list(
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
        return flatten_paginated_arrays(response.stdout, label=f"gh api {endpoint}"), None
    except GitHubCLIError as exc:
        return None, str(exc)

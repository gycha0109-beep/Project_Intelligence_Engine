from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


class GitHubCLIError(RuntimeError):
    """Raised when GitHub CLI execution or response validation fails."""


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class GitHubCLI:
    def __init__(self, executable: str | None = None, *, timeout_seconds: int = 120) -> None:
        resolved = executable or shutil.which("gh")
        self.executable = resolved
        self.timeout_seconds = timeout_seconds

    @property
    def installed(self) -> bool:
        return bool(self.executable)

    def run(
        self,
        arguments: Iterable[str],
        *,
        cwd: str | Path | None = None,
        check: bool = True,
        timeout_seconds: int | None = None,
    ) -> CommandResult:
        if not self.executable:
            raise GitHubCLIError("GitHub CLI 'gh' is not installed or not available on PATH")
        args = (self.executable, *tuple(str(value) for value in arguments))
        env = os.environ.copy()
        env.update({"GH_PAGER": "cat", "PAGER": "cat", "NO_COLOR": "1"})
        result: CommandResult | None = None
        for attempt in range(3):
            try:
                completed = subprocess.run(
                    args,
                    cwd=Path(cwd).resolve() if cwd else None,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds or self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise GitHubCLIError(f"GitHub CLI command timed out after {exc.timeout} seconds") from exc
            except OSError as exc:
                raise GitHubCLIError(f"failed to execute GitHub CLI: {exc}") from exc
            result = CommandResult(args=args, returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
            detail = f"{result.stderr}\n{result.stdout}".lower()
            retryable = result.returncode != 0 and any(marker in detail for marker in (
                "rate limit", "http 429", "http 502", "http 503", "http 504",
            ))
            if not retryable or attempt == 2:
                break
            time.sleep(2 ** attempt)
        assert result is not None
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown GitHub CLI failure"
            if "rate limit" in detail.lower() or "http 429" in detail.lower():
                raise GitHubCLIError(
                    f"GitHub API rate limit persisted after 3 attempts: {detail}; "
                    "check 'gh api rate_limit' and retry after the reported reset time"
                )
            raise GitHubCLIError(f"GitHub CLI command failed ({result.returncode}): {detail}")
        return result

    def version(self) -> str | None:
        if not self.installed:
            return None
        result = self.run(["--version"], check=False)
        return result.stdout.splitlines()[0].strip() if result.returncode == 0 and result.stdout.strip() else None

    def auth_status(self, hostname: str = "github.com") -> dict[str, Any]:
        if not self.installed:
            return {"hostname": hostname, "authenticated": False, "detail": "gh is not installed"}
        result = self.run(["auth", "status", "--active", "--hostname", hostname], check=False)
        detail = (result.stdout.strip() or result.stderr.strip()).replace("\r\n", "\n")
        return {
            "hostname": hostname,
            "authenticated": result.returncode == 0,
            "detail": detail,
        }

    def current_repository(self, cwd: str | Path) -> dict[str, str] | None:
        result = self.run(["repo", "view", "--json", "nameWithOwner,url"], cwd=cwd, check=False)
        if result.returncode != 0:
            return None
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        name = data.get("nameWithOwner")
        url = data.get("url")
        if not isinstance(name, str) or not name:
            return None
        host = urlparse(url).hostname if isinstance(url, str) else None
        return {"name_with_owner": name, "url": url or "", "hostname": host or "github.com"}

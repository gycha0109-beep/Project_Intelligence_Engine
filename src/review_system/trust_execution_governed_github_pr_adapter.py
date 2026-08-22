from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


PROVIDER = "GITHUB"
RESOURCE_TYPE = "PULL_REQUEST"
MARK_READY_OPERATION = "MARK_READY_FOR_REVIEW"
ROLLBACK_OPERATION = "CONVERT_TO_DRAFT"
_ALLOWED_OPERATIONS = (MARK_READY_OPERATION, ROLLBACK_OPERATION)


class GovernedAdapterError(RuntimeError):
    """Base error for fail-closed governed pull-request adapter failures."""


class GovernedAdapterPreconditionError(GovernedAdapterError):
    """Raised before dispatch when the exact target precondition is not met."""


class GovernedAdapterPostconditionError(GovernedAdapterError):
    """Raised after dispatch when provider readback does not prove the effect."""


@dataclass(frozen=True)
class PullRequestSnapshot:
    repository: str
    pr_number: int
    state: str
    draft: bool
    merged: bool
    head_sha: str


class GitHubPullRequestTransport(Protocol):
    """Narrow provider transport required by the governed adapter.

    Implementations may only expose the three provider operations the adapter needs.
    Arbitrary command, arbitrary URL/API, merge, close, file, branch, workflow,
    secret, or repository-settings mutation is outside this protocol.
    """

    def read_pull_request(self, repository: str, pr_number: int) -> PullRequestSnapshot: ...

    def mark_ready_for_review(self, repository: str, pr_number: int) -> None: ...

    def convert_to_draft(self, repository: str, pr_number: int) -> None: ...


class GovernedGitHubPullRequestAdapter:
    """Exact-target adapter for controlled non-production PR state calibration.

    The repository, pull-request number, and expected head are constructor-bound.
    Public methods do not accept alternate repository/PR targets. Every mutation is
    guarded by exact provider readback before dispatch and verified by a second
    provider readback after dispatch.
    """

    def __init__(
        self,
        *,
        repository: str,
        pr_number: int,
        expected_head_sha: str,
        transport: GitHubPullRequestTransport,
    ) -> None:
        if not repository or "/" not in repository:
            raise ValueError("repository must be an exact owner/name identifier")
        if not isinstance(pr_number, int) or pr_number <= 0:
            raise ValueError("pr_number must be a positive integer")
        if len(expected_head_sha) != 40 or any(
            char not in "0123456789abcdef" for char in expected_head_sha
        ):
            raise ValueError("expected_head_sha must be a lowercase 40-hex SHA")

        self._repository = repository
        self._pr_number = pr_number
        self._expected_head_sha = expected_head_sha
        self._transport = transport

    @property
    def repository(self) -> str:
        return self._repository

    @property
    def pr_number(self) -> int:
        return self._pr_number

    @property
    def expected_head_sha(self) -> str:
        return self._expected_head_sha

    def descriptor(self) -> dict[str, object]:
        return {
            "provider": PROVIDER,
            "repository": self._repository,
            "resource_type": RESOURCE_TYPE,
            "pr_number": self._pr_number,
            "expected_head_sha": self._expected_head_sha,
            "exact_pr_binding": True,
            "exact_head_binding": True,
            "exact_precondition_binding": True,
            "allowed_operations": list(_ALLOWED_OPERATIONS),
            "arbitrary_command_surface": False,
            "arbitrary_api_surface": False,
            "merge_surface": False,
            "close_surface": False,
            "file_write_surface": False,
            "branch_write_surface": False,
            "workflow_write_surface": False,
            "secret_write_surface": False,
            "repository_settings_surface": False,
        }

    def read_target(self) -> PullRequestSnapshot:
        snapshot = self._transport.read_pull_request(self._repository, self._pr_number)
        self._verify_identity(snapshot)
        return snapshot

    def mark_ready(self) -> dict[str, object]:
        before = self._require_precondition(expected_draft=True)
        self._transport.mark_ready_for_review(self._repository, self._pr_number)
        after = self.read_target()
        self._verify_postcondition(after, expected_draft=False)
        return self._receipt(MARK_READY_OPERATION, before, after)

    def rollback_to_draft(self) -> dict[str, object]:
        before = self._require_precondition(expected_draft=False)
        self._transport.convert_to_draft(self._repository, self._pr_number)
        after = self.read_target()
        self._verify_postcondition(after, expected_draft=True)
        return self._receipt(ROLLBACK_OPERATION, before, after)

    def verify_state(self, *, expected_draft: bool) -> PullRequestSnapshot:
        snapshot = self.read_target()
        self._verify_postcondition(snapshot, expected_draft=expected_draft)
        return snapshot

    def _verify_identity(self, snapshot: PullRequestSnapshot) -> None:
        if snapshot.repository != self._repository:
            raise GovernedAdapterPostconditionError("provider repository identity drift")
        if snapshot.pr_number != self._pr_number:
            raise GovernedAdapterPostconditionError("provider pull-request identity drift")
        if snapshot.head_sha != self._expected_head_sha:
            raise GovernedAdapterPostconditionError("provider pull-request head drift")

    def _require_precondition(self, *, expected_draft: bool) -> PullRequestSnapshot:
        snapshot = self.read_target()
        if snapshot.state != "open":
            raise GovernedAdapterPreconditionError("target pull request is not open")
        if snapshot.merged:
            raise GovernedAdapterPreconditionError("target pull request is merged")
        if snapshot.draft is not expected_draft:
            raise GovernedAdapterPreconditionError("target draft precondition mismatch")
        return snapshot

    def _verify_postcondition(
        self, snapshot: PullRequestSnapshot, *, expected_draft: bool
    ) -> None:
        if snapshot.state != "open":
            raise GovernedAdapterPostconditionError("target pull request is not open")
        if snapshot.merged:
            raise GovernedAdapterPostconditionError("target pull request is merged")
        if snapshot.draft is not expected_draft:
            raise GovernedAdapterPostconditionError("target draft postcondition mismatch")

    @staticmethod
    def _receipt(
        operation: str,
        before: PullRequestSnapshot,
        after: PullRequestSnapshot,
    ) -> dict[str, object]:
        return {
            "provider": PROVIDER,
            "resource_type": RESOURCE_TYPE,
            "operation": operation,
            "before": asdict(before),
            "after": asdict(after),
            "postcondition_verified": True,
        }

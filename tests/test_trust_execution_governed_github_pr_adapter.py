from __future__ import annotations

import unittest

from review_system.trust_execution_governed_github_pr_adapter import (
    GovernedAdapterPostconditionError,
    GovernedAdapterPreconditionError,
    GovernedGitHubPullRequestAdapter,
    PullRequestSnapshot,
)


REPOSITORY = "gycha0109-beep/pie-peb3-calibration"
PR_NUMBER = 1
HEAD = "0123456789abcdef0123456789abcdef01234567"


class FakeTransport:
    def __init__(self, *, draft: bool = True) -> None:
        self.snapshot = PullRequestSnapshot(
            repository=REPOSITORY,
            pr_number=PR_NUMBER,
            state="open",
            draft=draft,
            merged=False,
            head_sha=HEAD,
        )
        self.calls: list[tuple[str, str, int]] = []

    def read_pull_request(self, repository: str, pr_number: int) -> PullRequestSnapshot:
        self.calls.append(("read", repository, pr_number))
        return self.snapshot

    def mark_ready_for_review(self, repository: str, pr_number: int) -> None:
        self.calls.append(("mark_ready", repository, pr_number))
        self.snapshot = PullRequestSnapshot(
            repository=self.snapshot.repository,
            pr_number=self.snapshot.pr_number,
            state=self.snapshot.state,
            draft=False,
            merged=self.snapshot.merged,
            head_sha=self.snapshot.head_sha,
        )

    def convert_to_draft(self, repository: str, pr_number: int) -> None:
        self.calls.append(("convert_to_draft", repository, pr_number))
        self.snapshot = PullRequestSnapshot(
            repository=self.snapshot.repository,
            pr_number=self.snapshot.pr_number,
            state=self.snapshot.state,
            draft=True,
            merged=self.snapshot.merged,
            head_sha=self.snapshot.head_sha,
        )


class NoEffectTransport(FakeTransport):
    def mark_ready_for_review(self, repository: str, pr_number: int) -> None:
        self.calls.append(("mark_ready", repository, pr_number))


class HeadDriftTransport(FakeTransport):
    def read_pull_request(self, repository: str, pr_number: int) -> PullRequestSnapshot:
        self.calls.append(("read", repository, pr_number))
        return PullRequestSnapshot(
            repository=REPOSITORY,
            pr_number=PR_NUMBER,
            state="open",
            draft=self.snapshot.draft,
            merged=False,
            head_sha="f" * 40,
        )


def make_adapter(transport: FakeTransport) -> GovernedGitHubPullRequestAdapter:
    return GovernedGitHubPullRequestAdapter(
        repository=REPOSITORY,
        pr_number=PR_NUMBER,
        expected_head_sha=HEAD,
        transport=transport,
    )


class GovernedGitHubPullRequestAdapterTests(unittest.TestCase):
    def test_descriptor_freezes_exact_target_and_forbidden_surfaces(self) -> None:
        adapter = make_adapter(FakeTransport())
        descriptor = adapter.descriptor()

        self.assertEqual(descriptor["repository"], REPOSITORY)
        self.assertEqual(descriptor["pr_number"], PR_NUMBER)
        self.assertEqual(descriptor["expected_head_sha"], HEAD)
        self.assertTrue(descriptor["exact_pr_binding"])
        self.assertTrue(descriptor["exact_head_binding"])
        self.assertTrue(descriptor["exact_precondition_binding"])
        self.assertEqual(
            set(descriptor["allowed_operations"]),
            {"MARK_READY_FOR_REVIEW", "CONVERT_TO_DRAFT"},
        )
        for field in (
            "arbitrary_command_surface",
            "arbitrary_api_surface",
            "merge_surface",
            "close_surface",
            "file_write_surface",
            "branch_write_surface",
            "workflow_write_surface",
            "secret_write_surface",
            "repository_settings_surface",
        ):
            self.assertIs(descriptor[field], False)

    def test_public_adapter_has_no_forbidden_mutation_methods(self) -> None:
        adapter = make_adapter(FakeTransport())
        for name in (
            "run",
            "shell",
            "request",
            "merge_pr",
            "close_pr",
            "write_file",
            "update_branch",
            "mutate_workflow",
            "mutate_secret",
            "mutate_repository_settings",
        ):
            self.assertFalse(hasattr(adapter, name), name)

    def test_mark_ready_binds_all_provider_calls_to_exact_target(self) -> None:
        transport = FakeTransport(draft=True)
        adapter = make_adapter(transport)

        receipt = adapter.mark_ready()

        self.assertTrue(receipt["postcondition_verified"])
        self.assertEqual(receipt["operation"], "MARK_READY_FOR_REVIEW")
        self.assertFalse(receipt["after"]["draft"])
        self.assertEqual(
            transport.calls,
            [
                ("read", REPOSITORY, PR_NUMBER),
                ("mark_ready", REPOSITORY, PR_NUMBER),
                ("read", REPOSITORY, PR_NUMBER),
            ],
        )

    def test_rollback_binds_all_provider_calls_to_exact_target(self) -> None:
        transport = FakeTransport(draft=False)
        adapter = make_adapter(transport)

        receipt = adapter.rollback_to_draft()

        self.assertTrue(receipt["postcondition_verified"])
        self.assertEqual(receipt["operation"], "CONVERT_TO_DRAFT")
        self.assertTrue(receipt["after"]["draft"])
        self.assertEqual(
            transport.calls,
            [
                ("read", REPOSITORY, PR_NUMBER),
                ("convert_to_draft", REPOSITORY, PR_NUMBER),
                ("read", REPOSITORY, PR_NUMBER),
            ],
        )

    def test_wrong_initial_draft_state_fails_before_dispatch(self) -> None:
        transport = FakeTransport(draft=False)
        adapter = make_adapter(transport)

        with self.assertRaises(GovernedAdapterPreconditionError):
            adapter.mark_ready()

        self.assertEqual(transport.calls, [("read", REPOSITORY, PR_NUMBER)])

    def test_head_drift_fails_before_dispatch(self) -> None:
        transport = HeadDriftTransport(draft=True)
        adapter = make_adapter(transport)

        with self.assertRaises(GovernedAdapterPostconditionError):
            adapter.mark_ready()

        self.assertEqual(transport.calls, [("read", REPOSITORY, PR_NUMBER)])

    def test_missing_effect_fails_postcondition_verification(self) -> None:
        transport = NoEffectTransport(draft=True)
        adapter = make_adapter(transport)

        with self.assertRaises(GovernedAdapterPostconditionError):
            adapter.mark_ready()

        self.assertEqual(
            transport.calls,
            [
                ("read", REPOSITORY, PR_NUMBER),
                ("mark_ready", REPOSITORY, PR_NUMBER),
                ("read", REPOSITORY, PR_NUMBER),
            ],
        )

    def test_constructor_rejects_unbound_target_inputs(self) -> None:
        transport = FakeTransport()
        with self.assertRaises(ValueError):
            GovernedGitHubPullRequestAdapter(
                repository="not-a-full-name",
                pr_number=PR_NUMBER,
                expected_head_sha=HEAD,
                transport=transport,
            )
        with self.assertRaises(ValueError):
            GovernedGitHubPullRequestAdapter(
                repository=REPOSITORY,
                pr_number=0,
                expected_head_sha=HEAD,
                transport=transport,
            )
        with self.assertRaises(ValueError):
            GovernedGitHubPullRequestAdapter(
                repository=REPOSITORY,
                pr_number=PR_NUMBER,
                expected_head_sha="ABC",
                transport=transport,
            )


if __name__ == "__main__":
    unittest.main()

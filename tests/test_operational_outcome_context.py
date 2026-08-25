from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

from review_system.operational_outcome_context import (
    OperationalOutcomeContextError,
    OperationalOutcomeSource,
    build_github_outcome_observation,
    build_operational_outcome_context,
    verify_operational_outcome_context_data,
)
from review_system.trust_prospective_evidence_cli import build_parser


HEAD = "b" * 40
BASE = "a" * 40
HASH = lambda value: value * 64
ASSESSMENT = "assessment-" + "c" * 32
EVENT = "event-" + "d" * 32
PACKET = "prospective-review-packet-" + "e" * 32


def _source(decision: str = "APPROVE") -> OperationalOutcomeSource:
    action = {
        "action_sha256": HASH("1"),
        "source": {
            "project_id": "demo-project",
            "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
            "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
            "review_brief_sha256": HASH("2"),
            "review_packet_id": PACKET,
            "review_packet_sha256": HASH("3"),
            "operational_binding_sha256": HASH("4"),
        },
        "review": {
            "review_level": "REVIEWED",
            "decision": decision,
            "confirmed_risk_band": None,
            "actor": "reviewer",
            "reason": "explicit review",
        },
    }
    assessment = {
        "assessment_id": ASSESSMENT,
        "source_revision": "git:" + HEAD,
        "trust_report_id": "trust-report-demo",
        "trust_report_sha256": HASH("5"),
    }
    event = {
        "event_id": EVENT,
        "event_sha256": HASH("6"),
        "occurred_at": "2026-08-25T00:00:00Z",
    }
    registry = {"registry_sha256": HASH("7")}
    return OperationalOutcomeSource(
        artifact_root=Path("/tmp/orl4"),
        action=action,
        bridge_root=Path("/tmp/orl4/bridge"),
        workspace_root=Path("/tmp/orl4/bridge/workspace"),
        registry=registry,
        assessment=assessment,
        review_event=event,
        review_source=SimpleNamespace(),
    )


def _live(checks=None, *, head: str = HEAD, base: str = BASE, state: str = "MERGED"):
    return {
        "repository": {"name_with_owner": "demo/repo"},
        "pull_request": {
            "number": 7,
            "head_oid": head,
            "base_oid": base,
            "state": state,
            "merged_at": "2026-08-25T00:20:00Z" if state == "MERGED" else None,
            "merged_by": {"login": "merger"} if state == "MERGED" else None,
            "mergeable": "UNKNOWN",
            "merge_state_status": "UNKNOWN",
            "review_decision": "APPROVED",
            "checks": checks or [],
        },
    }


def _api(*, head: str = HEAD, base: str = BASE, merged: bool = True):
    return {
        "number": 7,
        "head": {"sha": head},
        "base": {"sha": base},
        "merged": merged,
        "merge_commit_sha": "f" * 40 if merged else None,
    }


class OperationalOutcomeContextTests(unittest.TestCase):
    def test_merged_green_ci_remains_observation_only(self):
        live = _live(
            [
                {
                    "__typename": "CheckRun",
                    "name": "test (3.11)",
                    "workflowName": "CI",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                },
                {
                    "__typename": "CheckRun",
                    "name": "test (3.14)",
                    "workflowName": "CI",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                },
            ]
        )
        observation = build_github_outcome_observation(
            live_source=live,
            pr_api=_api(),
            expected_repository="demo/repo",
            expected_pull_request=7,
            expected_base_oid=BASE,
            expected_head_oid=HEAD,
        )
        context = build_operational_outcome_context(source=_source(), observations=observation)

        self.assertTrue(context["observations"]["pull_request"]["merged"])
        self.assertEqual(
            ["SUCCESS", "SUCCESS"],
            [item["conclusion"] for item in context["observations"]["checks"]],
        )
        self.assertTrue(context["authority"]["human_review_recorded"])
        self.assertFalse(context["authority"]["human_outcome_declared"])
        self.assertFalse(context["authority"]["automatic_outcome_inference"])
        self.assertFalse(context["authority"]["outcome_recorded"])
        self.assertFalse(context["authority"]["merge_observation_is_outcome_authority"])
        self.assertFalse(context["authority"]["ci_observation_is_outcome_authority"])
        self.assertIsNone(context["auto3_declaration_context"]["selected_authority_type"])
        self.assertIsNone(context["auto3_declaration_context"]["selected_verdict"])
        self.assertFalse(context["auto3_declaration_context"]["declaration_materialized"])
        self.assertEqual([], verify_operational_outcome_context_data(context))

    def test_same_semantic_observation_is_deterministic_across_check_order(self):
        check_a = {
            "__typename": "CheckRun",
            "name": "a",
            "workflowName": "CI",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        }
        check_b = {
            "__typename": "CheckRun",
            "name": "b",
            "workflowName": "CI",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        }
        first = build_github_outcome_observation(
            live_source=_live([check_b, check_a]),
            pr_api=_api(),
            expected_repository="demo/repo",
            expected_pull_request=7,
            expected_base_oid=BASE,
            expected_head_oid=HEAD,
        )
        second = build_github_outcome_observation(
            live_source=_live([check_a, check_b]),
            pr_api=_api(),
            expected_repository="demo/repo",
            expected_pull_request=7,
            expected_base_oid=BASE,
            expected_head_oid=HEAD,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            build_operational_outcome_context(source=_source(), observations=first),
            build_operational_outcome_context(source=_source(), observations=second),
        )

    def test_stale_head_or_base_fails_closed(self):
        with self.assertRaises(OperationalOutcomeContextError) as raised:
            build_github_outcome_observation(
                live_source=_live(head="9" * 40),
                pr_api=_api(head="9" * 40),
                expected_repository="demo/repo",
                expected_pull_request=7,
                expected_base_oid=BASE,
                expected_head_oid=HEAD,
            )
        self.assertEqual("STALE_SOURCE_REVISION", raised.exception.code)

    def test_tampered_verdict_or_authority_selection_is_rejected(self):
        observation = build_github_outcome_observation(
            live_source=_live(),
            pr_api=_api(),
            expected_repository="demo/repo",
            expected_pull_request=7,
            expected_base_oid=BASE,
            expected_head_oid=HEAD,
        )
        context = build_operational_outcome_context(source=_source(), observations=observation)
        tampered = deepcopy(context)
        tampered["auto3_declaration_context"]["selected_verdict"] = "SAFE"
        errors = verify_operational_outcome_context_data(tampered)
        self.assertTrue(any("selected_verdict" in item or "must not select" in item for item in errors))
        self.assertIn("context_sha256 mismatch", errors)

    def test_auto3_authority_requirements_are_contract_only(self):
        observation = build_github_outcome_observation(
            live_source=_live(state="OPEN"),
            pr_api=_api(merged=False),
            expected_repository="demo/repo",
            expected_pull_request=7,
            expected_base_oid=BASE,
            expected_head_oid=HEAD,
        )
        context = build_operational_outcome_context(
            source=_source(decision="REQUEST_CHANGES"),
            observations=observation,
        )
        auto3 = context["auto3_declaration_context"]
        self.assertEqual(
            ["CONTROLLED_EVALUATION", "INDEPENDENT_AUDIT", "PRODUCTION_DEFECT"],
            auto3["allowed_authority_types"],
        )
        self.assertTrue(auto3["production_defect_safe_forbidden"])
        self.assertEqual(
            ["actor", "authority_type", "verdict", "authority_source"],
            auto3["unresolved_human_inputs"],
        )
        self.assertEqual("REQUEST_CHANGES", auto3["review"]["decision"])

    def test_cli_has_no_outcome_selection_inputs(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "prepare-operational-outcome-context",
                "--target-repository",
                "demo/repo",
                "--pull-request",
                "7",
                "--artifact-cache-root",
                ".pie/orl5-cache",
                "--output",
                ".pie/context.json",
            ]
        )
        self.assertEqual("prepare-operational-outcome-context", args.command)
        self.assertFalse(hasattr(args, "outcome_type"))
        self.assertFalse(hasattr(args, "verdict"))
        self.assertFalse(hasattr(args, "actor"))


if __name__ == "__main__":
    unittest.main()

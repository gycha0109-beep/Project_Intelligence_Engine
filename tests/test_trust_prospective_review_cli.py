from __future__ import annotations

import unittest

from review_system import trust_prospective_evidence
from review_system.trust_prospective_evidence_cli import build_parser


class GovernedProspectiveReviewCliTests(unittest.TestCase):
    def test_legacy_public_prospective_module_no_longer_exports_unbound_review_mutation(self):
        self.assertFalse(hasattr(trust_prospective_evidence, "record_case_review"))

    def test_record_prospective_review_requires_exact_packet_input(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "record-prospective-review",
                "--workspace", "campaign",
                "--github-candidate", "candidate.json",
                "--repository-root", ".",
                "--review-level", "REVIEWED",
                "--decision", "APPROVE",
                "--actor", "reviewer-a",
            ])

    def test_workflow_accepted_cannot_be_promoted_through_review_submit_cli(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "submit-prospective-review",
                "--workspace", "campaign",
                "--github-candidate", "candidate.json",
                "--repository-root", ".",
                "--packet", "review-packet.json",
                "--review-level", "WORKFLOW_ACCEPTED",
                "--decision", "APPROVE",
                "--actor", "reviewer-a",
            ])

    def test_prepare_verify_submit_commands_are_registered(self):
        parser = build_parser()
        for name in (
            "prepare-prospective-review",
            "verify-prospective-review",
            "submit-prospective-review",
            "record-prospective-review",
        ):
            self.assertIn(name, parser._subparsers._group_actions[0].choices)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.operational_outcome_action import (
    CONTRACT_VERSION,
    OperationalOutcomeActionError,
    OperationalOutcomeActionRequest,
    OperationalOutcomeContextSource,
    _authority_sources,
    _normalize_inputs,
    build_operational_outcome_action,
    reject_prior_operational_outcome_action,
    select_operational_outcome_context,
    verify_operational_outcome_action_data,
)
from review_system.trust_outcome_declaration import build_outcome_declaration
from review_system.trust_prospective_evidence_cli import build_parser


HEAD = "b" * 40
BASE = "a" * 40
ASSESSMENT = "assessment-" + "c" * 32
REVIEW_EVENT = "event-" + "d" * 32
OUTCOME_EVENT = "event-" + "e" * 32
PACKET = "prospective-review-packet-" + "f" * 32
HASH1 = "1" * 64
HASH2 = "2" * 64
HASH3 = "3" * 64
HASH4 = "4" * 64
HASH5 = "5" * 64
HASH6 = "6" * 64
HASH7 = "7" * 64


def _context(*, review_action_sha256: str = HASH4) -> dict:
    return {
        "context_sha256": HASH1,
        "source": {
            "authority_repository": "gycha0109-beep/Project_Intelligence_Engine",
            "project_id": "demo-project",
            "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
            "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
            "assessment": {
                "assessment_id": ASSESSMENT,
                "source_revision": "git:" + HEAD,
                "trust_report_id": "trust-report-demo",
                "trust_report_sha256": HASH2,
            },
            "review_action_sha256": review_action_sha256,
            "review_brief_sha256": HASH3,
            "review_packet_id": PACKET,
            "review_packet_sha256": HASH5,
            "operational_binding_sha256": None,
            "registry_sha256": HASH6,
        },
        "review": {
            "event_id": REVIEW_EVENT,
            "event_sha256": HASH7,
            "occurred_at": "2026-08-25T00:00:00Z",
            "review_level": "REVIEWED",
            "decision": "APPROVE",
            "confirmed_risk_band": None,
            "actor": "reviewer",
            "reason": "explicit review",
        },
        "auto3_declaration_context": {
            "project_id": "demo-project",
            "assessment": {
                "assessment_id": ASSESSMENT,
                "source_revision": "git:" + HEAD,
                "trust_report_id": "trust-report-demo",
                "trust_report_sha256": HASH2,
            },
            "review": {
                "event_id": REVIEW_EVENT,
                "event_sha256": HASH7,
                "review_level": "REVIEWED",
                "decision": "APPROVE",
                "review_packet_id": PACKET,
                "review_packet_sha256": HASH5,
            },
        },
    }


def _declaration() -> dict:
    return build_outcome_declaration(
        actor="operator",
        project_id="demo-project",
        assessment_id=ASSESSMENT,
        source_revision=HEAD,
        trust_report_id="trust-report-demo",
        trust_report_sha256=HASH2,
        review_event_id=REVIEW_EVENT,
        review_event_sha256=HASH7,
        review_level="REVIEWED",
        decision="APPROVE",
        review_packet_id=PACKET,
        review_packet_sha256=HASH5,
        authority_type="CONTROLLED_EVALUATION",
        verdict="SAFE",
        declared_at="2026-08-25T00:10:00Z",
        evidence_refs=["evaluation-demo", HASH3],
        evaluation_id="evaluation-demo",
        evaluation_report_sha256=HASH3,
    )


def _transport(*, idempotent: bool = False) -> dict:
    declaration = _declaration()
    return {
        "declaration_id": declaration["declaration_id"],
        "declaration_sha256": declaration["declaration_sha256"],
        "project_id": "demo-project",
        "assessment_id": ASSESSMENT,
        "source_revision": "git:" + HEAD,
        "review_event_id": REVIEW_EVENT,
        "outcome_type": "CONTROLLED_EVALUATION",
        "verdict": "SAFE",
        "event_id": OUTCOME_EVENT,
        "registry_sha256": HASH6,
        "idempotent": idempotent,
        "reconciliation_status": "RECONCILED",
        "authority_key": "evaluation:" + HASH3 + ":case-demo",
        "human_outcome_declared": True,
        "automatic_outcome_inference": False,
        "outcome_recorded": True,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
        "transport_sha256": HASH1,
    }


def _receipt() -> dict:
    return build_operational_outcome_action(
        context=_context(),
        declaration=_declaration(),
        transport=_transport(),
        authority_files=[{"role": "evaluation_report", "file_sha256": HASH4}],
    )


def _context_source(review_action_sha256: str, root: str) -> OperationalOutcomeContextSource:
    return OperationalOutcomeContextSource(
        artifact_root=Path(root),
        context_path=Path(root) / "context.json",
        context=_context(review_action_sha256=review_action_sha256),
        review_action_root=Path(root) / "review-action-source",
    )


class OperationalOutcomeActionTests(unittest.TestCase):
    def test_receipt_projects_existing_auto3_authority_without_execution_authority(self):
        receipt = _receipt()
        self.assertEqual(CONTRACT_VERSION, receipt["contract_version"])
        self.assertEqual("EXPLICIT_OUTCOME_RECORDED", receipt["status"])
        self.assertEqual("CONTROLLED_EVALUATION", receipt["action"]["authority_type"])
        self.assertEqual("SAFE", receipt["action"]["verdict"])
        self.assertTrue(receipt["authority"]["human_review_recorded"])
        self.assertTrue(receipt["authority"]["human_outcome_declared"])
        self.assertTrue(receipt["authority"]["outcome_recorded"])
        for field in (
            "automatic_outcome_inference",
            "automation_authorized",
            "pilot_authorized",
            "merge_authorized",
            "deploy_authorized",
            "production_effect_authorized",
        ):
            self.assertFalse(receipt["authority"][field])
        self.assertEqual([], verify_operational_outcome_action_data(receipt))

    def test_production_defect_safe_is_rejected_before_auto3(self):
        with self.assertRaises(OperationalOutcomeActionError) as caught:
            _normalize_inputs(
                actor="operator",
                authority_type="PRODUCTION_DEFECT",
                verdict="SAFE",
                defect_id="defect-demo",
                evidence_refs=[],
            )
        self.assertEqual("INVALID_VERDICT", caught.exception.code)

    def test_authority_source_roles_fail_closed(self):
        request = OperationalOutcomeActionRequest(
            target_repository="demo/repo",
            pull_request=7,
            actor="operator",
            authority_type="CONTROLLED_EVALUATION",
            verdict="SAFE",
            repository_root=".",
            artifact_cache_root="cache",
            output_root="output",
            ledger="unexpected-ledger",
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(OperationalOutcomeActionError) as caught:
                _authority_sources(
                    request,
                    authority_type="CONTROLLED_EVALUATION",
                    actor="operator",
                    verdict="SAFE",
                    defect_id=None,
                    evidence_refs=[],
                    destination=Path(temporary) / "sources",
                )
        self.assertEqual("AUTHORITY_SOURCE_MISMATCH", caught.exception.code)

    def test_controlled_evaluation_source_identity_is_derived_from_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "evaluation.json"
            source.write_text("{}\n", encoding="utf-8")
            request = OperationalOutcomeActionRequest(
                target_repository="demo/repo",
                pull_request=7,
                actor="operator",
                authority_type="CONTROLLED_EVALUATION",
                verdict="SAFE",
                repository_root=".",
                artifact_cache_root="cache",
                output_root="output",
                evaluation_report=source,
            )
            with patch(
                "review_system.operational_outcome_action.load_evaluation_report",
                return_value=(source, {"evaluation_id": "evaluation-demo", "report_sha256": HASH3}),
            ):
                binding, files, transport_sources, refs = _authority_sources(
                    request,
                    authority_type="CONTROLLED_EVALUATION",
                    actor="operator",
                    verdict="SAFE",
                    defect_id=None,
                    evidence_refs=["operator-note"],
                    destination=Path(temporary) / "preserved",
                )
        self.assertEqual("evaluation-demo", binding["evaluation_id"])
        self.assertEqual(HASH3, binding["evaluation_report_sha256"])
        self.assertIsNone(binding["audit_id"])
        self.assertEqual(["evaluation_report"], [item["role"] for item in files])
        self.assertIn("evaluation_report", transport_sources)
        self.assertEqual(
            [HASH3, "evaluation-demo", "operator-note"],
            sorted(refs),
        )

    def test_idempotent_transport_cannot_be_promoted_to_orl6_action(self):
        with self.assertRaises(Exception):
            build_operational_outcome_action(
                context=_context(),
                declaration=_declaration(),
                transport=_transport(idempotent=True),
                authority_files=[{"role": "evaluation_report", "file_sha256": HASH4}],
            )

    def test_observation_only_context_refreshes_do_not_create_authority_ambiguity(self):
        newest = _context_source(HASH4, "/tmp/new")
        older = _context_source(HASH4, "/tmp/old")
        with patch(
            "review_system.operational_outcome_action.inspect_operational_outcome_context_artifact",
            side_effect=[newest, older],
        ):
            selected = select_operational_outcome_context(
                ["/tmp/new", "/tmp/old"],
                target_repository="demo/repo",
                pull_request=7,
                repository_root="/tmp",
                github_cli=object(),
            )
        self.assertEqual(Path("/tmp/new"), selected.artifact_root)

    def test_distinct_review_actions_make_context_ambiguous(self):
        first = _context_source(HASH4, "/tmp/a")
        second = _context_source(HASH5, "/tmp/b")
        with patch(
            "review_system.operational_outcome_action.inspect_operational_outcome_context_artifact",
            side_effect=[first, second],
        ):
            with self.assertRaises(OperationalOutcomeActionError) as caught:
                select_operational_outcome_context(
                    ["/tmp/a", "/tmp/b"],
                    target_repository="demo/repo",
                    pull_request=7,
                    repository_root="/tmp",
                    github_cli=object(),
                )
        self.assertEqual("AMBIGUOUS_OUTCOME_CONTEXT", caught.exception.code)

    def test_prior_current_outcome_action_blocks_second_declaration(self):
        receipt = _receipt()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "prior"
            root.mkdir()
            (root / "action.json").write_text(
                json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(OperationalOutcomeActionError) as caught:
                reject_prior_operational_outcome_action(
                    [root],
                    repository="demo/repo",
                    pull_request=7,
                    head_oid=HEAD,
                    assessment_id=ASSESSMENT,
                    review_action_sha256=HASH4,
                )
        self.assertEqual("OUTCOME_ALREADY_RECORDED", caught.exception.code)

    def test_receipt_tampering_is_detected(self):
        receipt = _receipt()
        forged = deepcopy(receipt)
        forged["authority"]["merge_authorized"] = True
        errors = verify_operational_outcome_action_data(forged)
        self.assertTrue(any("merge_authorized" in error for error in errors))
        self.assertIn("action_sha256 mismatch", errors)

    def test_cli_requires_explicit_outcome_semantics_but_not_hash_copying(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "submit-operational-outcome",
                "--target-repository",
                "demo/repo",
                "--pull-request",
                "7",
                "--artifact-cache-root",
                ".pie/orl6-cache",
                "--output-root",
                ".pie/orl6-output",
                "--actor",
                "operator",
                "--authority-type",
                "CONTROLLED_EVALUATION",
                "--verdict",
                "SAFE",
                "--evaluation-report",
                "evaluation.json",
            ]
        )
        self.assertEqual("submit-operational-outcome", args.command)
        self.assertEqual("CONTROLLED_EVALUATION", args.authority_type)
        self.assertFalse(hasattr(args, "assessment_id"))
        self.assertFalse(hasattr(args, "trust_report_sha256"))
        self.assertFalse(hasattr(args, "review_packet_sha256"))
        self.assertFalse(hasattr(args, "evaluation_report_sha256"))


if __name__ == "__main__":
    unittest.main()

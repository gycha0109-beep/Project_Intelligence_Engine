from __future__ import annotations

from copy import deepcopy
import unittest

from review_system.operational_review_brief import (
    OperationalReviewBriefError,
    build_operational_review_brief,
    render_operational_review_brief_markdown,
    verify_operational_review_brief_data,
    verify_operational_review_brief_sources,
)


HEAD = "a" * 40
BASE = "b" * 40
PIE = "c" * 40
CANDIDATE_SHA = "d" * 64


def _candidate() -> dict:
    return {
        "project_id": "demo",
        "candidate_id": "github-capture-demo",
        "task_id": "github-pr:demo",
        "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
        "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
        "changed_files": ["src/runtime/worker.py", "src/api.py"],
    }


def _impact() -> dict:
    return {
        "direct": {"components": ["runtime", "api"]},
        "impact": {
            "dependent_files": [
                {"path": "tests/test_runtime.py"},
                {"path": "src/caller.py"},
            ]
        },
        "review": {
            "selected_packs": ["universal.test-completeness", "domain.runtime"],
            "required_tests": ["python -m unittest", "tests/test_runtime.py"],
        },
        "limitations": [
            "A reported relation is a review signal, not proof that behavior changed.",
            "Runtime reflection may be absent.",
        ],
    }


def _binding() -> dict:
    return {
        "project_id": "demo",
        "candidate_id": "github-capture-demo",
        "source_revision": "git:" + HEAD,
        "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
        "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
        "changed_files": ["src/api.py", "src/runtime/worker.py"],
        "status": "MISSING_TRUST_FIELDS",
        "match_status": "UNIQUE_POLICY_MATCH",
        "selected_operational_class": "runtime",
        "requirements": {
            "trust_task_class": "routine_code",
            "required_scenarios": ["process-restart"],
            "required_evidence": ["ci"],
        },
        "missing_inputs": ["rollback_evidence", "required_evidence:ci"],
        "policy": {
            "policy_revision": "git:" + BASE,
            "policy_blob_sha": "e" * 40,
            "policy_content_sha256": "f" * 64,
            "policy_sha256": "1" * 64,
        },
        "binding_sha256": "2" * 64,
    }


def _waiting_summary() -> dict:
    return {
        "repository": "demo/repo",
        "pull_request": 7,
        "source_revision": HEAD,
        "pie_revision": PIE,
        "candidate_id": "github-capture-demo",
        "status": "WAITING_FOR_TRUST_INPUT",
        "next_step": "PROVIDE_EXPLICIT_OPERATIONAL_TRUST_FACTS",
        "assessment_id": None,
        "packet_id": None,
        "risk_band": None,
        "readiness": None,
    }


def _packet() -> dict:
    return {
        "project_id": "demo",
        "packet_id": "prospective-review-packet-demo",
        "packet_sha256": "3" * 64,
        "assessment_id": "assessment-demo",
        "assessment_sha256": "4" * 64,
        "task_id": "github-pr:demo",
        "source_revision": "git:" + HEAD,
        "trust_report_id": "trust-report-demo",
        "trust_report_sha256": "5" * 64,
        "github": {
            "candidate_id": "github-capture-demo",
            "hostname": "github.com",
            "repository": "demo/repo",
            "pr_number": 7,
            "base_oid": BASE,
            "head_oid": HEAD,
        },
        "predicted_risk_band": "R2",
        "changed_files": ["src/runtime/worker.py", "src/api.py"],
        "hard_gates": ["REPLAY_EVIDENCE_REQUIRED"],
        "review_requirement": "HUMAN_APPROVAL_REQUIRED",
    }


def _ready_summary() -> dict:
    value = _waiting_summary()
    value.update({
        "status": "READY_FOR_HUMAN_REVIEW",
        "next_step": "EXPLICIT_HUMAN_REVIEW_REQUIRED",
        "assessment_id": "assessment-demo",
        "packet_id": "prospective-review-packet-demo",
        "risk_band": "R2",
        "readiness": "NOT_READY",
    })
    return value


class OperationalReviewBriefTests(unittest.TestCase):
    def test_waiting_brief_is_deterministic_non_authoritative_projection(self):
        brief = build_operational_review_brief(
            summary=_waiting_summary(),
            candidate=_candidate(),
            candidate_sha256=CANDIDATE_SHA,
            impact=_impact(),
            operational_binding=_binding(),
        )
        self.assertEqual("WAITING_FOR_TRUST_INPUT", brief["status"])
        self.assertEqual(["api", "runtime"], brief["affected"]["components"])
        self.assertEqual(["python -m unittest", "tests/test_runtime.py"], brief["required_verification"]["analysis_required_tests"])
        self.assertEqual("git:" + BASE, brief["trust"]["operational_policy"]["policy_revision"])
        self.assertFalse(brief["history"]["available"])
        self.assertTrue(all(value is False for value in brief["authority"].values()))
        self.assertEqual([], verify_operational_review_brief_data(brief))
        self.assertEqual([], verify_operational_review_brief_sources(
            brief,
            summary=_waiting_summary(),
            candidate=_candidate(),
            candidate_sha256=CANDIDATE_SHA,
            impact=_impact(),
            operational_binding=_binding(),
        ))

    def test_ready_brief_copies_exact_governed_packet_identity(self):
        brief = build_operational_review_brief(
            summary=_ready_summary(),
            candidate=_candidate(),
            candidate_sha256=CANDIDATE_SHA,
            impact=_impact(),
            operational_binding=_binding(),
            review_packet=_packet(),
        )
        self.assertEqual("READY_FOR_HUMAN_REVIEW", brief["status"])
        self.assertEqual("assessment-demo", brief["trust"]["assessment_id"])
        self.assertEqual("prospective-review-packet-demo", brief["trust"]["review_packet_id"])
        self.assertEqual("HUMAN_APPROVAL_REQUIRED", brief["risk"]["review_requirement"])
        self.assertEqual(["REPLAY_EVIDENCE_REQUIRED"], brief["risk"]["hard_gates"])
        self.assertFalse(brief["authority"]["human_review_recorded"])
        self.assertFalse(brief["authority"]["outcome_recorded"])

    def test_ready_without_packet_is_rejected(self):
        with self.assertRaises(OperationalReviewBriefError):
            build_operational_review_brief(
                summary=_ready_summary(),
                candidate=_candidate(),
                candidate_sha256=CANDIDATE_SHA,
                impact=_impact(),
            )

    def test_packet_from_different_head_is_rejected(self):
        packet = _packet()
        packet["github"]["head_oid"] = "9" * 40
        with self.assertRaises(OperationalReviewBriefError):
            build_operational_review_brief(
                summary=_ready_summary(),
                candidate=_candidate(),
                candidate_sha256=CANDIDATE_SHA,
                impact=_impact(),
                operational_binding=_binding(),
                review_packet=packet,
            )

    def test_binding_from_different_base_is_rejected(self):
        binding = _binding()
        binding["pull_request"]["base_oid"] = "9" * 40
        with self.assertRaises(OperationalReviewBriefError):
            build_operational_review_brief(
                summary=_waiting_summary(),
                candidate=_candidate(),
                candidate_sha256=CANDIDATE_SHA,
                impact=_impact(),
                operational_binding=binding,
            )

    def test_ordering_does_not_change_brief_hash(self):
        first = build_operational_review_brief(
            summary=_waiting_summary(), candidate=_candidate(), candidate_sha256=CANDIDATE_SHA, impact=_impact(), operational_binding=_binding()
        )
        impact = deepcopy(_impact())
        impact["direct"]["components"].reverse()
        impact["review"]["selected_packs"].reverse()
        impact["review"]["required_tests"].reverse()
        impact["impact"]["dependent_files"].reverse()
        second = build_operational_review_brief(
            summary=_waiting_summary(), candidate=_candidate(), candidate_sha256=CANDIDATE_SHA, impact=impact, operational_binding=_binding()
        )
        self.assertEqual(first["brief_sha256"], second["brief_sha256"])

    def test_authority_or_payload_tamper_is_detected(self):
        brief = build_operational_review_brief(
            summary=_waiting_summary(), candidate=_candidate(), candidate_sha256=CANDIDATE_SHA, impact=_impact(), operational_binding=_binding()
        )
        forged = deepcopy(brief)
        forged["authority"]["merge_authorized"] = True
        errors = verify_operational_review_brief_data(forged)
        self.assertTrue(any("merge_authorized" in error for error in errors))
        self.assertIn("brief_sha256 mismatch", errors)

    def test_markdown_exposes_required_sections_and_authority_ceiling(self):
        brief = build_operational_review_brief(
            summary=_waiting_summary(), candidate=_candidate(), candidate_sha256=CANDIDATE_SHA, impact=_impact(), operational_binding=_binding()
        )
        text = render_operational_review_brief_markdown(brief)
        for heading in ("## CHANGE", "## AFFECTED", "## RISK", "## REQUIRED VERIFICATION", "## HISTORY", "## TRUST", "## AUTHORITY"):
            self.assertIn(heading, text)
        self.assertIn("Human review: NOT RECORDED", text)
        self.assertIn("Merge authority: NOT GRANTED", text)
        self.assertIn("ORL-7_NOT_IMPLEMENTED", text)


if __name__ == "__main__":
    unittest.main()

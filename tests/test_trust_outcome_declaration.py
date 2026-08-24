from __future__ import annotations

import unittest

from review_system.trust_outcome_declaration import (
    OutcomeDeclarationError,
    OutcomeDeclarationVerificationError,
    build_outcome_declaration,
    verify_outcome_declaration_data,
)


SHA = "a" * 40
HASH_A = "1" * 64
HASH_B = "2" * 64
HASH_C = "3" * 64


def _base(**overrides):
    values = {
        "actor": "human:reviewer@example.test",
        "project_id": "auto3-calibration",
        "assessment_id": "assessment-" + "a" * 32,
        "source_revision": SHA,
        "trust_report_id": "trust-report-auto3-calibration",
        "trust_report_sha256": HASH_A,
        "review_event_id": "event-" + "b" * 32,
        "review_event_sha256": HASH_B,
        "review_level": "REVIEWED",
        "decision": "APPROVE",
        "review_packet_id": "prospective-review-packet-" + "c" * 32,
        "review_packet_sha256": HASH_C,
        "authority_type": "CONTROLLED_EVALUATION",
        "verdict": "SAFE",
        "declared_at": "2026-08-24T04:40:00Z",
        "evaluation_id": "evaluation-auto3-calibration",
        "evaluation_report_sha256": "4" * 64,
    }
    values.update(overrides)
    return values


class ExplicitOutcomeDeclarationTests(unittest.TestCase):
    def test_controlled_evaluation_declaration_is_deterministic_and_non_executing(self):
        first = build_outcome_declaration(**_base())
        second = build_outcome_declaration(**_base())

        self.assertEqual(first, second)
        self.assertEqual("git:" + SHA, first["assessment"]["source_revision"])
        self.assertEqual("EXPLICIT_OUTCOME_DECLARATION_VALIDATED", first["status"])
        self.assertEqual("AUTO3B_VERIFY_AUTHORITY_SOURCE_AND_RECORD", first["next_step"])
        self.assertTrue(first["human_outcome_declared"])
        self.assertFalse(first["automatic_outcome_inference"])
        self.assertFalse(first["outcome_recorded"])
        self.assertFalse(first["automation_authorized"])
        self.assertFalse(first["pilot_authorized"])
        self.assertFalse(first["merge_authorized"])
        self.assertFalse(first["deploy_authorized"])
        self.assertFalse(first["production_effect_authorized"])
        self.assertEqual([], verify_outcome_declaration_data(first))

    def test_production_defect_cannot_declare_safe(self):
        with self.assertRaises(OutcomeDeclarationError):
            build_outcome_declaration(
                **_base(
                    authority_type="PRODUCTION_DEFECT",
                    verdict="SAFE",
                    defect_id="defect-auto3",
                    evaluation_id=None,
                    evaluation_report_sha256=None,
                    defect_registry_sha256="5" * 64,
                    ledger_sha256="6" * 64,
                )
            )

    def test_production_defect_requires_exact_defect_sources(self):
        value = build_outcome_declaration(
            **_base(
                authority_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                defect_id="defect-auto3",
                evaluation_id=None,
                evaluation_report_sha256=None,
                defect_registry_sha256="5" * 64,
                ledger_sha256="6" * 64,
            )
        )
        self.assertEqual("UNSAFE", value["outcome"]["verdict"])
        self.assertEqual("defect-auto3", value["outcome"]["defect_id"])
        self.assertEqual([], verify_outcome_declaration_data(value))

    def test_authority_binding_rejects_unrelated_source_fields(self):
        with self.assertRaises(OutcomeDeclarationVerificationError):
            build_outcome_declaration(**_base(audit_id="unexpected-audit"))

    def test_prior_review_must_be_reviewed_or_audited(self):
        with self.assertRaises(OutcomeDeclarationError):
            build_outcome_declaration(**_base(review_level="WORKFLOW_ACCEPTED"))

    def test_independent_audit_requires_all_audit_bindings(self):
        with self.assertRaises(OutcomeDeclarationVerificationError):
            build_outcome_declaration(
                **_base(
                    authority_type="INDEPENDENT_AUDIT",
                    evaluation_id=None,
                    evaluation_report_sha256=None,
                    audit_id="audit-auto3",
                    audit_artifact_sha256="7" * 64,
                )
            )

        value = build_outcome_declaration(
            **_base(
                authority_type="INDEPENDENT_AUDIT",
                verdict="INCONCLUSIVE",
                evaluation_id=None,
                evaluation_report_sha256=None,
                audit_id="audit-auto3",
                audit_artifact_sha256="7" * 64,
                audit_authority_registry_sha256="8" * 64,
            )
        )
        self.assertEqual([], verify_outcome_declaration_data(value))

    def test_tampering_invalidates_semantic_hash(self):
        value = build_outcome_declaration(**_base())
        value["outcome"]["verdict"] = "UNSAFE"
        errors = verify_outcome_declaration_data(value)
        self.assertIn("declaration_id mismatch", errors)
        self.assertIn("declaration_sha256 mismatch", errors)


if __name__ == "__main__":
    unittest.main()

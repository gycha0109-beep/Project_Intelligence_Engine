from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from review_system.identity import canonical_json_sha256
from review_system.trust_audit import (
    TrustAuditError,
    add_trust_root,
    authorize_issuer,
    evaluate_audit_authority,
    issue_audit_data,
    new_authority_registry,
    revoke_issuer,
    verify_audit_artifact_data,
    verify_authority_registry_data,
    write_audit_artifact,
)
from review_system.trust_comparison import _assessment_id, _finalize, new_registry


class AuditAuthorityFixture:
    @staticmethod
    def comparison() -> tuple[dict, str]:
        registry = new_registry("demo", created_at="2026-08-01T00:00:00Z")
        assessment = {
            "assessment_id": "",
            "task_id": "TASK-10F-001",
            "source_revision": "git:" + "a" * 40,
            "trust_report_id": "trust-report-" + "1" * 32,
            "trust_report_sha256": "b" * 64,
            "predicted_risk_band": "R0",
            "readiness_status": "READY_FOR_HUMAN_COMPARISON",
            "triggered_hard_gates": [],
            "captured_at": "2026-08-01T00:30:00Z",
            "assessment_sha256": "",
        }
        assessment["assessment_id"] = _assessment_id("demo", assessment)
        assessment["assessment_sha256"] = canonical_json_sha256({
            key: value for key, value in assessment.items() if key != "assessment_sha256"
        })
        registry["assessments"].append(assessment)
        registry = _finalize(registry)
        return registry, assessment["assessment_id"]

    @staticmethod
    def authority() -> tuple[dict, str]:
        registry = new_authority_registry("demo", created_at="2026-08-01T00:00:00Z")
        registry = add_trust_root(
            registry,
            identity_kind="EXTERNAL_AUDITOR",
            subject="external-audit-root",
            fingerprint="audit-root-fingerprint-v1",
            registered_at="2026-08-01T01:00:00Z",
            valid_from="2026-08-01T01:00:00Z",
        )
        root_id = registry["trust_roots"][0]["trust_root_id"]
        registry = authorize_issuer(
            registry,
            trust_root_id=root_id,
            issuer_subject="auditor@example.test",
            granted_at="2026-08-01T02:00:00Z",
            valid_from="2026-08-01T02:00:00Z",
        )
        return registry, registry["grants"][0]["grant_id"]


class TrustAuditAuthorityTests(unittest.TestCase):
    def test_authority_registry_is_deterministic_and_valid(self) -> None:
        registry, _ = AuditAuthorityFixture.authority()
        self.assertEqual([], verify_authority_registry_data(registry))
        self.assertEqual(1, len(registry["trust_roots"]))
        self.assertEqual(1, len(registry["grants"]))

    def test_trust_root_cannot_be_backdated_before_registration(self) -> None:
        registry = new_authority_registry("demo", created_at="2026-08-01T00:00:00Z")
        with self.assertRaises(TrustAuditError):
            add_trust_root(
                registry,
                identity_kind="EXTERNAL_AUDITOR",
                subject="root",
                fingerprint="fingerprint-1234",
                registered_at="2026-08-02T00:00:00Z",
                valid_from="2026-08-01T00:00:00Z",
            )

    def test_issuer_grant_cannot_be_backdated_before_grant(self) -> None:
        registry = new_authority_registry("demo", created_at="2026-08-01T00:00:00Z")
        registry = add_trust_root(
            registry,
            identity_kind="TEAM",
            subject="audit-team",
            fingerprint="fingerprint-1234",
            registered_at="2026-08-01T00:00:00Z",
            valid_from="2026-08-01T00:00:00Z",
        )
        with self.assertRaises(TrustAuditError):
            authorize_issuer(
                registry,
                trust_root_id=registry["trust_roots"][0]["trust_root_id"],
                issuer_subject="auditor@example.test",
                granted_at="2026-08-02T00:00:00Z",
                valid_from="2026-08-01T00:00:00Z",
            )

    def test_nonretroactive_revocation_cannot_take_effect_before_recording(self) -> None:
        registry, grant_id = AuditAuthorityFixture.authority()
        with self.assertRaises(TrustAuditError):
            revoke_issuer(
                registry,
                grant_id=grant_id,
                effective_at="2026-08-03T00:00:00Z",
                recorded_at="2026-08-04T00:00:00Z",
                retroactive=False,
            )

    def test_active_grant_issues_report_only_audit(self) -> None:
        comparison, assessment_id = AuditAuthorityFixture.comparison()
        authority, grant_id = AuditAuthorityFixture.authority()
        artifact = issue_audit_data(
            comparison,
            authority,
            assessment_id=assessment_id,
            grant_id=grant_id,
            verdict="SAFE",
            evidence_refs=["evidence:independent-review-1"],
            issued_at="2026-08-03T00:00:00Z",
        )
        self.assertEqual([], verify_audit_artifact_data(artifact))
        self.assertTrue(evaluate_audit_authority(artifact, authority)["valid"])
        self.assertEqual("REPORT_ONLY", artifact["mode"])
        self.assertFalse(artifact["automation_authorized"])
        self.assertFalse(artifact["pilot_authorized"])

    def test_conclusive_audit_requires_evidence(self) -> None:
        comparison, assessment_id = AuditAuthorityFixture.comparison()
        authority, grant_id = AuditAuthorityFixture.authority()
        with self.assertRaises(TrustAuditError):
            issue_audit_data(
                comparison,
                authority,
                assessment_id=assessment_id,
                grant_id=grant_id,
                verdict="UNSAFE",
                evidence_refs=[],
                issued_at="2026-08-03T00:00:00Z",
            )

    def test_artifact_mutation_is_detected_even_with_original_hash(self) -> None:
        comparison, assessment_id = AuditAuthorityFixture.comparison()
        authority, grant_id = AuditAuthorityFixture.authority()
        artifact = issue_audit_data(
            comparison,
            authority,
            assessment_id=assessment_id,
            grant_id=grant_id,
            verdict="SAFE",
            evidence_refs=["evidence:1"],
            issued_at="2026-08-03T00:00:00Z",
        )
        forged = deepcopy(artifact)
        forged["issuer_subject"] = "attacker@example.test"
        self.assertTrue(verify_audit_artifact_data(forged))

    def test_authority_registry_mutation_invalidates_grant_binding(self) -> None:
        comparison, assessment_id = AuditAuthorityFixture.comparison()
        authority, grant_id = AuditAuthorityFixture.authority()
        artifact = issue_audit_data(
            comparison,
            authority,
            assessment_id=assessment_id,
            grant_id=grant_id,
            verdict="SAFE",
            evidence_refs=["evidence:1"],
            issued_at="2026-08-03T00:00:00Z",
        )
        forged = deepcopy(authority)
        forged["grants"][0]["issuer_subject"] = "attacker@example.test"
        self.assertTrue(verify_authority_registry_data(forged))
        self.assertFalse(evaluate_audit_authority(artifact, forged)["valid"])

    def test_retroactive_revocation_invalidates_prior_audit_authority(self) -> None:
        comparison, assessment_id = AuditAuthorityFixture.comparison()
        authority, grant_id = AuditAuthorityFixture.authority()
        artifact = issue_audit_data(
            comparison,
            authority,
            assessment_id=assessment_id,
            grant_id=grant_id,
            verdict="SAFE",
            evidence_refs=["evidence:1"],
            issued_at="2026-08-05T00:00:00Z",
        )
        revoked = revoke_issuer(
            authority,
            grant_id=grant_id,
            effective_at="2026-08-04T00:00:00Z",
            recorded_at="2026-08-06T00:00:00Z",
            retroactive=True,
            reason_codes=["COMPROMISED_ISSUER"],
        )
        self.assertFalse(evaluate_audit_authority(artifact, revoked)["valid"])

    def test_audit_output_symlink_is_rejected(self) -> None:
        comparison, assessment_id = AuditAuthorityFixture.comparison()
        authority, grant_id = AuditAuthorityFixture.authority()
        artifact = issue_audit_data(
            comparison,
            authority,
            assessment_id=assessment_id,
            grant_id=grant_id,
            verdict="SAFE",
            evidence_refs=["evidence:1"],
            issued_at="2026-08-03T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text("original\n", encoding="utf-8")
            link = root / "audit.json"
            link.symlink_to(target)
            with self.assertRaises(TrustAuditError):
                write_audit_artifact(link, artifact)
            self.assertEqual("original\n", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

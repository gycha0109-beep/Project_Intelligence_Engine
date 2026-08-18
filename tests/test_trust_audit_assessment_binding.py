from pathlib import Path
import tempfile
import unittest

from review_system.trust_audit import (
    add_trust_root,
    authorize_issuer,
    issue_audit_data as issue_low_level_audit,
    new_authority_registry,
)
from review_system.trust_audit_verified import verify_audit_assessment_binding
from test_trust_reconciliation import ReconciliationFixture


class TrustAuditAssessmentBindingTests(unittest.TestCase):
    def _authority(self):
        authority = new_authority_registry("demo", created_at="2026-08-01T00:00:00Z")
        authority = add_trust_root(
            authority,
            identity_kind="EXTERNAL_AUDITOR",
            subject="external-audit-root",
            fingerprint="external-audit-root-v1",
            registered_at="2026-08-01T00:30:00Z",
            valid_from="2026-08-01T00:30:00Z",
        )
        authority = authorize_issuer(
            authority,
            trust_root_id=authority["trust_roots"][0]["trust_root_id"],
            issuer_subject="auditor@example.test",
            granted_at="2026-08-01T01:00:00Z",
            valid_from="2026-08-01T01:00:00Z",
        )
        return authority

    def test_comparison_verifier_rejects_pre_capture_artifact_even_if_authority_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReconciliationFixture(Path(temporary))
            assessment_id = fixture.capture(
                task_class="generated_artifact",
                changed_file="generated/audit-input.json",
            )
            authority = self._authority()
            artifact = issue_low_level_audit(
                fixture.registry,
                authority,
                assessment_id=assessment_id,
                grant_id=authority["grants"][0]["grant_id"],
                verdict="SAFE",
                evidence_refs=["evidence:review"],
                issued_at="2026-08-01T23:59:59Z",
            )
            result = verify_audit_assessment_binding(artifact, fixture.registry)
            self.assertFalse(result["valid"])
            self.assertFalse(result["checks"]["issued_after_assessment"])

    def test_comparison_verifier_accepts_exact_captured_assessment_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReconciliationFixture(Path(temporary))
            assessment_id = fixture.capture(
                task_class="generated_artifact",
                changed_file="generated/audit-input.json",
            )
            assessment = next(item for item in fixture.registry["assessments"] if item["assessment_id"] == assessment_id)
            authority = self._authority()
            artifact = issue_low_level_audit(
                fixture.registry,
                authority,
                assessment_id=assessment_id,
                grant_id=authority["grants"][0]["grant_id"],
                verdict="SAFE",
                evidence_refs=["evidence:review"],
                issued_at=assessment["captured_at"],
            )
            result = verify_audit_assessment_binding(artifact, fixture.registry)
            self.assertTrue(result["valid"])
            self.assertTrue(all(result["checks"].values()))


if __name__ == "__main__":
    unittest.main()

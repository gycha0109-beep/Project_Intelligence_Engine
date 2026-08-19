from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.io import dump_json, load_data
from review_system.trust_audit import (
    add_trust_root,
    authorize_issuer,
    new_authority_registry,
    verify_audit_artifact_data,
)
from review_system.trust_audit_verified import TrustAuditError, issue_audit_data
from review_system.trust_reconciliation_hardened import (
    TrustReconciliationError,
    reconcile_sources,
    verify_reconciliation_report_sources,
    write_reconciliation_report,
)
from test_trust_reconciliation import ReconciliationFixture
from test_trust_reconciliation_audit import AuditReconciliationFixture


class TrustAuditHardeningTests(unittest.TestCase):
    def test_public_issuance_rejects_audit_before_assessment_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReconciliationFixture(Path(temporary))
            assessment_id = fixture.capture(
                task_class="generated_artifact",
                changed_file="generated/audit-input.json",
            )
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
            with self.assertRaises(TrustAuditError):
                issue_audit_data(
                    fixture.registry,
                    authority,
                    assessment_id=assessment_id,
                    grant_id=authority["grants"][0]["grant_id"],
                    verdict="SAFE",
                    evidence_refs=["evidence:review"],
                    issued_at="2026-08-01T23:59:59Z",
                )

    def test_public_issuance_accepts_audit_at_assessment_capture_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReconciliationFixture(Path(temporary))
            assessment_id = fixture.capture(
                task_class="generated_artifact",
                changed_file="generated/audit-input.json",
            )
            assessment = next(item for item in fixture.registry["assessments"] if item["assessment_id"] == assessment_id)
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
            artifact = issue_audit_data(
                fixture.registry,
                authority,
                assessment_id=assessment_id,
                grant_id=authority["grants"][0]["grant_id"],
                verdict="SAFE",
                evidence_refs=["evidence:review"],
                issued_at=assessment["captured_at"],
            )
            self.assertEqual([], verify_audit_artifact_data(artifact))

    def test_audit_artifact_mutation_breaks_exact_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue()
            wrapped.record()
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            self.assertEqual([], verify_reconciliation_report_sources(
                report,
                registry_path=wrapped.fixture.registry_path,
                source_manifest_path=wrapped.fixture.sources_path,
            ))
            artifact = load_data(wrapped.audit_path)
            artifact["evidence_refs"].append("evidence:mutated")
            dump_json(wrapped.audit_path, artifact)
            errors = verify_reconciliation_report_sources(
                report,
                registry_path=wrapped.fixture.registry_path,
                source_manifest_path=wrapped.fixture.sources_path,
            )
            self.assertTrue(errors)

    def test_authority_registry_mutation_breaks_exact_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue()
            wrapped.record()
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            authority = load_data(wrapped.authority_path)
            authority["grants"][0]["issuer_subject"] = "mutated@example.test"
            dump_json(wrapped.authority_path, authority)
            errors = verify_reconciliation_report_sources(
                report,
                registry_path=wrapped.fixture.registry_path,
                source_manifest_path=wrapped.fixture.sources_path,
            )
            self.assertTrue(errors)

    def test_stage10f_atomic_replace_failure_preserves_existing_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrapped = AuditReconciliationFixture(root)
            wrapped.issue()
            wrapped.record()
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            target = root / "reconciliation-report.json"
            target.write_text("original\n", encoding="utf-8")
            with patch("review_system.trust_reconciliation_hardened.os.replace", side_effect=OSError("boom")):
                with self.assertRaises(TrustReconciliationError):
                    write_reconciliation_report(target, report)
            self.assertEqual("original\n", target.read_text(encoding="utf-8"))

    def test_report_authorization_flags_remain_false(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue()
            wrapped.record()
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            self.assertFalse(report["automation_authorized"])
            self.assertFalse(report["pilot_authorized"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from review_system.identity import canonical_json_sha256
from review_system.io import dump_json
from review_system.trust_audit import (
    add_trust_root,
    authorize_issuer,
    issue_audit_data,
    new_authority_registry,
    revoke_issuer,
    write_audit_artifact,
    write_authority_registry,
)
from review_system.trust_reconciliation_verified import (
    reconcile_sources,
    verify_reconciliation_report_data,
    verify_reconciliation_report_sources,
)
from review_system import trust_reconciliation as legacy_reconciliation
from review_system.trust_pilot_review import _reconciliation_projection
from test_trust_reconciliation import ReconciliationFixture


class AuditReconciliationFixture:
    def __init__(self, root: Path):
        self.root = root
        self.fixture = ReconciliationFixture(root)
        self.assessment_id = self.fixture.capture()
        self.authority = new_authority_registry("demo", created_at="2026-08-01T00:00:00Z")
        self.authority = add_trust_root(
            self.authority,
            identity_kind="EXTERNAL_AUDITOR",
            subject="external-audit-root",
            fingerprint="external-audit-root-v1",
            registered_at="2026-08-01T00:30:00Z",
            valid_from="2026-08-01T00:30:00Z",
        )
        self.authority = authorize_issuer(
            self.authority,
            trust_root_id=self.authority["trust_roots"][0]["trust_root_id"],
            issuer_subject="auditor@example.test",
            granted_at="2026-08-01T01:00:00Z",
            valid_from="2026-08-01T01:00:00Z",
        )
        self.authority_path = root / "audit-authority.json"
        self.audit_path = root / "audit.json"
        self.artifact = None

    @property
    def grant_id(self) -> str:
        return self.authority["grants"][0]["grant_id"]

    def issue(self, *, verdict: str = "SAFE", issued_at: str = "2026-08-03T00:00:00Z") -> dict:
        self.artifact = issue_audit_data(
            self.fixture.registry,
            self.authority,
            assessment_id=self.assessment_id,
            grant_id=self.grant_id,
            verdict=verdict,
            evidence_refs=["evidence:external-audit-review"],
            issued_at=issued_at,
        )
        write_audit_artifact(self.audit_path, self.artifact)
        return self.artifact

    def record(
        self,
        *,
        verdict: str | None = None,
        actor: str | None = None,
        occurred_at: str = "2026-08-05T00:00:00Z",
        refs: list[str] | None = None,
        map_source: bool = True,
    ) -> str:
        assert self.artifact is not None
        event_id = self.fixture.add_outcome(
            assessment_id=self.assessment_id,
            outcome_type="INDEPENDENT_AUDIT",
            verdict=verdict or self.artifact["verdict"],
            actor=actor or self.artifact["issuer_subject"],
            occurred_at=occurred_at,
            evidence_refs=refs if refs is not None else [self.artifact["audit_id"], self.artifact["artifact_sha256"]],
        )
        if map_source:
            self.fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "INDEPENDENT_AUDIT",
                "audit_artifact": self.fixture.rel(self.audit_path),
                "audit_authority_registry": self.fixture.rel(self.authority_path),
            })
        return event_id

    def persist(self) -> None:
        write_authority_registry(self.authority_path, self.authority)
        self.fixture.persist()


class TrustReconciliationAuditTests(unittest.TestCase):
    def test_verified_audit_reconciles_and_counts_for_stage10e(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue()
            wrapped.record()
            wrapped.persist()
            report = reconcile_sources(
                wrapped.fixture.registry_path,
                wrapped.fixture.sources_path,
                generated_at="2026-08-18T00:00:00Z",
            )
            audit = report["outcome_reconciliation"][0]
            self.assertEqual("RECONCILED", audit["status"])
            self.assertTrue(audit["checks"]["independent_provenance_verified"])
            self.assertTrue(report["summary"]["source_reconciliation_complete"])
            self.assertEqual([], verify_reconciliation_report_data(report))
            self.assertEqual([], verify_reconciliation_report_sources(
                report,
                registry_path=wrapped.fixture.registry_path,
                source_manifest_path=wrapped.fixture.sources_path,
            ))
            projection = _reconciliation_projection(report, wrapped.fixture.registry)
            self.assertEqual(1, projection["verified_r0_independent_audit_assessment_count"])

    def test_legacy_audit_without_authority_mapping_remains_provenance_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue()
            wrapped.record(map_source=False)
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            self.assertEqual("PROVENANCE_UNVERIFIED", report["outcome_reconciliation"][0]["status"])
            self.assertFalse(report["outcome_reconciliation"][0]["reconciled"])

    def test_declared_but_missing_audit_source_fails_as_source_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrapped = AuditReconciliationFixture(root)
            wrapped.issue()
            event_id = wrapped.record()
            wrapped.persist()
            manifest = {
                "schema_version": "1.0",
                "project_id": "demo",
                "assessment_sources": wrapped.fixture.assessment_sources,
                "outcome_sources": [{
                    "event_id": event_id,
                    "authority_type": "INDEPENDENT_AUDIT",
                    "audit_artifact": "missing-audit.json",
                    "audit_authority_registry": "missing-authority.json",
                }],
            }
            dump_json(wrapped.fixture.sources_path, manifest)
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            self.assertEqual("SOURCE_MISSING", report["outcome_reconciliation"][0]["status"])
            self.assertEqual([], verify_reconciliation_report_data(report))

    def test_outcome_must_reference_both_audit_id_and_artifact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            artifact = wrapped.issue()
            wrapped.record(refs=[artifact["audit_id"]])
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            self.assertEqual("OUTCOME_REFERENCE_MISMATCH", report["outcome_reconciliation"][0]["status"])

    def test_outcome_actor_must_match_authorized_audit_issuer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue()
            wrapped.record(actor="different-auditor@example.test")
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            audit = report["outcome_reconciliation"][0]
            self.assertEqual("PROVENANCE_UNVERIFIED", audit["status"])
            self.assertFalse(audit["checks"]["issuer_match"])

    def test_audit_issued_after_outcome_cannot_backfill_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue(issued_at="2026-08-06T00:00:00Z")
            wrapped.record(occurred_at="2026-08-05T00:00:00Z")
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            audit = report["outcome_reconciliation"][0]
            self.assertEqual("PROVENANCE_UNVERIFIED", audit["status"])
            self.assertFalse(audit["checks"]["issued_before_outcome"])

    def test_audit_verdict_must_match_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue(verdict="SAFE")
            wrapped.record(verdict="UNSAFE")
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            self.assertEqual("OUTCOME_VERDICT_MISMATCH", report["outcome_reconciliation"][0]["status"])

    def test_retroactive_revocation_invalidates_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue(issued_at="2026-08-03T00:00:00Z")
            wrapped.record(occurred_at="2026-08-05T00:00:00Z")
            wrapped.authority = revoke_issuer(
                wrapped.authority,
                grant_id=wrapped.grant_id,
                effective_at="2026-08-02T00:00:00Z",
                recorded_at="2026-08-04T00:00:00Z",
                retroactive=True,
                reason_codes=["COMPROMISED_ISSUER"],
            )
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            self.assertEqual("PROVENANCE_UNVERIFIED", report["outcome_reconciliation"][0]["status"])

    def test_reusing_same_conclusive_audit_authority_is_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue()
            wrapped.record(occurred_at="2026-08-05T00:00:00Z")
            wrapped.record(occurred_at="2026-08-06T00:00:00Z")
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            statuses = [item["status"] for item in report["outcome_reconciliation"]]
            self.assertEqual(["DUPLICATE_AUTHORITY", "DUPLICATE_AUTHORITY"], statuses)
            self.assertEqual(2, report["summary"]["duplicate_authority_count"])

    def test_semantic_rehash_cannot_flip_audit_provenance_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue()
            wrapped.record()
            wrapped.persist()
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            forged = deepcopy(report)
            audit = forged["outcome_reconciliation"][0]
            audit["checks"]["issuer_match"] = False
            audit["checks"]["independent_provenance_verified"] = True
            forged["evidence_snapshot_sha256"] = canonical_json_sha256(legacy_reconciliation._snapshot_payload(forged))
            forged["report_id"] = legacy_reconciliation._report_id(forged, forged["evidence_snapshot_sha256"])
            forged["report_sha256"] = canonical_json_sha256(legacy_reconciliation._report_payload(forged))
            errors = verify_reconciliation_report_data(forged)
            self.assertTrue(any("independent_provenance_verified projection mismatch" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

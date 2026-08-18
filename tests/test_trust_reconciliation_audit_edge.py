from pathlib import Path
import tempfile
import unittest

from review_system.io import dump_json
from review_system.trust_reconciliation_hardened import reconcile_sources
from review_system.trust_reconciliation_verified import verify_reconciliation_report_data
from test_trust_reconciliation_audit import AuditReconciliationFixture


class TrustReconciliationAuditEdgeTests(unittest.TestCase):
    def test_unreconciled_assessment_keeps_audit_assessment_unreconciled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wrapped = AuditReconciliationFixture(Path(temporary))
            wrapped.issue()
            event_id = wrapped.record()
            wrapped.persist()
            assessment_source = dict(wrapped.fixture.assessment_sources[0])
            assessment_source["trust_report"] = "missing-trust-report.json"
            dump_json(wrapped.fixture.sources_path, {
                "schema_version": "1.0",
                "project_id": "demo",
                "assessment_sources": [assessment_source],
                "outcome_sources": [{
                    "event_id": event_id,
                    "authority_type": "INDEPENDENT_AUDIT",
                    "audit_artifact": wrapped.fixture.rel(wrapped.audit_path),
                    "audit_authority_registry": wrapped.fixture.rel(wrapped.authority_path),
                }],
            })
            report = reconcile_sources(wrapped.fixture.registry_path, wrapped.fixture.sources_path)
            audit = report["outcome_reconciliation"][0]
            self.assertEqual("ASSESSMENT_UNRECONCILED", audit["base_status"])
            self.assertEqual("ASSESSMENT_UNRECONCILED", audit["status"])
            self.assertFalse(audit["reconciled"])
            self.assertFalse(audit["checks"]["assessment_reconciled"])
            self.assertFalse(audit["checks"]["independent_provenance_verified"])
            self.assertEqual([], verify_reconciliation_report_data(report))


if __name__ == "__main__":
    unittest.main()

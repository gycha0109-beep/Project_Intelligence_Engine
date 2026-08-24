from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.trust_outcome_transport import (
    OutcomeTransportError,
    _assessment_binding,
    _review_binding,
    transport_declared_outcome,
)


ASSESSMENT_ID = "assessment-" + "a" * 32
EVENT_ID = "event-" + "b" * 32
PACKET_ID = "prospective-review-packet-" + "c" * 32
HASH_A = "1" * 64
HASH_B = "2" * 64
HASH_C = "3" * 64


def _declaration():
    return {
        "declaration_id": "outcome-declaration-" + "d" * 32,
        "declaration_sha256": "4" * 64,
        "declared_at": "2026-08-24T05:10:00Z",
        "actor": "human:reviewer@example.test",
        "project_id": "auto3-calibration",
        "assessment": {
            "assessment_id": ASSESSMENT_ID,
            "source_revision": "git:" + "a" * 40,
            "trust_report_id": "trust-report-auto3",
            "trust_report_sha256": HASH_A,
        },
        "review": {
            "event_id": EVENT_ID,
            "event_sha256": HASH_B,
            "review_level": "REVIEWED",
            "decision": "APPROVE",
            "review_packet_id": PACKET_ID,
            "review_packet_sha256": HASH_C,
        },
        "outcome": {
            "authority_type": "CONTROLLED_EVALUATION",
            "verdict": "SAFE",
            "defect_id": None,
            "evidence_refs": [],
            "source_binding": {
                "evaluation_id": "evaluation-auto3",
                "evaluation_report_sha256": "5" * 64,
            },
        },
    }


def _registry():
    return {
        "project_id": "auto3-calibration",
        "registry_sha256": "6" * 64,
        "assessments": [
            {
                "assessment_id": ASSESSMENT_ID,
                "source_revision": "git:" + "a" * 40,
                "trust_report_id": "trust-report-auto3",
                "trust_report_sha256": HASH_A,
            }
        ],
        "events": [
            {
                "event_id": EVENT_ID,
                "event_sha256": HASH_B,
                "event_type": "HUMAN_DECISION",
                "assessment_id": ASSESSMENT_ID,
                "occurred_at": "2026-08-24T05:00:00Z",
                "payload": {
                    "review_level": "REVIEWED",
                    "decision": "APPROVE",
                    "reason_codes": [
                        f"REVIEW_PACKET_ID:{PACKET_ID}",
                        f"REVIEW_PACKET_SHA256:{HASH_C}",
                    ],
                },
            }
        ],
    }


class DeclaredOutcomeTransportTests(unittest.TestCase):
    def test_assessment_binding_requires_exact_source_and_trust_identity(self):
        assessment = _assessment_binding(_registry(), _declaration())
        self.assertEqual(ASSESSMENT_ID, assessment["assessment_id"])

        changed = _declaration()
        changed["assessment"]["source_revision"] = "git:" + "f" * 40
        with self.assertRaises(OutcomeTransportError):
            _assessment_binding(_registry(), changed)

    def test_review_binding_requires_governed_packet_reasons_and_ordering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch(
                "review_system.trust_outcome_transport._load_review_packet_archive",
                return_value={"packet_id": PACKET_ID},
            ) as archive:
                result = _review_binding(root, _registry(), _declaration())
        self.assertEqual(EVENT_ID, result["event"]["event_id"])
        archive.assert_called_once()

        changed_registry = _registry()
        changed_registry["events"][0]["payload"]["reason_codes"] = []
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(OutcomeTransportError):
                _review_binding(Path(temporary), changed_registry, _declaration())

    def test_review_binding_rejects_outcome_declared_before_review(self):
        changed = _declaration()
        changed["declared_at"] = "2026-08-24T04:59:59Z"
        with tempfile.TemporaryDirectory() as temporary:
            with patch(
                "review_system.trust_outcome_transport._load_review_packet_archive",
                return_value={"packet_id": PACKET_ID},
            ):
                with self.assertRaises(OutcomeTransportError):
                    _review_binding(Path(temporary), _registry(), changed)

    def test_transport_commits_only_after_matching_preflight_projection(self):
        declared = _declaration()
        registry = _registry()
        manifest = {"schema_version": "1.0", "project_id": "auto3-calibration", "assessment_sources": [], "outcome_sources": []}
        result = {
            "event_id": "event-" + "e" * 32,
            "assessment_id": ASSESSMENT_ID,
            "outcome_type": "CONTROLLED_EVALUATION",
            "verdict": "SAFE",
            "registry_sha256": "7" * 64,
            "idempotent": False,
        }
        reconciliation = {
            "event_id": result["event_id"],
            "status": "RECONCILED",
            "reconciled": True,
            "authority_key": "evaluation:" + "8" * 64 + ":case-auto3",
        }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch("review_system.trust_outcome_transport.verify_outcome_declaration_file", return_value=declared),
                patch("review_system.trust_outcome_transport._required_workspace", return_value=(root / "comparison-registry.json", root / "reconciliation-sources.json", root / "observation-policy.json", registry, manifest, {})),
                patch("review_system.trust_outcome_transport._assessment_binding"),
                patch("review_system.trust_outcome_transport._review_binding"),
                patch("review_system.trust_outcome_transport._source_binding", return_value={}),
                patch("review_system.trust_outcome_transport._record", side_effect=[result, result]) as record,
                patch("review_system.trust_outcome_transport._reconciliation", side_effect=[reconciliation, reconciliation]),
                patch("review_system.trust_outcome_transport.load_registry", return_value=(root / "comparison-registry.json", registry)),
                patch("review_system.trust_outcome_transport.manifest_sha256", return_value="9" * 64),
                patch("review_system.trust_reconciliation_authority.load_source_manifest", return_value=(root / "reconciliation-sources.json", manifest)),
            ):
                output = transport_declared_outcome(root, declaration=root / "declaration.json")

        self.assertEqual(2, record.call_count)
        self.assertTrue(output["human_outcome_declared"])
        self.assertFalse(output["automatic_outcome_inference"])
        self.assertTrue(output["outcome_recorded"])
        self.assertFalse(output["automation_authorized"])
        self.assertFalse(output["pilot_authorized"])
        self.assertFalse(output["merge_authorized"])
        self.assertFalse(output["deploy_authorized"])
        self.assertFalse(output["production_effect_authorized"])
        self.assertEqual("DECLARED_OUTCOME_RECORDED_AND_RECONCILED", output["status"])

    def test_transport_refuses_preflight_commit_divergence(self):
        declared = _declaration()
        registry = _registry()
        manifest = {"schema_version": "1.0", "project_id": "auto3-calibration", "assessment_sources": [], "outcome_sources": []}
        first = {"event_id": "event-" + "e" * 32, "registry_sha256": "7" * 64, "idempotent": False}
        second = {"event_id": "event-" + "f" * 32, "registry_sha256": "8" * 64, "idempotent": False}
        rec_a = {"status": "RECONCILED", "reconciled": True, "authority_key": "authority-a"}
        rec_b = {"status": "RECONCILED", "reconciled": True, "authority_key": "authority-a"}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch("review_system.trust_outcome_transport.verify_outcome_declaration_file", return_value=declared),
                patch("review_system.trust_outcome_transport._required_workspace", return_value=(root / "comparison-registry.json", root / "reconciliation-sources.json", root / "observation-policy.json", registry, manifest, {})),
                patch("review_system.trust_outcome_transport._assessment_binding"),
                patch("review_system.trust_outcome_transport._review_binding"),
                patch("review_system.trust_outcome_transport._source_binding", return_value={}),
                patch("review_system.trust_outcome_transport._record", side_effect=[first, second]),
                patch("review_system.trust_outcome_transport._reconciliation", side_effect=[rec_a, rec_b]),
                patch("review_system.trust_outcome_transport.load_registry", return_value=(root / "comparison-registry.json", registry)),
                patch("review_system.trust_outcome_transport.manifest_sha256", return_value="9" * 64),
                patch("review_system.trust_reconciliation_authority.load_source_manifest", return_value=(root / "reconciliation-sources.json", manifest)),
            ):
                with self.assertRaises(Exception):
                    transport_declared_outcome(root, declaration=root / "declaration.json")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.prospective_trust_bridge_result import stabilize_trusted_bridge_result


class Auto2SemanticReplayTests(unittest.TestCase):
    def _result(self, root: Path, packet: dict) -> dict:
        bundle = root / "bundle"
        packet_path = bundle / "review" / "packet.json"
        packet_path.parent.mkdir(parents=True)
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        result_file = root / "result.json"
        result = {
            "schema_version": "1.0",
            "result_contract": "PIE_AUTO2_HUMAN_REVIEW_RESULT_V1",
            "bridge_contract": "PIE_AUTO2_HUMAN_REVIEW_BRIDGE_V1",
            "authority": {
                "repository": "gycha0109-beep/Project_Intelligence_Engine",
                "revision": "a" * 40,
                "committed_at": "2026-08-24T00:00:00Z",
                "path": "evidence/trust/requests/example.json",
                "provider_blob_sha": "b" * 40,
                "content_sha256": "1" * 64,
            },
            "target": {
                "repository": "demo/repo",
                "pull_request": 7,
                "head_sha": "c" * 40,
                "base_sha": "d" * 40,
                "changed_files": ["src/app.py"],
                "project_id": "demo",
            },
            "trust_request": {
                "task_id": "github-pr:example",
                "source_revision": "git:" + "c" * 40,
                "content_sha256": "1" * 64,
            },
            "status": "READY_FOR_HUMAN_REVIEW",
            "assessment_id": "assessment-1",
            "packet_id": packet["packet_id"],
            "packet_evidence_snapshot_sha256": packet["evidence_snapshot_sha256"],
            "risk_band": "R1",
            "readiness": None,
            "human_review_recorded": False,
            "outcome_recorded": False,
            "automation_authorized": False,
            "pilot_authorized": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
            "deterministic_result_sha256": "0" * 64,
            "bundle": str(bundle),
            "result_file": str(result_file),
        }
        result_file.write_text(json.dumps(result), encoding="utf-8")
        return result

    def _packet(self, *, transport: str, head: str = "c" * 40) -> dict:
        return {
            "schema_version": "1.0",
            "packet_contract": "GOVERNED_PROSPECTIVE_REVIEW_PACKET_V1",
            "packet_id": "prospective-review-packet-" + transport[:32],
            "packet_sha256": transport * 2,
            "project_id": "demo",
            "assessment_id": "assessment-1",
            "assessment_sha256": "2" * 64,
            "task_id": "github-pr:example",
            "source_revision": "git:" + head,
            "trust_report_id": "trust-report-1",
            "trust_report_sha256": "3" * 64,
            "github": {
                "candidate_id": "github-capture-stable",
                "candidate_evidence_snapshot_sha256": transport * 2,
                "candidate_report_sha256": transport[::-1] * 2,
                "hostname": "github.com",
                "repository": "demo/repo",
                "pr_number": 7,
                "pr_url": "https://github.com/demo/repo/pull/7",
                "base_oid": "d" * 40,
                "head_oid": head,
            },
            "predicted_risk_band": "R1",
            "changed_files": ["src/app.py"],
            "hard_gates": [],
            "review_requirement": "REVIEWED",
            "evidence_references": {"trust_evidence_fingerprint_sha256": "4" * 64},
            "source_replay_state": {
                "trust_sources_verified": True,
                "assessment_source_sha256": "5" * 64,
                "assessment_reconciled": True,
                "assessment_reconciliation_status": "RECONCILED",
            },
            "reconciliation_state": {
                "status": "RECONCILED",
                "source_reconciliation_complete": True,
            },
            "generated_at": "2026-08-24T00:00:00Z" if transport[0] == "6" else "2026-08-24T00:10:00Z",
            "mode": "REPORT_ONLY",
            "automation_authorized": False,
            "pilot_authorized": False,
            "human_review_recorded": False,
            "outcome_recorded": False,
            "evidence_snapshot_sha256": transport[::-1] * 2,
        }

    def test_raw_packet_transport_drift_preserves_auto2_semantic_hash(self):
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = stabilize_trusted_bridge_result(
                self._result(Path(first_tmp), self._packet(transport="6" * 32))
            )
            second = stabilize_trusted_bridge_result(
                self._result(Path(second_tmp), self._packet(transport="7" * 32))
            )
            self.assertNotEqual(first["packet_id"], second["packet_id"])
            self.assertNotEqual(
                first["packet_evidence_snapshot_sha256"],
                second["packet_evidence_snapshot_sha256"],
            )
            self.assertEqual(first["semantic_packet_sha256"], second["semantic_packet_sha256"])
            self.assertEqual(
                first["deterministic_result_sha256"],
                second["deterministic_result_sha256"],
            )
            persisted = json.loads(Path(first["result_file"]).read_text(encoding="utf-8"))
            self.assertEqual(first["semantic_packet_sha256"], persisted["semantic_packet_sha256"])
            self.assertEqual(
                first["deterministic_result_sha256"],
                persisted["deterministic_result_sha256"],
            )

    def test_semantic_target_change_changes_auto2_hash(self):
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = stabilize_trusted_bridge_result(
                self._result(Path(first_tmp), self._packet(transport="6" * 32))
            )
            second = stabilize_trusted_bridge_result(
                self._result(Path(second_tmp), self._packet(transport="7" * 32, head="e" * 40))
            )
            self.assertNotEqual(first["semantic_packet_sha256"], second["semantic_packet_sha256"])
            self.assertNotEqual(
                first["deterministic_result_sha256"],
                second["deterministic_result_sha256"],
            )


if __name__ == "__main__":
    unittest.main()

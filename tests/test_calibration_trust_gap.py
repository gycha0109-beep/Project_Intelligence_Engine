from __future__ import annotations

from io import BytesIO
import json
import unittest
from zipfile import ZipFile

from review_system.calibration_trust_gap import (
    TrustGapDiagnosticError,
    build_historical_trust_gap_observation,
    build_trust_gap_diagnostic,
    parse_legacy_trust_gap_artifact,
)

PIE = "a" * 40
HEAD = "b" * 40
INTERFACE = "c" * 64
POLICY = "d" * 64


def _zip(trust_gap: bool = True, read_match: bool = True) -> bytes:
    if not trust_gap:
        signal = {"contract_version":"PIE_SIGNAL_V1","status":"CLEAR","reason":"NO_POLICY_MATCH","match_status":"NO_POLICY_MATCH","next":"NONE"}
        targeted = {}
        brief = None
    else:
        signal = {"contract_version":"PIE_SIGNAL_V1","status":"ACTION_REQUIRED","reason":"MISSING_TRUST_FIELDS","match_status":"UNIQUE_POLICY_MATCH","next":"READ_TRUST_GAPS"}
        targeted = {
            "control:replay_evidence":"targeted/01-control.json",
            "evidence:repository-ci":"targeted/02-evidence.json",
            "scenario:deterministic-output":"targeted/03-scenario.json",
        }
        brief = {
            "contract_version":"PIE_OPERATIONAL_BRIEF_V1",
            "signal_reason":"MISSING_TRUST_FIELDS",
            "match_status":"UNIQUE_POLICY_MATCH",
            "operational_class":"web-runtime",
            "trust_task_class":"routine_code",
            "required":{"scenarios":["deterministic-output"],"evidence":["repository-ci"]},
            "missing":["completed_scenarios","replay_evidence","required_evidence:repository-ci"],
            "read_evidence":list(targeted) if read_match else ["control:replay_evidence"],
        }
    manifest = {
        "contract_version":"PIE_GPT_OPERATIONAL_INTERFACE_V1",
        "level0":{"signal":"signal.json","text":"SIGNAL.txt"},
        "level1":{"brief":"brief.json" if trust_gap else None},
        "level2":{"index":"targeted/index.json","items":targeted},
        "level3":{"full_capsule":"SEPARATE_ARTIFACT"},
        "interface_sha256":INTERFACE,
        "manifest_sha256":"e"*64,
    }
    buffer = BytesIO()
    with ZipFile(buffer,"w") as archive:
        archive.writestr("signal.json",json.dumps(signal))
        archive.writestr("manifest.json",json.dumps(manifest))
        archive.writestr("targeted/index.json",json.dumps(targeted))
        if brief:
            archive.writestr("brief.json",json.dumps(brief))
            for evidence_id,path in targeted.items():
                prefix, requirement = evidence_id.split(":",1)
                kind = {"control":"trust_control","evidence":"required_evidence","scenario":"scenario"}[prefix]
                archive.writestr(path,json.dumps({
                    "contract_version":"PIE_TARGETED_EVIDENCE_V1","id":evidence_id,
                    "kind":kind,"requirement":requirement,"state":"MISSING","observed":None,
                    "provenance":{"policy_revision":"git:"+"f"*40,"policy_sha256":POLICY,"binding_sha256":"1"*64,"facts_sha256":None},
                }))
    return buffer.getvalue()


def _run(run_id: int = 123) -> dict:
    return {"id":run_id,"run_attempt":1,"head_sha":HEAD,"referenced_workflows":[{"path":f"owner/repo/.github/workflows/prospective-pr.yml@{PIE}","sha":PIE}]}


def _artifact(run_id: int = 123, artifact_id: int = 456) -> dict:
    return {"id":artifact_id,"name":"pie-owner-repo-pr-42-bbbbbbbbbbbb-eeeeeeeeeeee-interface","workflow_run":{"id":run_id,"head_sha":HEAD}}


class HistoricalTrustGapTests(unittest.TestCase):
    def test_restores_source_backed_gap_detail(self):
        parsed = parse_legacy_trust_gap_artifact(_zip())
        assert parsed is not None
        self.assertEqual("web-runtime",parsed["operational_class"])
        self.assertEqual("routine_code",parsed["trust_task_class"])
        self.assertEqual(["completed_scenarios","replay_evidence","required_evidence:repository-ci"],parsed["missing_fields"])
        self.assertEqual(3,len(parsed["targeted_evidence"]))
        self.assertTrue(all(item["facts_sha256"] is None for item in parsed["targeted_evidence"]))

    def test_non_trust_gap_is_not_reclassified(self):
        self.assertIsNone(parse_legacy_trust_gap_artifact(_zip(False)))

    def test_read_evidence_mismatch_fails_closed(self):
        with self.assertRaisesRegex(TrustGapDiagnosticError,"read_evidence"):
            parse_legacy_trust_gap_artifact(_zip(True,False))

    def test_rerun_dedup_and_authority(self):
        first = build_historical_trust_gap_observation(repository="owner/repo",pie_revision=PIE,run=_run(123),artifact=_artifact(123,456),artifact_zip=_zip())
        second = build_historical_trust_gap_observation(repository="owner/repo",pie_revision=PIE,run=_run(124),artifact=_artifact(124,457),artifact_zip=_zip())
        assert first is not None and second is not None
        result = build_trust_gap_diagnostic([first,second])
        self.assertEqual(1,result["unique_calibration_count"])
        self.assertEqual(1,result["duplicate_observation_count"])
        self.assertEqual(1,result["histograms"]["missing_field"]["completed_scenarios"])
        self.assertEqual(3,result["targeted"]["missing_item_total"])
        self.assertFalse(result["authority"]["trust_fact_inferred"])
        self.assertTrue(first["authority"]["historical_observation_only"])
        self.assertFalse(first["authority"]["outcome_inferred"])


if __name__ == "__main__":
    unittest.main()

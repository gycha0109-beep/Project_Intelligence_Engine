from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
import unittest
from zipfile import ZipFile

from review_system.calibration_policy_ambiguity import (
    PolicyAmbiguityDiagnosticError,
    build_historical_policy_ambiguity_observation,
    build_policy_ambiguity_diagnostic,
    parse_legacy_policy_ambiguity_artifact,
)

PIE = "a" * 40
HEAD = "b" * 40
INTERFACE = "c" * 64
POLICY = "d" * 64


def _zip(
    *,
    ambiguous: bool = True,
    matched_classes: list[str] | None = None,
    read_match: bool = True,
) -> bytes:
    matched_classes = matched_classes or ["api-contract", "runtime-integration"]
    if not ambiguous:
        signal = {
            "contract_version": "PIE_SIGNAL_V1",
            "status": "CLEAR",
            "reason": "NO_POLICY_MATCH",
            "match_status": "NO_POLICY_MATCH",
            "next": "NONE",
        }
        targeted = {}
        brief = None
    else:
        signal = {
            "contract_version": "PIE_SIGNAL_V1",
            "status": "ACTION_REQUIRED",
            "reason": "AMBIGUOUS_POLICY_MATCH",
            "match_status": "AMBIGUOUS_POLICY_MATCH",
            "next": "READ_POLICY_MATCH_DETAILS",
        }
        targeted = {"policy-match-details": "targeted/01-policy-match-details.json"}
        brief = {
            "contract_version": "PIE_OPERATIONAL_BRIEF_V1",
            "signal_reason": "AMBIGUOUS_POLICY_MATCH",
            "match_status": "AMBIGUOUS_POLICY_MATCH",
            "operational_class": None,
            "trust_task_class": None,
            "required": {"scenarios": [], "evidence": []},
            "missing": ["AMBIGUOUS_OPERATIONAL_CLASS_MATCH"],
            "read_evidence": list(targeted) if read_match else [],
        }
    manifest = {
        "contract_version": "PIE_GPT_OPERATIONAL_INTERFACE_V1",
        "level0": {"signal": "signal.json", "text": "SIGNAL.txt"},
        "level1": {"brief": "brief.json" if ambiguous else None},
        "level2": {"index": "targeted/index.json", "items": targeted},
        "level3": {"full_capsule": "SEPARATE_ARTIFACT"},
        "interface_sha256": INTERFACE,
        "manifest_sha256": "e" * 64,
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("signal.json", json.dumps(signal))
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("targeted/index.json", json.dumps(targeted))
        if brief:
            archive.writestr("brief.json", json.dumps(brief))
            archive.writestr(
                "targeted/01-policy-match-details.json",
                json.dumps(
                    {
                        "contract_version": "PIE_TARGETED_EVIDENCE_V1",
                        "id": "policy-match-details",
                        "kind": "policy_match",
                        "state": "AMBIGUOUS",
                        "matched_operational_classes": matched_classes,
                        "provenance": {
                            "policy_revision": "git:" + "f" * 40,
                            "policy_sha256": POLICY,
                            "binding_sha256": "1" * 64,
                            "facts_sha256": None,
                        },
                    }
                ),
            )
    return buffer.getvalue()


def _run(run_id: int = 123) -> dict:
    return {
        "id": run_id,
        "run_attempt": 1,
        "head_sha": HEAD,
        "referenced_workflows": [
            {"path": f"owner/repo/.github/workflows/prospective-pr.yml@{PIE}", "sha": PIE}
        ],
    }


def _artifact(run_id: int = 123, artifact_id: int = 456) -> dict:
    return {
        "id": artifact_id,
        "name": "pie-owner-repo-pr-42-bbbbbbbbbbbb-eeeeeeeeeeee-interface",
        "workflow_run": {"id": run_id, "head_sha": HEAD},
    }


class HistoricalPolicyAmbiguityTests(unittest.TestCase):
    def test_restores_source_backed_ambiguity_detail(self):
        parsed = parse_legacy_policy_ambiguity_artifact(_zip())
        assert parsed is not None
        self.assertEqual(["api-contract", "runtime-integration"], parsed["matched_operational_classes"])
        self.assertEqual(2, parsed["match_cardinality"])
        self.assertEqual(POLICY, parsed["policy_match_details"]["policy_sha256"])
        self.assertIsNone(parsed["policy_match_details"]["facts_sha256"])

    def test_non_ambiguity_is_not_reclassified(self):
        self.assertIsNone(parse_legacy_policy_ambiguity_artifact(_zip(ambiguous=False)))

    def test_read_evidence_mismatch_fails_closed(self):
        with self.assertRaisesRegex(PolicyAmbiguityDiagnosticError, "read_evidence"):
            parse_legacy_policy_ambiguity_artifact(_zip(read_match=False))

    def test_single_class_ambiguity_fails_closed(self):
        with self.assertRaisesRegex(PolicyAmbiguityDiagnosticError, "at least two"):
            parse_legacy_policy_ambiguity_artifact(_zip(matched_classes=["api-contract"]))

    def test_rerun_dedup_and_no_resolution_authority(self):
        first = build_historical_policy_ambiguity_observation(
            repository="owner/repo",
            pie_revision=PIE,
            run=_run(123),
            artifact=_artifact(123, 456),
            artifact_zip=_zip(),
        )
        second = build_historical_policy_ambiguity_observation(
            repository="owner/repo",
            pie_revision=PIE,
            run=_run(124),
            artifact=_artifact(124, 457),
            artifact_zip=_zip(),
        )
        assert first is not None and second is not None
        result = build_policy_ambiguity_diagnostic([first, second])
        self.assertEqual(1, result["unique_calibration_count"])
        self.assertEqual(1, result["duplicate_observation_count"])
        self.assertEqual(1, result["histograms"]["ambiguity_set"]["api-contract|runtime-integration"])
        self.assertEqual(1, result["histograms"]["class_pair"]["api-contract|runtime-integration"])
        self.assertFalse(result["authority"]["policy_resolution_inferred"])
        self.assertFalse(result["authority"]["operational_class_selected"])
        self.assertFalse(first["authority"]["merge_authorized"])

    def test_same_calibration_key_semantic_conflict_fails_closed(self):
        first = build_historical_policy_ambiguity_observation(
            repository="owner/repo",
            pie_revision=PIE,
            run=_run(123),
            artifact=_artifact(123, 456),
            artifact_zip=_zip(),
        )
        second = build_historical_policy_ambiguity_observation(
            repository="owner/repo",
            pie_revision=PIE,
            run=_run(124),
            artifact=_artifact(124, 457),
            artifact_zip=_zip(),
        )
        assert first is not None and second is not None
        conflicting = deepcopy(second)
        conflicting["matched_operational_classes"] = ["api-contract", "storage"]
        conflicting["match_cardinality"] = 2
        semantic_body = {
            key: conflicting[key]
            for key in (
                "contract_version",
                "identity",
                "interface_sha256",
                "matched_operational_classes",
                "match_cardinality",
                "policy_match_details",
            )
        }
        from review_system.identity import canonical_json_sha256

        conflicting["semantic_sha256"] = canonical_json_sha256(semantic_body)
        observation_body = dict(conflicting)
        observation_body.pop("observation_sha256", None)
        conflicting["observation_sha256"] = canonical_json_sha256(observation_body)
        with self.assertRaisesRegex(PolicyAmbiguityDiagnosticError, "conflicting"):
            build_policy_ambiguity_diagnostic([first, conflicting])

    def test_empty_corpus_is_valid(self):
        result = build_policy_ambiguity_diagnostic([])
        self.assertEqual(0, result["unique_calibration_count"])
        self.assertEqual(0, result["ambiguity"]["observation_total"])
        self.assertEqual({}, result["histograms"]["ambiguity_set"])


if __name__ == "__main__":
    unittest.main()

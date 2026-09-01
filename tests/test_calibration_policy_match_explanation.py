from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.calibration_observation import build_calibration_record
from review_system.calibration_policy_match_explanation import (
    CONTRACT_VERSION,
    FILENAME,
    LEDGER_CONTRACT_VERSION,
    CalibrationPolicyMatchExplanationError,
    build_calibration_policy_match_explanation_ledger,
    build_calibration_policy_match_explanation_sidecar,
    verify_calibration_policy_match_explanation_binding,
    verify_calibration_policy_match_explanation_sidecar,
    write_calibration_policy_match_explanation_sidecar,
)
from review_system.identity import canonical_json_sha256
from review_system.operational_policy_match_explanation import (
    CONTRACT_VERSION as SOURCE_CONTRACT_VERSION,
    SCHEMA_VERSION as SOURCE_SCHEMA_VERSION,
)


HEAD = "a" * 40
PIE = "b" * 40
INTERFACE = "d" * 64
POLICY = "c" * 64

SOURCE_AUTHORITY = {
    "operational_class_resolution_authorized": False,
    "trust_fact_inferred": False,
    "human_review_inferred": False,
    "outcome_inferred": False,
    "merge_authorized": False,
    "deploy_authorized": False,
    "production_effect_authorized": False,
}


def _record() -> dict:
    return build_calibration_record(
        repository="gycha0109-beep/K_beauty",
        pull_request=356,
        source_revision=HEAD,
        pie_revision=PIE,
        execution_id="exec-1",
        workflow_run_id="33499781005",
        workflow_run_attempt=1,
        interface={
            "signal": {
                "contract_version": "PIE_SIGNAL_V1",
                "status": "ACTION_REQUIRED",
                "reason": "AMBIGUOUS_POLICY_MATCH",
                "match_status": "AMBIGUOUS_POLICY_MATCH",
                "next": "READ_OPERATIONAL_BRIEF",
            },
            "brief": {},
            "targeted_evidence_ids": [],
            "targeted_evidence": {},
            "interface_sha256": INTERFACE,
        },
    )


def _source(
    *,
    changed_files: list[str] | None = None,
    matched_classes: list[str] | None = None,
    path_matches: list[dict] | None = None,
    mechanism: str = "SAME_PATH_MULTI_CLASS",
) -> dict:
    files = changed_files or ["tools/verify.py"]
    classes = matched_classes or ["engine-runtime", "verifier-boundary"]
    rows = path_matches or [
        {
            "path": "tools/verify.py",
            "matched_operational_classes": ["engine-runtime", "verifier-boundary"],
        }
    ]
    body = {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "contract_version": SOURCE_CONTRACT_VERSION,
        "project_id": "k-beauty",
        "policy": {
            "contract_version": "PIE_OPERATIONAL_POLICY_V1",
            "policy_authority": "PR_BASE_REVISION",
            "policy_sha256": POLICY,
        },
        "changed_files": files,
        "matched_operational_classes": classes,
        "match_cardinality": len(classes),
        "ambiguous": len(classes) > 1,
        "ambiguity_mechanism": mechanism,
        "path_matches": rows,
        "authority": dict(SOURCE_AUTHORITY),
    }
    return {**body, "explanation_sha256": canonical_json_sha256(body)}


class CalibrationPolicyMatchExplanationTests(unittest.TestCase):
    def test_builds_sidecar_without_mutating_calibration_v1(self):
        record = _record()
        original_record_hash = record["record_sha256"]
        source = _source()
        sidecar = build_calibration_policy_match_explanation_sidecar(
            calibration_record=record,
            policy_match_explanation=source,
        )

        self.assertEqual(CONTRACT_VERSION, sidecar["contract_version"])
        self.assertEqual(record["identity"], sidecar["identity"])
        self.assertEqual(record["calibration_key_sha256"], sidecar["calibration_key_sha256"])
        self.assertEqual(record["semantic_sha256"], sidecar["calibration_semantic_sha256"])
        self.assertEqual(
            source["explanation_sha256"],
            sidecar["source_explanation"]["explanation_sha256"],
        )
        self.assertEqual(
            "SAME_PATH_MULTI_CLASS",
            sidecar["explanation"]["ambiguity_mechanism"],
        )
        self.assertEqual(source["path_matches"], sidecar["explanation"]["path_matches"])
        self.assertTrue(sidecar["authority"]["calibration_only"])
        self.assertFalse(sidecar["authority"]["operational_class_resolution_authorized"])
        self.assertFalse(sidecar["authority"]["trust_fact_inferred"])
        self.assertFalse(sidecar["authority"]["human_review_inferred"])
        self.assertFalse(sidecar["authority"]["outcome_inferred"])
        self.assertFalse(sidecar["authority"]["merge_authorized"])
        self.assertFalse(sidecar["authority"]["deploy_authorized"])
        self.assertFalse(sidecar["authority"]["production_effect_authorized"])
        self.assertEqual([], verify_calibration_policy_match_explanation_sidecar(sidecar))
        self.assertEqual([], verify_calibration_policy_match_explanation_binding(record, sidecar))
        self.assertEqual(original_record_hash, record["record_sha256"])

    def test_validates_multi_path_and_mixed_mechanisms(self):
        multi_path = _source(
            changed_files=["app/page.tsx", "middleware.ts"],
            matched_classes=["application-runtime", "authorization-boundary"],
            path_matches=[
                {
                    "path": "app/page.tsx",
                    "matched_operational_classes": ["application-runtime"],
                },
                {
                    "path": "middleware.ts",
                    "matched_operational_classes": ["authorization-boundary"],
                },
            ],
            mechanism="MULTI_PATH_MULTI_CLASS",
        )
        mixed = _source(
            changed_files=["app/auth/login.ts", "tools/verify.py"],
            matched_classes=[
                "application-runtime",
                "authorization-boundary",
                "verifier-boundary",
            ],
            path_matches=[
                {
                    "path": "app/auth/login.ts",
                    "matched_operational_classes": [
                        "application-runtime",
                        "authorization-boundary",
                    ],
                },
                {
                    "path": "tools/verify.py",
                    "matched_operational_classes": ["verifier-boundary"],
                },
            ],
            mechanism="MIXED",
        )
        for source in (multi_path, mixed):
            sidecar = build_calibration_policy_match_explanation_sidecar(
                calibration_record=_record(),
                policy_match_explanation=source,
            )
            self.assertEqual([], verify_calibration_policy_match_explanation_sidecar(sidecar))

    def test_rejects_mechanism_that_disagrees_with_path_rows(self):
        source = _source()
        source["ambiguity_mechanism"] = "MULTI_PATH_MULTI_CLASS"
        body = dict(source)
        body.pop("explanation_sha256")
        source["explanation_sha256"] = canonical_json_sha256(body)
        with self.assertRaisesRegex(
            CalibrationPolicyMatchExplanationError,
            "ambiguity_mechanism does not match",
        ):
            build_calibration_policy_match_explanation_sidecar(
                calibration_record=_record(),
                policy_match_explanation=source,
            )

    def test_rejects_source_hash_tampering(self):
        source = _source()
        source["explanation_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            CalibrationPolicyMatchExplanationError,
            "explanation_sha256 does not match",
        ):
            build_calibration_policy_match_explanation_sidecar(
                calibration_record=_record(),
                policy_match_explanation=source,
            )

    def test_writer_materializes_optional_sidecar_at_calibration_root(self):
        sidecar = build_calibration_policy_match_explanation_sidecar(
            calibration_record=_record(),
            policy_match_explanation=_source(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = write_calibration_policy_match_explanation_sidecar(tmp, sidecar)
            self.assertEqual(Path(tmp).resolve() / FILENAME, path)
            self.assertEqual(sidecar, json.loads(path.read_text(encoding="utf-8")))

    def test_ledger_deduplicates_same_explanation_and_emits_mechanism_histogram(self):
        sidecar = build_calibration_policy_match_explanation_sidecar(
            calibration_record=_record(),
            policy_match_explanation=_source(),
        )
        ledger = build_calibration_policy_match_explanation_ledger([sidecar, sidecar])
        self.assertEqual(LEDGER_CONTRACT_VERSION, ledger["contract_version"])
        self.assertEqual(2, ledger["input_sidecar_count"])
        self.assertEqual(1, ledger["unique_calibration_count"])
        self.assertEqual(1, ledger["duplicate_observation_count"])
        self.assertEqual(
            {"SAME_PATH_MULTI_CLASS": 1},
            ledger["histograms"]["ambiguity_mechanism"],
        )
        self.assertEqual({"true": 1}, ledger["histograms"]["ambiguous"])
        self.assertEqual({"2": 1}, ledger["histograms"]["match_cardinality"])
        self.assertTrue(ledger["authority"]["calibration_only"])
        self.assertFalse(ledger["authority"]["operational_class_resolution_authorized"])

    def test_ledger_fails_closed_when_same_calibration_key_changes_explanation(self):
        first = build_calibration_policy_match_explanation_sidecar(
            calibration_record=_record(),
            policy_match_explanation=_source(),
        )
        second_source = _source(
            changed_files=["scripts/verify.py"],
            path_matches=[
                {
                    "path": "scripts/verify.py",
                    "matched_operational_classes": ["engine-runtime", "verifier-boundary"],
                }
            ],
        )
        second = build_calibration_policy_match_explanation_sidecar(
            calibration_record=_record(),
            policy_match_explanation=second_source,
        )
        with self.assertRaisesRegex(
            CalibrationPolicyMatchExplanationError,
            "conflicting policy-match explanations",
        ):
            build_calibration_policy_match_explanation_ledger([first, second])

    def test_tampered_calibration_authority_is_rejected(self):
        sidecar = build_calibration_policy_match_explanation_sidecar(
            calibration_record=_record(),
            policy_match_explanation=_source(),
        )
        sidecar["authority"]["operational_class_resolution_authorized"] = True
        errors = verify_calibration_policy_match_explanation_sidecar(sidecar)
        self.assertIn(
            "authority boundary must remain calibration-only and explicitly false",
            errors,
        )


if __name__ == "__main__":
    unittest.main()

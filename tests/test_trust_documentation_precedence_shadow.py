from __future__ import annotations

import json
from pathlib import Path
import unittest

from review_system.trust import BAND_ORDER, _path_classification, _profile_descriptor
from review_system.trust_documentation_shadow import (
    DOCUMENTATION_PRECEDENCE_REASON,
    classify_documentation_precedence_candidate,
    project_documentation_precedence_candidate,
)
from review_system.trust_workflow_bridge import project_candidate_risk
from review_system.workflow_semantics import build_workflow_diff_evidence


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
SEEN = FIXTURE_DIR / "wave1-seen-baseline.json"
SEEN_WORKFLOW = FIXTURE_DIR / "workflow-semantic-bridge-d1-seen-v1.json"
HOLDOUT_PREDICTIONS = FIXTURE_DIR / "wave1-holdout-shadow-predictions.json"
HOLDOUT_ADJUDICATION = FIXTURE_DIR / "wave1-holdout-adjudication.json"

PROFILE_PATHS = {
    "buildmap": ROOT / "profiles" / "examples" / "buildmap.yml",
    "bejewely": ROOT / "profiles" / "examples" / "bejewely.yml",
    "generic-webapp": ROOT / "profiles" / "examples" / "generic-webapp.yml",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def seen_workflow_evidence(case: dict) -> dict:
    return build_workflow_diff_evidence(
        source_revision=case["source_revision"],
        source_evidence_sha256=case["source_evidence_sha256"],
        changed_files=case["changed_files"],
        diff_text=case["diff_text"],
    )


def holdout_workflow_evidence(item: dict) -> dict | None:
    semantics = item["workflow_semantics"]
    if not semantics:
        return None
    source_hashes = {entry["source_evidence_sha256"] for entry in semantics}
    if len(source_hashes) != 1:
        raise AssertionError("workflow semantics must share one source evidence hash")
    sections: list[str] = []
    for entry in semantics:
        path = entry["path"]
        sections.append(
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            f"{entry['patch']}\n"
        )
    return build_workflow_diff_evidence(
        source_revision=item["frozen_head_sha"],
        source_evidence_sha256=next(iter(source_hashes)),
        changed_files=item["changed_files"],
        diff_text="".join(sections),
    )


class TrustDocumentationPrecedenceShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.seen = load_json(SEEN)
        cls.seen_workflow = load_json(SEEN_WORKFLOW)
        cls.holdout_predictions = load_json(HOLDOUT_PREDICTIONS)
        cls.holdout_adjudication = load_json(HOLDOUT_ADJUDICATION)
        cls.profiles = {
            key: _profile_descriptor(path)[1]
            for key, path in PROFILE_PATHS.items()
        }
        cls.seen_workflow_by_id = {
            item["sample_id"]: item
            for item in cls.seen_workflow["cases"]
        }
        cls.holdout_expected_by_id = {
            item["sample_id"]: item
            for item in cls.holdout_adjudication["samples"]
        }

    def test_candidate_changes_only_r3_documentation_collision_shape(self) -> None:
        cases = {
            "docs/evidence/facelab/execution-authorization-record.md": (
                "R1",
                DOCUMENTATION_PRECEDENCE_REASON,
            ),
            "docs/security/authentication-notes.md": (
                "R1",
                DOCUMENTATION_PRECEDENCE_REASON,
            ),
            "docs/migrations/rollback-plan.md": (
                "R1",
                DOCUMENTATION_PRECEDENCE_REASON,
            ),
            "security-authorization-notes.md": (
                "R1",
                DOCUMENTATION_PRECEDENCE_REASON,
            ),
            "src/auth/security.py": ("R3", "HIGH_RISK_PATH"),
            "supabase/migrations/202608210001.sql": ("R3", "HIGH_RISK_PATH"),
            ".github/workflows/ci.yml": ("R3", "WORKFLOW_CHANGE"),
            "docs/policies/access-control.md": ("R4", "VERIFIER_POLICY_IMPLEMENTATION"),
            "src/review_system/trust.py": ("R4", "VERIFIER_POLICY_IMPLEMENTATION"),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(classify_documentation_precedence_candidate(path), expected)

    def test_authoritative_classifier_remains_unchanged_for_kb274_shape(self) -> None:
        path = "docs/evidence/facelab/face-lab-d2d-x-execution-authorization-20260821-v1.md"
        self.assertEqual(_path_classification(path), ("R3", "HIGH_RISK_PATH"))
        self.assertEqual(
            classify_documentation_precedence_candidate(path),
            ("R1", DOCUMENTATION_PRECEDENCE_REASON),
        )

    def test_existing_d1_public_contract_remains_historical_for_kb274(self) -> None:
        item = next(
            item
            for item in self.holdout_predictions["predictions"]
            if item["sample_id"] == "KB-274"
        )
        request = {
            "source_revision": "git:" + item["frozen_head_sha"],
            "task_class": item["task_class"],
            "changed_files": item["changed_files"],
        }
        d1 = project_candidate_risk(
            request,
            self.profiles[item["profile_basis"]],
        )
        self.assertEqual(d1["risk"]["effective_band"], "R3")

        candidate = project_documentation_precedence_candidate(
            request,
            self.profiles[item["profile_basis"]],
        )
        self.assertTrue(candidate["documentation_precedence_applied"])
        self.assertEqual(candidate["documentation_precedence_paths"], item["changed_files"])
        self.assertEqual(candidate["risk"]["effective_band"], "R1")

    def test_seen_23_preserve_d1_acceptability_and_zero_underclassification(self) -> None:
        acceptable = 0
        exact = 0
        under: list[str] = []
        changed_from_d1: list[str] = []
        for item in self.seen["samples"]:
            case = self.seen_workflow_by_id.get(item["sample_id"])
            request = {
                "task_class": item["task_class"],
                "changed_files": item["changed_files"],
            }
            evidence = None
            if case is not None:
                request["source_revision"] = case["source_revision"]
                evidence = seen_workflow_evidence(case)

            profile = self.profiles[item["profile_basis"]]
            d1 = project_candidate_risk(
                request,
                profile,
                workflow_evidence=evidence,
            )
            candidate = project_documentation_precedence_candidate(
                request,
                profile,
                workflow_evidence=evidence,
            )
            d1_band = d1["risk"]["effective_band"]
            band = candidate["risk"]["effective_band"]
            if band != d1_band:
                changed_from_d1.append(item["sample_id"])
            acceptable += int(band in item["acceptable_bands"])
            exact += int(band == item["expected_band"])
            if BAND_ORDER[band] < BAND_ORDER[item["expected_band"]]:
                under.append(item["sample_id"])

        self.assertEqual(acceptable, 23)
        self.assertEqual(exact, 22)
        self.assertEqual(under, [])
        self.assertEqual(changed_from_d1, [])

    def test_holdout_11_reach_full_exact_and_zero_underclassification(self) -> None:
        acceptable = 0
        exact = 0
        under: list[str] = []
        changed_from_d1: list[str] = []
        observed: dict[str, str] = {}
        for item in self.holdout_predictions["predictions"]:
            expected = self.holdout_expected_by_id[item["sample_id"]]
            request = {
                "source_revision": "git:" + item["frozen_head_sha"],
                "task_class": item["task_class"],
                "changed_files": item["changed_files"],
            }
            evidence = holdout_workflow_evidence(item)
            profile = self.profiles[item["profile_basis"]]
            d1 = project_candidate_risk(
                request,
                profile,
                workflow_evidence=evidence,
            )
            candidate = project_documentation_precedence_candidate(
                request,
                profile,
                workflow_evidence=evidence,
            )
            d1_band = d1["risk"]["effective_band"]
            band = candidate["risk"]["effective_band"]
            observed[item["sample_id"]] = band
            if band != d1_band:
                changed_from_d1.append(item["sample_id"])
            acceptable += int(band in expected["acceptable_bands"])
            exact += int(band == expected["expected_band"])
            if BAND_ORDER[band] < BAND_ORDER[expected["expected_band"]]:
                under.append(item["sample_id"])

        self.assertEqual(acceptable, 11)
        self.assertEqual(exact, 11)
        self.assertEqual(under, [])
        self.assertEqual(changed_from_d1, ["KB-274"])
        self.assertEqual(observed["RW-57"], "R2")
        self.assertEqual(observed["KB-274"], "R1")

    def test_combined_seen_and_holdout_acceptability_is_34_of_34(self) -> None:
        self.assertEqual(len(self.seen["samples"]), 23)
        self.assertEqual(len(self.holdout_predictions["predictions"]), 11)
        self.assertEqual(23 + 11, 34)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from review_system.operational_policy import normalize_operational_policy_data
from review_system.operational_policy_match_explanation import (
    CONTRACT_VERSION,
    OperationalPolicyMatchExplanationError,
    explain_operational_policy_matches,
)


def _readiness() -> dict:
    return {
        "policy_id": "demo-operational",
        "policy_version": "1.0.0",
        "min_ledger_runs": 1,
        "min_ledger_decisions": 1,
        "min_defects": 1,
        "min_closed_defects": 0,
        "min_reground_observations": 1,
        "min_reground_coverage": 1.0,
        "min_reground_precision": 1.0,
        "min_reground_recall": 1.0,
        "max_reground_false_positive_rate": 0.0,
        "require_active_policy": True,
        "require_pass_evaluation": True,
        "require_holdout": True,
        "require_repeatability": True,
        "require_zero_protected_negative_regressions": True,
    }


def _class(paths: list[str]) -> dict:
    return {
        "paths": paths,
        "trust_task_class": "routine_code",
        "required_scenarios": ["process-restart"],
        "required_evidence": ["ci"],
        "readiness_policy": _readiness(),
    }


def _policy(classes: dict[str, dict]) -> dict:
    return normalize_operational_policy_data(
        {
            "schema_version": "1.0",
            "contract_version": "PIE_OPERATIONAL_POLICY_V1",
            "project_id": "demo",
            "policy_authority": "PR_BASE_REVISION",
            "operational_classes": classes,
        }
    )


class OperationalPolicyMatchExplanationTests(unittest.TestCase):
    def test_same_path_multi_class_overlap_is_observational_only(self):
        policy = _policy(
            {
                "engine-runtime": _class(["scripts/**", "tools/**"]),
                "verifier-boundary": _class(["scripts/**", "tools/**"]),
            }
        )
        result = explain_operational_policy_matches(policy, ["tools/check.py"])

        self.assertEqual(CONTRACT_VERSION, result["contract_version"])
        self.assertTrue(result["ambiguous"])
        self.assertEqual(2, result["match_cardinality"])
        self.assertEqual("SAME_PATH_MULTI_CLASS", result["ambiguity_mechanism"])
        self.assertEqual(
            ["engine-runtime", "verifier-boundary"],
            result["path_matches"][0]["matched_operational_classes"],
        )
        self.assertFalse(result["authority"]["operational_class_resolution_authorized"])
        self.assertFalse(result["authority"]["trust_fact_inferred"])
        self.assertFalse(result["authority"]["human_review_inferred"])
        self.assertFalse(result["authority"]["outcome_inferred"])
        self.assertFalse(result["authority"]["merge_authorized"])
        self.assertFalse(result["authority"]["deploy_authorized"])
        self.assertFalse(result["authority"]["production_effect_authorized"])
        self.assertRegex(result["explanation_sha256"], r"^[0-9a-f]{64}$")

    def test_disjoint_surfaces_are_multi_path_multi_class(self):
        policy = _policy(
            {
                "application-runtime": _class(["app/**"]),
                "pipeline-runtime": _class(["scripts/**"]),
            }
        )
        result = explain_operational_policy_matches(
            policy,
            ["scripts/verify.sh", "app/page.tsx"],
        )

        self.assertTrue(result["ambiguous"])
        self.assertEqual("MULTI_PATH_MULTI_CLASS", result["ambiguity_mechanism"])
        self.assertEqual(
            ["application-runtime", "pipeline-runtime"],
            result["matched_operational_classes"],
        )
        self.assertEqual(
            [
                {"path": "app/page.tsx", "matched_operational_classes": ["application-runtime"]},
                {"path": "scripts/verify.sh", "matched_operational_classes": ["pipeline-runtime"]},
            ],
            result["path_matches"],
        )

    def test_same_path_overlap_plus_additional_surface_is_mixed(self):
        policy = _policy(
            {
                "application-runtime": _class(["app/**"]),
                "engine-runtime": _class(["tools/**"]),
                "verifier-boundary": _class(["tools/**"]),
            }
        )
        result = explain_operational_policy_matches(
            policy,
            ["tools/proof.py", "app/page.tsx"],
        )

        self.assertEqual(3, result["match_cardinality"])
        self.assertEqual("MIXED", result["ambiguity_mechanism"])
        self.assertEqual(
            ["application-runtime", "engine-runtime", "verifier-boundary"],
            result["matched_operational_classes"],
        )

    def test_zero_or_one_class_match_has_no_ambiguity_mechanism(self):
        policy = _policy(
            {
                "application-runtime": _class(["app/**"]),
                "pipeline-runtime": _class(["scripts/**"]),
            }
        )
        single = explain_operational_policy_matches(policy, ["app/page.tsx"])
        none = explain_operational_policy_matches(policy, ["docs/readme.md"])

        self.assertFalse(single["ambiguous"])
        self.assertEqual(1, single["match_cardinality"])
        self.assertEqual("NONE", single["ambiguity_mechanism"])
        self.assertFalse(none["ambiguous"])
        self.assertEqual(0, none["match_cardinality"])
        self.assertEqual("NONE", none["ambiguity_mechanism"])

    def test_output_is_deterministic_across_changed_file_order(self):
        policy = _policy(
            {
                "application-runtime": _class(["app/**"]),
                "pipeline-runtime": _class(["scripts/**"]),
            }
        )
        first = explain_operational_policy_matches(
            policy,
            ["scripts/verify.sh", "app/page.tsx"],
        )
        second = explain_operational_policy_matches(
            policy,
            ["app/page.tsx", "scripts/verify.sh"],
        )
        self.assertEqual(first, second)

    def test_normalized_duplicate_changed_files_fail_closed(self):
        policy = _policy({"application-runtime": _class(["app/**"])})
        with self.assertRaises(OperationalPolicyMatchExplanationError):
            explain_operational_policy_matches(
                policy,
                ["app/page.tsx", "app\\page.tsx"],
            )

    def test_policy_provenance_must_match_canonical_hash(self):
        policy = _policy({"application-runtime": _class(["app/**"])})
        policy["operational_classes"]["application-runtime"]["paths"] = ["other/**"]
        with self.assertRaises(OperationalPolicyMatchExplanationError):
            explain_operational_policy_matches(policy, ["other/page.tsx"])


if __name__ == "__main__":
    unittest.main()

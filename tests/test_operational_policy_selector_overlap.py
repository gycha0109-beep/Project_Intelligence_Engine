from __future__ import annotations

import unittest

from review_system.identity import canonical_json_sha256
from review_system.operational_policy import normalize_operational_policy_data
from review_system.operational_policy_selector_overlap import (
    CONTRACT_VERSION,
    OperationalPolicySelectorOverlapError,
    diagnose_operational_policy_selector_overlaps,
)


def _readiness(policy_id: str) -> dict:
    return {
        "policy_id": policy_id,
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


def _class(name: str, paths: list[str], trust_task_class: str = "routine_code") -> dict:
    return {
        "paths": paths,
        "trust_task_class": trust_task_class,
        "required_scenarios": ["deterministic-replay"],
        "required_evidence": ["repository-ci"],
        "readiness_policy": _readiness(f"demo-{name}"),
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


def _kbeauty_like_policy() -> dict:
    return _policy(
        {
            "application-runtime": _class(
                "application-runtime",
                ["app/**", "components/**", "lib/**"],
            ),
            "authorization-boundary": _class(
                "authorization-boundary",
                ["app/**/auth/**", "lib/**/auth/**", "app/**/middleware*", "middleware*"],
                "authorization",
            ),
            "engine-runtime": _class(
                "engine-runtime",
                ["scripts/**", "packages/**", "tools/**"],
            ),
            "verifier-boundary": _class(
                "verifier-boundary",
                [
                    "tools/**",
                    "scripts/**/*verify*",
                    "scripts/**/*evaluation*",
                    "packages/**/*verify*",
                    "packages/**/*evaluation*",
                ],
                "verifier",
            ),
            "crawler-runtime": _class("crawler-runtime", ["crawler/**"]),
            "database-contract": _class("database-contract", ["supabase/**"], "database_migration"),
        }
    )


class OperationalPolicySelectorOverlapTests(unittest.TestCase):
    def test_kbeauty_like_policy_has_eight_proven_overlaps(self):
        result = diagnose_operational_policy_selector_overlaps(_kbeauty_like_policy())

        self.assertEqual(CONTRACT_VERSION, result["contract_version"])
        self.assertEqual(8, result["summary"]["finding_count"])
        self.assertEqual(2, result["summary"]["class_pair_count"])
        self.assertEqual(
            [
                "application-runtime|authorization-boundary",
                "engine-runtime|verifier-boundary",
            ],
            result["summary"]["class_pairs"],
        )
        self.assertEqual(
            {
                "EXACT_SELECTOR_DUPLICATE": 1,
                "LITERAL_PREFIX_RECURSIVE_SUBSUMPTION": 7,
            },
            result["summary"]["relation_histogram"],
        )
        exact = [item for item in result["findings"] if item["relation"] == "EXACT_SELECTOR_DUPLICATE"]
        self.assertEqual(1, len(exact))
        self.assertEqual("tools/**", exact[0]["selector_a"])
        self.assertEqual("tools/**", exact[0]["selector_b"])

    def test_literal_recursive_prefix_subsumption_is_directional(self):
        policy = _policy(
            {
                "application-runtime": _class("application-runtime", ["app/**"]),
                "authorization-boundary": _class(
                    "authorization-boundary",
                    ["app/**/auth/**"],
                    "authorization",
                ),
            }
        )
        result = diagnose_operational_policy_selector_overlaps(policy)

        self.assertEqual(1, result["summary"]["finding_count"])
        finding = result["findings"][0]
        self.assertEqual("LITERAL_PREFIX_RECURSIVE_SUBSUMPTION", finding["relation"])
        self.assertEqual("application-runtime", finding["broad_class"])
        self.assertEqual("app/**", finding["broad_selector"])
        self.assertEqual("authorization-boundary", finding["narrow_class"])
        self.assertEqual("app/**/auth/**", finding["narrow_selector"])
        self.assertTrue(finding["proven_overlap"])

    def test_arbitrary_glob_intersection_is_deliberately_not_claimed(self):
        policy = _policy(
            {
                "left": _class("left", ["app/*/auth/**"]),
                "right": _class("right", ["app/**/auth/**"]),
            }
        )
        result = diagnose_operational_policy_selector_overlaps(policy)

        self.assertEqual(0, result["summary"]["finding_count"])
        self.assertTrue(result["detection_scope"]["proven_overlap_only"])
        self.assertFalse(result["detection_scope"]["arbitrary_glob_intersection_exhaustive"])

    def test_output_order_and_hash_are_deterministic(self):
        first = diagnose_operational_policy_selector_overlaps(_kbeauty_like_policy())
        second = diagnose_operational_policy_selector_overlaps(_kbeauty_like_policy())
        self.assertEqual(first, second)
        body = {key: value for key, value in first.items() if key != "diagnostic_sha256"}
        self.assertEqual(canonical_json_sha256(body), first["diagnostic_sha256"])
        for finding in first["findings"]:
            finding_body = {key: value for key, value in finding.items() if key != "finding_sha256"}
            self.assertEqual(canonical_json_sha256(finding_body), finding["finding_sha256"])

    def test_policy_provenance_mismatch_fails_closed(self):
        policy = _policy({"application-runtime": _class("application-runtime", ["app/**"])})
        policy["operational_classes"]["application-runtime"]["paths"] = ["other/**"]
        with self.assertRaises(OperationalPolicySelectorOverlapError):
            diagnose_operational_policy_selector_overlaps(policy)

    def test_authority_is_observational_only(self):
        result = diagnose_operational_policy_selector_overlaps(_kbeauty_like_policy())
        self.assertTrue(all(value is False for value in result["authority"].values()))
        self.assertFalse(result["authority"]["policy_defect_inferred"])
        self.assertFalse(result["authority"]["policy_intent_inferred"])
        self.assertFalse(result["authority"]["operational_class_resolution_authorized"])
        self.assertFalse(result["authority"]["policy_change_authorized"])


if __name__ == "__main__":
    unittest.main()

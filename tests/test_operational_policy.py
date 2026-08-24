import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from review_system.io import load_data
from review_system.operational_policy import (
    CONTRACT_VERSION,
    POLICY_AUTHORITY,
    OperationalPolicyError,
    OperationalPolicyVerificationError,
    load_operational_policy,
    normalize_operational_policy_data,
    verify_operational_policy_file,
)
from review_system.paths import asset


def _readiness() -> dict:
    return {
        "policy_id": "thought-drawer-operational",
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


def _policy() -> dict:
    return {
        "schema_version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "project_id": "thought-drawer",
        "policy_authority": POLICY_AUTHORITY,
        "operational_classes": {
            "reminder-runtime": {
                "paths": [
                    "app/src/main/**/*Reminder*",
                    "app/src/main/**/*Worker*",
                ],
                "trust_task_class": "routine_code",
                "required_scenarios": [
                    "process-restart",
                    "duplicate-scheduling",
                    "timezone-change",
                    "reboot-recovery",
                ],
                "required_evidence": ["android-ci"],
                "readiness_policy": _readiness(),
            }
        },
    }


class OperationalPolicyTests(unittest.TestCase):
    def test_loads_normalizes_and_hashes_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "policy.json"
            source.write_text(json.dumps(_policy()), encoding="utf-8")
            path, value = load_operational_policy(source)

        self.assertEqual(path.name, "policy.json")
        self.assertEqual(value["policy_authority"], "PR_BASE_REVISION")
        self.assertEqual(value["operational_classes"]["reminder-runtime"]["trust_task_class"], "routine_code")
        self.assertEqual(
            value["operational_classes"]["reminder-runtime"]["required_evidence"],
            ["android-ci"],
        )
        self.assertNotIn("completed_scenarios", value["operational_classes"]["reminder-runtime"])
        self.assertRegex(value["policy_sha256"], r"^[0-9a-f]{64}$")

    def test_semantic_hash_is_stable_across_ordering(self):
        left = _policy()
        right = deepcopy(left)
        right["operational_classes"]["reminder-runtime"]["paths"].reverse()
        right["operational_classes"]["reminder-runtime"]["required_scenarios"].reverse()
        self.assertEqual(
            normalize_operational_policy_data(left)["policy_sha256"],
            normalize_operational_policy_data(right)["policy_sha256"],
        )

    def test_rejects_head_revision_authority(self):
        value = _policy()
        value["policy_authority"] = "PR_HEAD_REVISION"
        with self.assertRaises(OperationalPolicyVerificationError):
            normalize_operational_policy_data(value)

    def test_rejects_hidden_review_or_outcome_authority_fields(self):
        value = _policy()
        value["human_review_recorded"] = False
        with self.assertRaises(OperationalPolicyVerificationError):
            normalize_operational_policy_data(value)

        value = _policy()
        value["operational_classes"]["reminder-runtime"]["outcome"] = "SAFE"
        with self.assertRaises(OperationalPolicyVerificationError):
            normalize_operational_policy_data(value)

    def test_rejects_unsafe_or_normalized_duplicate_paths(self):
        value = _policy()
        value["operational_classes"]["reminder-runtime"]["paths"] = ["../escape/**"]
        with self.assertRaises(OperationalPolicyError):
            normalize_operational_policy_data(value)

        value = _policy()
        value["operational_classes"]["reminder-runtime"]["paths"] = ["src/**", "src\\**"]
        with self.assertRaises(OperationalPolicyError):
            normalize_operational_policy_data(value)

    def test_rejects_unknown_trust_task_class(self):
        value = _policy()
        value["operational_classes"]["reminder-runtime"]["trust_task_class"] = "reminder-runtime"
        with self.assertRaises(OperationalPolicyVerificationError):
            normalize_operational_policy_data(value)

    def test_operational_schema_tracks_existing_trust_contract(self):
        operational = load_data(asset("schemas/operational-policy.schema.json"))
        trust = load_data(asset("schemas/trust-request.schema.json"))
        self.assertEqual(
            operational["$defs"]["operationalClass"]["properties"]["trust_task_class"]["enum"],
            trust["properties"]["task_class"]["enum"],
        )
        self.assertEqual(
            operational["$defs"]["readinessPolicy"],
            trust["$defs"]["readinessPolicy"],
        )

    def test_verify_file_returns_errors_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "policy.json"
            value = _policy()
            value["policy_authority"] = "CURRENT_HEAD"
            source.write_text(json.dumps(value), encoding="utf-8")
            errors = verify_operational_policy_file(source)

        self.assertTrue(errors)
        self.assertIn("PR_BASE_REVISION", errors[0])


if __name__ == "__main__":
    unittest.main()

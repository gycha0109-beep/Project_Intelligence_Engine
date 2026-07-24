import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from review_system.identity import canonical_json_sha256
from review_system.io import dump_json, dump_yaml, load_data
from review_system.policy_cli import main
from review_system.policy_registry import (
    PolicyRegistryError,
    approve_policy,
    build_policy,
    retire_policy,
    verify_policy_registry_data,
    verify_policy_registry_file,
)
from test_policy_registry import PolicyFixture


def rehash_policy(policy: dict) -> None:
    payload = copy.deepcopy(policy)
    payload.pop("policy_sha256", None)
    policy["policy_sha256"] = canonical_json_sha256(payload)


def rehash_registry(registry: dict) -> None:
    payload = copy.deepcopy(registry)
    payload.pop("registry_sha256", None)
    registry["registry_sha256"] = canonical_json_sha256(payload)


class PolicyRegistryHardeningTests(unittest.TestCase):
    def test_rehashed_event_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            fixture.build_root()
            registry = load_data(fixture.registry)
            event = registry["policies"][0]["events"][0]
            event["actor"] = "attacker"
            event_payload = copy.deepcopy(event)
            event_payload.pop("event_sha256")
            event["event_sha256"] = canonical_json_sha256(event_payload)
            rehash_policy(registry["policies"][0])
            rehash_registry(registry)
            errors = verify_policy_registry_data(registry)
            self.assertTrue(any("event_id mismatch" in error for error in errors))

    def test_parent_cycle_and_active_projection_tamper_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            parent = fixture.activate_root()
            child = fixture.build_child(parent["policy_id"])
            registry = load_data(fixture.registry)
            policy_map = {item["policy_id"]: item for item in registry["policies"]}
            policy_map[parent["policy_id"]]["parent_policy_id"] = child["policy_id"]
            policy_map[child["policy_id"]]["status"] = "ACTIVE"
            rehash_policy(policy_map[parent["policy_id"]])
            rehash_policy(policy_map[child["policy_id"]])
            rehash_registry(registry)
            errors = verify_policy_registry_data(registry)
            self.assertTrue(any("cycle" in error for error in errors))
            self.assertTrue(any("multiple ACTIVE" in error or "lifecycle" in error for error in errors))

    def test_rehashed_registry_and_policy_identity_tamper_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            fixture.build_root()
            registry = load_data(fixture.registry)
            registry["registry_id"] = "policy-registry-forged"
            registry["policies"][0]["policy_id"] = "policy-forged"
            rehash_policy(registry["policies"][0])
            rehash_registry(registry)
            errors = verify_policy_registry_data(registry)
            self.assertIn("registry_id mismatch", errors)
            self.assertTrue(any("policy_id mismatch" in error for error in errors))

    def test_parent_version_must_increase(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            parent = fixture.build_root()
            with self.assertRaisesRegex(PolicyRegistryError, "greater than its parent"):
                build_policy(
                    fixture.registry,
                    project_id="demo",
                    version="0.9.0",
                    rules=fixture.rules_ab,
                    evaluation_report=fixture.report_ab,
                    created_by="builder",
                    created_at="2026-07-24T03:00:00Z",
                    parent_policy_id=parent["policy_id"],
                )

    def test_rehashed_unsafe_report_reference_and_event_projection_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            fixture.activate_root()
            registry = load_data(fixture.registry)
            policy = registry["policies"][0]
            policy["evaluation"]["report"] = "../outside.json"
            policy["approval"]["approved_by"] = "forged"
            duplicate = copy.deepcopy(policy["events"][0])
            duplicate["sequence"] = len(policy["events"]) + 1
            duplicate["previous_event_sha256"] = policy["events"][-1]["event_sha256"]
            base = copy.deepcopy(duplicate)
            base.pop("event_id", None)
            base.pop("event_sha256", None)
            duplicate["event_id"] = f"policy-event-{canonical_json_sha256(base)[:24]}"
            event_payload = copy.deepcopy(duplicate)
            event_payload.pop("event_sha256", None)
            duplicate["event_sha256"] = canonical_json_sha256(event_payload)
            policy["events"].append(duplicate)
            rehash_policy(policy)
            rehash_registry(registry)
            errors = verify_policy_registry_data(registry)
            self.assertTrue(any("unsafe relative path" in error for error in errors))
            self.assertTrue(any("approval does not match" in error for error in errors))
            self.assertTrue(any("BUILT may only" in error for error in errors))

    def test_registry_policy_and_materialized_tamper_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            fixture.activate_root()
            registry = load_data(fixture.registry)
            registry["policies"][0]["ruleset"]["rules"]["rules"][0]["title"] = "Tampered"
            dump_json(fixture.registry, registry)
            errors = verify_policy_registry_file(
                fixture.registry,
                materialized_rules=fixture.materialized,
                verify_evaluation_reports=False,
            )
            self.assertTrue(any("sha256 mismatch" in error for error in errors))

            fixture = PolicyFixture(Path(tmp) / "other")
            fixture.activate_root()
            dump_yaml(fixture.materialized, {"schema_version": "1.0", "rules": []})
            errors = verify_policy_registry_file(
                fixture.registry,
                materialized_rules=fixture.materialized,
            )
            self.assertIn("materialized approved Rule file does not match active Policy", errors)

    def test_atomic_activation_failure_restores_registry_and_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            draft = fixture.build_root()
            dump_yaml(fixture.materialized, {"schema_version": "1.0", "rules": []})
            registry_before = fixture.registry.read_bytes()
            view_before = fixture.materialized.read_bytes()
            real_replace = os.replace
            calls = {"count": 0}

            def flaky_replace(source, target):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("simulated second replace failure")
                return real_replace(source, target)

            with patch("review_system.policy_registry.os.replace", side_effect=flaky_replace):
                with self.assertRaisesRegex(OSError, "second replace"):
                    approve_policy(
                        fixture.registry,
                        draft["policy_id"],
                        approved_by="approver",
                        approved_at="2026-07-24T02:00:00Z",
                        materialized_rules=fixture.materialized,
                    )
            self.assertEqual(registry_before, fixture.registry.read_bytes())
            self.assertEqual(view_before, fixture.materialized.read_bytes())

    def test_invalid_semver_future_effective_and_active_retire_without_view_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            with self.assertRaisesRegex(PolicyRegistryError, "semantic version"):
                build_policy(
                    fixture.registry,
                    project_id="demo",
                    version="v1",
                    rules=fixture.rules_a,
                    evaluation_report=fixture.report_a,
                    created_by="builder",
                    created_at="2026-07-24T01:00:00Z",
                )
            draft = fixture.build_root()
            with self.assertRaisesRegex(PolicyRegistryError, "future effective_at"):
                approve_policy(
                    fixture.registry,
                    draft["policy_id"],
                    approved_by="approver",
                    approved_at="2026-07-24T02:00:00Z",
                    effective_at="2026-07-25T02:00:00Z",
                    materialized_rules=fixture.materialized,
                )
            active = approve_policy(
                fixture.registry,
                draft["policy_id"],
                approved_by="approver",
                approved_at="2026-07-24T02:00:00Z",
                materialized_rules=fixture.materialized,
            )
            with self.assertRaisesRegex(PolicyRegistryError, "requires materialized_rules"):
                retire_policy(
                    fixture.registry,
                    active["policy_id"],
                    retired_by="operator",
                    retired_at="2026-07-24T03:00:00Z",
                    reason="No longer active.",
                )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_symlink_registry_and_materialized_targets_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = PolicyFixture(root / "fixture")
            outside = root / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            registry_link = root / "registry-link.json"
            try:
                registry_link.symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(PolicyRegistryError, "symlink"):
                build_policy(
                    registry_link,
                    project_id="demo",
                    version="1.0.0",
                    rules=fixture.rules_a,
                    evaluation_report=fixture.report_a,
                    created_by="builder",
                    created_at="2026-07-24T01:00:00Z",
                )

    def test_cli_build_verify_list_show_compare_and_verification_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "build",
                        "--registry", str(fixture.registry),
                        "--project-id", "demo",
                        "--version", "1.0.0",
                        "--rules", str(fixture.rules_a),
                        "--evaluation-report", str(fixture.report_a),
                        "--created-by", "builder",
                        "--created-at", "2026-07-24T01:00:00Z",
                    ]
                )
            self.assertEqual(0, code)
            policy_id = json.loads(stdout.getvalue())["policy_id"]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["list", "--registry", str(fixture.registry)]))
                self.assertEqual(0, main(["show", "--registry", str(fixture.registry), "--policy-id", policy_id]))
                self.assertEqual(
                    0,
                    main(
                        [
                            "approve",
                            "--registry", str(fixture.registry),
                            "--policy-id", policy_id,
                            "--approved-by", "approver",
                            "--approved-at", "2026-07-24T02:00:00Z",
                            "--materialized-rules", str(fixture.materialized),
                        ]
                    ),
                )
                self.assertEqual(
                    0,
                    main(
                        [
                            "verify",
                            "--registry", str(fixture.registry),
                            "--materialized-rules", str(fixture.materialized),
                        ]
                    ),
                )
            data = load_data(fixture.registry)
            data["registry_sha256"] = "0" * 64
            dump_json(fixture.registry, data)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(4, main(["verify", "--registry", str(fixture.registry)]))


if __name__ == "__main__":
    unittest.main()

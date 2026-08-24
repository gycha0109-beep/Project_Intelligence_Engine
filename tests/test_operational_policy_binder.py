from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import yaml

from review_system.operational_policy_binder import (
    OperationalPolicyBindingError,
    bind_operational_policy,
    verify_operational_policy_binding_data,
)
from review_system.trust import load_trust_request


HEAD = "a" * 40
BASE = "d" * 40
BLOB = "e" * 40


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


def _policy(*, ambiguous: bool = False, no_match: bool = False) -> dict:
    path = "other/**" if no_match else "src/runtime/**"
    classes = {
        "runtime": {
            "paths": [path],
            "trust_task_class": "routine_code",
            "required_scenarios": ["process-restart"],
            "required_evidence": ["ci"],
            "readiness_policy": _readiness(),
        }
    }
    if ambiguous:
        classes["runtime-secondary"] = {
            "paths": ["src/**"],
            "trust_task_class": "routine_code",
            "required_scenarios": ["process-restart"],
            "required_evidence": ["ci"],
            "readiness_policy": _readiness(),
        }
    return {
        "schema_version": "1.0",
        "contract_version": "PIE_OPERATIONAL_POLICY_V1",
        "project_id": "demo",
        "policy_authority": "PR_BASE_REVISION",
        "operational_classes": classes,
    }


def _candidate() -> dict:
    return {
        "candidate_id": "github-capture-test",
        "project_id": "demo",
        "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
        "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
        "task_id": "github-pr:test",
        "changed_files": ["src/runtime/job.py"],
        "blockers": [
            "TRUST_READINESS_POLICY_REQUIRED",
            "TRUST_REPLAY_EVIDENCE_REQUIRED",
            "TRUST_ROLLBACK_EVIDENCE_REQUIRED",
            "TRUST_SCENARIOS_REQUIRED",
            "TRUST_TASK_CLASS_REQUIRED",
        ],
        "request_scaffold": {
            "schema_version": "1.0",
            "task_id": "github-pr:test",
            "source_revision": HEAD,
            "task_class": None,
            "changed_files": ["src/runtime/job.py"],
            "required_scenarios": None,
            "completed_scenarios": None,
            "repository_match": True,
            "head_match": True,
            "rollback_evidence": None,
            "replay_evidence": None,
            "readiness_policy": None,
        },
    }


class _CLI:
    def __init__(self, policy: dict | None):
        self.policy = policy
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments, *, cwd=None, check=True):
        args = tuple(str(value) for value in arguments)
        self.calls.append(args)
        if self.policy is None:
            return SimpleNamespace(returncode=1, stdout="", stderr="HTTP 404: Not Found")
        raw = yaml.safe_dump(self.policy, sort_keys=False).encode("utf-8")
        body = {
            "type": "file",
            "sha": BLOB,
            "encoding": "base64",
            "content": base64.b64encode(raw).decode("ascii"),
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(body), stderr="")


def _facts(
    path: Path,
    *,
    revision: str = HEAD,
    verified_evidence=None,
    completed_scenarios=None,
    rollback=False,
    replay=False,
) -> Path:
    value = {
        "schema_version": "1.0",
        "contract_version": "PIE_OPERATIONAL_TRUST_FACTS_V1",
        "project_id": "demo",
        "source_revision": "git:" + revision,
        "completed_scenarios": ["process-restart"] if completed_scenarios is None else completed_scenarios,
        "verified_evidence": ["ci"] if verified_evidence is None else verified_evidence,
        "rollback_evidence": rollback,
        "replay_evidence": replay,
        "provided_by": "operator",
        "provided_at": "2026-08-24T09:00:00Z",
    }
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


class OperationalPolicyBinderTests(unittest.TestCase):
    def _bind(self, root: Path, cli: _CLI, **kwargs):
        candidate_path = root / "candidate.json"
        candidate_path.write_text("{}\n", encoding="utf-8")
        with patch(
            "review_system.operational_policy_binder.load_github_prospective_capture_candidate",
            return_value=(candidate_path, _candidate()),
        ):
            return bind_operational_policy(
                candidate_path,
                github_cli=cli,
                repository_root=root,
                **kwargs,
            )

    def test_unique_match_reads_policy_from_exact_pr_base_and_stops_on_missing_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = _CLI(_policy())
            result = self._bind(root, cli)
            self.assertEqual("UNIQUE_POLICY_MATCH", result["match_status"])
            self.assertEqual("MISSING_TRUST_FIELDS", result["status"])
            self.assertEqual("git:" + BASE, result["policy"]["policy_revision"])
            self.assertEqual(BLOB, result["policy"]["policy_blob_sha"])
            self.assertIn(f"ref={BASE}", cli.calls[0][-1])
            self.assertIn("completed_scenarios", result["missing_inputs"])
            self.assertIn("required_evidence:ci", result["missing_inputs"])
            self.assertFalse(result["human_review_recorded"])
            self.assertFalse(result["outcome_recorded"])
            self.assertFalse(result["merge_authorized"])
            self.assertEqual([], verify_operational_policy_binding_data(result))

    def test_missing_base_policy_fails_closed_without_using_head_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".review" / "operational").mkdir(parents=True)
            (root / ".review" / "operational" / "policy.yml").write_text(
                yaml.safe_dump(_policy(), sort_keys=False),
                encoding="utf-8",
            )
            cli = _CLI(None)
            result = self._bind(root, cli)
            self.assertEqual("NO_POLICY_MATCH", result["status"])
            self.assertFalse(result["policy"]["available"])
            self.assertIn("OPERATIONAL_POLICY_NOT_FOUND_AT_BASE", result["missing_inputs"])
            self.assertIn(f"ref={BASE}", cli.calls[0][-1])

    def test_invalid_base_policy_is_normalized_to_binding_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = _policy()
            invalid["policy_authority"] = "PR_HEAD_REVISION"
            with self.assertRaises(OperationalPolicyBindingError) as caught:
                self._bind(root, _CLI(invalid))
            self.assertEqual("POLICY_SOURCE_INVALID", caught.exception.code)

    def test_ambiguous_match_is_not_auto_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._bind(root, _CLI(_policy(ambiguous=True)))
            self.assertEqual("AMBIGUOUS_POLICY_MATCH", result["match_status"])
            self.assertEqual("AMBIGUOUS_POLICY_MATCH", result["status"])
            self.assertIsNone(result["selected_operational_class"])
            self.assertFalse(result["trust_request"]["materialized"])

    def test_no_class_match_stays_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._bind(root, _CLI(_policy(no_match=True)))
            self.assertEqual("NO_POLICY_MATCH", result["match_status"])
            self.assertEqual("NO_POLICY_MATCH", result["status"])
            self.assertIn("NO_OPERATIONAL_CLASS_MATCH", result["missing_inputs"])

    def test_required_evidence_cannot_disappear_during_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = _facts(root / "facts.yml", verified_evidence=[])
            result = self._bind(root, _CLI(_policy()), trust_facts=facts)
            self.assertEqual("MISSING_TRUST_FIELDS", result["status"])
            self.assertIn("required_evidence:ci", result["missing_inputs"])
            self.assertFalse(result["trust_request"]["materialized"])

    def test_stale_explicit_facts_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = _facts(root / "facts.yml", revision="b" * 40)
            with self.assertRaises(OperationalPolicyBindingError) as caught:
                self._bind(root, _CLI(_policy()), trust_facts=facts)
            self.assertEqual("STALE_TRUST_FACTS", caught.exception.code)

    def test_undeclared_completed_scenario_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = _facts(root / "facts.yml", completed_scenarios=["process-restart", "invented-scenario"])
            with self.assertRaises(OperationalPolicyBindingError) as caught:
                self._bind(root, _CLI(_policy()), trust_facts=facts)
            self.assertEqual("TRUST_FACTS_INVALID", caught.exception.code)

    def test_complete_explicit_facts_materialize_existing_trust_request_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = _facts(root / "facts.yml", rollback=False, replay=False)
            request = root / "trust-request.json"
            snapshot = root / "base-policy.yml"
            result = self._bind(
                root,
                _CLI(_policy()),
                trust_facts=facts,
                trust_request_output=request,
                policy_snapshot_output=snapshot,
            )
            self.assertEqual("TRUST_REQUEST_MATERIALIZED", result["status"])
            self.assertTrue(result["trust_request"]["materialized"])
            self.assertTrue(snapshot.is_file())
            _source, normalized = load_trust_request(request)
            self.assertEqual("routine_code", normalized["task_class"])
            self.assertEqual(["process-restart"], normalized["required_scenarios"])
            self.assertEqual(["process-restart"], normalized["completed_scenarios"])
            self.assertFalse(normalized["rollback_evidence"])
            self.assertFalse(normalized["replay_evidence"])
            self.assertEqual("git:" + HEAD, normalized["source_revision"])
            self.assertEqual(result["trust_request"]["request_sha256"], normalized["request_sha256"])
            self.assertFalse(result["automation_authorized"])
            self.assertFalse(result["pilot_authorized"])

    def test_same_inputs_produce_same_binding_hash_independent_of_output_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = _facts(root / "facts.yml")
            candidate_path = root / "candidate.json"
            candidate_path.write_text("{}\n", encoding="utf-8")
            with patch(
                "review_system.operational_policy_binder.load_github_prospective_capture_candidate",
                return_value=(candidate_path, _candidate()),
            ):
                first = bind_operational_policy(
                    candidate_path,
                    github_cli=_CLI(_policy()),
                    repository_root=root,
                    trust_facts=facts,
                    trust_request_output=root / "one.json",
                )
                second = bind_operational_policy(
                    candidate_path,
                    github_cli=_CLI(_policy()),
                    repository_root=root,
                    trust_facts=facts,
                    trust_request_output=root / "two.json",
                )
            self.assertNotEqual(first["trust_request"]["artifact_name"], second["trust_request"]["artifact_name"])
            self.assertEqual(first["binding_sha256"], second["binding_sha256"])
            self.assertEqual(first["trust_request"]["request_sha256"], second["trust_request"]["request_sha256"])


if __name__ == "__main__":
    unittest.main()

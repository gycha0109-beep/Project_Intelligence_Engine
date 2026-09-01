from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from review_system.operational_policy_match_explanation_cli import main


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


def _write_policy(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contract_version": "PIE_OPERATIONAL_POLICY_V1",
                "project_id": "demo",
                "policy_authority": "PR_BASE_REVISION",
                "operational_classes": {
                    "application-runtime": _class(["app/**"]),
                    "pipeline-runtime": _class(["scripts/**"]),
                },
            }
        ),
        encoding="utf-8",
    )


class OperationalPolicyMatchExplanationCLITests(unittest.TestCase):
    def test_cli_writes_multi_surface_explanation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy = root / "policy.json"
            output = root / "explanation.json"
            _write_policy(policy)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "--policy",
                        str(policy),
                        "--changed-file",
                        "app/page.tsx",
                        "--changed-file",
                        "scripts/verify.sh",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(0, code)
            value = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("MULTI_PATH_MULTI_CLASS", value["ambiguity_mechanism"])
            self.assertFalse(value["authority"]["operational_class_resolution_authorized"])
            self.assertEqual(value, json.loads(stdout.getvalue()))

    def test_cli_fails_closed_on_normalized_duplicate_changed_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy = root / "policy.json"
            _write_policy(policy)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main(
                    [
                        "--policy",
                        str(policy),
                        "--changed-file",
                        "app/page.tsx",
                        "--changed-file",
                        "app\\page.tsx",
                    ]
                )
            self.assertEqual(1, code)
            self.assertIn("normalized duplicates", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

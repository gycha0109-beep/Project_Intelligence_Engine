from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from review_system.github.source import refresh_source_hash
from review_system.identity import canonical_json_sha256
from review_system.io import dump_json
from review_system.trust import (
    BAND_ORDER,
    TRUST_RISK_MODEL_VERSION,
    TrustError,
    _hard_gate_projection,
    _profile_descriptor,
    _risk_projection,
    assess_trust,
    verify_trust_report_data,
    verify_trust_report_sources,
)
from review_system.trust_workflow_authority import build_trust_workflow_evidence
from review_system.workflow_semantics import build_workflow_diff_evidence
from test_trust_gate import TrustReadinessFixture


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "trust-risk-calibration"
SEEN = FIXTURE_DIR / "wave1-seen-baseline.json"
SEEN_WORKFLOW = FIXTURE_DIR / "workflow-semantic-bridge-d1-seen-v1.json"
HOLDOUT = FIXTURE_DIR / "wave1-holdout-shadow-predictions.json"
HOLDOUT_LABELS = FIXTURE_DIR / "wave1-holdout-adjudication.json"

PROFILE_PATHS = {
    "buildmap": ROOT / "profiles" / "examples" / "buildmap.yml",
    "bejewely": ROOT / "profiles" / "examples" / "bejewely.yml",
    "generic-webapp": ROOT / "profiles" / "examples" / "generic-webapp.yml",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def wrapped_semantics(
    *,
    source_revision: str,
    changed_files: list[str],
    diff_text: str,
    source_evidence_sha256: str,
) -> dict:
    semantics = build_workflow_diff_evidence(
        source_revision=source_revision,
        source_evidence_sha256=source_evidence_sha256,
        changed_files=changed_files,
        diff_text=diff_text,
    )
    projection = {
        "schema_version": "1.0",
        "repository_hostname": "github.com",
        "repository_name_with_owner": "calibration/fixture",
        "pull_request_number": 1,
        "semantics": semantics,
    }
    return {**projection, "evidence_sha256": canonical_json_sha256(projection)}


def holdout_semantics(item: dict) -> dict | None:
    entries = item["workflow_semantics"]
    if not entries:
        return None
    hashes = {entry["source_evidence_sha256"] for entry in entries}
    if len(hashes) != 1:
        raise AssertionError("workflow semantics must share one source evidence hash")
    sections = []
    for entry in entries:
        path = entry["path"]
        sections.append(
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            f"{entry['patch']}\n"
        )
    return wrapped_semantics(
        source_revision=item["frozen_head_sha"],
        changed_files=item["changed_files"],
        diff_text="".join(sections),
        source_evidence_sha256=next(iter(hashes)),
    )


def github_source_for(*, revision: str, changed_files: list[str], diff_text: str) -> dict:
    encoded = diff_text.encode("utf-8")
    source = {
        "schema_version": "1.0",
        "source": "github-cli",
        "retrieved_at": "2026-08-21T00:00:00Z",
        "repository": {
            "hostname": "github.com",
            "name_with_owner": "example/demo",
            "gh_repo_argument": "example/demo",
        },
        "pull_request": {
            "number": 1,
            "head_oid": revision,
            "changed_files": [{"path": path} for path in sorted(changed_files)],
        },
        "diff": {
            "requested": True,
            "available": True,
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        },
        "discussion": {},
        "warnings": [],
    }
    refresh_source_hash(source)
    return source


class TrustAuthoritativeRiskPromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.seen = load_json(SEEN)
        cls.seen_workflow = load_json(SEEN_WORKFLOW)
        cls.holdout = load_json(HOLDOUT)
        cls.holdout_labels = load_json(HOLDOUT_LABELS)
        cls.profiles = {
            key: _profile_descriptor(path)[1]
            for key, path in PROFILE_PATHS.items()
        }
        cls.seen_workflow_by_id = {
            item["sample_id"]: item for item in cls.seen_workflow["cases"]
        }
        cls.holdout_labels_by_id = {
            item["sample_id"]: item for item in cls.holdout_labels["samples"]
        }

    def test_documentation_precedence_preserves_executable_and_r4_floors(self) -> None:
        profile = self.profiles["generic-webapp"]
        cases = {
            "docs/evidence/execution-authorization-record.md": "R1",
            "security-authorization-notes.md": "R1",
            "src/auth/security.py": "R3",
            "supabase/migrations/202608210001.sql": "R3",
            "docs/policies/access-control.md": "R4",
            "src/review_system/trust.py": "R4",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                result = _risk_projection(
                    {"task_class": "documentation" if path.endswith(".md") else "routine_code", "changed_files": [path]},
                    profile,
                )
                self.assertEqual(result["effective_band"], expected)

        legacy = _risk_projection(
            {
                "task_class": "documentation",
                "changed_files": ["docs/evidence/execution-authorization-record.md"],
            },
            profile,
            risk_model_version=None,
        )
        self.assertEqual(legacy["effective_band"], "R3")

    def test_workflow_without_bound_evidence_remains_fail_closed_r3(self) -> None:
        result = _risk_projection(
            {"task_class": "routine_code", "changed_files": [".github/workflows/ci.yml"]},
            self.profiles["generic-webapp"],
        )
        self.assertEqual(result["effective_band"], "R3")
        self.assertIn("HIGH_RISK_PATH", {item["reason_id"] for item in result["reasons"]})

    def test_bound_ci_wiring_can_reduce_only_workflow_floor(self) -> None:
        revision = "a" * 40
        path = ".github/workflows/ci.yml"
        diff_text = (
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n+++ b/{path}\n"
            "@@ -1 +1,2 @@\n"
            " run: npm run test\n"
            "+run: npm run verify:contracts\n"
        )
        source = github_source_for(revision=revision, changed_files=[path], diff_text=diff_text)
        evidence = build_trust_workflow_evidence(
            github_source=source,
            diff_text=diff_text,
            source_revision=revision,
            changed_files=[path],
        )
        result = _risk_projection(
            {"source_revision": revision, "task_class": "routine_code", "changed_files": [path]},
            self.profiles["generic-webapp"],
            evidence,
        )
        self.assertEqual(result["effective_band"], "R2")
        self.assertIn("WORKFLOW_CI_TEST_WIRING_ONLY", {item["reason_id"] for item in result["reasons"]})

    def test_workflow_authority_mutation_remains_r3_and_hard_gated(self) -> None:
        revision = "b" * 40
        path = ".github/workflows/release.yml"
        diff_text = (
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n+++ b/{path}\n"
            "@@ -1 +1,2 @@\n"
            " permissions:\n"
            "+  statuses: write\n"
        )
        source = github_source_for(revision=revision, changed_files=[path], diff_text=diff_text)
        evidence = build_trust_workflow_evidence(
            github_source=source,
            diff_text=diff_text,
            source_revision=revision,
            changed_files=[path],
        )
        request = {"source_revision": revision, "task_class": "routine_code", "changed_files": [path]}
        risk = _risk_projection(request, self.profiles["generic-webapp"], evidence)
        self.assertEqual(risk["effective_band"], "R3")
        self.assertIn("WORKFLOW_AUTHORITY_MUTATION", {item["reason_id"] for item in risk["reasons"]})
        gate_request = {
            **request,
            "required_scenarios": [],
            "completed_scenarios": [],
            "repository_match": True,
            "head_match": True,
            "rollback_evidence": True,
            "replay_evidence": True,
        }
        gates = _hard_gate_projection(
            gate_request,
            risk,
            {"policy": {"policy_evaluation_ready": True}},
        )
        gate = next(item for item in gates if item["gate_id"] == "AUTHORIZATION_OR_MIGRATION_CHANGE")
        self.assertTrue(gate["triggered"])
        self.assertIn(path, gate["details"])

    def test_raw_source_binding_rejects_head_changed_files_and_diff_tamper(self) -> None:
        revision = "c" * 40
        path = ".github/workflows/ci.yml"
        diff_text = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n+run: npm run test\n"
        source = github_source_for(revision=revision, changed_files=[path], diff_text=diff_text)

        with self.assertRaisesRegex(ValueError, "head revision"):
            build_trust_workflow_evidence(
                github_source=source,
                diff_text=diff_text,
                source_revision="d" * 40,
                changed_files=[path],
            )
        with self.assertRaisesRegex(ValueError, "changed files"):
            build_trust_workflow_evidence(
                github_source=source,
                diff_text=diff_text,
                source_revision=revision,
                changed_files=[path, "src/extra.py"],
            )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_trust_workflow_evidence(
                github_source=source,
                diff_text=diff_text + "\n",
                source_revision=revision,
                changed_files=[path],
            )

    def test_assess_and_source_replay_bind_raw_github_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = TrustReadinessFixture(root)
            revision = "a" * 40
            path = ".github/workflows/ci.yml"
            fixture.write_request(task_class="routine_code", changed_files=[path])
            diff_text = (
                f"diff --git a/{path} b/{path}\n"
                f"--- a/{path}\n+++ b/{path}\n"
                "+run: npm run verify:trust\n"
            )
            source = github_source_for(revision=revision, changed_files=[path], diff_text=diff_text)
            source_path = root / "github-source.json"
            diff_path = root / "pull-request.diff"
            dump_json(source_path, source)
            diff_path.write_text(diff_text, encoding="utf-8")

            report = assess_trust(
                fixture.request,
                fixture.profile,
                ledger=fixture.reground_fixture.ledger,
                policy_registry=fixture.policy_registry,
                evaluation_report=fixture.evaluation_report,
                reground_report=fixture.reground_report,
                reground_observations=fixture.observations,
                github_source=source_path,
                workflow_diff=diff_path,
                generated_at="2026-07-25T02:00:00Z",
            )
            self.assertEqual(report["risk_model_version"], TRUST_RISK_MODEL_VERSION)
            self.assertEqual(report["risk"]["effective_band"], "R2")
            self.assertIn("workflow_diff", report["evidence"])
            self.assertEqual([], verify_trust_report_data(report))
            self.assertEqual(
                [],
                verify_trust_report_sources(
                    report,
                    **fixture.source_args(),
                    github_source=source_path,
                    workflow_diff=diff_path,
                ),
            )

            diff_path.write_text(diff_text + "\n", encoding="utf-8")
            replay_errors = verify_trust_report_sources(
                report,
                **fixture.source_args(),
                github_source=source_path,
                workflow_diff=diff_path,
            )
            self.assertTrue(replay_errors)
            self.assertIn("SHA-256", " ".join(replay_errors))

    def test_assess_rejects_partial_workflow_source_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TrustReadinessFixture(Path(tmp))
            with self.assertRaisesRegex(TrustError, "both GitHub source and workflow diff"):
                assess_trust(
                    fixture.request,
                    fixture.profile,
                    github_source=fixture.request,
                )

    def test_authoritative_wave1_replay_is_34_of_34_acceptable_zero_underclassification(self) -> None:
        seen_evidence: dict[str, dict] = {}
        for sample_id, case in self.seen_workflow_by_id.items():
            seen_evidence[sample_id] = wrapped_semantics(
                source_revision=case["source_revision"],
                changed_files=case["changed_files"],
                diff_text=case["diff_text"],
                source_evidence_sha256=case["source_evidence_sha256"],
            )

        seen_acceptable = seen_exact = 0
        under: list[str] = []
        observed: dict[str, str] = {}
        for item in self.seen["samples"]:
            request = {"task_class": item["task_class"], "changed_files": item["changed_files"]}
            evidence = seen_evidence.get(item["sample_id"])
            if evidence is not None:
                request["source_revision"] = self.seen_workflow_by_id[item["sample_id"]]["source_revision"]
            result = _risk_projection(request, self.profiles[item["profile_basis"]], evidence)
            band = result["effective_band"]
            observed[item["sample_id"]] = band
            seen_acceptable += int(band in item["acceptable_bands"])
            seen_exact += int(band == item["expected_band"])
            if BAND_ORDER[band] < BAND_ORDER[item["expected_band"]]:
                under.append(item["sample_id"])

        holdout_acceptable = holdout_exact = 0
        for item in self.holdout["predictions"]:
            expected = self.holdout_labels_by_id[item["sample_id"]]
            request = {
                "source_revision": item["frozen_head_sha"],
                "task_class": item["task_class"],
                "changed_files": item["changed_files"],
            }
            result = _risk_projection(
                request,
                self.profiles[item["profile_basis"]],
                holdout_semantics(item),
            )
            band = result["effective_band"]
            observed[item["sample_id"]] = band
            holdout_acceptable += int(band in expected["acceptable_bands"])
            holdout_exact += int(band == expected["expected_band"])
            if BAND_ORDER[band] < BAND_ORDER[expected["expected_band"]]:
                under.append(item["sample_id"])

        self.assertEqual(seen_acceptable, 23)
        self.assertEqual(seen_exact, 22)
        self.assertEqual(holdout_acceptable, 11)
        self.assertEqual(holdout_exact, 11)
        self.assertEqual(seen_acceptable + holdout_acceptable, 34)
        self.assertEqual(seen_exact + holdout_exact, 33)
        self.assertEqual(under, [])
        self.assertEqual(observed["RW-54"], "R2")
        self.assertEqual(observed["RW-57"], "R2")
        self.assertEqual(observed["KB-269"], "R3")
        self.assertEqual(observed["KB-275"], "R3")
        self.assertEqual(observed["KB-274"], "R1")


if __name__ == "__main__":
    unittest.main()

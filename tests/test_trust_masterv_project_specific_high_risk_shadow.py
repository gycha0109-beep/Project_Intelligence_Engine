from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from review_system.github.source import refresh_source_hash
from review_system.trust import TRUST_RISK_MODEL_VERSION, _profile_descriptor, _risk_projection
from review_system.trust_project_specific_high_risk_shadow import (
    CONTRACT_VERSION,
    audit_high_risk_case,
)
from review_system.trust_r4_semantics_authority import build_trust_r4_semantic_evidence
from review_system.trust_workflow_authority import build_trust_workflow_evidence


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trust-risk-calibration" / "masterv-project-specific-high-risk-shadow-v1.json"
PROFILE = ROOT / "profiles" / "examples" / "generic-webapp.yml"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def diff_section(path: str, excerpt: str) -> str:
    lines = excerpt.splitlines() or [""]
    additions = "\n".join(f"+{line}" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{additions}\n"
    )


def bounded_diff(case: dict) -> str:
    return "".join(diff_section(item["path"], item["excerpt"]) for item in case["files"])


def github_source(case: dict, diff_text: str, *, repository: str | None = None) -> dict:
    encoded = diff_text.encode("utf-8")
    source = {
        "schema_version": "1.0",
        "source": "github-cli",
        "retrieved_at": "2026-08-22T01:00:00Z",
        "repository": {
            "hostname": "github.com",
            "name_with_owner": repository or case["repository"],
            "gh_repo_argument": repository or case["repository"],
        },
        "pull_request": {
            "number": case["pull_request"],
            "head_oid": case["head_sha"],
            "changed_files": [{"path": item["path"]} for item in sorted(case["files"], key=lambda item: item["path"])],
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


def bound_evidence(case: dict, *, repository: str | None = None) -> tuple[dict | None, dict]:
    diff_text = bounded_diff(case)
    source = github_source(case, diff_text, repository=repository)
    changed_files = [item["path"] for item in case["files"]]
    workflow = None
    if any(path.startswith(".github/workflows/") for path in changed_files):
        workflow = build_trust_workflow_evidence(
            github_source=source,
            diff_text=diff_text,
            source_revision=case["head_sha"],
            changed_files=changed_files,
        )
    r4 = build_trust_r4_semantic_evidence(
        github_source=source,
        diff_text=diff_text,
        source_revision=case["head_sha"],
        changed_files=changed_files,
    )
    return workflow, r4


class TrustMasterVProjectSpecificHighRiskShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture()
        cls.profile = _profile_descriptor(PROFILE)[1]
        cls.cases = {case["case_id"]: case for case in cls.fixture["cases"]}

    def audit(self, case: dict, *, repository: str | None = None) -> dict:
        workflow, r4 = bound_evidence(case, repository=repository)
        request = {
            "source_revision": case["head_sha"],
            "task_class": case["task_class"],
            "changed_files": [item["path"] for item in case["files"]],
        }
        return audit_high_risk_case(
            request,
            self.profile,
            expected_band=case["policy_expected_band"],
            workflow_evidence=workflow,
            r4_semantic_evidence=r4,
        )

    def test_contract_is_shadow_only_and_current_authority_is_v13(self) -> None:
        self.assertEqual(TRUST_RISK_MODEL_VERSION, "1.3")
        self.assertEqual(self.fixture["contract_version"], CONTRACT_VERSION)
        ceiling = self.fixture["authority_ceiling"]
        self.assertTrue(ceiling["shadow_only"])
        self.assertFalse(ceiling["automation_authorized"])
        self.assertFalse(ceiling["pilot_authorized"])
        self.assertFalse(ceiling["authoritative_remediation_authorized"])
        self.assertFalse(ceiling["blind_holdout_claim"])

    def test_mv3_known_wave1_signing_anchor_reproduces_r3_blind_spot(self) -> None:
        case = self.cases["MV-3-SEEN-SIGNING-TRUST-ROOT"]
        result = self.audit(case)
        self.assertEqual(result["current_band"], case["expected_current_band"])
        self.assertEqual(result["outcome"], case["expected_outcome"])
        self.assertEqual(result["expected_band"], "R3")
        self.assertNotIn(
            "SEMANTIC_R4_AUTHORITY",
            {item["reason_id"] for item in result["current_risk"]["reasons"]},
        )

    def test_mv5_release_context_negative_control_remains_r2(self) -> None:
        case = self.cases["MV-5-POST-WAVE1-RELEASE-CONTEXT-NEGATIVE"]
        result = self.audit(case)
        self.assertEqual(result["current_band"], "R2")
        self.assertEqual(result["outcome"], "MATCH")

    def test_mv7_post_wave1_verifier_authority_is_underclassified(self) -> None:
        case = self.cases["MV-7-POST-WAVE1-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER"]
        workflow, r4 = bound_evidence(case)
        workflow_classes = {item["classification"] for item in workflow["semantics"]["workflows"]}
        self.assertIn("UNKNOWN", workflow_classes)
        verifier_analysis = next(
            item for item in r4["semantics"]["files"]
            if item["path"] == "scripts/desktop-rel-1c-published-updater-windows.mjs"
        )
        self.assertEqual(verifier_analysis["classification"], "SUPPORTING_REGRESSION_ONLY")
        self.assertFalse(verifier_analysis["is_r4_authority"])

        result = self.audit(case)
        self.assertEqual(result["current_band"], case["expected_current_band"])
        self.assertEqual(result["outcome"], "UNDERCLASSIFIED")
        self.assertEqual(result["expected_band"], "R4")

    def test_mv12_latent_production_boundary_paths_are_r2_under_current_v13(self) -> None:
        for case_id in (
            "MV-12-PATH-PRODUCTION-DEPLOYMENT-SURFACE",
            "MV-12-PATH-LEGACY-PROVIDER-ROUTE-GUARD",
        ):
            with self.subTest(case_id=case_id):
                case = self.cases[case_id]
                result = self.audit(case)
                self.assertEqual(result["current_band"], "R2")
                self.assertEqual(result["expected_band"], "R3")
                self.assertEqual(result["outcome"], "UNDERCLASSIFIED")

    def test_audit_does_not_depend_on_masterv_repository_name(self) -> None:
        for case_id in (
            "MV-3-SEEN-SIGNING-TRUST-ROOT",
            "MV-7-POST-WAVE1-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER",
            "MV-12-PATH-PRODUCTION-DEPLOYMENT-SURFACE",
        ):
            with self.subTest(case_id=case_id):
                case = self.cases[case_id]
                masterv = self.audit(case)
                neutral = self.audit(case, repository="neutral/example")
                self.assertEqual(masterv["current_risk"], neutral["current_risk"])
                self.assertEqual(masterv["outcome"], neutral["outcome"])

    def test_all_fixture_expectations_match_current_projection(self) -> None:
        observed = {}
        for case in self.fixture["cases"]:
            result = self.audit(case)
            observed[case["case_id"]] = {
                "current_band": result["current_band"],
                "outcome": result["outcome"],
            }
            self.assertEqual(result["current_band"], case["expected_current_band"])
            self.assertEqual(result["outcome"], case["expected_outcome"])
        self.assertEqual(
            sum(item["outcome"] == "UNDERCLASSIFIED" for item in observed.values()),
            4,
        )


if __name__ == "__main__":
    unittest.main()

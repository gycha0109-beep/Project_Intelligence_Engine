from pathlib import Path
import tempfile
import unittest

from review_system.io import dump_json
from review_system.trust import assess_trust, verify_trust_report_data, verify_trust_report_sources


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "examples" / "buildmap.yml"
PR65 = [
    "apps/web/app/settings/integrations/github-integration-actions.ts",
    "apps/web/docs/access-policy-tests/phase-2-provider-connection-acceptance.md",
    "apps/web/lib/notion/api.ts",
    "apps/web/lib/notion/resource.ts",
]
PR66 = [
    "apps/web/docs/implementation/phase-2-p5-production-readiness-status.md",
]
PR67 = [
    ".github/workflows/web-phase2-operation.yml",
    "apps/web/.env.example",
    "apps/web/README.md",
    "apps/web/app/api/health/route.ts",
    "apps/web/app/decisions/[decisionId]/page.tsx",
    "apps/web/app/page.tsx",
    "apps/web/components/app-shell.tsx",
    "apps/web/docs/implementation/phase-2-evidence-closure-status.md",
    "apps/web/docs/implementation/phase-2-f5-state-mutation-proof.md",
    "apps/web/docs/implementation/phase-2-f6-queue-snapshot-proof.md",
    "apps/web/docs/implementation/phase-2-f8-rollback-proof.md",
    "apps/web/docs/implementation/phase-2-w11-editorial-proof.md",
    "apps/web/docs/implementation/phase-2-w2-primary-action-name-proof.md",
    "apps/web/docs/implementation/phase-2-w3-primary-action-body-proof.md",
    "apps/web/docs/implementation/phase-2-w4-primary-action-links-proof.md",
    "apps/web/docs/implementation/phase-2-w6-return-context-proof.md",
    "apps/web/docs/implementation/phase-2-w8-notion-context-proof.md",
    "apps/web/docs/implementation/phase-3-operational-activation-plan.md",
    "apps/web/lib/server/decision-queries.ts",
    "apps/web/lib/server/decisions.ts",
    "apps/web/lib/server/migrations/0004_operational_control_plane.sql",
    "apps/web/lib/server/proof-targets.ts",
    "apps/web/package.json",
    "apps/web/vercel.json",
]
SYNTHETIC_AUTH_RLS = [
    "apps/web/lib/provider/api-client.ts",
    "apps/web/lib/provider/supabase-access.ts",
]


def readiness_policy():
    return {
        "policy_id": "buildmap-corroboration-regression-v1",
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


class BuildMapTaskClassCorroborationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.counter = 0

    def assess(self, files, task_class, revision, *, include_corroboration=True):
        self.counter += 1
        request = self.root / f"request-{self.counter}.json"
        dump_json(
            request,
            {
                "schema_version": "1.0",
                "task_id": f"buildmap-corroboration-{self.counter}",
                "source_revision": "git:" + revision,
                "task_class": task_class,
                "changed_files": files,
                "required_scenarios": ["current_ci"],
                "completed_scenarios": ["current_ci"],
                "repository_match": True,
                "head_match": True,
                "rollback_evidence": True,
                "replay_evidence": True,
                "readiness_policy": readiness_policy(),
            },
        )
        report = assess_trust(
            request,
            PROFILE,
            generated_at="2026-08-21T00:00:00Z",
            _include_corroboration=include_corroboration,
        )
        return request, report

    def assert_source_replay(self, request, report):
        self.assertEqual([], verify_trust_report_data(report))
        self.assertEqual(
            [],
            verify_trust_report_sources(report, request=request, profile=PROFILE),
        )

    def test_buildmap_pr66_docs_only_stays_r1(self):
        request, report = self.assess(
            PR66,
            "documentation",
            "b498ad0b7068b848c89ce3641b37c688f58b842e",
        )
        risk = report["risk"]
        self.assertEqual("R1", risk["path_floor_band"])
        self.assertEqual("R0", risk["corroborated_semantic_floor_band"])
        self.assertEqual("R1", risk["effective_band"])
        self.assertFalse(risk["task_class_underdeclared"])
        self.assert_source_replay(request, report)

    def test_buildmap_pr65_provider_change_is_not_promoted_by_docs_only_rls(self):
        request, report = self.assess(
            PR65,
            "routine_code",
            "d22f84f1bf58350f208e305472522cde7602dc44",
        )
        risk = report["risk"]
        self.assertEqual("R2", risk["path_floor_band"])
        self.assertIn("application.authorization", risk["selected_review_packs"])
        self.assertIn("data.rls", risk["selected_review_packs"])
        self.assertEqual("R0", risk["corroborated_semantic_floor_band"])
        self.assertEqual("R2", risk["effective_band"])
        self.assertFalse(risk["task_class_underdeclared"])
        self.assertFalse(
            any(
                item["reason_id"] == "REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS"
                for item in risk["reasons"]
            )
        )
        self.assert_source_replay(request, report)

    def test_buildmap_pr67_control_plane_stays_r3(self):
        request, report = self.assess(
            PR67,
            "routine_code",
            "64d9785709b8c00d66be3275815269910adf0b94",
        )
        risk = report["risk"]
        self.assertEqual("R3", risk["path_floor_band"])
        self.assertEqual("R3", risk["corroborated_semantic_floor_band"])
        self.assertEqual("R3", risk["effective_band"])
        self.assertTrue(risk["task_class_underdeclared"])
        self.assertTrue(
            any(
                item["reason_id"] == "REVIEW_PACK_CORROBORATION:MIGRATION_SAFETY"
                for item in risk["reasons"]
            )
        )
        self.assert_source_replay(request, report)

    def test_non_documentation_auth_rls_combination_promotes_routine_code(self):
        request, report = self.assess(
            SYNTHETIC_AUTH_RLS,
            "routine_code",
            "1111111111111111111111111111111111111111",
        )
        risk = report["risk"]
        self.assertEqual("R2", risk["path_floor_band"])
        self.assertEqual("R3", risk["corroborated_semantic_floor_band"])
        self.assertEqual("R3", risk["effective_band"])
        self.assertTrue(risk["task_class_underdeclared"])
        self.assertTrue(
            any(
                item["reason_id"] == "REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS"
                for item in risk["reasons"]
            )
        )
        gate = next(
            item
            for item in report["hard_gates"]
            if item["gate_id"] == "AUTHORIZATION_OR_MIGRATION_CHANGE"
        )
        self.assertTrue(gate["triggered"])
        self.assert_source_replay(request, report)

    def test_legacy_report_shape_replays_without_new_optional_fields(self):
        request, report = self.assess(
            PR66,
            "documentation",
            "2222222222222222222222222222222222222222",
            include_corroboration=False,
        )
        self.assertNotIn("configured_review_packs", report["profile"])
        self.assertNotIn("corroborated_semantic_floor_band", report["risk"])
        self.assertNotIn("selected_review_packs", report["risk"])
        self.assertNotIn("task_class_underdeclared", report["risk"])
        self.assert_source_replay(request, report)


if __name__ == "__main__":
    unittest.main()

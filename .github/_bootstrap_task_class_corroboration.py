from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TRUST = ROOT / "src" / "review_system" / "trust.py"
SCHEMAS = [
    ROOT / "schemas" / "trust-report.schema.json",
    ROOT / "src" / "review_system" / "assets" / "schemas" / "trust-report.schema.json",
]
TEST = ROOT / "tests" / "test_buildmap_task_class_corroboration.py"
SELF = ".github/_bootstrap_task_class_corroboration.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def replace_block(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{label}: start anchor missing")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{label}: end anchor missing")
    return text[:start_index] + replacement.rstrip() + text[end_index:]


def patch_trust() -> None:
    text = TRUST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from .path_globs import expand_trailing_recursive_glob\nfrom .paths import asset\n",
        "from .path_globs import expand_trailing_recursive_glob\nfrom .packs import select_packs_with_reasons\nfrom .paths import asset\n",
        "packs import",
    )

    profile = '''def _profile_descriptor(\n    path: str | Path,\n    *,\n    include_corroboration: bool = True,\n) -> tuple[Path, dict[str, Any]]:\n    source = _safe_input_file(path, "Project Profile")\n    profile = resolve_profile_file(source)\n    errors = validate_profile_data(profile)\n    if errors:\n        raise TrustError("invalid Project Profile: " + "; ".join(errors))\n    project = profile.get("project")\n    if not isinstance(project, dict) or not isinstance(project.get("id"), str) or not project["id"].strip():\n        raise TrustError("Project Profile project.id is required")\n    patterns = sorted(\n        {\n            _normalize_glob(value, f"protected_paths[{index}]")\n            for index, value in enumerate(profile.get("protected_paths", []))\n        }\n    )\n    descriptor = {\n        "source": source.name,\n        "project_id": project["id"].strip(),\n        "profile_sha256": canonical_json_sha256(profile),\n        "protected_paths": patterns,\n    }\n    if include_corroboration:\n        review = profile.get("review")\n        packs = review.get("packs", []) if isinstance(review, dict) else []\n        descriptor["configured_review_packs"] = sorted(\n            {value.strip() for value in packs if isinstance(value, str) and value.strip()}\n        )\n    return source, descriptor\n'''
    text = replace_block(
        text,
        "def _profile_descriptor(",
        "\n\ndef _band_max",
        profile,
        "profile descriptor",
    )

    risk = '''def _is_documentation_path(path: str) -> bool:\n    lowered = path.lower()\n    return (\n        lowered.startswith("docs/")\n        or "/docs/" in f"/{lowered}"\n        or PurePosixPath(lowered).suffix in {".md", ".rst", ".adoc"}\n    )\n\n\ndef _review_pack_corroboration(\n    profile: dict[str, Any],\n    changed_files: list[str],\n) -> dict[str, Any] | None:\n    configured = profile.get("configured_review_packs")\n    if not isinstance(configured, list):\n        return None\n    selection = select_packs_with_reasons(changed_files, configured)\n    non_documentation = {\n        pack: sorted(path for path in paths if not _is_documentation_path(path))\n        for pack, paths in selection.items()\n    }\n    reasons: list[dict[str, Any]] = []\n\n    def add_reason(rule_id: str, paths: list[str]) -> None:\n        if paths:\n            reasons.append(\n                {\n                    "reason_id": f"REVIEW_PACK_CORROBORATION:{rule_id}",\n                    "band": "R3",\n                    "paths": sorted(set(paths)),\n                }\n            )\n\n    add_reason(\n        "AUTHENTICATION",\n        non_documentation.get("application.authentication", []),\n    )\n    add_reason(\n        "MIGRATION_SAFETY",\n        [\n            *non_documentation.get("application.migration-safety", []),\n            *non_documentation.get("data.migration-safety", []),\n        ],\n    )\n    authorization_paths = non_documentation.get("application.authorization", [])\n    rls_paths = non_documentation.get("data.rls", [])\n    if authorization_paths and rls_paths:\n        add_reason("AUTHORIZATION_RLS", [*authorization_paths, *rls_paths])\n\n    floor = _band_max("R0", *[item["band"] for item in reasons])\n    return {\n        "floor_band": floor,\n        "selected_review_packs": sorted(selection),\n        "reasons": reasons,\n    }\n\n\ndef _risk_projection(request: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:\n    base_band = TASK_CLASS_BANDS[request["task_class"]]\n    grouped: dict[tuple[str, str], set[str]] = {}\n    path_bands: list[str] = []\n    for path in request["changed_files"]:\n        band, reason_id = _path_classification(path)\n        path_bands.append(band)\n        grouped.setdefault((reason_id, band), set()).add(path)\n    protected = sorted(\n        path\n        for path in request["changed_files"]\n        if any(_matches_pattern(path, pattern) for pattern in profile["protected_paths"])\n    )\n    if protected:\n        path_bands.append("R3")\n        grouped.setdefault(("PROFILE_PROTECTED_PATH", "R3"), set()).update(protected)\n    path_floor = _band_max(*path_bands)\n    reasons = [\n        {\n            "reason_id": f"TASK_CLASS:{request['task_class']}",\n            "band": base_band,\n            "paths": [],\n        },\n        *[\n            {"reason_id": reason_id, "band": band, "paths": sorted(paths)}\n            for (reason_id, band), paths in sorted(\n                grouped.items(),\n                key=lambda item: (BAND_ORDER[item[0][1]], item[0][0]),\n            )\n        ],\n    ]\n    output = {\n        "base_band": base_band,\n        "path_floor_band": path_floor,\n        "effective_band": _band_max(base_band, path_floor),\n        "protected_files": protected,\n        "reasons": reasons,\n    }\n    corroboration = _review_pack_corroboration(profile, request["changed_files"])\n    if corroboration is None:\n        return output\n\n    corroborated_floor = corroboration["floor_band"]\n    semantic_floor = _band_max(path_floor, corroborated_floor)\n    underdeclared = BAND_ORDER[base_band] < BAND_ORDER[semantic_floor]\n    reasons.extend(corroboration["reasons"])\n    if underdeclared:\n        reasons.append(\n            {\n                "reason_id": "TASK_CLASS_UNDERDECLARED",\n                "band": semantic_floor,\n                "paths": [],\n            }\n        )\n    output.update(\n        {\n            "corroborated_semantic_floor_band": corroborated_floor,\n            "selected_review_packs": corroboration["selected_review_packs"],\n            "task_class_underdeclared": underdeclared,\n            "effective_band": _band_max(base_band, path_floor, corroborated_floor),\n            "reasons": reasons,\n        }\n    )\n    return output\n'''
    text = replace_block(
        text,
        "def _risk_projection(",
        "\n\ndef _empty_ledger_evidence",
        risk,
        "risk projection",
    )

    text = replace_once(
        text,
        '    high_risk_path = "HIGH_RISK_PATH" in risk_reason_ids\n    verifier_changed = (\n',
        '    high_risk_path = "HIGH_RISK_PATH" in risk_reason_ids\n    corroborated_high_risk = any(\n        reason_id.startswith("REVIEW_PACK_CORROBORATION:")\n        for reason_id in risk_reason_ids\n    )\n    verifier_changed = (\n',
        "hard gate risk signal",
    )
    old_gate = '''        "AUTHORIZATION_OR_MIGRATION_CHANGE": (\n            high_risk_task or high_risk_path,\n            "TASK",\n            sorted(\n                {\n                    request["task_class"],\n                    *[\n                        path\n                        for item in risk["reasons"]\n                        if item["reason_id"] == "HIGH_RISK_PATH"\n                        for path in item["paths"]\n                    ],\n                }\n            )\n            if high_risk_task or high_risk_path\n            else [],\n        ),\n'''
    new_gate = '''        "AUTHORIZATION_OR_MIGRATION_CHANGE": (\n            high_risk_task or high_risk_path or corroborated_high_risk,\n            "TASK",\n            sorted(\n                {\n                    request["task_class"],\n                    *[\n                        path\n                        for item in risk["reasons"]\n                        if (\n                            item["reason_id"] == "HIGH_RISK_PATH"\n                            or item["reason_id"].startswith("REVIEW_PACK_CORROBORATION:")\n                        )\n                        for path in item["paths"]\n                    ],\n                }\n            )\n            if high_risk_task or high_risk_path or corroborated_high_risk\n            else [],\n        ),\n'''
    text = replace_once(text, old_gate, new_gate, "authorization hard gate")

    text = replace_once(
        text,
        '    reground_observations: str | Path | None = None,\n    generated_at: str | None = None,\n) -> dict[str, Any]:\n    _, request_data = load_trust_request(request)\n    _, profile_data = _profile_descriptor(profile)\n',
        '    reground_observations: str | Path | None = None,\n    generated_at: str | None = None,\n    _include_corroboration: bool = True,\n) -> dict[str, Any]:\n    _, request_data = load_trust_request(request)\n    _, profile_data = _profile_descriptor(\n        profile, include_corroboration=_include_corroboration\n    )\n',
        "assess signature",
    )

    verification_anchor = '''            if profile.get("protected_paths") != normalized_patterns:\n                errors.append("profile.protected_paths canonical projection mismatch")\n'''
    verification_replacement = verification_anchor + '''            if "configured_review_packs" in profile:\n                configured_packs = profile.get("configured_review_packs")\n                if not isinstance(configured_packs, list):\n                    errors.append("profile.configured_review_packs must be an array")\n                else:\n                    normalized_packs = sorted(\n                        {\n                            value.strip()\n                            for value in configured_packs\n                            if isinstance(value, str) and value.strip()\n                        }\n                    )\n                    if configured_packs != normalized_packs:\n                        errors.append(\n                            "profile.configured_review_packs canonical projection mismatch"\n                        )\n'''
    text = replace_once(
        text,
        verification_anchor,
        verification_replacement,
        "profile corroboration verification",
    )

    text = replace_once(
        text,
        '            reground_observations=reground_observations,\n            generated_at=report["generated_at"],\n        )\n',
        '            reground_observations=reground_observations,\n            generated_at=report["generated_at"],\n            _include_corroboration=(\n                "configured_review_packs" in report.get("profile", {})\n            ),\n        )\n',
        "source replay compatibility",
    )
    TRUST.write_text(text, encoding="utf-8")


def patch_schemas() -> None:
    bands = ["R0", "R1", "R2", "R3", "R4"]
    for path in SCHEMAS:
        schema = json.loads(path.read_text(encoding="utf-8"))
        profile_properties = schema["$defs"]["profile"]["properties"]
        profile_properties["configured_review_packs"] = {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        }
        risk_properties = schema["$defs"]["risk"]["properties"]
        risk_properties["corroborated_semantic_floor_band"] = {"enum": bands}
        risk_properties["selected_review_packs"] = {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        }
        risk_properties["task_class_underdeclared"] = {"type": "boolean"}
        path.write_text(
            json.dumps(schema, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def write_regression_tests() -> None:
    TEST.write_text(
        '''from pathlib import Path\nimport tempfile\nimport unittest\n\nfrom review_system.io import dump_json\nfrom review_system.trust import assess_trust, verify_trust_report_data, verify_trust_report_sources\n\n\nROOT = Path(__file__).resolve().parents[1]\nPROFILE = ROOT / "profiles" / "examples" / "buildmap.yml"\nPR65 = [\n    "apps/web/app/settings/integrations/github-integration-actions.ts",\n    "apps/web/docs/access-policy-tests/phase-2-provider-connection-acceptance.md",\n    "apps/web/lib/notion/api.ts",\n    "apps/web/lib/notion/resource.ts",\n]\nPR66 = [\n    "apps/web/docs/implementation/phase-2-p5-production-readiness-status.md",\n]\nPR67 = [\n    ".github/workflows/web-phase2-operation.yml",\n    "apps/web/.env.example",\n    "apps/web/README.md",\n    "apps/web/app/api/health/route.ts",\n    "apps/web/app/decisions/[decisionId]/page.tsx",\n    "apps/web/app/page.tsx",\n    "apps/web/components/app-shell.tsx",\n    "apps/web/docs/implementation/phase-2-evidence-closure-status.md",\n    "apps/web/docs/implementation/phase-2-f5-state-mutation-proof.md",\n    "apps/web/docs/implementation/phase-2-f6-queue-snapshot-proof.md",\n    "apps/web/docs/implementation/phase-2-f8-rollback-proof.md",\n    "apps/web/docs/implementation/phase-2-w11-editorial-proof.md",\n    "apps/web/docs/implementation/phase-2-w2-primary-action-name-proof.md",\n    "apps/web/docs/implementation/phase-2-w3-primary-action-body-proof.md",\n    "apps/web/docs/implementation/phase-2-w4-primary-action-links-proof.md",\n    "apps/web/docs/implementation/phase-2-w6-return-context-proof.md",\n    "apps/web/docs/implementation/phase-2-w8-notion-context-proof.md",\n    "apps/web/docs/implementation/phase-3-operational-activation-plan.md",\n    "apps/web/lib/server/decision-queries.ts",\n    "apps/web/lib/server/decisions.ts",\n    "apps/web/lib/server/migrations/0004_operational_control_plane.sql",\n    "apps/web/lib/server/proof-targets.ts",\n    "apps/web/package.json",\n    "apps/web/vercel.json",\n]\nSYNTHETIC_AUTH_RLS = [\n    "apps/web/lib/provider/api-client.ts",\n    "apps/web/lib/provider/supabase-access.ts",\n]\n\n\ndef readiness_policy():\n    return {\n        "policy_id": "buildmap-corroboration-regression-v1",\n        "policy_version": "1.0.0",\n        "min_ledger_runs": 1,\n        "min_ledger_decisions": 1,\n        "min_defects": 1,\n        "min_closed_defects": 0,\n        "min_reground_observations": 1,\n        "min_reground_coverage": 1.0,\n        "min_reground_precision": 1.0,\n        "min_reground_recall": 1.0,\n        "max_reground_false_positive_rate": 0.0,\n        "require_active_policy": True,\n        "require_pass_evaluation": True,\n        "require_holdout": True,\n        "require_repeatability": True,\n        "require_zero_protected_negative_regressions": True,\n    }\n\n\nclass BuildMapTaskClassCorroborationTests(unittest.TestCase):\n    def setUp(self):\n        self.tempdir = tempfile.TemporaryDirectory()\n        self.addCleanup(self.tempdir.cleanup)\n        self.root = Path(self.tempdir.name)\n        self.counter = 0\n\n    def assess(self, files, task_class, revision, *, include_corroboration=True):\n        self.counter += 1\n        request = self.root / f"request-{self.counter}.json"\n        dump_json(\n            request,\n            {\n                "schema_version": "1.0",\n                "task_id": f"buildmap-corroboration-{self.counter}",\n                "source_revision": "git:" + revision,\n                "task_class": task_class,\n                "changed_files": files,\n                "required_scenarios": ["current_ci"],\n                "completed_scenarios": ["current_ci"],\n                "repository_match": True,\n                "head_match": True,\n                "rollback_evidence": True,\n                "replay_evidence": True,\n                "readiness_policy": readiness_policy(),\n            },\n        )\n        report = assess_trust(\n            request,\n            PROFILE,\n            generated_at="2026-08-21T00:00:00Z",\n            _include_corroboration=include_corroboration,\n        )\n        return request, report\n\n    def assert_source_replay(self, request, report):\n        self.assertEqual([], verify_trust_report_data(report))\n        self.assertEqual(\n            [],\n            verify_trust_report_sources(report, request=request, profile=PROFILE),\n        )\n\n    def test_buildmap_pr66_docs_only_stays_r1(self):\n        request, report = self.assess(\n            PR66,\n            "documentation",\n            "b498ad0b7068b848c89ce3641b37c688f58b842e",\n        )\n        risk = report["risk"]\n        self.assertEqual("R1", risk["path_floor_band"])\n        self.assertEqual("R0", risk["corroborated_semantic_floor_band"])\n        self.assertEqual("R1", risk["effective_band"])\n        self.assertFalse(risk["task_class_underdeclared"])\n        self.assert_source_replay(request, report)\n\n    def test_buildmap_pr65_provider_change_is_not_promoted_by_docs_only_rls(self):\n        request, report = self.assess(\n            PR65,\n            "routine_code",\n            "d22f84f1bf58350f208e305472522cde7602dc44",\n        )\n        risk = report["risk"]\n        self.assertEqual("R2", risk["path_floor_band"])\n        self.assertIn("application.authorization", risk["selected_review_packs"])\n        self.assertIn("data.rls", risk["selected_review_packs"])\n        self.assertEqual("R0", risk["corroborated_semantic_floor_band"])\n        self.assertEqual("R2", risk["effective_band"])\n        self.assertFalse(risk["task_class_underdeclared"])\n        self.assertFalse(\n            any(\n                item["reason_id"] == "REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS"\n                for item in risk["reasons"]\n            )\n        )\n        self.assert_source_replay(request, report)\n\n    def test_buildmap_pr67_control_plane_stays_r3(self):\n        request, report = self.assess(\n            PR67,\n            "routine_code",\n            "64d9785709b8c00d66be3275815269910adf0b94",\n        )\n        risk = report["risk"]\n        self.assertEqual("R3", risk["path_floor_band"])\n        self.assertEqual("R3", risk["corroborated_semantic_floor_band"])\n        self.assertEqual("R3", risk["effective_band"])\n        self.assertTrue(risk["task_class_underdeclared"])\n        self.assertTrue(\n            any(\n                item["reason_id"] == "REVIEW_PACK_CORROBORATION:MIGRATION_SAFETY"\n                for item in risk["reasons"]\n            )\n        )\n        self.assert_source_replay(request, report)\n\n    def test_non_documentation_auth_rls_combination_promotes_routine_code(self):\n        request, report = self.assess(\n            SYNTHETIC_AUTH_RLS,\n            "routine_code",\n            "1111111111111111111111111111111111111111",\n        )\n        risk = report["risk"]\n        self.assertEqual("R2", risk["path_floor_band"])\n        self.assertEqual("R3", risk["corroborated_semantic_floor_band"])\n        self.assertEqual("R3", risk["effective_band"])\n        self.assertTrue(risk["task_class_underdeclared"])\n        self.assertTrue(\n            any(\n                item["reason_id"] == "REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS"\n                for item in risk["reasons"]\n            )\n        )\n        gate = next(\n            item\n            for item in report["hard_gates"]\n            if item["gate_id"] == "AUTHORIZATION_OR_MIGRATION_CHANGE"\n        )\n        self.assertTrue(gate["triggered"])\n        self.assert_source_replay(request, report)\n\n    def test_legacy_report_shape_replays_without_new_optional_fields(self):\n        request, report = self.assess(\n            PR66,\n            "documentation",\n            "2222222222222222222222222222222222222222",\n            include_corroboration=False,\n        )\n        self.assertNotIn("configured_review_packs", report["profile"])\n        self.assertNotIn("corroborated_semantic_floor_band", report["risk"])\n        self.assertNotIn("selected_review_packs", report["risk"])\n        self.assertNotIn("task_class_underdeclared", report["risk"])\n        self.assert_source_replay(request, report)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',\n        encoding="utf-8",\n    )\n\n\ndef run_checks() -> None:\n    subprocess.run([sys.executable, "scripts/sync_package_assets.py"], cwd=ROOT, check=True)\n    subprocess.run(\n        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],\n        cwd=ROOT,\n        check=True,\n    )\n\n\ndef main() -> None:\n    patch_trust()\n    patch_schemas()\n    write_regression_tests()\n    run_checks()\n    subprocess.run(["git", "rm", "--", SELF], cwd=ROOT, check=True)\n\n\nif __name__ == "__main__":\n    main()\n
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.io import load_data
from review_system.trust_comparison import load_registry, new_registry
from review_system.trust_prospective_evidence import (
    ProspectiveEvidenceError,
    ProspectiveEvidenceVerificationError,
    intake_prospective_case,
    snapshot_campaign,
)
from review_system.trust_prospective_common import _replace_registry_manifest
from test_trust_prospective_evidence import build_r0_case, init_workspace, intake


class ProspectiveEvidenceHardeningTests(unittest.TestCase):
    def test_symlinked_trust_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            fixture, _report, report_path = build_r0_case(root)
            link = root / "report-link.json"
            link.symlink_to(report_path)
            with self.assertRaisesRegex(ProspectiveEvidenceError, "must not contain symlinks"):
                intake_prospective_case(
                    workspace,
                    trust_report=link,
                    request=fixture.request,
                    profile=fixture.profile,
                    ledger=fixture.reground_fixture.ledger,
                    policy_registry=fixture.policy_registry,
                    evaluation_report=fixture.evaluation_report,
                    reground_report=fixture.reground_report,
                    reground_observations=fixture.observations,
                    captured_at="2026-08-18T02:00:00Z",
                )

    def test_pair_replace_failure_restores_original_registry_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            registry_path = workspace / "comparison-registry.json"
            manifest_path = workspace / "reconciliation-sources.json"
            original_registry = registry_path.read_bytes()
            original_manifest = manifest_path.read_bytes()
            replacement_registry = new_registry("demo", created_at="2026-08-18T00:00:01Z")
            manifest = load_data(manifest_path)

            from review_system import trust_prospective_common as module
            real_replace = module.os.replace
            calls = {"count": 0}

            def fail_second(source, target):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("forced manifest replace failure")
                return real_replace(source, target)

            with patch("review_system.trust_prospective_common.os.replace", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "forced manifest replace failure"):
                    _replace_registry_manifest(registry_path, manifest_path, replacement_registry, manifest)

            self.assertEqual(original_registry, registry_path.read_bytes())
            self.assertEqual(original_manifest, manifest_path.read_bytes())
            self.assertEqual([], list(workspace.glob(".*.tmp")))

    def test_intake_persist_failure_removes_case_and_preserves_authority_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            fixture, _report, report_path = build_r0_case(root)
            registry_before = (workspace / "comparison-registry.json").read_bytes()
            manifest_before = (workspace / "reconciliation-sources.json").read_bytes()
            with patch(
                "review_system.trust_prospective_intake._replace_registry_manifest",
                side_effect=OSError("forced persist failure"),
            ):
                with self.assertRaisesRegex(OSError, "forced persist failure"):
                    intake(workspace, fixture, report_path)
            self.assertEqual(registry_before, (workspace / "comparison-registry.json").read_bytes())
            self.assertEqual(manifest_before, (workspace / "reconciliation-sources.json").read_bytes())
            cases = workspace / "cases"
            self.assertFalse(cases.exists() and any(cases.iterdir()))

    def test_existing_snapshot_mutation_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_workspace(root)
            fixture, _report, report_path = build_r0_case(root)
            intake(workspace, fixture, report_path)
            snapshots = root / "snapshots"
            first = snapshot_campaign(workspace, snapshots, generated_at="2026-08-18T04:00:00Z")
            package = Path(first["package"])
            (package / "acquisition-attestation.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ProspectiveEvidenceVerificationError):
                snapshot_campaign(workspace, snapshots, generated_at="2026-08-18T05:00:00Z")


if __name__ == "__main__":
    unittest.main()

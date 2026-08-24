from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from review_system.operational_review_brief import (
    OperationalReviewBriefError,
    build_operational_review_brief,
    write_operational_review_brief,
    write_operational_review_brief_markdown,
)


HEAD = "a" * 40
BASE = "b" * 40
PIE = "c" * 40


def _brief() -> dict:
    return build_operational_review_brief(
        summary={
            "repository": "demo/repo",
            "pull_request": 7,
            "source_revision": HEAD,
            "pie_revision": PIE,
            "candidate_id": "github-capture-demo",
            "status": "WAITING_FOR_TRUST_INPUT",
            "next_step": "PROVIDE_EXPLICIT_TRUST_REQUEST",
            "risk_band": None,
            "readiness": None,
        },
        candidate={
            "project_id": "demo",
            "candidate_id": "github-capture-demo",
            "task_id": "github-pr:demo",
            "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
            "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
            "changed_files": ["src/core.py"],
        },
        candidate_sha256="d" * 64,
        impact={
            "direct": {"components": ["core"]},
            "impact": {"dependent_files": []},
            "review": {"selected_packs": [], "required_tests": []},
            "limitations": [],
        },
    )


@unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
class OperationalReviewBriefOutputSafetyTests(unittest.TestCase):
    def test_parent_symlink_is_rejected_for_json_and_markdown_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            linked = root / "linked"
            try:
                linked.symlink_to(real, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"cannot create symlink on this platform: {exc}")

            brief = _brief()
            with self.assertRaises(OperationalReviewBriefError):
                write_operational_review_brief(linked / "brief.json", brief)
            with self.assertRaises(OperationalReviewBriefError):
                write_operational_review_brief_markdown(linked / "BRIEF.md", brief)
            self.assertFalse((real / "brief.json").exists())
            self.assertFalse((real / "BRIEF.md").exists())


if __name__ == "__main__":
    unittest.main()

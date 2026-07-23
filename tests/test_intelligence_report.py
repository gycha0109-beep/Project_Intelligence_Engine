import unittest

from review_system.intelligence_report import pull_request_markdown


class PullRequestReportTests(unittest.TestCase):
    def test_reports_status_context_and_evidence_completeness(self):
        source = {
            "repository": {"name_with_owner": "demo/repo"},
            "pull_request": {
                "number": 1,
                "changed_files": [{"path": "src/a.ts"}],
                "checks": [{"__typename": "StatusContext", "context": "Vercel", "state": "SUCCESS"}],
            },
            "diff": {"available": False},
            "discussion": {"complete": True},
            "local_repository_verification": {"status": "matched"},
        }
        impact = {
            "direct": {"components": ["web"], "files_missing_from_graph": []},
            "impact": {"dependent_files": []},
            "review": {"selected_packs": [], "required_tests": []},
            "evidence": [{"classification": "confirmed_change"}],
            "limitations": [],
        }
        report = pull_request_markdown(source, impact)
        self.assertIn("1 success / 0 failed / 0 pending-or-neutral", report)
        self.assertIn("`web`", report)
        self.assertIn("Diff evidence: `unavailable`", report)
        self.assertIn("Discussion evidence: `complete`", report)


if __name__ == "__main__":
    unittest.main()

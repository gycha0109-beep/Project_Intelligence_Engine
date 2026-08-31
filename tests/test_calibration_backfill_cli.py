from __future__ import annotations

import unittest
from urllib.request import Request

from review_system.calibration_backfill_cli import _StripAuthorizationCrossHostRedirect


class CalibrationBackfillCliTests(unittest.TestCase):
    def test_cross_host_redirect_strips_github_authorization(self):
        handler = _StripAuthorizationCrossHostRedirect()
        request = Request(
            "https://api.github.com/repos/owner/repo/actions/artifacts/123/zip",
            headers={"Authorization": "Bearer secret", "User-Agent": "pie-test"},
        )
        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://objects.githubusercontent.com/actions-results/file.zip?sig=abc",
        )
        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))
        self.assertEqual("pie-test", redirected.get_header("User-agent"))

    def test_same_host_redirect_keeps_authorization(self):
        handler = _StripAuthorizationCrossHostRedirect()
        request = Request(
            "https://api.github.com/old",
            headers={"Authorization": "Bearer secret"},
        )
        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://api.github.com/new",
        )
        self.assertIsNotNone(redirected)
        self.assertEqual("Bearer secret", redirected.get_header("Authorization"))


if __name__ == "__main__":
    unittest.main()

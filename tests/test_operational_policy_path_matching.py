from __future__ import annotations

import unittest

from review_system.operational_policy_binder import _matches_path


class OperationalPolicyPathMatchingTests(unittest.TestCase):
    def test_single_star_does_not_cross_path_segment(self):
        self.assertTrue(_matches_path("src/runtime.py", "src/*"))
        self.assertFalse(_matches_path("src/deep/runtime.py", "src/*"))

    def test_trailing_recursive_glob_matches_direct_and_nested_files(self):
        self.assertTrue(_matches_path("src/runtime/job.py", "src/runtime/**"))
        self.assertTrue(_matches_path("src/runtime/deep/job.py", "src/runtime/**"))

    def test_recursive_directory_segment_can_match_zero_or_more_directories(self):
        pattern = "app/src/main/**/*Reminder*"
        self.assertTrue(_matches_path("app/src/main/ReminderWorker.kt", pattern))
        self.assertTrue(_matches_path("app/src/main/work/ReminderWorker.kt", pattern))
        self.assertTrue(_matches_path("app/src/main/work/deep/ReminderWorker.kt", pattern))


if __name__ == "__main__":
    unittest.main()

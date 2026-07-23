import unittest

from review_system.path_globs import expand_trailing_recursive_glob


class PathGlobCompatibilityTests(unittest.TestCase):
    def test_trailing_recursive_glob_adds_explicit_descendant_pattern(self):
        self.assertEqual(("src/**", "src/**/*"), expand_trailing_recursive_glob("src/**"))

    def test_non_trailing_recursive_glob_is_unchanged(self):
        self.assertEqual(("**/*",), expand_trailing_recursive_glob("**/*"))


if __name__ == "__main__":
    unittest.main()

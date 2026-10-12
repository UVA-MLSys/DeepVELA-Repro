import unittest

from _fixture import SCRIPTS  # noqa: F401
from compare_results import compare_value


class CompareResultsTest(unittest.TestCase):
    def test_absolute_tolerance(self):
        passed, difference = compare_value(1.005, 1.0, "absolute_tolerance", 0.01)
        self.assertTrue(passed)
        self.assertAlmostEqual(difference, 0.005)

    def test_relative_tolerance_rejects_large_difference(self):
        passed, _ = compare_value(1.02, 1.0, "relative_tolerance", 0.01)
        self.assertFalse(passed)

    def test_exact_supports_structured_values(self):
        self.assertEqual(compare_value([1, 2], [1, 2], "exact", None), (True, None))


if __name__ == "__main__":
    unittest.main()

import unittest

from core.metrics import parse_elapsed, project_profit, profit_rate_per_second


class MetricsTests(unittest.TestCase):
    def test_parse_elapsed(self):
        self.assertEqual(parse_elapsed("01:02:03"), 3723)

    def test_profit_rate(self):
        self.assertEqual(profit_rate_per_second(120, 60), 2)
        self.assertEqual(profit_rate_per_second(120, 0), 0)

    def test_projection_requires_stable_sample(self):
        self.assertEqual(project_profit(100, 30, 3600), 0)
        self.assertEqual(project_profit(120, 60, 3600), 7200)


if __name__ == "__main__":
    unittest.main()


"""
Pytest & Unittest Test Suite for IMDb Intelligence Evals.
Runs all test cases in dataset.json through deterministic code assertions.
"""

import unittest
from evals.engine import EvalEngine, EvalMode


class TestIMDbEvaluationSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = EvalEngine()
        cls.test_cases = cls.engine.load_dataset()

    def test_all_gold_baseline_cases(self):
        """Executes all test cases against DuckDB baseline and asserts 100% invariant satisfaction."""
        suite_result = self.engine.run_suite(mode=EvalMode.GOLD)
        
        failures = []
        for r in suite_result.results:
            if not r.passed:
                failed_assertions = [a.message for a in r.assertions if not a.passed]
                failures.append(f"[{r.category}] {r.test_id}: {'; '.join(failed_assertions)}")
                
        self.assertEqual(
            suite_result.failed_tests,
            0,
            f"Evaluation baseline had {suite_result.failed_tests} failure(s):\n" + "\n".join(failures)
        )

    def test_categories_represented(self):
        """Ensures all 6 core evaluation categories are populated."""
        categories = {t["category"] for t in self.test_cases}
        expected = {
            "plain_and_easy",
            "disambiguation",
            "regional_cinema",
            "relational_queries",
            "typo_and_reflection",
            "security_and_performance"
        }
        self.assertTrue(expected.issubset(categories), f"Missing categories: {expected - categories}")


if __name__ == "__main__":
    unittest.main()

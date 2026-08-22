"""Regression tests for the reproducible Candidate A optimizer."""

from __future__ import annotations

import unittest

from generator.build_matrix import build_transformation_matrix
from optimizer.optimize import independently_check, search_seed


class OptimizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = build_transformation_matrix()

    def test_seed_is_reproducible_and_exact(self) -> None:
        first = search_seed(3, self.rows)
        second = search_seed(3, self.rows)
        self.assertEqual(first, second)
        metrics = independently_check(first)
        self.assertEqual(metrics.unreachable_nodes, ())
        self.assertLess(metrics.xor2_count, 454)

    def test_different_seeds_remain_valid(self) -> None:
        for seed in (0, 1, 2):
            candidate = search_seed(seed, self.rows)
            metrics = independently_check(candidate)
            self.assertGreater(metrics.xor2_count, 0)
            self.assertEqual(len(metrics.output_depths), 32)


if __name__ == "__main__":
    unittest.main()

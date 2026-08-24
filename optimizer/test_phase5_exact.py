"""Regression tests for bounded exact cone synthesis."""

from __future__ import annotations

import unittest

from optimizer.phase5_exact import Cone, solve_strict_improvement


class Phase5ExactTests(unittest.TestCase):
    def test_solver_finds_the_exact_three_input_lower_bound(self) -> None:
        cone = Cone(
            root="root",
            nodes=("n0", "n1", "n2"),
            leaves=("a", "b", "c"),
            target_vector=0b111,
        )

        result = solve_strict_improvement(cone, timeout_ms=1_000)

        self.assertEqual(result.status, "sat")
        self.assertEqual(result.gate_count, 2)
        self.assertIsNotNone(result.witness)


if __name__ == "__main__":
    unittest.main()

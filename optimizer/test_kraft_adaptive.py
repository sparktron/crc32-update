"""Regression tests for the tight-row (cap-adaptive) Kraft-slack tie-break."""

from __future__ import annotations

from pathlib import Path
import unittest

from optimizer.depth_bounded import search_seed_bounded
from optimizer.kraft_adaptive import STAGES, THETA, _AdaptiveBuilder, search_seed_adaptive
from optimizer.kraft_slack import search_seed_slack
from optimizer.optimize import independently_check

ROOT = Path(__file__).resolve().parents[1]


def _rows(*expressions: tuple[int, ...]) -> list[int]:
    return [sum(1 << signal for signal in expression) for expression in expressions]


class DeterminismGateTests(unittest.TestCase):
    def test_theta_zero_reproduces_the_slack_variant(self) -> None:
        self.assertEqual(
            search_seed_adaptive(240000, 6, theta=0.0).render(),
            search_seed_slack(240000, 6).render(),
        )

    def test_theta_two_reproduces_the_baseline(self) -> None:
        self.assertEqual(
            search_seed_adaptive(40000, 7, theta=2.0).render(),
            search_seed_bounded(40000, 7).render(),
        )

    def test_theta_zero_reproduces_the_467_network(self) -> None:
        recorded = ROOT / "results/kraft_slack/stage2_depth6.v"
        self.assertEqual(
            search_seed_adaptive(246653, 6, theta=0.0).render("candidate_depth6_kraft_slack"),
            recorded.read_text(),
        )


class TightRowTests(unittest.TestCase):
    def test_cost_counts_only_rows_at_or_above_the_floor(self) -> None:
        # Cap 3 has a limit of 8 and theta 1/2 a floor of 4. Row 0 (Kraft 2) is
        # loose and row 1 (Kraft 5) is tight. Merging depths 0 and 1 costs
        # 4 - 1 - 2 = 1 per row.
        builder = _AdaptiveBuilder(_rows((0, 1), (0, 1, 2, 3, 4)), 3, 0)
        builder.depths[1] = 1
        _, costs = builder._frequencies_and_costs(new_only=True)
        self.assertEqual(THETA, 0.5)
        self.assertEqual(costs[(0, 1)], 1)

    def test_variant_trial_is_exact_within_cap_and_replayable(self) -> None:
        candidate = search_seed_adaptive(1, 7)
        self.assertLessEqual(independently_check(candidate).maximum_depth, 7)
        self.assertEqual(candidate.render(), search_seed_adaptive(1, 7).render())


class StageTests(unittest.TestCase):
    def test_stage_ranges_are_disjoint(self) -> None:
        ranges = sorted((start, start + count) for start, count in STAGES.values())
        for (_, end), (start, _) in zip(ranges, ranges[1:]):
            self.assertLessEqual(end, start)


if __name__ == "__main__":
    unittest.main()

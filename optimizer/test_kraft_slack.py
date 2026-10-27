"""Regression tests for the Kraft-slack tie-break variant."""

from __future__ import annotations

from pathlib import Path
import unittest

from generator.build_matrix import INPUT_COUNT
from optimizer.depth_bounded import search_seed_bounded
from optimizer.kraft_slack import STAGES, _SlackBuilder, search_seed_slack
from optimizer.optimize import independently_check

ROOT = Path(__file__).resolve().parents[1]


def _rows(*expressions: tuple[int, ...]) -> list[int]:
    return [sum(1 << signal for signal in expression) for expression in expressions]


class DeterminismGateTests(unittest.TestCase):
    def test_slack_off_reproduces_the_recorded_baseline(self) -> None:
        for cap, seed in ((7, 40000), (6, 50000)):
            with self.subTest(cap=cap):
                self.assertEqual(
                    search_seed_slack(seed, cap, use_slack=False).render(),
                    search_seed_bounded(seed, cap).render(),
                )

    def test_slack_off_reproduces_the_c_incumbent(self) -> None:
        recorded = ROOT / "results/checkpoints/depth6_bounded_incumbents/seed_56140.v"
        self.assertEqual(
            search_seed_slack(56140, 6, use_slack=False).render("candidate_depth6_bounded"),
            recorded.read_text(),
        )


class SlackCostTests(unittest.TestCase):
    def test_equal_depth_merge_is_free_and_unequal_merge_costs(self) -> None:
        builder = _SlackBuilder(_rows((0, 1, 2), (0, 1, 2)), 3, 0)
        builder._apply((0, 1))  # signal INPUT_COUNT has depth 1 in both rows
        gate = INPUT_COUNT
        _, costs = builder._frequencies_and_costs(new_only=True)
        # Depth 1 with depth 0 makes a depth-2 gate: 4 - 2 - 1 = 1 per row.
        self.assertEqual(costs[(2, gate)], 2)
        builder = _SlackBuilder(_rows((0, 1)), 3, 0)
        _, costs = builder._frequencies_and_costs(new_only=True)
        self.assertEqual(costs[(0, 1)], 0)

    def test_variant_trial_is_exact_within_cap_and_replayable(self) -> None:
        candidate = search_seed_slack(1, 7)
        self.assertLessEqual(independently_check(candidate).maximum_depth, 7)
        self.assertEqual(candidate.render(), search_seed_slack(1, 7).render())


class StageTests(unittest.TestCase):
    def test_stage_ranges_are_disjoint(self) -> None:
        ranges = sorted((start, start + count) for start, count in STAGES.values())
        for (_, end), (start, _) in zip(ranges, ranges[1:]):
            self.assertLessEqual(end, start)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for the tight-row (cap-adaptive) Kraft-slack tie-break."""

from __future__ import annotations

from pathlib import Path
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

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
    def test_v1_stages_cannot_run_with_v2_code(self) -> None:
        for (stage, cap), (_, _, version) in STAGES.items():
            if version != "v1":
                continue
            with self.subTest(stage=stage, cap=cap):
                with patch("sys.argv", ["kraft_adaptive", "--stage", stage,
                                        "--depth-cap", str(cap)]), \
                     patch("optimizer.kraft_adaptive.run_bounded_search") as run, \
                     patch("optimizer.kraft_adaptive._exclusive_search_lock") as lock, \
                     redirect_stderr(StringIO()) as errors:
                    from optimizer.kraft_adaptive import main
                    with self.assertRaises(SystemExit) as raised:
                        main()
                    self.assertEqual(raised.exception.code, 2)
                    self.assertIn("v1 stages are frozen", errors.getvalue())
                    run.assert_not_called()
                    lock.assert_not_called()

    def test_v2_rerun_keeps_its_versioned_algorithm(self) -> None:
        with patch("sys.argv", ["kraft_adaptive", "--stage", "stage2_rerun",
                                "--depth-cap", "6"]), \
             patch("optimizer.kraft_adaptive.run_bounded_search",
                   return_value=(286375, {})) as run, \
             patch("optimizer.kraft_adaptive._exclusive_search_lock"), \
             patch("builtins.print"):
            from optimizer.kraft_adaptive import main
            self.assertEqual(main(), 0)
            self.assertEqual(run.call_args.kwargs["algorithm"],
                             "kraft-adaptive-tiebreak-half-depth6-v2")

    def test_stage_ranges_are_disjoint(self) -> None:
        # The v2 rerun deliberately repeats stage 2's seeds under a new name.
        ranges = sorted(
            (start, start + count)
            for (stage, _), (start, count, _) in STAGES.items()
            if stage != "stage2_rerun"
        )
        for (_, end), (start, _) in zip(ranges, ranges[1:]):
            self.assertLessEqual(end, start)

    def test_rerun_repeats_stage_two_under_v2(self) -> None:
        self.assertEqual(STAGES[("stage2_rerun", 6)], (281_000, 10_000, "v2"))
        self.assertEqual(STAGES[("stage2", 6)][:2], STAGES[("stage2_rerun", 6)][:2])


class FinishingFallbackTests(unittest.TestCase):
    def test_seed_that_stopped_v1_now_completes_within_cap(self) -> None:
        # v1 raised "no depth-feasible pair" here: the only merge that fit had an
        # XOR that already existed as a deeper signal.
        for search in (search_seed_adaptive, search_seed_slack):
            with self.subTest(search=search.__name__):
                candidate = search(284862, 6)
                self.assertLessEqual(independently_check(candidate).maximum_depth, 6)

    def test_fallback_leaves_the_466_network_unchanged(self) -> None:
        incumbents = ROOT / "results/checkpoints/kraft_adaptive/stage2_depth6_incumbents"
        recorded = incumbents / "seed_281125.v"
        self.assertEqual(
            search_seed_adaptive(281125, 6).render("candidate_depth6_kraft_adaptive"),
            recorded.read_text(),
        )


if __name__ == "__main__":
    unittest.main()

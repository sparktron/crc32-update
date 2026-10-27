"""Regression tests for the one-component-at-a-time ablation toward DCLO."""

from __future__ import annotations

from pathlib import Path
import unittest

from optimizer.ablation import (
    COMPONENTS,
    build_ablated,
    components_for,
    search_seed_ablated,
)
from optimizer.depth_bounded import search_seed_bounded
from optimizer.optimize import independently_check

ROOT = Path(__file__).resolve().parents[1]


class ArmTests(unittest.TestCase):
    def test_each_single_arm_switches_exactly_one_component(self) -> None:
        self.assertEqual(components_for("none"), frozenset())
        self.assertEqual(components_for("all"), frozenset(COMPONENTS))
        for component in COMPONENTS:
            self.assertEqual(components_for(component), frozenset({component}))
        with self.assertRaisesRegex(ValueError, "unknown ablation arm"):
            components_for("dclo")


class DeterminismGateTests(unittest.TestCase):
    def test_no_component_reproduces_the_recorded_baseline(self) -> None:
        for cap, seed in ((7, 40000), (6, 50000)):
            with self.subTest(cap=cap):
                self.assertEqual(
                    search_seed_ablated(seed, cap, "none").render(),
                    search_seed_bounded(seed, cap).render(),
                )

    def test_no_component_reproduces_the_b7_incumbent(self) -> None:
        recorded = ROOT / "results/checkpoints/depth7_bounded_incumbents/seed_40505.v"
        self.assertEqual(
            search_seed_ablated(40505, 7, "none").render("candidate_depth7_bounded"),
            recorded.read_text(),
        )


class ArmTrialTests(unittest.TestCase):
    def test_every_arm_is_exact_within_cap_and_replayable(self) -> None:
        for arm in (*COMPONENTS, "all"):
            with self.subTest(arm=arm):
                candidate, _ = build_ablated(1, 7, arm)
                self.assertLessEqual(independently_check(candidate).maximum_depth, 7)
                self.assertEqual(candidate.render(), search_seed_ablated(1, 7, arm).render())

    def test_rewrite_arm_never_reuses_a_signal_by_vector(self) -> None:
        _, builder = build_ablated(1, 7, "rewrite")
        self.assertEqual(builder._target((0, 1))[0], None)


if __name__ == "__main__":
    unittest.main()

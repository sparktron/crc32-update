"""Prerun identity, RNG isolation, replay and future-opportunity tests."""
import unittest
from generator.build_matrix import build_transformation_matrix
from optimizer.depth_bounded import search_seed_bounded
from optimizer.kraft_slack import search_seed_slack
from optimizer.optimize import independently_check
from optimizer.sharing_lookahead import _LookaheadBuilder, build_trial, passes_screen


class LookaheadTests(unittest.TestCase):
    def test_control_identity_and_candidate_replay(self):
        for cap, seed in ((7, 390000), (6, 390001)):
            historical = search_seed_bounded(seed, cap) if cap == 7 else search_seed_slack(seed, cap)
            control, _ = build_trial(seed, cap, "control")
            self.assertEqual(control.render(), historical.render())
            first, diagnostics = build_trial(seed, cap, "candidate")
            second, replay = build_trial(seed, cap, "candidate")
            self.assertEqual(first.render(), second.render())
            diagnostics.pop("runtime")
            replay.pop("runtime")
            self.assertEqual(diagnostics, replay)
            self.assertGreater(diagnostics["lookahead"]["probes"], 0)
            self.assertLessEqual(independently_check(first).maximum_depth, cap)

    def test_probes_preserve_all_live_state_and_rng(self):
        builder = _LookaheadBuilder(build_transformation_matrix(), 6, 390002)
        before = repr(builder.snapshot())
        pairs = builder.ranked()[:3]
        forward = {pair: builder.probe(pair) for pair in pairs}
        backward = {pair: builder.probe(pair) for pair in reversed(pairs)}
        self.assertEqual(forward, backward)
        self.assertEqual(before, repr(builder.snapshot()))

    def test_future_reward_distinguishes_equal_immediate_savings(self):
        # Equal root rewards; changed residual states expose different
        # deterministic next-move rewards (including feasible free reuse).
        builder = _LookaheadBuilder([], 3, 1)
        builder.expressions = [set(row) for row in
            [[0, 2, 4], [3, 6], [0, 1, 3, 4, 5], [3, 6],
             [0, 2, 3, 4, 6], [0, 2, 4]]]
        a, b = builder.probe((0, 2)), builder.probe((3, 6))
        self.assertEqual(a[0] - a[1], b[0] - b[1])
        self.assertNotEqual(a[1], b[1])

    def test_frozen_screen(self):
        self.assertTrue(passes_screen({"mean": -0.5, "z_normal_approximation": -3}))
        for mean, z in ((-0.499, -4), (-1, -2.99), (-1, None), (1, 4)):
            self.assertFalse(passes_screen({"mean": mean, "z_normal_approximation": z}))


if __name__ == "__main__":
    unittest.main()

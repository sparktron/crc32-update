"""Identity and causal-isolation gates for the registered phase experiment."""

import unittest

from optimizer.depth_bounded import search_seed_bounded
from optimizer.kraft_slack import search_seed_slack
from optimizer.phase_isolation import build_trial, paired_difference


class PhaseIsolationTests(unittest.TestCase):
    def test_controls_reproduce_historical_builders_and_isolate_finishing(self):
        for seed, cap in ((40_000, 7), (50_000, 6)):
            with self.subTest(seed=seed, cap=cap):
                results = {arm: build_trial(seed, cap, arm)
                           for arm in ("baseline", "sharing", "finishing", "both")}
                self.assertEqual(results["baseline"][0].render(), search_seed_bounded(seed, cap).render())
                self.assertEqual(results["both"][0].render(), search_seed_slack(seed, cap).render())
                for a, b in (("baseline", "finishing"), ("sharing", "both")):
                    for key in ("sharing_state_sha256", "finishing_rng_sha256", "sharing_created"):
                        self.assertEqual(results[a][1][key], results[b][1][key])
                for candidate, diagnostics in results.values():
                    self.assertEqual(len(candidate.operations), diagnostics["sharing_retained"]
                                     + diagnostics["finishing_retained"])
                    self.assertGreaterEqual(min(diagnostics["remaining_kraft_budget"]), 0)

    def test_paired_statistics(self):
        result = paired_difference([3, 4, 2], [4, 4, 4])
        self.assertEqual(result["mean"], -1)
        self.assertAlmostEqual(result["standard_error"], (1 / 3) ** 0.5)
        self.assertIsNone(paired_difference([1, 1], [2, 2])["z_normal_approximation"])
        with self.assertRaises(ValueError):
            paired_difference([1], [1, 2])


if __name__ == "__main__":
    unittest.main()

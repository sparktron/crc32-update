"""Regression tests for the reproducible Candidate A optimizer."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from generator.build_matrix import build_transformation_matrix
from optimizer.optimize import independently_check, run_search, search_seed
from verifier.verify_network import DEFAULT_RANDOM_SEED, DEFAULT_RANDOM_TESTS


ROOT = Path(__file__).resolve().parents[1]


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

    def test_completed_checkpoint_restores_requested_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            artifact = temporary / "candidate.v"
            frontier = temporary / "frontier.json"
            metrics = temporary / "metrics.csv"
            search_log = temporary / "search.jsonl"
            candidate = run_search(
                seed_start=0,
                seed_count=10_000,
                workers=1,
                checkpoint_path=(
                    ROOT / "results/checkpoints/candidate_a_checkpoint.json"
                ),
                artifact_path=artifact,
                frontier_path=frontier,
                metrics_path=metrics,
                log_path=search_log,
                random_tests=DEFAULT_RANDOM_TESTS,
                random_seed=DEFAULT_RANDOM_SEED,
            )
            self.assertEqual(candidate.seed, 3195)
            self.assertEqual(
                artifact.read_text(),
                (ROOT / "results/candidate_a_min_area.v").read_text(),
            )
            self.assertTrue(frontier.is_file())
            self.assertTrue(metrics.is_file())
            self.assertEqual(
                search_log.read_bytes(),
                (ROOT / "results/search_log.jsonl").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()

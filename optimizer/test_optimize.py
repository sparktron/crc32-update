"""Regression tests for the reproducible Candidate A optimizer."""

from __future__ import annotations

import json
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

    def test_log_ahead_of_checkpoint_resumes_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            log_path = temporary / "search.jsonl"
            records = (
                ROOT / "results/search_log.jsonl"
            ).read_text().splitlines()[:2]
            log_path.write_text("\n".join(records) + "\n")
            incumbent = search_seed(0, self.rows)
            checkpoint_path = temporary / "checkpoint.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "algorithm": "gf2-bp-cse-depth-stochastic-v1",
                        "seed_start": 0,
                        "seed_count": 2,
                        "random_tests": DEFAULT_RANDOM_TESTS,
                        "random_seed": DEFAULT_RANDOM_SEED,
                        "search_log_path": "search.jsonl",
                        "completed_seeds": 1,
                        "incumbent_seed": 0,
                        "incumbent_metrics": independently_check(
                            incumbent
                        ).to_dict(),
                        "status": "running",
                    }
                )
                + "\n"
            )
            candidate = run_search(
                seed_start=0,
                seed_count=2,
                workers=1,
                checkpoint_path=checkpoint_path,
                artifact_path=temporary / "candidate.v",
                frontier_path=temporary / "frontier.json",
                metrics_path=temporary / "metrics.csv",
                log_path=log_path,
                random_tests=DEFAULT_RANDOM_TESTS,
                random_seed=DEFAULT_RANDOM_SEED,
            )
            self.assertEqual(candidate.seed, 0)
            self.assertEqual(log_path.read_text().splitlines(), records)
            checkpoint = json.loads(checkpoint_path.read_text())
            self.assertEqual(checkpoint["completed_seeds"], 2)
            self.assertEqual(checkpoint["status"], "completed")


if __name__ == "__main__":
    unittest.main()

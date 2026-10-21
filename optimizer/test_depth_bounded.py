"""Regression tests for the Kraft-bounded depth-capped search."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from optimizer.depth_bounded import (
    _kraft_after,
    algorithm_name,
    run_bounded_search,
    search_seed_bounded,
)
from optimizer.optimize import independently_check


class KraftTests(unittest.TestCase):
    def test_equal_depth_pairing_is_free_and_unequal_pairing_costs(self) -> None:
        depths = [2, 2, 1, 3]
        expression = {0, 1, 2}
        kraft = 4 + 4 + 2
        self.assertEqual(_kraft_after(expression, kraft, (0, 1), None, 3, depths), kraft)
        self.assertEqual(_kraft_after(expression, kraft, (0, 2), None, 3, depths), 12)

    def test_existing_replacement_in_expression_cancels(self) -> None:
        depths = [1, 1, 2]
        self.assertEqual(_kraft_after({0, 1, 2}, 2 + 2 + 4, (0, 1), 2, 2, depths), 0)


class BoundedSeedTests(unittest.TestCase):
    def test_depth_seven_trial_is_exact_and_within_cap(self) -> None:
        candidate = search_seed_bounded(40000, 7)
        metrics = independently_check(candidate)
        self.assertLessEqual(metrics.maximum_depth, 7)
        self.assertEqual(candidate.render(), search_seed_bounded(40000, 7).render())

    def test_infeasible_cap_is_rejected_before_search(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot meet depth cap 5"):
            search_seed_bounded(40000, 5)


class ResumeTests(unittest.TestCase):
    def test_accepted_log_record_ahead_of_checkpoint_is_recovered(self) -> None:
        seed = 40000
        candidate = search_seed_bounded(seed, 7)
        metrics = independently_check(candidate).to_dict()
        metrics.pop("unreachable_nodes")
        algorithm = algorithm_name(7)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incumbents = root / "incumbents"
            incumbents.mkdir()
            source = candidate.render("candidate_depth7_bounded")
            (incumbents / f"seed_{seed}.v").write_text(source)
            log = root / "search_log.jsonl"
            log.write_text(
                json.dumps(
                    {
                        "algorithm": algorithm,
                        "seed": seed,
                        "accepted": True,
                        "final_metrics": metrics,
                    }
                )
                + "\n"
            )
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "algorithm": algorithm,
                        "depth_cap": 7,
                        "seed_start": seed,
                        "seed_count": 1,
                        "random_tests": 100_000,
                        "random_seed": 0xC32A5EED,
                        "completed_seeds": 0,
                        "incumbent_seed": None,
                        "status": "running",
                    }
                )
            )
            artifact = root / "candidate.v"
            best_seed, best_metrics = run_bounded_search(
                7, seed, 1, 1, checkpoint, artifact, incumbents, log, 100_000, 0xC32A5EED
            )
            self.assertEqual(best_seed, seed)
            self.assertEqual(best_metrics, metrics)
            self.assertEqual(artifact.read_text(), source)
            self.assertEqual(len(log.read_text().splitlines()), 1)
            self.assertEqual(json.loads(checkpoint.read_text())["status"], "completed")


if __name__ == "__main__":
    unittest.main()

"""Regression tests for the DCLO depth-capped search."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from generator.build_matrix import INPUT_COUNT
from optimizer.dclo import (
    _DcloBuilder,
    algorithm_name,
    module_name,
    search_seed_dclo,
)
from optimizer.depth_bounded import run_bounded_search
from optimizer.optimize import independently_check


def _rows(*expressions: tuple[int, ...]) -> list[int]:
    return [sum(1 << signal for signal in expression) for expression in expressions]


class DcloSeedTests(unittest.TestCase):
    def test_trials_are_exact_within_cap_and_replayable(self) -> None:
        for cap, seed in ((7, 70000), (6, 80000)):
            with self.subTest(cap=cap):
                candidate = search_seed_dclo(seed, cap)
                metrics = independently_check(candidate)
                self.assertLessEqual(metrics.maximum_depth, cap)
                self.assertEqual(candidate.render(), search_seed_dclo(seed, cap).render())

    def test_infeasible_cap_is_rejected_before_search(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot meet depth cap 5"):
            search_seed_dclo(70000, 5)


class DcloMoveTests(unittest.TestCase):
    def test_gate_updates_every_row_holding_both_inputs(self) -> None:
        builder = _DcloBuilder(_rows((0, 1, 2), (0, 1), (1, 2)), 3, 0)
        builder.add_gate((0, 1))
        gate = INPUT_COUNT
        self.assertEqual(builder.rows, [{gate, 2}, {gate}, {1, 2}])

    def test_cancelling_flip_replaces_gate_and_one_input_with_the_other(self) -> None:
        builder = _DcloBuilder(_rows((0, 1), (1, 3)), 3, 0)
        builder.add_gate((0, 1))
        gate = INPUT_COUNT
        # x0 ^ x1 ^ x0 ^ x3 = x1 ^ x3: the row holds the gate and one of its inputs.
        builder.rows[1] = {gate, 0, 3}
        builder.flip_to_exhaustion()
        self.assertEqual(builder.rows[1], {1, 3})

    def test_second_best_tier_is_used_only_when_the_draw_hits(self) -> None:
        builder = _DcloBuilder(_rows((0, 1, 2)), 3, 0)
        counts = Counter({(0, 1): 3, (0, 2): 2, (1, 2): 2})
        with mock.patch.object(builder.generator, "random", return_value=0.0):
            self.assertIn(builder.choose_pair(counts), {(0, 2), (1, 2)})
        with mock.patch.object(builder.generator, "random", return_value=0.5):
            self.assertEqual(builder.choose_pair(counts), (0, 1))


class DcloDriverTests(unittest.TestCase):
    def test_resume_replays_the_dclo_trial_under_its_own_name(self) -> None:
        seed, cap = 70000, 7
        candidate = search_seed_dclo(seed, cap)
        metrics = independently_check(candidate).to_dict()
        metrics.pop("unreachable_nodes")
        algorithm = algorithm_name(cap)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incumbents = root / "incumbents"
            incumbents.mkdir()
            source = candidate.render(module_name(cap))
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
            artifact = root / "candidate.v"
            with mock.patch("optimizer.depth_bounded._worker") as worker:
                result = run_bounded_search(
                    cap, seed, 1, 1, root / "checkpoint.json", artifact, incumbents, log,
                    100_000, 0xC32A5EED,
                    trial=search_seed_dclo, algorithm=algorithm, module_name=module_name(cap),
                )
            worker.assert_not_called()
            self.assertEqual(result, (seed, metrics))
            self.assertEqual(artifact.read_text(), source)
            checkpoint = json.loads((root / "checkpoint.json").read_text())
            self.assertEqual(checkpoint["algorithm"], "dclo-kraft-depth7-v1")
            self.assertEqual(checkpoint["status"], "completed")


if __name__ == "__main__":
    unittest.main()

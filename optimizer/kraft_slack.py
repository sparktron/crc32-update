"""Kraft-bounded search with a Kraft-slack tie-break ahead of the depth key.

The baseline (``optimizer.depth_bounded``) orders equal-frequency pairs by
new-gate depth, then result weight, then the pair. This variant puts one key
ahead of those: the total increase in Kraft sum over every row the move would
be applied to, with lower preferred. Pools, sampling, rewrites, finishing order
and RNG calls are otherwise unchanged. The pre-registered design is in
``docs/experiments/kraft_slack_tiebreak.md``.

With ``use_slack=False`` every override delegates to the baseline, so the
trial reproduces ``search_seed_bounded`` byte for byte. That is the
experiment's determinism gate.
"""

from __future__ import annotations

import argparse
from collections import Counter
from functools import partial
from itertools import combinations
import json
from pathlib import Path
from typing import Sequence

from generator.build_matrix import build_transformation_matrix
from optimizer.depth_bounded import _BoundedBuilder, _kraft, _kraft_after, run_bounded_search
from optimizer.optimize import (
    Candidate,
    _exclusive_search_lock,
    _prune_operations,
)
from verifier.verify_network import DEFAULT_RANDOM_SEED, DEFAULT_RANDOM_TESTS
from verifier.search_logs import log_file_for

ALGORITHM_VERSION = "v1"
# Pre-registered (stage, cap) -> (seed start, seed count); disjoint from every logged range.
STAGES = {
    ("stage1", 7): (220_000, 1_000),
    ("stage1", 6): (240_000, 1_000),
    ("stage2", 7): (221_000, 10_000),
    ("stage2", 6): (241_000, 10_000),
}


def algorithm_name(depth_cap: int) -> str:
    return f"kraft-slack-tiebreak-depth{depth_cap}-{ALGORITHM_VERSION}"


def module_name(depth_cap: int) -> str:
    return f"candidate_depth{depth_cap}_kraft_slack"


class _SlackBuilder(_BoundedBuilder):
    def __init__(
        self, rows: Sequence[int], depth_cap: int, seed: int, use_slack: bool = True
    ) -> None:
        super().__init__(rows, depth_cap, seed)
        self.use_slack = use_slack

    def _frequencies_and_costs(
        self, new_only: bool
    ) -> tuple[Counter[tuple[int, int]], Counter[tuple[int, int]]]:
        """Return each feasible pair's row count and total Kraft-sum increase."""
        frequencies: Counter[tuple[int, int]] = Counter()
        costs: Counter[tuple[int, int]] = Counter()
        for expression in self.expressions:
            kraft = _kraft(expression, self.depths)
            for pair in combinations(sorted(expression), 2):
                replacement, depth = self._target(pair)
                if new_only and replacement is not None:
                    continue
                after = _kraft_after(expression, kraft, pair, replacement, depth, self.depths)
                if after <= self.limit:
                    frequencies[pair] += 1
                    costs[pair] += after - kraft
        return frequencies, costs

    def choose_shared_pair(self) -> tuple[int, int] | None:
        if not self.use_slack:
            return super().choose_shared_pair()
        frequencies, costs = self._frequencies_and_costs(new_only=True)
        candidates = [pair for pair, frequency in frequencies.items() if frequency > 1]
        if not candidates:
            return None
        maximum_frequency = max(frequencies[pair] for pair in candidates)
        slack = 1 if self.generator.randrange(4) == 0 and maximum_frequency > 2 else 0
        pool = [
            pair for pair in candidates if frequencies[pair] >= maximum_frequency - slack
        ]
        pool.sort(
            key=lambda pair: (
                -frequencies[pair],
                costs[pair],
                1 + max(self.depths[pair[0]], self.depths[pair[1]]),
                (self.vectors[pair[0]] ^ self.vectors[pair[1]]).bit_count(),
                pair,
            )
        )
        width = min(len(pool), 1 + self.generator.randrange(min(12, len(pool))))
        weights = list(range(width, 0, -1))
        return self.generator.choices(pool[:width], weights=weights, k=1)[0]

    def finish_outputs(self) -> tuple[int, ...]:
        if not self.use_slack:
            return super().finish_outputs()
        output_sources = [-1] * len(self.expressions)
        order = list(range(len(self.expressions)))
        self.generator.shuffle(order)
        for output_index in order:
            expression = self.expressions[output_index]
            while len(expression) > 1:
                pairs = [
                    pair
                    for pair in combinations(sorted(expression), 2)
                    if self._fits(expression, pair)
                ]
                if not pairs:
                    raise RuntimeError("no depth-feasible pair; Kraft invariant broken")
                known = []
                for pair in pairs:
                    replacement, depth = self._target(pair)
                    if replacement is not None and replacement not in pair:
                        reduction = 3 if replacement in expression else 1
                        known.append((-reduction, depth, replacement, *pair))
                if known:
                    _, _, _, input_a, input_b = min(known)
                    self._apply((input_a, input_b))
                    continue
                frequencies, costs = self._frequencies_and_costs(new_only=True)
                pairs.sort(
                    key=lambda pair: (
                        -frequencies[pair],
                        costs[pair],
                        1 + max(self.depths[pair[0]], self.depths[pair[1]]),
                        self.depths[pair[0]] + self.depths[pair[1]],
                        self.vectors[pair[0]] ^ self.vectors[pair[1]],
                        pair,
                    )
                )
                best_frequency = frequencies[pairs[0]]
                tier = [pair for pair in pairs if frequencies[pair] == best_frequency]
                pair = tier[self.generator.randrange(min(len(tier), 4))]
                self._apply(pair)
            if not expression:
                raise RuntimeError("optimizer produced an unrepresentable zero output")
            output_sources[output_index] = next(iter(expression))
        return tuple(output_sources)


def search_seed_slack(
    seed: int, depth_cap: int, use_slack: bool = True, rows: Sequence[int] | None = None
) -> Candidate:
    """Run one deterministic seeded trial; ``use_slack=False`` is the baseline."""

    target_rows = tuple(build_transformation_matrix() if rows is None else rows)
    builder = _SlackBuilder(target_rows, depth_cap, seed, use_slack)
    while True:
        builder.free_rewrites()
        pair = builder.choose_shared_pair()
        if pair is None:
            break
        builder._apply(pair)
    output_sources = builder.finish_outputs()
    if tuple(builder.vectors[source] for source in output_sources) != target_rows:
        raise RuntimeError("GF(2) signal-vector check failed")
    if max(builder.depths[source] for source in output_sources) > depth_cap:
        raise RuntimeError("Kraft-slack trial exceeded its cap")
    return Candidate(
        seed=seed,
        operations=_prune_operations(builder.operations, output_sources),
        output_sources=output_sources,
        vectors=tuple(builder.vectors),
        depths=tuple(builder.depths),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["stage1", "stage2"], required=True)
    parser.add_argument("--depth-cap", type=int, choices=[6, 7], required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--search-log",
        type=Path,
        help="defaults to this algorithm's file under results/search_logs/",
    )
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--random-seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED
    )
    args = parser.parse_args()
    cap = args.depth_cap
    args.search_log = args.search_log or log_file_for(algorithm_name(cap))
    seed_start, seed_count = STAGES[(args.stage, cap)]
    run = f"{args.stage}_depth{cap}"
    checkpoints = Path("results/checkpoints/kraft_slack")
    try:
        with _exclusive_search_lock(args.search_log):
            seed, metrics = run_bounded_search(
                cap,
                seed_start,
                seed_count,
                args.workers,
                checkpoints / f"{run}_search.json",
                Path("results/kraft_slack") / f"{run}.v",
                checkpoints / f"{run}_incumbents",
                args.search_log,
                args.random_tests,
                args.random_seed,
                trial=partial(search_seed_slack, use_slack=True),
                algorithm=algorithm_name(cap),
                module_name=module_name(cap),
            )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"Kraft-slack search failed: {error}\n")
    print(json.dumps({"seed": seed, "metrics": metrics}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

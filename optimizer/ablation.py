"""Ablate the Kraft-bounded search toward DCLO, one component at a time.

Each arm is ``optimizer.depth_bounded`` with one component switched to its DCLO
form (see ``optimizer/dclo.py``). The pre-registered design is in
``docs/experiments/ablation_toward_dclo.md``.

- ``tiebreak``: equal-frequency pairs are chosen uniformly instead of by
  new-gate depth and result weight. The frequency level is still drawn
  exactly as the baseline draws it.
- ``second_best``: the baseline's 1/4 chance of a one-below-maximum pool is
  replaced by DCLO's 2% chance of the second-largest level.
- ``finish``: the per-output finishing pass is replaced by continuing the
  global greedy, with frequency-1 pairs allowed. If that stalls, the
  remaining rows fall back to the baseline's pass.
- ``rewrite``: reuse of any existing signal is replaced by DCLO flips over
  gate-input triples, and new gates are no longer deduplicated by vector.
- ``all``: all four switched at once, which is functionally DCLO.

With no component switched (arm ``none``), every override delegates to the
baseline method, so the trial reproduces ``search_seed_bounded`` byte for
byte.
"""

from __future__ import annotations

import argparse
from functools import partial
from itertools import combinations
import json
from pathlib import Path
from typing import Sequence

from generator.build_matrix import INPUT_COUNT, build_transformation_matrix
from optimizer.dclo import SECOND_BEST_PROBABILITY
from optimizer.depth_bounded import _BoundedBuilder, _kraft, run_bounded_search
from optimizer.optimize import (
    Candidate,
    _exclusive_search_lock,
    _prune_operations,
    independently_check,
)
from verifier.verify_network import DEFAULT_RANDOM_SEED, DEFAULT_RANDOM_TESTS
from verifier.search_logs import log_file_for

COMPONENTS = ("tiebreak", "second_best", "finish", "rewrite")
ARMS = ("none", *COMPONENTS, "all")
ALGORITHM_VERSION = "v1"
# Disjoint pre-registered ranges; each leaves room for a 10,000-seed extension.
RECORDED_SEED_STARTS = {
    ("tiebreak", 7): 100_000,
    ("tiebreak", 6): 110_000,
    ("second_best", 7): 120_000,
    ("second_best", 6): 130_000,
    ("finish", 7): 140_000,
    ("finish", 6): 150_000,
    ("rewrite", 7): 160_000,
    ("rewrite", 6): 170_000,
    ("all", 7): 180_000,
    ("all", 6): 190_000,
}


def components_for(arm: str) -> frozenset[str]:
    if arm not in ARMS:
        raise ValueError(f"unknown ablation arm {arm!r}")
    if arm == "none":
        return frozenset()
    return frozenset(COMPONENTS) if arm == "all" else frozenset({arm})


def algorithm_name(arm: str, depth_cap: int) -> str:
    return f"ablation-{arm}-depth{depth_cap}-{ALGORITHM_VERSION}"


def module_name(arm: str, depth_cap: int) -> str:
    return f"candidate_depth{depth_cap}_ablation_{arm}"


class _AblatedBuilder(_BoundedBuilder):
    def __init__(
        self, rows: Sequence[int], depth_cap: int, seed: int, components: frozenset[str]
    ) -> None:
        super().__init__(rows, depth_cap, seed)
        self.components = components
        self.parents: list[tuple[int, int] | None] = [None] * INPUT_COUNT
        self.children: list[list[int]] = [[] for _ in range(INPUT_COUNT)]
        self.finish_fallback_rows = 0

    def _target(self, pair: tuple[int, int]) -> tuple[int | None, int]:
        if "rewrite" in self.components:
            return None, 1 + max(self.depths[pair[0]], self.depths[pair[1]])
        return super()._target(pair)

    def _create(self, pair: tuple[int, int]) -> int:
        before = len(self.vectors)
        output = super()._create(pair)
        if len(self.vectors) > before:
            self.parents.append(pair)
            self.children.append([])
            self.children[pair[0]].append(output)
            self.children[pair[1]].append(output)
        return output

    def _merge_fresh(self, expression: set[int]) -> tuple[tuple[int, int], int]:
        pair, output = super()._merge_fresh(expression)
        self.parents.append(pair)
        self.children.append([])
        self.children[pair[0]].append(output)
        self.children[pair[1]].append(output)
        return pair, output

    def free_rewrites(self) -> None:
        if "rewrite" not in self.components:
            super().free_rewrites()
            return
        while True:
            flips = []
            for index, expression in enumerate(self.expressions):
                if len(expression) < 2:
                    continue
                kraft = _kraft(expression, self.depths)
                gates = {
                    gate
                    for signal in expression
                    for gate in ([signal] if self.parents[signal] else [])
                    + self.children[signal]
                }
                for gate in gates:
                    triple = (gate, *self.parents[gate])
                    present = [signal for signal in triple if signal in expression]
                    if len(present) < 2:
                        continue
                    after = kraft + sum(
                        -(1 << self.depths[signal])
                        if signal in expression
                        else (1 << self.depths[signal])
                        for signal in triple
                    )
                    if after <= self.limit:
                        flips.append((2 * len(present) - 3, index, gate))
            if not flips:
                return
            best = max(flip[0] for flip in flips)
            tier = sorted(flip for flip in flips if flip[0] == best)
            _, index, gate = tier[self.generator.randrange(len(tier))]
            expression = self.expressions[index]
            for signal in (gate, *self.parents[gate]):
                if signal in expression:
                    expression.remove(signal)
                else:
                    expression.add(signal)
            if not expression:
                raise RuntimeError("flip produced an unrepresentable zero output")

    def choose_shared_pair(self, min_frequency: int = 2) -> tuple[int, int] | None:
        selection = {"tiebreak", "second_best"} & self.components
        if not selection and min_frequency == 2:
            return super().choose_shared_pair()
        frequencies = self._feasible_frequencies(new_only=True)
        candidates = [pair for pair, frequency in frequencies.items() if frequency >= min_frequency]
        if not candidates:
            return None
        levels = sorted({frequencies[pair] for pair in candidates}, reverse=True)
        if "second_best" in self.components:
            level = levels[0]
            if len(levels) > 1 and self.generator.random() < SECOND_BEST_PROBABILITY:
                level = levels[1]
            pool = [pair for pair in candidates if frequencies[pair] == level]
        else:
            maximum_frequency = levels[0]
            slack = 1 if self.generator.randrange(4) == 0 and maximum_frequency > 2 else 0
            pool = [
                pair for pair in candidates if frequencies[pair] >= maximum_frequency - slack
            ]
        if selection == {"tiebreak", "second_best"}:
            pool.sort()
            return pool[self.generator.randrange(len(pool))]
        pool.sort(
            key=lambda pair: (
                -frequencies[pair],
                1 + max(self.depths[pair[0]], self.depths[pair[1]]),
                (self.vectors[pair[0]] ^ self.vectors[pair[1]]).bit_count(),
                pair,
            )
        )
        width = min(len(pool), 1 + self.generator.randrange(min(12, len(pool))))
        weights = list(range(width, 0, -1))
        chosen = self.generator.choices(pool[:width], weights=weights, k=1)[0]
        if "tiebreak" in self.components:
            tier = sorted(pair for pair in pool if frequencies[pair] == frequencies[chosen])
            return tier[self.generator.randrange(len(tier))]
        return chosen

    def finish_outputs(self) -> tuple[int, ...]:
        if "finish" in self.components:
            while True:
                self.free_rewrites()
                pair = self.choose_shared_pair(min_frequency=1)
                if pair is None:
                    break
                self._apply(pair)
            self.finish_fallback_rows = sum(len(row) > 1 for row in self.expressions)
            if not self.finish_fallback_rows:
                if any(not row for row in self.expressions):
                    raise RuntimeError("optimizer produced an unrepresentable zero output")
                return tuple(next(iter(row)) for row in self.expressions)
        if "tiebreak" not in self.components:
            return super().finish_outputs()
        return self._finish_with_uniform_tiebreak()

    def _finish_with_uniform_tiebreak(self) -> tuple[int, ...]:
        """The baseline per-output pass, with uniform choice in the frequency tier."""
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
                    self._merge_fresh(expression)
                    continue
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
                frequencies = self._feasible_frequencies(new_only=True)
                best_frequency = max(frequencies[pair] for pair in pairs)
                tier = sorted(pair for pair in pairs if frequencies[pair] == best_frequency)
                self._apply(tier[self.generator.randrange(len(tier))])
            if not expression:
                raise RuntimeError("optimizer produced an unrepresentable zero output")
            output_sources[output_index] = next(iter(expression))
        return tuple(output_sources)


def build_ablated(
    seed: int, depth_cap: int, arm: str, rows: Sequence[int] | None = None
) -> tuple[Candidate, _AblatedBuilder]:
    """Run one seeded trial of ``arm`` and return it with its builder state."""

    target_rows = tuple(build_transformation_matrix() if rows is None else rows)
    builder = _AblatedBuilder(target_rows, depth_cap, seed, components_for(arm))
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
        raise RuntimeError("ablated trial exceeded its cap")
    candidate = Candidate(
        seed=seed,
        operations=_prune_operations(builder.operations, output_sources),
        output_sources=output_sources,
        vectors=tuple(builder.vectors),
        depths=tuple(builder.depths),
    )
    return candidate, builder


def search_seed_ablated(seed: int, depth_cap: int, arm: str) -> Candidate:
    return build_ablated(seed, depth_cap, arm)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=[arm for arm in ARMS if arm != "none"], required=True)
    parser.add_argument("--depth-cap", type=int, required=True)
    parser.add_argument("--seed-start", type=int)
    parser.add_argument("--seed-count", type=int, default=1000)
    parser.add_argument(
        "--run-name",
        help="names the checkpoint, incumbent directory and artifact; "
        "defaults to <arm>_depth<cap>",
    )
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
    arm, cap = args.arm, args.depth_cap
    args.search_log = args.search_log or log_file_for(algorithm_name(arm, cap))
    if args.seed_start is None:
        if (arm, cap) not in RECORDED_SEED_STARTS:
            parser.error(f"--seed-start is required for unrecorded arm/cap {arm}/{cap}")
        args.seed_start = RECORDED_SEED_STARTS[(arm, cap)]
    stem = args.run_name or f"{arm}_depth{cap}"
    checkpoints = Path("results/checkpoints/ablation")
    try:
        with _exclusive_search_lock(args.search_log):
            seed, metrics = run_bounded_search(
                cap,
                args.seed_start,
                args.seed_count,
                args.workers,
                checkpoints / f"{stem}_search.json",
                Path("results/ablation") / f"{stem}.v",
                checkpoints / f"{stem}_incumbents",
                args.search_log,
                args.random_tests,
                args.random_seed,
                trial=partial(search_seed_ablated, arm=arm),
                algorithm=algorithm_name(arm, cap),
                module_name=module_name(arm, cap),
            )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"Ablation search failed: {error}\n")
    print(json.dumps({"seed": seed, "metrics": metrics}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

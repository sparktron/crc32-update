"""Run DCLO (Boyar, Find and Peralta, 2019) on the frozen matrix under a depth cap.

DCLO is RAND-GREEDY-ALG plus three improvements (Cryptogr. Commun. 11(1),
Sects. 3.4-3.6; full text at https://pmc.ncbi.nlm.nih.gov/articles/PMC6463518/).

- Each output row holds the signals still to be XORed. A candidate gate is a
  pair of signals. Its improvement is the number of rows that contain both
  and stay depth-feasible after the update. The gate is chosen uniformly at
  random among the pairs with the largest improvement, and it is applied to
  every row where it stays feasible. Feasibility is the paper's FEASIBLE test,
  which is the Kraft test ``sum(2 ** d_i) <= 2 ** cap`` used by
  ``optimizer.depth_bounded``.
- Preprocessing (an output equal to the XOR of two other outputs) is a no-op
  here: no pair of rows of the frozen matrix XORs to a third row, so it is
  not implemented.
- A flip toggles a gate ``c = c1 ^ c2`` together with ``c1`` and ``c2`` in one
  row. It is applied when that lowers the row's weight, and only if the row
  stays feasible. Flips run to exhaustion before every gate choice.
- With probability 2%, the gate is chosen among the pairs with the
  second-largest improvement instead.

Unlike ``optimizer.depth_bounded``, new gates are never deduplicated by
vector. DCLO tracks matrix columns, not signal vectors. The experiment is
recorded in ``docs/experiments/dclo_depth_bounded.md``.
"""

from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import random
from typing import Sequence

from generator.build_matrix import INPUT_COUNT, build_transformation_matrix
from optimizer.depth_bounded import _kraft, run_bounded_search
from optimizer.optimize import (
    Candidate,
    Operation,
    _exclusive_search_lock,
    _prune_operations,
    independently_check,
)
from verifier.verify_network import DEFAULT_RANDOM_SEED, DEFAULT_RANDOM_TESTS
from verifier.search_logs import log_file_for

ALGORITHM_PREFIX = "dclo-kraft"
ALGORITHM_VERSION = "v1"
SECOND_BEST_PROBABILITY = 0.02
# Each cap is a separately recorded budget over a seed range disjoint from
# every Kraft-bounded and Candidate A budget.
RECORDED_SEED_STARTS = {7: 70_000, 6: 80_000}


def algorithm_name(depth_cap: int) -> str:
    return f"{ALGORITHM_PREFIX}-depth{depth_cap}-{ALGORITHM_VERSION}"


def module_name(depth_cap: int) -> str:
    return f"candidate_depth{depth_cap}_dclo"


class _DcloBuilder:
    def __init__(self, rows: Sequence[int], depth_cap: int, seed: int) -> None:
        self.limit = 1 << depth_cap
        self.generator = random.Random(seed)
        self.vectors = [1 << index for index in range(INPUT_COUNT)]
        self.depths = [0] * INPUT_COUNT
        self.parents: list[tuple[int, int] | None] = [None] * INPUT_COUNT
        self.children: list[list[int]] = [[] for _ in range(INPUT_COUNT)]
        self.rows = [
            {index for index in range(INPUT_COUNT) if row & (1 << index)} for row in rows
        ]
        self.operations: list[Operation] = []
        for index, row in enumerate(self.rows):
            if _kraft(row, self.depths) > self.limit:
                raise ValueError(f"output {index} cannot meet depth cap {depth_cap}")

    def _gate_depth(self, pair: tuple[int, int]) -> int:
        return 1 + max(self.depths[pair[0]], self.depths[pair[1]])

    def _update_fits(self, kraft: int, pair: tuple[int, int]) -> bool:
        return (
            kraft
            - (1 << self.depths[pair[0]])
            - (1 << self.depths[pair[1]])
            + (1 << self._gate_depth(pair))
            <= self.limit
        )

    def improvements(self) -> Counter[tuple[int, int]]:
        counts: Counter[tuple[int, int]] = Counter()
        for row in self.rows:
            if len(row) < 2:
                continue
            kraft = _kraft(row, self.depths)
            for pair in combinations(sorted(row), 2):
                if self._update_fits(kraft, pair):
                    counts[pair] += 1
        return counts

    def choose_pair(self, counts: Counter[tuple[int, int]]) -> tuple[int, int]:
        levels = sorted(set(counts.values()), reverse=True)
        level = levels[0]
        if len(levels) > 1 and self.generator.random() < SECOND_BEST_PROBABILITY:
            level = levels[1]
        tier = sorted(pair for pair, count in counts.items() if count == level)
        return tier[self.generator.randrange(len(tier))]

    def add_gate(self, pair: tuple[int, int]) -> None:
        gate = len(self.vectors)
        self.vectors.append(self.vectors[pair[0]] ^ self.vectors[pair[1]])
        self.depths.append(self._gate_depth(pair))
        self.parents.append(pair)
        self.children.append([])
        self.children[pair[0]].append(gate)
        self.children[pair[1]].append(gate)
        self.operations.append(Operation(gate, pair[0], pair[1]))
        applied = 0
        for row in self.rows:
            if (
                pair[0] in row
                and pair[1] in row
                and self._update_fits(_kraft(row, self.depths), pair)
            ):
                row.remove(pair[0])
                row.remove(pair[1])
                row.add(gate)
                applied += 1
        if not applied:
            raise RuntimeError("DCLO gate has no feasible row")

    def _flips(self) -> list[tuple[int, int, int]]:
        """Return (weight decrease, row index, gate) for every feasible flip."""
        flips = []
        for index, row in enumerate(self.rows):
            if len(row) < 2:
                continue
            kraft = _kraft(row, self.depths)
            gates = {
                gate
                for signal in row
                for gate in ([signal] if self.parents[signal] else []) + self.children[signal]
            }
            for gate in gates:
                triple = (gate, *self.parents[gate])
                present = [signal for signal in triple if signal in row]
                if len(present) < 2:
                    continue
                after = kraft + sum(
                    -(1 << self.depths[signal]) if signal in row else (1 << self.depths[signal])
                    for signal in triple
                )
                if after <= self.limit:
                    flips.append((2 * len(present) - 3, index, gate))
        return flips

    def flip_to_exhaustion(self) -> None:
        while True:
            flips = self._flips()
            if not flips:
                return
            best = max(flip[0] for flip in flips)
            tier = sorted(flip for flip in flips if flip[0] == best)
            _, index, gate = tier[self.generator.randrange(len(tier))]
            row = self.rows[index]
            for signal in (gate, *self.parents[gate]):
                if signal in row:
                    row.remove(signal)
                else:
                    row.add(signal)
            if not row:
                raise RuntimeError("flip produced an unrepresentable zero output")


def search_seed_dclo(
    seed: int, depth_cap: int, rows: Sequence[int] | None = None
) -> Candidate:
    """Run one deterministic seeded DCLO trial whose outputs all meet ``depth_cap``."""

    target_rows = tuple(build_transformation_matrix() if rows is None else rows)
    builder = _DcloBuilder(target_rows, depth_cap, seed)
    while True:
        builder.flip_to_exhaustion()
        counts = builder.improvements()
        if not counts:
            break
        builder.add_gate(builder.choose_pair(counts))
    if any(len(row) != 1 for row in builder.rows):
        raise RuntimeError("DCLO stopped with an unfinished row; Kraft invariant broken")
    output_sources = tuple(next(iter(row)) for row in builder.rows)
    if tuple(builder.vectors[source] for source in output_sources) != target_rows:
        raise RuntimeError("GF(2) signal-vector check failed")
    if max(builder.depths[source] for source in output_sources) > depth_cap:
        raise RuntimeError("DCLO trial exceeded its cap")
    return Candidate(
        seed=seed,
        operations=_prune_operations(builder.operations, output_sources),
        output_sources=output_sources,
        vectors=tuple(builder.vectors),
        depths=tuple(builder.depths),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth-cap", type=int, required=True)
    parser.add_argument(
        "--replay-seed",
        type=int,
        help="regenerate one seed's network into --artifact without running or "
        "logging a search",
    )
    parser.add_argument(
        "--seed-start",
        type=int,
        help="defaults to the recorded budget start for the cap "
        f"({', '.join(f'{cap}: {start}' for cap, start in RECORDED_SEED_STARTS.items())})",
    )
    parser.add_argument("--seed-count", type=int, default=10000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="defaults to results/checkpoints/depth<cap>_dclo_search.json",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        help="defaults to results/phase7/candidate_depth<cap>_dclo.v",
    )
    parser.add_argument(
        "--incumbent-dir",
        type=Path,
        help="defaults to results/checkpoints/depth<cap>_dclo_incumbents",
    )
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
    if args.seed_start is None:
        if cap not in RECORDED_SEED_STARTS:
            parser.error(f"--seed-start is required for unrecorded depth cap {cap}")
        args.seed_start = RECORDED_SEED_STARTS[cap]
    args.checkpoint = args.checkpoint or Path(f"results/checkpoints/depth{cap}_dclo_search.json")
    args.artifact = args.artifact or Path(f"results/phase7/candidate_depth{cap}_dclo.v")
    args.incumbent_dir = args.incumbent_dir or Path(
        f"results/checkpoints/depth{cap}_dclo_incumbents"
    )
    if args.replay_seed is not None:
        try:
            candidate = search_seed_dclo(args.replay_seed, cap)
            independently_check(candidate)
            args.artifact.parent.mkdir(parents=True, exist_ok=True)
            args.artifact.write_text(candidate.render(module_name(cap)))
        except (OSError, RuntimeError, ValueError) as error:
            parser.exit(1, f"DCLO replay failed: {error}\n")
        return 0
    try:
        # Each experiment appends to its own log; lock that log.
        with _exclusive_search_lock(args.search_log):
            seed, metrics = run_bounded_search(
                cap,
                args.seed_start,
                args.seed_count,
                args.workers,
                args.checkpoint,
                args.artifact,
                args.incumbent_dir,
                args.search_log,
                args.random_tests,
                args.random_seed,
                trial=search_seed_dclo,
                algorithm=algorithm_name(cap),
                module_name=module_name(cap),
            )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"DCLO search failed: {error}\n")
    print(json.dumps({"seed": seed, "metrics": metrics}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

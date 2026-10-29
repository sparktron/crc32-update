"""Kraft-slack tie-break that counts slack only in rows near their Kraft limit.

This is ``optimizer.kraft_slack`` with one change: a pair's cost sums the
Kraft-sum increase only over rows whose Kraft sum is already at least
``theta * 2 ** cap``. While none of a pair's rows is that full, its cost is 0
and the baseline's depth key decides. The search therefore runs depth-first
while rows have room and switches to slack-first per row as they fill.
``theta = 1/2`` is fixed in advance. The pre-registered design is in
``docs/experiments/kraft_adaptive_tiebreak.md``.

``theta = 0`` reproduces the slack variant and ``theta = 2`` the baseline,
byte for byte. These are the experiment's determinism gates.
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
from optimizer.depth_bounded import _kraft, _kraft_after, run_bounded_search
from optimizer.kraft_slack import _SlackBuilder
from optimizer.optimize import Candidate, _exclusive_search_lock, _prune_operations
from verifier.verify_network import DEFAULT_RANDOM_SEED, DEFAULT_RANDOM_TESTS
from verifier.search_logs import log_file_for

THETA = 0.5
# v1 raised "no depth-feasible pair" on seed 284,862, which stopped stage 2.
# v2 adds the shared finishing fallback (``_BoundedBuilder._merge_fresh``). It
# matches v1 on every trial v1 completed, and also completes v1's failing
# trials. ``stage2_rerun`` repeats stage 2's seeds under v2.
# Pre-registered (stage, cap) -> (seed start, seed count, version).
STAGES = {
    ("stage1", 7): (260_000, 1_000, "v1"),
    ("stage1", 6): (280_000, 1_000, "v1"),
    ("stage2", 7): (261_000, 10_000, "v1"),
    ("stage2", 6): (281_000, 10_000, "v1"),
    ("stage2_rerun", 6): (281_000, 10_000, "v2"),
}


def algorithm_name(depth_cap: int, version: str = "v1") -> str:
    return f"kraft-adaptive-tiebreak-half-depth{depth_cap}-{version}"


def module_name(depth_cap: int) -> str:
    return f"candidate_depth{depth_cap}_kraft_adaptive"


class _AdaptiveBuilder(_SlackBuilder):
    def __init__(
        self, rows: Sequence[int], depth_cap: int, seed: int, theta: float = THETA
    ) -> None:
        super().__init__(rows, depth_cap, seed, use_slack=True)
        self.tight_floor = theta * self.limit

    def _frequencies_and_costs(
        self, new_only: bool
    ) -> tuple[Counter[tuple[int, int]], Counter[tuple[int, int]]]:
        """Return each feasible pair's row count and its Kraft increase in tight rows."""
        frequencies: Counter[tuple[int, int]] = Counter()
        costs: Counter[tuple[int, int]] = Counter()
        for expression in self.expressions:
            kraft = _kraft(expression, self.depths)
            tight = kraft >= self.tight_floor
            for pair in combinations(sorted(expression), 2):
                replacement, depth = self._target(pair)
                if new_only and replacement is not None:
                    continue
                after = _kraft_after(expression, kraft, pair, replacement, depth, self.depths)
                if after <= self.limit:
                    frequencies[pair] += 1
                    if tight:
                        costs[pair] += after - kraft
        return frequencies, costs


def search_seed_adaptive(
    seed: int, depth_cap: int, theta: float = THETA, rows: Sequence[int] | None = None
) -> Candidate:
    """Run one deterministic seeded trial of the tight-row tie-break."""

    target_rows = tuple(build_transformation_matrix() if rows is None else rows)
    builder = _AdaptiveBuilder(target_rows, depth_cap, seed, theta)
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
        raise RuntimeError("adaptive trial exceeded its cap")
    return Candidate(
        seed=seed,
        operations=_prune_operations(builder.operations, output_sources),
        output_sources=output_sources,
        vectors=tuple(builder.vectors),
        depths=tuple(builder.depths),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", choices=sorted({stage for stage, _ in STAGES}), required=True
    )
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
    if (args.stage, cap) not in STAGES:
        parser.error(f"stage {args.stage} is not registered at cap {cap}")
    seed_start, seed_count, version = STAGES[(args.stage, cap)]
    if version == "v1":
        parser.error(
            "v1 stages are frozen: this runner uses the v2 finishing algorithm; "
            "use the recorded v1 commit for historical reproduction, or "
            "--stage stage2_rerun --depth-cap 6 for the registered v2 rerun"
        )
    args.search_log = args.search_log or log_file_for(algorithm_name(cap, version))
    run = f"{args.stage}_depth{cap}"
    checkpoints = Path("results/checkpoints/kraft_adaptive")
    try:
        with _exclusive_search_lock(args.search_log):
            seed, metrics = run_bounded_search(
                cap,
                seed_start,
                seed_count,
                args.workers,
                checkpoints / f"{run}_search.json",
                Path("results/kraft_adaptive") / f"{run}.v",
                checkpoints / f"{run}_incumbents",
                args.search_log,
                args.random_tests,
                args.random_seed,
                trial=partial(search_seed_adaptive, theta=THETA),
                algorithm=algorithm_name(cap, version),
                module_name=module_name(cap),
            )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"Adaptive search failed: {error}\n")
    print(json.dumps({"seed": seed, "metrics": metrics}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

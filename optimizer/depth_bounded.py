"""Run a resumable depth-bounded XOR2 search with a hard per-output depth cap.

The Candidate A heuristic reaches depth 8 at best: none of the 40,000 Phase 3
and Phase 4 attempts produced depth 7 or lower, so filtering its output by
depth cannot find a depth-7 network. This search enforces the cap during
construction instead. A set of signals with depths ``d_i`` can be XORed by a
binary tree of depth at most ``D`` exactly when ``sum(2 ** d_i) <= 2 ** D``
(the Kraft inequality), so every sharing, rewrite, and finishing move is
applied to an output expression only when that expression still satisfies the
inequality afterwards. Sharing therefore never makes an output unreachable
within the cap, and every completed trial meets the bound by construction.
"""

from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import random
import time
from typing import Callable, Sequence
from functools import partial

from generator.build_matrix import INPUT_COUNT, build_transformation_matrix
from optimizer.optimize import (
    Candidate,
    Operation,
    _exclusive_search_lock,
    _prune_operations,
    _replace_pair,
    independently_check,
)
from optimizer.refine_candidates import _append_log, _metrics, _write_checkpoint
from optimizer.search_lifecycle import (
    budget_records,
    callable_identity,
    inspect_log,
    run_budget,
)
from verifier.run_formal import run as run_formal
from verifier.verify_network import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    verification_report,
    parse_network_file,
    verify_exact_equivalence,
)

ALGORITHM_PREFIX = "kraft-bounded-bp-cse"
ALGORITHM_VERSION = "v1"
DEFAULT_DEPTH_CAP = 7
# Each cap is a separately recorded budget over a disjoint seed range.
RECORDED_SEED_STARTS = {7: 40_000, 6: 50_000}


def algorithm_name(depth_cap: int) -> str:
    return f"{ALGORITHM_PREFIX}-depth{depth_cap}-{ALGORITHM_VERSION}"


def _kraft(expression: set[int], depths: Sequence[int]) -> int:
    return sum(1 << depths[signal] for signal in expression)


def _kraft_after(
    expression: set[int],
    kraft: int,
    pair: tuple[int, int],
    replacement: int | None,
    replacement_depth: int,
    depths: Sequence[int],
) -> int:
    """Return the expression's Kraft sum after replacing ``pair``.

    ``replacement`` is an existing signal or ``None`` for a not-yet-created
    node. An existing replacement already in the expression cancels over GF(2).
    """
    updated = kraft - (1 << depths[pair[0]]) - (1 << depths[pair[1]])
    if replacement is not None and replacement in expression:
        return updated - (1 << depths[replacement])
    return updated + (1 << replacement_depth)


class _BoundedBuilder:
    def __init__(self, rows: Sequence[int], depth_cap: int, seed: int) -> None:
        self.limit = 1 << depth_cap
        self.generator = random.Random(seed)
        self.vectors = [1 << index for index in range(INPUT_COUNT)]
        self.depths = [0] * INPUT_COUNT
        self.vector_to_signal = {
            vector: index for index, vector in enumerate(self.vectors)
        }
        self.expressions = [
            {index for index in range(INPUT_COUNT) if row & (1 << index)}
            for row in rows
        ]
        self.operations: list[Operation] = []
        for index, expression in enumerate(self.expressions):
            if _kraft(expression, self.depths) > self.limit:
                raise ValueError(f"output {index} cannot meet depth cap {depth_cap}")

    def _target(self, pair: tuple[int, int]) -> tuple[int | None, int]:
        replacement = self.vector_to_signal.get(
            self.vectors[pair[0]] ^ self.vectors[pair[1]]
        )
        if replacement is not None:
            return replacement, self.depths[replacement]
        return None, 1 + max(self.depths[pair[0]], self.depths[pair[1]])

    def _fits(self, expression: set[int], pair: tuple[int, int]) -> bool:
        replacement, depth = self._target(pair)
        kraft = _kraft(expression, self.depths)
        return (
            _kraft_after(expression, kraft, pair, replacement, depth, self.depths)
            <= self.limit
        )

    def _feasible_frequencies(self, new_only: bool) -> Counter[tuple[int, int]]:
        frequencies: Counter[tuple[int, int]] = Counter()
        for expression in self.expressions:
            kraft = _kraft(expression, self.depths)
            for pair in combinations(sorted(expression), 2):
                replacement, depth = self._target(pair)
                if new_only and replacement is not None:
                    continue
                if (
                    _kraft_after(
                        expression, kraft, pair, replacement, depth, self.depths
                    )
                    <= self.limit
                ):
                    frequencies[pair] += 1
        return frequencies

    def _create(self, pair: tuple[int, int]) -> int:
        replacement, depth = self._target(pair)
        if replacement is not None:
            return replacement
        output = len(self.vectors)
        self.vectors.append(self.vectors[pair[0]] ^ self.vectors[pair[1]])
        self.depths.append(depth)
        self.vector_to_signal[self.vectors[output]] = output
        self.operations.append(Operation(output, pair[0], pair[1]))
        return output

    def _apply(self, pair: tuple[int, int]) -> None:
        """Replace ``pair`` in every expression where the result stays within the cap."""
        targets = [
            expression
            for expression in self.expressions
            if pair[0] in expression
            and pair[1] in expression
            and self._fits(expression, pair)
        ]
        if not targets:
            raise RuntimeError("depth-bounded move has no feasible expression")
        replacement = self._create(pair)
        for expression in targets:
            _replace_pair(expression, pair, replacement)

    def free_rewrites(self) -> None:
        while True:
            best: tuple[int, int, int, int] | None = None
            for expression in self.expressions:
                kraft = _kraft(expression, self.depths)
                for pair in combinations(sorted(expression), 2):
                    replacement = self.vector_to_signal.get(
                        self.vectors[pair[0]] ^ self.vectors[pair[1]]
                    )
                    if replacement is None or replacement in pair:
                        continue
                    depth = self.depths[replacement]
                    if (
                        _kraft_after(
                            expression, kraft, pair, replacement, depth, self.depths
                        )
                        > self.limit
                    ):
                        continue
                    reduction = 3 if replacement in expression else 1
                    candidate = (reduction, -replacement, -pair[0], -pair[1])
                    if best is None or candidate > best:
                        best = candidate
            if best is None:
                return
            self._apply((-best[2], -best[3]))

    def choose_shared_pair(self) -> tuple[int, int] | None:
        frequencies = self._feasible_frequencies(new_only=True)
        candidates = [pair for pair, frequency in frequencies.items() if frequency > 1]
        if not candidates:
            return None
        maximum_frequency = max(frequencies[pair] for pair in candidates)
        slack = 1 if self.generator.randrange(4) == 0 and maximum_frequency > 2 else 0
        pool = [
            pair
            for pair in candidates
            if frequencies[pair] >= maximum_frequency - slack
        ]
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
        return self.generator.choices(pool[:width], weights=weights, k=1)[0]

    def finish_outputs(self) -> tuple[int, ...]:
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
                frequencies = self._feasible_frequencies(new_only=True)
                pairs.sort(
                    key=lambda pair: (
                        -frequencies[pair],
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


def search_seed_bounded(
    seed: int, depth_cap: int = DEFAULT_DEPTH_CAP, rows: Sequence[int] | None = None
) -> Candidate:
    """Run one deterministic seeded trial whose outputs all meet ``depth_cap``."""

    target_rows = tuple(build_transformation_matrix() if rows is None else rows)
    builder = _BoundedBuilder(target_rows, depth_cap, seed)
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
        raise RuntimeError("depth-bounded trial exceeded its cap")
    return Candidate(
        seed=seed,
        operations=_prune_operations(builder.operations, output_sources),
        output_sources=output_sources,
        vectors=tuple(builder.vectors),
        depths=tuple(builder.depths),
    )


Trial = Callable[[int, int], Candidate]


def _worker(
    seed: int, depth_cap: int, module_name: str, trial: Trial = search_seed_bounded
) -> tuple[int, dict[str, object], str, float]:
    started = time.perf_counter()
    candidate = trial(seed, depth_cap)
    metrics = independently_check(candidate).to_dict()
    metrics.pop("unreachable_nodes")
    return seed, metrics, candidate.render(module_name), time.perf_counter() - started


def _score(metrics: dict[str, object], seed: int) -> tuple[int, ...]:
    return (
        int(metrics["xor2_count"]),
        int(metrics["maximum_depth"]),
        int(metrics["maximum_fanout"]),
        int(metrics["total_excess_fanout_above_4"]),
        seed,
    )


def logged_attempts(
    log_path: Path, algorithm: str, seed_start: int, seed_count: int
) -> list[dict[str, object]]:
    """Return successful terminals, validating retries and the contiguous prefix."""
    return budget_records(inspect_log(log_path)[0], algorithm, seed_start, seed_count)[
        0
    ]


def run_bounded_search(
    depth_cap: int,
    seed_start: int,
    seed_count: int,
    workers: int,
    checkpoint_path: Path,
    artifact_path: Path,
    incumbent_dir: Path,
    log_path: Path,
    random_tests: int,
    random_seed: int,
    *,
    trial: Trial = search_seed_bounded,
    algorithm: str | None = None,
    module_name: str | None = None,
) -> tuple[int | None, dict[str, object] | None]:
    """Search a reproducible seed range and keep the best verified bounded network.

    ``trial`` builds one seeded network under the cap. The defaults run the
    recorded Kraft-bounded search; other trial functions log under their own
    ``algorithm`` name and render under their own ``module_name``.
    """

    if random_tests < DEFAULT_RANDOM_TESTS:
        raise ValueError(f"random_tests must be at least {DEFAULT_RANDOM_TESTS}")
    algorithm = algorithm or algorithm_name(depth_cap)
    module_name = module_name or f"candidate_depth{depth_cap}_bounded"
    configuration = {
        "algorithm": algorithm,
        "depth_cap": depth_cap,
        "seed_start": seed_start,
        "seed_count": seed_count,
        "random_tests": random_tests,
        "random_seed": random_seed,
    }

    def restore(record):
        path = incumbent_dir / f"seed_{record['seed']}.v"
        normalized = parse_network_file(path).normalize()
        verify_exact_equivalence(normalized)
        metrics = normalized.metrics().to_dict()
        metrics.pop("unreachable_nodes")
        return metrics, path.read_text()

    def accept(seed, metrics, source):
        path = incumbent_dir / f"seed_{seed}.v"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        report = verification_report(path, random_tests, random_seed)
        run_formal(path)
        if _metrics(report) != metrics:
            raise RuntimeError("full verification metrics disagree with worker")
        return path

    best_seed, best_metrics, source = run_budget(
        configuration=configuration,
        workers=workers,
        checkpoint_path=checkpoint_path,
        log_path=log_path,
        worker=partial(
            _worker, depth_cap=depth_cap, module_name=module_name, trial=trial
        ),
        score=_score,
        eligible=lambda metrics: int(metrics["maximum_depth"]) <= depth_cap,
        restore=restore,
        accept=accept,
        append=_append_log,
        save=_write_checkpoint,
        identity_inputs={
            "module_name": module_name,
            "trial": callable_identity(trial),
        },
    )
    if best_seed is None:
        raise RuntimeError("no trial produced a depth-bounded network")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(source)
    return best_seed, best_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth-cap", type=int, default=DEFAULT_DEPTH_CAP)
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
        help="defaults to results/checkpoints/depth<cap>_bounded_search.json",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        help="defaults to results/phase6/candidate_depth<cap>_bounded.v",
    )
    parser.add_argument(
        "--incumbent-dir",
        type=Path,
        help="defaults to results/checkpoints/depth<cap>_bounded_incumbents",
    )
    parser.add_argument(
        "--search-log", type=Path, default=Path("results/search_log.jsonl")
    )
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--random-seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED
    )
    args = parser.parse_args()
    cap = args.depth_cap
    if args.seed_start is None:
        if cap not in RECORDED_SEED_STARTS:
            parser.error(f"--seed-start is required for unrecorded depth cap {cap}")
        args.seed_start = RECORDED_SEED_STARTS[cap]
    args.checkpoint = args.checkpoint or Path(
        f"results/checkpoints/depth{cap}_bounded_search.json"
    )
    args.artifact = args.artifact or Path(
        f"results/phase6/candidate_depth{cap}_bounded.v"
    )
    args.incumbent_dir = args.incumbent_dir or Path(
        f"results/checkpoints/depth{cap}_bounded_incumbents"
    )
    if args.replay_seed is not None:
        try:
            candidate = search_seed_bounded(args.replay_seed, cap)
            independently_check(candidate)
            args.artifact.parent.mkdir(parents=True, exist_ok=True)
            args.artifact.write_text(candidate.render(f"candidate_depth{cap}_bounded"))
        except (OSError, RuntimeError, ValueError) as error:
            parser.exit(1, f"Depth-bounded replay failed: {error}\n")
        return 0
    try:
        # Every search appends to one canonical log, so lock the log itself.
        with _exclusive_search_lock(args.search_log):
            seed, metrics = run_bounded_search(
                args.depth_cap,
                args.seed_start,
                args.seed_count,
                args.workers,
                args.checkpoint,
                args.artifact,
                args.incumbent_dir,
                args.search_log,
                args.random_tests,
                args.random_seed,
            )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"Depth-bounded search failed: {error}\n")
    print(json.dumps({"seed": seed, "metrics": metrics}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

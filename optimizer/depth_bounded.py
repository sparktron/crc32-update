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
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from itertools import combinations, repeat
import json
from pathlib import Path
import random
import time
from typing import Sequence

from generator.build_matrix import INPUT_COUNT, build_transformation_matrix
from optimizer.optimize import (
    Candidate,
    Operation,
    _exclusive_search_lock,
    _prune_operations,
    _replace_pair,
    independently_check,
)
from optimizer.refine_candidates import _append_log, _metrics, _timestamp, _write_checkpoint
from verifier.run_formal import run as run_formal
from verifier.verify_network import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    verification_report,
)

ALGORITHM_PREFIX = "kraft-bounded-bp-cse"
ALGORITHM_VERSION = "v1"
DEFAULT_DEPTH_CAP = 7


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
        self.vector_to_signal = {vector: index for index, vector in enumerate(self.vectors)}
        self.expressions = [
            {index for index in range(INPUT_COUNT) if row & (1 << index)} for row in rows
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
        return _kraft_after(expression, kraft, pair, replacement, depth, self.depths) <= self.limit

    def _feasible_frequencies(self, new_only: bool) -> Counter[tuple[int, int]]:
        frequencies: Counter[tuple[int, int]] = Counter()
        for expression in self.expressions:
            kraft = _kraft(expression, self.depths)
            for pair in combinations(sorted(expression), 2):
                replacement, depth = self._target(pair)
                if new_only and replacement is not None:
                    continue
                if (
                    _kraft_after(expression, kraft, pair, replacement, depth, self.depths)
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
            if pair[0] in expression and pair[1] in expression and self._fits(expression, pair)
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
                        _kraft_after(expression, kraft, pair, replacement, depth, self.depths)
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
            pair for pair in candidates if frequencies[pair] >= maximum_frequency - slack
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


def _worker(
    seed: int, depth_cap: int, module_name: str
) -> tuple[int, dict[str, object], str, float]:
    started = time.perf_counter()
    candidate = search_seed_bounded(seed, depth_cap)
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
    """Return this budget's records, which must form a contiguous seed prefix."""
    if not log_path.exists():
        return []
    attempts = []
    for line_number, line in enumerate(log_path.read_text().splitlines(), 1):
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"{log_path}:{line_number}: record is not an object")
        seed = record.get("seed")
        if (
            record.get("algorithm") == algorithm
            and isinstance(seed, int)
            and seed_start <= seed < seed_start + seed_count
        ):
            attempts.append(record)
    if [record.get("seed") for record in attempts] != list(
        range(seed_start, seed_start + len(attempts))
    ):
        raise ValueError("depth-bounded search log is not a contiguous unique seed prefix")
    return attempts


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
) -> tuple[int | None, dict[str, object] | None]:
    """Search a reproducible seed range and keep the best verified bounded network."""

    if seed_count <= 0 or workers <= 0:
        raise ValueError("seed_count and workers must be positive")
    if random_tests < DEFAULT_RANDOM_TESTS:
        raise ValueError(f"random_tests must be at least {DEFAULT_RANDOM_TESTS}")
    algorithm = algorithm_name(depth_cap)
    module_name = f"candidate_depth{depth_cap}_bounded"
    configuration = {
        "algorithm": algorithm,
        "depth_cap": depth_cap,
        "seed_start": seed_start,
        "seed_count": seed_count,
        "random_tests": random_tests,
        "random_seed": random_seed,
    }
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text())
        if {key: checkpoint.get(key) for key in configuration} != configuration:
            raise ValueError("checkpoint configuration does not match requested search")
        if checkpoint.get("status") == "completed":
            return checkpoint.get("incumbent_seed"), checkpoint.get("incumbent_metrics")
    attempts = logged_attempts(log_path, algorithm, seed_start, seed_count)
    completed = len(attempts)

    # The log is authoritative: an accepted record may have been appended just
    # before an interruption prevented the matching checkpoint update.
    best_seed: int | None = None
    best_metrics: dict[str, object] | None = None
    accepted = [record for record in attempts if record.get("accepted")]
    if accepted:
        best_seed = int(accepted[-1]["seed"])
        replay = search_seed_bounded(best_seed, depth_cap)
        best_metrics = independently_check(replay).to_dict()
        best_metrics.pop("unreachable_nodes")
        if best_metrics != accepted[-1].get("final_metrics"):
            raise ValueError("replayed incumbent does not match its logged metrics")
        incumbent = incumbent_dir / f"seed_{best_seed}.v"
        if not incumbent.exists() or incumbent.read_text() != replay.render(module_name):
            raise ValueError(f"incumbent artifact {incumbent} is missing or differs")

    checkpoint = {
        **configuration,
        "completed_seeds": completed,
        "incumbent_seed": best_seed,
        "incumbent_metrics": best_metrics,
        "search_log_path": str(log_path),
        "status": "running",
    }
    _write_checkpoint(checkpoint_path, checkpoint)
    incumbent_dir.mkdir(parents=True, exist_ok=True)

    seeds = range(seed_start + completed, seed_start + seed_count)
    executor = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    results = (
        executor.map(_worker, seeds, repeat(depth_cap), repeat(module_name), chunksize=1)
        if executor
        else (_worker(seed, depth_cap, module_name) for seed in seeds)
    )
    try:
        for offset, (seed, metrics, source, runtime) in enumerate(results, 1):
            eligible = int(metrics["maximum_depth"]) <= depth_cap
            improves = eligible and (
                best_metrics is None
                or _score(metrics, seed) < _score(best_metrics, best_seed or 0)
            )
            artifact = None
            if improves:
                artifact = incumbent_dir / f"seed_{seed}.v"
                artifact.write_text(source)
                report = verification_report(artifact, random_tests, random_seed)
                run_formal(artifact)
                if _metrics(report) != metrics:
                    raise RuntimeError("full verification metrics disagree with worker")
                best_metrics = metrics
                best_seed = seed
            record = {
                "timestamp_utc": _timestamp(),
                "attempt_id": f"{algorithm}-seed-{seed}",
                "algorithm": algorithm,
                "parameters": {
                    "depth_cap": depth_cap,
                    "seed_start": seed_start,
                    "seed_budget": seed_count,
                },
                "seed": seed,
                "runtime_seconds": round(runtime, 6),
                "starting_metrics": None,
                "final_metrics": metrics,
                "verification_passed": True,
                "accepted": improves,
                "rejection_reason": None
                if improves
                else ("exceeds depth bound" if not eligible else "does not improve incumbent"),
                "artifact": str(artifact) if artifact else None,
            }
            _append_log(log_path, [record])
            checkpoint.update(
                {
                    "completed_seeds": completed + offset,
                    "incumbent_seed": best_seed,
                    "incumbent_metrics": best_metrics,
                }
            )
            _write_checkpoint(checkpoint_path, checkpoint)
    finally:
        if executor:
            executor.shutdown()
    if best_seed is None:
        raise RuntimeError("no trial produced a depth-bounded network")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text((incumbent_dir / f"seed_{best_seed}.v").read_text())
    checkpoint["status"] = "completed"
    _write_checkpoint(checkpoint_path, checkpoint)
    return best_seed, best_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth-cap", type=int, default=DEFAULT_DEPTH_CAP)
    parser.add_argument("--seed-start", type=int, default=40000)
    parser.add_argument("--seed-count", type=int, default=10000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("results/checkpoints/depth7_bounded_search.json"),
    )
    parser.add_argument(
        "--artifact", type=Path, default=Path("results/phase6/candidate_depth7_bounded.v")
    )
    parser.add_argument(
        "--incumbent-dir",
        type=Path,
        default=Path("results/checkpoints/depth7_bounded_incumbents"),
    )
    parser.add_argument("--search-log", type=Path, default=Path("results/search_log.jsonl"))
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--random-seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED
    )
    args = parser.parse_args()
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

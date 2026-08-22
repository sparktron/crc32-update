"""Search for Candidate A, the best-found unrestricted-depth XOR2 network."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from itertools import combinations
import os
from pathlib import Path
import random
import tempfile
import time
from typing import Iterable, Sequence

from generator.build_matrix import (
    INPUT_COUNT,
    OUTPUT_COUNT,
    basis_signal_names,
    build_transformation_matrix,
)
from verifier.run_formal import run as run_formal
from verifier.verify_network import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    Metrics,
    parse_network,
    verification_report,
    verify_exact_equivalence,
)

ALGORITHM = "gf2-bp-cse-depth-stochastic-v1"
DEFAULT_SEED_COUNT = 10_000


@dataclass(frozen=True)
class Operation:
    output: int
    input_a: int
    input_b: int


@dataclass(frozen=True)
class Candidate:
    seed: int
    operations: tuple[Operation, ...]
    output_sources: tuple[int, ...]
    vectors: tuple[int, ...]
    depths: tuple[int, ...]

    def render(self) -> str:
        names = list(basis_signal_names()) + [
            f"n{index}" for index in range(len(self.vectors) - INPUT_COUNT)
        ]
        retained = {operation.output for operation in self.operations}
        lines = [
            "module candidate_a_min_area(crc, data, next_crc);",
            "input [31:0] crc;",
            "input [63:0] data;",
            "output [31:0] next_crc;",
        ]
        lines.extend(f"wire {names[signal]};" for signal in sorted(retained))
        lines.append("")
        for operation in self.operations:
            input_a, input_b = sorted(
                (operation.input_a, operation.input_b), key=names.__getitem__
            )
            lines.append(
                f"assign {names[operation.output]} = "
                f"{names[input_a]} ^ {names[input_b]};"
            )
        lines.append("")
        lines.extend(
            f"assign next_crc[{index}] = {names[source]};"
            for index, source in enumerate(self.output_sources)
        )
        lines.append("endmodule")
        return "\n".join(lines) + "\n"


def _toggle(expression: set[int], signal: int) -> None:
    if signal in expression:
        expression.remove(signal)
    else:
        expression.add(signal)


def _replace_pair(expression: set[int], pair: tuple[int, int], replacement: int) -> None:
    expression.remove(pair[0])
    expression.remove(pair[1])
    _toggle(expression, replacement)


def _free_rewrites(
    expressions: list[set[int]], vector_to_signal: dict[int, int], vectors: list[int]
) -> None:
    """Exhaust zero-gate rewrites exposed by already-computed GF(2) signals."""

    while True:
        best: tuple[int, int, int, int] | None = None
        for expression in expressions:
            ordered = sorted(expression)
            for input_a, input_b in combinations(ordered, 2):
                replacement = vector_to_signal.get(vectors[input_a] ^ vectors[input_b])
                if replacement is None or replacement in (input_a, input_b):
                    continue
                reduction = 3 if replacement in expression else 1
                candidate = (reduction, -replacement, -input_a, -input_b)
                if best is None or candidate > best:
                    best = candidate
        if best is None:
            return
        _, neg_replacement, neg_input_a, neg_input_b = best
        pair = (-neg_input_a, -neg_input_b)
        replacement = -neg_replacement
        for expression in expressions:
            if pair[0] in expression and pair[1] in expression:
                _replace_pair(expression, pair, replacement)


def _pair_frequencies(expressions: Iterable[set[int]]) -> Counter[tuple[int, int]]:
    frequencies: Counter[tuple[int, int]] = Counter()
    for expression in expressions:
        frequencies.update(combinations(sorted(expression), 2))
    return frequencies


def _choose_shared_pair(
    expressions: list[set[int]],
    vectors: list[int],
    depths: list[int],
    vector_to_signal: dict[int, int],
    generator: random.Random,
) -> tuple[int, int] | None:
    frequencies = _pair_frequencies(expressions)
    candidates = [
        pair
        for pair, frequency in frequencies.items()
        if frequency > 1
        and (vectors[pair[0]] ^ vectors[pair[1]]) not in vector_to_signal
    ]
    if not candidates:
        return None
    maximum_frequency = max(frequencies[pair] for pair in candidates)
    # Most seeds use the area-greedy tier. A minority admit one level of
    # frequency slack, which is the stochastic local-search move.
    slack = 1 if generator.randrange(4) == 0 and maximum_frequency > 2 else 0
    pool = [
        pair for pair in candidates if frequencies[pair] >= maximum_frequency - slack
    ]
    pool.sort(
        key=lambda pair: (
            -frequencies[pair],
            1 + max(depths[pair[0]], depths[pair[1]]),
            (vectors[pair[0]] ^ vectors[pair[1]]).bit_count(),
            pair,
        )
    )
    width = min(len(pool), 1 + generator.randrange(min(12, len(pool))))
    weights = list(range(width, 0, -1))
    return generator.choices(pool[:width], weights=weights, k=1)[0]


def _append_operation(
    pair: tuple[int, int],
    operations: list[Operation],
    vectors: list[int],
    depths: list[int],
    vector_to_signal: dict[int, int],
) -> int:
    vector = vectors[pair[0]] ^ vectors[pair[1]]
    existing = vector_to_signal.get(vector)
    if existing is not None:
        return existing
    output = len(vectors)
    vectors.append(vector)
    depths.append(1 + max(depths[pair[0]], depths[pair[1]]))
    vector_to_signal[vector] = output
    operations.append(Operation(output, pair[0], pair[1]))
    return output


def _finish_outputs(
    expressions: list[set[int]],
    operations: list[Operation],
    vectors: list[int],
    depths: list[int],
    vector_to_signal: dict[int, int],
    generator: random.Random,
) -> tuple[int, ...]:
    output_sources = [-1] * len(expressions)
    order = list(range(len(expressions)))
    generator.shuffle(order)
    for output_index in order:
        expression = expressions[output_index]
        while len(expression) > 1:
            known: list[tuple[int, int, int, int]] = []
            for pair in combinations(sorted(expression), 2):
                replacement = vector_to_signal.get(vectors[pair[0]] ^ vectors[pair[1]])
                if replacement is not None and replacement not in pair:
                    reduction = 3 if replacement in expression else 1
                    known.append((-reduction, depths[replacement], replacement, *pair))
            if known:
                _, _, replacement, input_a, input_b = min(known)
                _replace_pair(expression, (input_a, input_b), replacement)
                continue

            frequencies = _pair_frequencies(expressions)
            pairs = list(combinations(sorted(expression), 2))
            pairs.sort(
                key=lambda pair: (
                    -frequencies[pair],
                    1 + max(depths[pair[0]], depths[pair[1]]),
                    depths[pair[0]] + depths[pair[1]],
                    vectors[pair[0]] ^ vectors[pair[1]],
                    pair,
                )
            )
            # Depth-aware local variation changes only equal sharing tiers.
            best_frequency = frequencies[pairs[0]]
            tier = [pair for pair in pairs if frequencies[pair] == best_frequency]
            width = min(len(tier), 4)
            pair = tier[generator.randrange(width)]
            replacement = _append_operation(
                pair, operations, vectors, depths, vector_to_signal
            )
            for pending in expressions:
                if pair[0] in pending and pair[1] in pending:
                    _replace_pair(pending, pair, replacement)
        if not expression:
            raise RuntimeError("optimizer produced an unrepresentable zero output")
        output_sources[output_index] = next(iter(expression))
    return tuple(output_sources)


def _prune_operations(
    operations: Sequence[Operation], output_sources: Sequence[int]
) -> tuple[Operation, ...]:
    by_output = {operation.output: operation for operation in operations}
    reachable: set[int] = set()

    def visit(signal: int) -> None:
        operation = by_output.get(signal)
        if operation is None or signal in reachable:
            return
        reachable.add(signal)
        visit(operation.input_a)
        visit(operation.input_b)

    for source in output_sources:
        visit(source)
    return tuple(operation for operation in operations if operation.output in reachable)


def search_seed(seed: int, rows: Sequence[int] | None = None) -> Candidate:
    """Run one deterministic seeded BP/CSE/local-improvement trial."""

    target_rows = tuple(build_transformation_matrix() if rows is None else rows)
    generator = random.Random(seed)
    vectors = [1 << index for index in range(INPUT_COUNT)]
    depths = [0] * INPUT_COUNT
    vector_to_signal = {vector: index for index, vector in enumerate(vectors)}
    expressions = [
        {index for index in range(INPUT_COUNT) if row & (1 << index)}
        for row in target_rows
    ]
    operations: list[Operation] = []

    while True:
        _free_rewrites(expressions, vector_to_signal, vectors)
        pair = _choose_shared_pair(
            expressions, vectors, depths, vector_to_signal, generator
        )
        if pair is None:
            break
        replacement = _append_operation(
            pair, operations, vectors, depths, vector_to_signal
        )
        for expression in expressions:
            if pair[0] in expression and pair[1] in expression:
                _replace_pair(expression, pair, replacement)

    output_sources = _finish_outputs(
        expressions, operations, vectors, depths, vector_to_signal, generator
    )
    if tuple(vectors[source] for source in output_sources) != target_rows:
        raise RuntimeError("GF(2) signal-vector check failed")
    retained = _prune_operations(operations, output_sources)
    return Candidate(
        seed=seed,
        operations=retained,
        output_sources=output_sources,
        vectors=tuple(vectors),
        depths=tuple(depths),
    )


def independently_check(candidate: Candidate) -> Metrics:
    normalized = parse_network(candidate.render()).normalize()
    verify_exact_equivalence(normalized)
    return normalized.metrics()


def _worker(seed: int) -> tuple[int, dict[str, object], float]:
    started = time.perf_counter()
    candidate = search_seed(seed)
    metrics = independently_check(candidate)
    return seed, metrics.to_dict(), time.perf_counter() - started


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _metrics_for_log(metrics: dict[str, object]) -> dict[str, object]:
    result = dict(metrics)
    result.pop("unreachable_nodes", None)
    return result


def _append_log(path: Path, records: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as output:
        for record in records:
            output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _full_verify(candidate: Candidate, random_tests: int, random_seed: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="candidate-a-incumbent-") as directory:
        path = Path(directory) / "candidate_a_min_area.v"
        path.write_text(candidate.render())
        report = verification_report(path, random_tests, random_seed)
        run_formal(path)
    return report


def run_search(
    seed_start: int,
    seed_count: int,
    workers: int,
    checkpoint_path: Path,
    artifact_path: Path,
    frontier_path: Path,
    metrics_path: Path,
    log_path: Path,
    random_tests: int,
    random_seed: int,
) -> Candidate:
    if seed_count <= 0:
        raise ValueError("seed count must be positive")
    started = time.perf_counter()
    baseline = parse_network(
        Path("results/baselines/greedy_cse.v").read_text()
    ).normalize().metrics().to_dict()
    best: Candidate | None = None
    best_metrics: dict[str, object] | None = None
    completed_before = 0
    if checkpoint_path.exists():
        loaded = json.loads(checkpoint_path.read_text())
        expected = (ALGORITHM, seed_start, seed_count)
        actual = (
            loaded.get("algorithm"),
            loaded.get("seed_start"),
            loaded.get("seed_count"),
        )
        if actual != expected:
            raise ValueError(
                "checkpoint configuration does not match algorithm/seed range"
            )
        completed_before = int(loaded.get("completed_seeds", 0))
        if not 0 <= completed_before <= seed_count:
            raise ValueError("checkpoint completed-seed count is outside the budget")
        incumbent_seed = loaded.get("incumbent_seed")
        if incumbent_seed is not None:
            best = search_seed(int(incumbent_seed))
            best_metrics = independently_check(best).to_dict()
            if best_metrics != loaded.get("incumbent_metrics"):
                raise RuntimeError("replayed checkpoint incumbent metrics do not match")
        if loaded.get("status") == "completed":
            if best is None:
                raise RuntimeError("completed checkpoint has no incumbent")
            return best

    checkpoint = {
        "algorithm": ALGORITHM,
        "seed_start": seed_start,
        "seed_count": seed_count,
        "completed_seeds": completed_before,
        "incumbent_seed": None if best is None else best.seed,
        "incumbent_metrics": best_metrics,
        "status": "running",
    }
    _write_json(checkpoint_path, checkpoint)

    seeds = range(seed_start + completed_before, seed_start + seed_count)
    executor = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    results = executor.map(_worker, seeds, chunksize=1) if executor else map(_worker, seeds)
    buffered_records: list[dict[str, object]] = []
    try:
        for completed_now, (seed, metrics, trial_runtime) in enumerate(
            results, 1
        ):
            completed = completed_before + completed_now
            improves = best_metrics is None or (
                metrics["xor2_count"], metrics["maximum_depth"], seed
            ) < (
                best_metrics["xor2_count"], best_metrics["maximum_depth"], best.seed
            )
            accepted = False
            verification_passed = True
            rejection_reason: str | None = "dominated by verified incumbent"
            artifact: str | None = None
            if improves:
                candidate = search_seed(seed)
                if independently_check(candidate).to_dict() != metrics:
                    raise RuntimeError("seed replay changed before incumbent verification")
                report = _full_verify(candidate, random_tests, random_seed)
                verified_metrics = report["metrics"]
                if verified_metrics != metrics:
                    raise RuntimeError("independent incumbent metrics changed during verification")
                best = candidate
                best_metrics = metrics
                accepted = True
                rejection_reason = None
                incumbent_path = (
                    checkpoint_path.parent
                    / "candidate_a_incumbents"
                    / f"seed_{seed}.v"
                )
                incumbent_path.parent.mkdir(parents=True, exist_ok=True)
                incumbent_path.write_text(candidate.render())
                artifact = str(incumbent_path)
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text(candidate.render())
            buffered_records.append(
                {
                    "timestamp_utc": _timestamp(),
                    "attempt_id": f"candidate-a-{ALGORITHM}-seed-{seed}",
                    "algorithm": ALGORITHM,
                    "parameters": {
                        "candidate_class": "A",
                        "depth_cap": None,
                        "seed_budget": seed_count,
                        "seed_start": seed_start,
                    },
                    "seed": seed,
                    "runtime_seconds": round(trial_runtime, 6),
                    "starting_metrics": _metrics_for_log(baseline),
                    "final_metrics": _metrics_for_log(metrics),
                    "verification_passed": verification_passed,
                    "accepted": accepted,
                    "rejection_reason": rejection_reason,
                    "artifact": artifact,
                }
            )
            if completed % 25 == 0 or completed == seed_count:
                _append_log(log_path, buffered_records)
                buffered_records.clear()
                checkpoint.update(
                    {
                        "completed_seeds": completed,
                        "incumbent_seed": None if best is None else best.seed,
                        "incumbent_metrics": best_metrics,
                        "elapsed_seconds": round(time.perf_counter() - started, 6),
                    }
                )
                _write_json(checkpoint_path, checkpoint)
    finally:
        if executor:
            executor.shutdown()
    if best is None or best_metrics is None:
        raise RuntimeError("search completed without a verified incumbent")

    frontier = {
        "schema_version": 1,
        "generated_by": ALGORITHM,
        "candidate_scope": ["A"],
        "entries": [
            {
                "candidate_class": "A",
                "artifact": str(artifact_path),
                "seed": best.seed,
                "metrics": _metrics_for_log(best_metrics),
                "verification": {
                    "structural": "passed",
                    "exact_vectors": 97,
                    "random_vectors": random_tests,
                    "random_seed": random_seed,
                    "formal_equivalence": "passed",
                },
            }
        ],
    }
    _write_json(frontier_path, frontier)
    header = (
        "candidate_class,artifact,seed,xor2_count,maximum_depth,output_depths,"
        "maximum_fanout,total_fanout,total_excess_fanout_above_4,"
        "intermediate_node_count,direct_output_alias_count,exact_vectors_checked,"
        "random_vectors_checked,random_seed,formal_equivalence,verification_status\n"
    )
    output_depths = json.dumps(
        best_metrics["output_depths"], separators=(",", ":")
    )
    row = (
        f"A,{artifact_path},{best.seed},{best_metrics['xor2_count']},"
        f"{best_metrics['maximum_depth']},\"{output_depths}\","
        f"{best_metrics['maximum_fanout']},{best_metrics['total_fanout']},"
        f"{best_metrics['total_excess_fanout_above_4']},"
        f"{best_metrics['intermediate_node_count']},"
        f"{best_metrics['direct_output_alias_count']},97,{random_tests},"
        f"{random_seed},passed,passed\n"
    )
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(header + row)
    checkpoint["status"] = "completed"
    _write_json(checkpoint_path, checkpoint)
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    replay = parser.add_mutually_exclusive_group()
    replay.add_argument(
        "--replay-seed",
        type=int,
        help="regenerate one seed directly without running or logging a search",
    )
    replay.add_argument(
        "--replay-frontier",
        type=Path,
        help="regenerate the Candidate A seed recorded in a frontier JSON file",
    )
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-count", type=int, default=DEFAULT_SEED_COUNT)
    parser.add_argument(
        "--workers", type=int, default=min(8, max(1, os.cpu_count() or 1))
    )
    parser.add_argument(
        "--checkpoint", type=Path,
        default=Path("results/checkpoints/candidate_a_checkpoint.json"),
    )
    parser.add_argument(
        "--artifact", type=Path, default=Path("results/candidate_a_min_area.v")
    )
    parser.add_argument(
        "--frontier", type=Path, default=Path("results/pareto_frontier.json")
    )
    parser.add_argument("--metrics", type=Path, default=Path("results/metrics.csv"))
    parser.add_argument(
        "--search-log", type=Path, default=Path("results/search_log.jsonl")
    )
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--random-seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED
    )
    args = parser.parse_args()
    if args.replay_seed is not None or args.replay_frontier is not None:
        try:
            replay_seed = args.replay_seed
            if args.replay_frontier is not None:
                frontier = json.loads(args.replay_frontier.read_text())
                entries = frontier.get("entries")
                if not isinstance(entries, list) or len(entries) != 1:
                    raise ValueError("frontier must contain exactly Candidate A")
                replay_seed = entries[0].get("seed")
                if not isinstance(replay_seed, int):
                    raise ValueError("frontier Candidate A seed must be an integer")
            assert replay_seed is not None
            candidate = search_seed(replay_seed)
            independently_check(candidate)
            args.artifact.parent.mkdir(parents=True, exist_ok=True)
            args.artifact.write_text(candidate.render())
        except (OSError, RuntimeError, ValueError) as error:
            parser.exit(1, f"Candidate A replay failed: {error}\n")
        return 0
    if args.random_tests < DEFAULT_RANDOM_TESTS:
        parser.error(f"--random-tests must be at least {DEFAULT_RANDOM_TESTS}")
    try:
        candidate = run_search(
            args.seed_start,
            args.seed_count,
            args.workers,
            args.checkpoint,
            args.artifact,
            args.frontier,
            args.metrics,
            args.search_log,
            args.random_tests,
            args.random_seed,
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Candidate A search failed: {error}\n")
    metrics = independently_check(candidate)
    print(
        f"Candidate A seed {candidate.seed}: {metrics.xor2_count} XOR2, "
        f"depth {metrics.maximum_depth}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

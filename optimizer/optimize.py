"""Search for Candidate A, the best-found unrestricted-depth XOR2 network."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import fcntl
from itertools import combinations
import os
from pathlib import Path
import random
import shutil
import tempfile
import time
from typing import Iterable, Sequence

from generator.build_matrix import (
    INPUT_COUNT,
    basis_signal_names,
    build_transformation_matrix,
)
from optimizer.search_lifecycle import (
    append_log,
    budget_records,
    inspect_log,
    run_budget,
    write_checkpoint,
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

    def render(self, module_name: str = "candidate_a_min_area") -> str:
        names = list(basis_signal_names()) + [
            f"n{index}" for index in range(len(self.vectors) - INPUT_COUNT)
        ]
        retained = {operation.output for operation in self.operations}
        lines = [
            f"module {module_name}(crc, data, next_crc);",
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


def _replace_pair(
    expression: set[int], pair: tuple[int, int], replacement: int
) -> None:
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


def _worker(seed: int) -> tuple[int, dict[str, object], str, float]:
    started = time.perf_counter()
    candidate = search_seed(seed)
    metrics = independently_check(candidate)
    return seed, metrics.to_dict(), candidate.render(), time.perf_counter() - started


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, document: object) -> None:
    write_checkpoint(path, document)


def _metrics_for_log(metrics: dict[str, object]) -> dict[str, object]:
    result = dict(metrics)
    result.pop("unreachable_nodes", None)
    return result


def _append_log(path: Path, records: Sequence[dict[str, object]]) -> None:
    append_log(path, records)


@contextmanager
def _exclusive_search_lock(checkpoint_path: Path) -> Iterable[None]:
    """Prevent two CLI invocations from sharing one checkpoint and search log."""

    lock_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                f"search checkpoint is already active: {checkpoint_path}"
            ) from error
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _full_verify(
    candidate: Candidate, random_tests: int, random_seed: int
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="candidate-a-incumbent-") as directory:
        path = Path(directory) / "candidate_a_min_area.v"
        path.write_text(candidate.render())
        report = verification_report(path, random_tests, random_seed)
        run_formal(path)
    return report


def _checkpoint_search_log_path(
    checkpoint: dict[str, object], checkpoint_path: Path
) -> Path:
    recorded_value = checkpoint.get("search_log_path")
    if not isinstance(recorded_value, str) or not recorded_value:
        raise ValueError("checkpoint does not record its search log path")
    recorded_path = Path(recorded_value)
    if not recorded_path.is_absolute():
        recorded_path = checkpoint_path.parent / recorded_path
    return recorded_path


def _candidate_a_attempts(
    log_path: Path, seed_start: int, seed_count: int
) -> list[dict[str, object]]:
    return budget_records(inspect_log(log_path)[0], ALGORITHM, seed_start, seed_count)[
        0
    ]


def _reconcile_checkpoint(
    checkpoint: dict[str, object], log_path: Path, seed_start: int, seed_count: int
) -> tuple[int, int | None, dict[str, object] | None]:
    completed = int(checkpoint.get("completed_seeds", 0))
    attempts = _candidate_a_attempts(log_path, seed_start, seed_count)
    if len(attempts) < completed:
        raise ValueError("search log is behind the recorded checkpoint")
    accepted = [attempt for attempt in attempts if attempt.get("accepted") is True]
    if accepted:
        incumbent = accepted[-1]
        incumbent_seed = incumbent.get("seed")
        incumbent_metrics = incumbent.get("final_metrics")
        if not isinstance(incumbent_seed, int) or not isinstance(
            incumbent_metrics, dict
        ):
            raise ValueError("accepted search-log incumbent is malformed")
    else:
        incumbent_seed = checkpoint.get("incumbent_seed")
        incumbent_metrics = checkpoint.get("incumbent_metrics")
        if incumbent_seed is not None or incumbent_metrics is not None:
            raise ValueError("checkpoint incumbent is absent from the search log")
    return len(attempts), incumbent_seed, incumbent_metrics


def _restore_search_log(
    checkpoint: dict[str, object], checkpoint_path: Path, requested_path: Path
) -> None:
    recorded_path = _checkpoint_search_log_path(checkpoint, checkpoint_path)
    if not recorded_path.is_file():
        raise FileNotFoundError(
            f"completed checkpoint search log is missing: {recorded_path}"
        )
    if recorded_path.resolve() == requested_path.resolve():
        return
    if requested_path.exists():
        if requested_path.read_bytes() != recorded_path.read_bytes():
            raise ValueError(
                "requested search log conflicts with checkpoint search log"
            )
        return
    requested_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(recorded_path, requested_path)


def _write_result_artifacts(
    best: Candidate,
    best_metrics: dict[str, object],
    artifact_path: Path,
    frontier_path: Path,
    metrics_path: Path,
    random_tests: int,
    random_seed: int,
) -> None:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(best.render())
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
    output_depths = json.dumps(best_metrics["output_depths"], separators=(",", ":"))
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
    if random_tests < DEFAULT_RANDOM_TESTS:
        raise ValueError(f"random_tests must be at least {DEFAULT_RANDOM_TESTS}")
    configuration = {
        "algorithm": ALGORITHM,
        "seed_start": seed_start,
        "seed_count": seed_count,
        "random_tests": random_tests,
        "random_seed": random_seed,
    }
    incumbent_dir = checkpoint_path.parent / "candidate_a_incumbents"

    def restore(record):
        path = incumbent_dir / f"seed_{record['seed']}.v"
        if not path.is_file():
            path = Path(record["artifact"])
        source = path.read_text()
        normalized = parse_network(source).normalize()
        verify_exact_equivalence(normalized)
        return _metrics_for_log(normalized.metrics().to_dict()), source

    def accept(seed, metrics, source):
        candidate = search_seed(seed)
        if candidate.render() != source:
            raise RuntimeError("seed replay source differs from the worker artifact")
        if _metrics_for_log(independently_check(candidate).to_dict()) != metrics:
            raise RuntimeError("seed replay changed before incumbent verification")
        report = _full_verify(candidate, random_tests, random_seed)
        if _metrics_for_log(report["metrics"]) != metrics:
            raise RuntimeError(
                "independent incumbent metrics changed during verification"
            )
        path = incumbent_dir / f"seed_{seed}.v"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        return path

    best_seed, metrics, source = run_budget(
        configuration=configuration,
        workers=workers,
        checkpoint_path=checkpoint_path,
        log_path=log_path,
        worker=_lifecycle_worker,
        score=lambda metrics, seed: (
            metrics["xor2_count"],
            metrics["maximum_depth"],
            seed,
        ),
        eligible=lambda metrics: True,
        restore=restore,
        accept=accept,
        append=_append_log,
        save=_write_json,
    )
    if best_seed is None or metrics is None:
        raise RuntimeError("search completed without a verified incumbent")
    best = _saved_candidate(best_seed, source)
    full_metrics = {**metrics, "unreachable_nodes": []}
    _write_result_artifacts(
        best,
        full_metrics,
        artifact_path,
        frontier_path,
        metrics_path,
        random_tests,
        random_seed,
    )
    return best


@dataclass(frozen=True)
class _SavedCandidate(Candidate):
    source: str

    def render(self, module_name: str = "candidate_a_min_area") -> str:
        import re

        return re.sub(r"module \w+\(", f"module {module_name}(", self.source, count=1)


def _saved_candidate(seed, source):
    normalized = parse_network(source).normalize()
    names = list(basis_signal_names()) + [node.output for node in normalized.nodes]
    indices = {name: index for index, name in enumerate(names)}
    vectors = [1 << index for index in range(INPUT_COUNT)]
    depths = [0] * INPUT_COUNT
    operations = []
    for node in normalized.nodes:
        a, b = (indices[name] for name in normalized.canonical_inputs[node.output])
        operations.append(Operation(indices[node.output], a, b))
        vectors.append(vectors[a] ^ vectors[b])
        depths.append(1 + max(depths[a], depths[b]))
    return _SavedCandidate(
        seed,
        tuple(operations),
        tuple(indices[name] for name in normalized.output_sources),
        tuple(vectors),
        tuple(depths),
        source,
    )


def _lifecycle_worker(seed):
    seed, metrics, source, runtime = _worker(seed)
    return seed, _metrics_for_log(metrics), source, runtime


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
        "--checkpoint",
        type=Path,
        default=Path("results/checkpoints/candidate_a_checkpoint.json"),
    )
    parser.add_argument(
        "--artifact", type=Path, default=Path("results/candidate_a_min_area.v")
    )
    parser.add_argument(
        "--frontier",
        type=Path,
        default=Path("results/phase3/candidate_a_frontier.json"),
    )
    parser.add_argument(
        "--metrics", type=Path, default=Path("results/phase3/candidate_a_metrics.csv")
    )
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
        with _exclusive_search_lock(args.checkpoint):
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

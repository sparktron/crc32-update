"""Run resumable Phase 4 refinement searches for Candidate B or Candidate C."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import repeat
import json
import os
from pathlib import Path
import time
from typing import Callable

from optimizer.optimize import _exclusive_search_lock, independently_check, search_seed
from verifier.run_formal import run as run_formal
from verifier.verify_network import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    parse_network_file,
    verification_report,
)


@dataclass(frozen=True)
class SearchConfig:
    candidate_class: str
    algorithm: str
    initial_artifact: Path
    output_artifact: Path
    depth_cap: int | None
    score: Callable[[dict[str, object], int], tuple[int, ...]]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _metrics(report: dict[str, object]) -> dict[str, object]:
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise RuntimeError("verifier returned malformed metrics")
    return {key: value for key, value in metrics.items() if key != "unreachable_nodes"}


def _config(candidate_class: str, output_dir: Path) -> SearchConfig:
    if candidate_class == "B":
        return SearchConfig(
            "B",
            "phase4-depth8-refinement-v1",
            output_dir / "candidate_b_depth8.v",
            output_dir / "candidate_b_refined.v",
            8,
            lambda metrics, seed: (
                int(metrics["xor2_count"]),
                int(metrics["maximum_depth"]),
                int(metrics["maximum_fanout"]),
                seed,
            ),
        )
    if candidate_class == "C":
        return SearchConfig(
            "C",
            "phase4-min-depth-refinement-v1",
            output_dir / "candidate_c_min_depth.v",
            output_dir / "candidate_c_refined.v",
            None,
            lambda metrics, seed: (
                int(metrics["maximum_depth"]),
                int(metrics["xor2_count"]),
                int(metrics["maximum_fanout"]),
                seed,
            ),
        )
    raise ValueError("candidate_class must be B or C")


def _worker(seed: int, module_name: str) -> tuple[int, dict[str, object], str, float]:
    started = time.perf_counter()
    candidate = search_seed(seed)
    metrics = independently_check(candidate).to_dict()
    metrics.pop("unreachable_nodes")
    return seed, metrics, candidate.render(module_name), time.perf_counter() - started


def _attempts(log_path: Path, config: SearchConfig, seed_start: int, seed_count: int) -> list[dict[str, object]]:
    if not log_path.exists():
        return []
    attempts = []
    for line_number, line in enumerate(log_path.read_text().splitlines(), 1):
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"{log_path}:{line_number}: record is not an object")
        seed = record.get("seed")
        if record.get("algorithm") == config.algorithm and isinstance(seed, int) and seed_start <= seed < seed_start + seed_count:
            attempts.append(record)
    expected = list(range(seed_start, seed_start + len(attempts)))
    if [record.get("seed") for record in attempts] != expected:
        raise ValueError("refinement search log is not a contiguous unique seed prefix")
    return attempts


def _append_log(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("a") as output:
        for record in records:
            output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _write_checkpoint(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run_refinement(
    candidate_class: str,
    seed_start: int,
    seed_count: int,
    workers: int,
    checkpoint_path: Path,
    output_dir: Path,
    log_path: Path,
    random_tests: int,
    random_seed: int,
) -> tuple[int | None, dict[str, object]]:
    """Search a reproducible seed range and preserve the best valid candidate."""

    if seed_count <= 0 or workers <= 0:
        raise ValueError("seed_count and workers must be positive")
    if random_tests < DEFAULT_RANDOM_TESTS:
        raise ValueError(f"random_tests must be at least {DEFAULT_RANDOM_TESTS}")
    config = _config(candidate_class, output_dir)
    initial_report = verification_report(config.initial_artifact, random_tests, random_seed)
    run_formal(config.initial_artifact)
    best_metrics = _metrics(initial_report)
    best_source = config.initial_artifact.read_text()
    best_seed: int | None = None

    completed = 0
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text())
        expected = (config.algorithm, seed_start, seed_count, random_tests, random_seed)
        actual = tuple(checkpoint.get(key) for key in ("algorithm", "seed_start", "seed_count", "random_tests", "random_seed"))
        if actual != expected:
            raise ValueError("checkpoint configuration does not match requested search")
        attempts = _attempts(log_path, config, seed_start, seed_count)
        completed = len(attempts)
        if completed < int(checkpoint.get("completed_seeds", 0)):
            raise ValueError("search log is behind checkpoint")
        checkpoint_best_seed = checkpoint.get("incumbent_seed")
        if isinstance(checkpoint_best_seed, int):
            candidate = search_seed(checkpoint_best_seed)
            best_source = candidate.render(f"candidate_{candidate_class.lower()}_refined")
            best_metrics = independently_check(candidate).to_dict()
            best_metrics.pop("unreachable_nodes")
            best_seed = checkpoint_best_seed
        if checkpoint.get("status") == "completed":
            return best_seed, best_metrics

    checkpoint = {
        "algorithm": config.algorithm,
        "candidate_class": candidate_class,
        "seed_start": seed_start,
        "seed_count": seed_count,
        "random_tests": random_tests,
        "random_seed": random_seed,
        "completed_seeds": completed,
        "incumbent_seed": best_seed,
        "incumbent_metrics": best_metrics,
        "status": "running",
    }
    _write_checkpoint(checkpoint_path, checkpoint)

    module_name = f"candidate_{candidate_class.lower()}_refined"
    seeds = range(seed_start + completed, seed_start + seed_count)
    executor = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    results = (
        executor.map(_worker, seeds, repeat(module_name), chunksize=1)
        if executor
        else map(lambda seed: _worker(seed, module_name), seeds)
    )
    try:
        for offset, (seed, metrics, source, runtime) in enumerate(results, 1):
            eligible = config.depth_cap is None or int(metrics["maximum_depth"]) <= config.depth_cap
            improves = eligible and config.score(metrics, seed) < config.score(best_metrics, best_seed if best_seed is not None else -1)
            accepted = False
            if improves:
                artifact = output_dir / f"candidate_{candidate_class.lower()}_incumbent_seed_{seed}.v"
                artifact.write_text(source)
                report = verification_report(artifact, random_tests, random_seed)
                run_formal(artifact)
                best_metrics = _metrics(report)
                best_source = source
                best_seed = seed
                accepted = True
            record = {
                "timestamp_utc": _timestamp(),
                "attempt_id": f"candidate-{candidate_class.lower()}-{config.algorithm}-seed-{seed}",
                "algorithm": config.algorithm,
                "parameters": {"candidate_class": candidate_class, "depth_cap": config.depth_cap, "seed_start": seed_start, "seed_budget": seed_count},
                "seed": seed,
                "runtime_seconds": round(runtime, 6),
                "starting_metrics": _metrics(initial_report),
                "final_metrics": metrics,
                "verification_passed": True,
                "accepted": accepted,
                "rejection_reason": None if accepted else ("exceeds depth bound" if not eligible else "does not improve incumbent"),
                "artifact": str(output_dir / f"candidate_{candidate_class.lower()}_incumbent_seed_{seed}.v") if accepted else None,
            }
            _append_log(log_path, [record])
            checkpoint.update({"completed_seeds": completed + offset, "incumbent_seed": best_seed, "incumbent_metrics": best_metrics})
            _write_checkpoint(checkpoint_path, checkpoint)
    finally:
        if executor:
            executor.shutdown()
    config.output_artifact.write_text(best_source)
    checkpoint["status"] = "completed"
    _write_checkpoint(checkpoint_path, checkpoint)
    return best_seed, best_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_class", choices=("B", "C"))
    parser.add_argument("--seed-start", type=int, default=20000)
    parser.add_argument("--seed-count", type=int, default=10000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=Path("results/phase4"))
    parser.add_argument("--search-log", type=Path, default=Path("results/search_log.jsonl"))
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument("--random-seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED)
    args = parser.parse_args()
    checkpoint = args.checkpoint or Path(f"results/checkpoints/candidate_{args.candidate_class.lower()}_refinement.json")
    try:
        # B and C have separate checkpoints but append to one canonical log.
        # Lock the log, rather than only the selected checkpoint, to prevent
        # overlapping manual budgets from creating duplicate or interleaved rows.
        with _exclusive_search_lock(args.search_log):
            seed, metrics = run_refinement(args.candidate_class, args.seed_start, args.seed_count, args.workers, checkpoint, args.output_dir, args.search_log, args.random_tests, args.random_seed)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"Candidate {args.candidate_class} refinement failed: {error}\n")
    print(json.dumps({"seed": seed, "metrics": metrics}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

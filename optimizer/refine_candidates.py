"""Run resumable Phase 4 refinement searches for Candidate B or Candidate C."""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
import time
from typing import Callable

from optimizer.optimize import _exclusive_search_lock, independently_check, search_seed
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
    parse_network_file,
    verification_report,
    verify_exact_equivalence,
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


def _attempts(
    log_path: Path, config: SearchConfig, seed_start: int, seed_count: int
) -> list[dict[str, object]]:
    return budget_records(
        inspect_log(log_path)[0], config.algorithm, seed_start, seed_count
    )[0]


_append_log = append_log
_write_checkpoint = write_checkpoint


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
    initial_report = verification_report(
        config.initial_artifact, random_tests, random_seed
    )
    run_formal(config.initial_artifact)
    best_metrics = _metrics(initial_report)
    best_source = config.initial_artifact.read_text()
    best_seed: int | None = None

    configuration = {
        "algorithm": config.algorithm,
        "candidate_class": candidate_class,
        "seed_start": seed_start,
        "seed_count": seed_count,
        "random_tests": random_tests,
        "random_seed": random_seed,
    }
    module_name = f"candidate_{candidate_class.lower()}_refined"

    def incumbent(seed):
        return (
            output_dir / f"candidate_{candidate_class.lower()}_incumbent_seed_{seed}.v"
        )

    def restore(record):
        path = incumbent(record["seed"])
        normalized = parse_network_file(path).normalize()
        verify_exact_equivalence(normalized)
        return _metrics({"metrics": normalized.metrics().to_dict()}), path.read_text()

    def accept(seed, metrics, source):
        path = incumbent(seed)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        report = verification_report(path, random_tests, random_seed)
        run_formal(path)
        if _metrics(report) != metrics:
            raise RuntimeError("full verification metrics disagree with worker")
        return path

    best_seed, best_metrics, best_source = run_budget(
        configuration=configuration,
        workers=workers,
        checkpoint_path=checkpoint_path,
        log_path=log_path,
        worker=partial(_worker, module_name=module_name),
        score=config.score,
        eligible=lambda metrics: config.depth_cap is None
        or int(metrics["maximum_depth"]) <= config.depth_cap,
        restore=restore,
        accept=accept,
        initial=(None, best_metrics, best_source),
        append=_append_log,
        save=_write_checkpoint,
        identity_inputs={
            "initial_artifact_sha256": hashlib.sha256(best_source.encode()).hexdigest()
        },
    )
    config.output_artifact.parent.mkdir(parents=True, exist_ok=True)
    config.output_artifact.write_text(best_source)
    return best_seed, best_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_class", choices=("B", "C"))
    parser.add_argument("--seed-start", type=int, default=20000)
    parser.add_argument("--seed-count", type=int, default=10000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=Path("results/phase4"))
    parser.add_argument(
        "--search-log", type=Path, default=Path("results/search_log.jsonl")
    )
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--random-seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED
    )
    args = parser.parse_args()
    checkpoint = args.checkpoint or Path(
        f"results/checkpoints/candidate_{args.candidate_class.lower()}_refinement.json"
    )
    try:
        # B and C have separate checkpoints but append to one canonical log.
        # Lock the log, rather than only the selected checkpoint, to prevent
        # overlapping manual budgets from creating duplicate or interleaved rows.
        with _exclusive_search_lock(args.search_log):
            seed, metrics = run_refinement(
                args.candidate_class,
                args.seed_start,
                args.seed_count,
                args.workers,
                checkpoint,
                args.output_dir,
                args.search_log,
                args.random_tests,
                args.random_seed,
            )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"Candidate {args.candidate_class} refinement failed: {error}\n")
    print(json.dumps({"seed": seed, "metrics": metrics}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

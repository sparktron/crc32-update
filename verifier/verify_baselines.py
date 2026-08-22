"""Verify every Phase 2 baseline and write independently measured metrics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import time

from verifier.run_formal import run as run_formal
from verifier.verify_network import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    VerificationError,
    verification_report,
)


BASELINES = (
    ("independent_per_output", "independent_per_output.v"),
    ("balanced_per_output", "balanced_per_output.v"),
    ("greedy_cse", "greedy_cse.v"),
    ("yosys_abc", "yosys_abc.v"),
)

FIELDNAMES = (
    "baseline",
    "xor2_count",
    "maximum_depth",
    "output_depths",
    "maximum_fanout",
    "total_fanout",
    "total_excess_fanout_above_4",
    "intermediate_node_count",
    "direct_output_alias_count",
    "generation_runtime_seconds",
    "verifier_runtime_seconds",
    "formal_runtime_seconds",
    "total_runtime_seconds",
    "exact_vectors_checked",
    "random_vectors_checked",
    "formal_equivalence",
    "verification_status",
)


def verify_baselines(
    baselines_dir: Path,
    generation_timings: dict[str, float],
    random_tests: int,
    seed: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for baseline, filename in BASELINES:
        path = baselines_dir / filename
        generation_runtime = generation_timings.get(filename)
        if not isinstance(generation_runtime, (int, float)):
            raise ValueError(f"missing generation runtime for {filename}")

        started = time.perf_counter()
        report = verification_report(path, random_tests, seed)
        verifier_runtime = time.perf_counter() - started
        started = time.perf_counter()
        run_formal(path)
        formal_runtime = time.perf_counter() - started
        metrics = report["metrics"]
        if not isinstance(metrics, dict):
            raise RuntimeError(f"malformed verifier metrics for {filename}")
        total_runtime = generation_runtime + verifier_runtime + formal_runtime
        rows.append(
            {
                "baseline": baseline,
                "xor2_count": metrics["xor2_count"],
                "maximum_depth": metrics["maximum_depth"],
                "output_depths": json.dumps(
                    metrics["output_depths"], separators=(",", ":")
                ),
                "maximum_fanout": metrics["maximum_fanout"],
                "total_fanout": metrics["total_fanout"],
                "total_excess_fanout_above_4": metrics[
                    "total_excess_fanout_above_4"
                ],
                "intermediate_node_count": metrics["intermediate_node_count"],
                "direct_output_alias_count": metrics["direct_output_alias_count"],
                "generation_runtime_seconds": f"{generation_runtime:.6f}",
                "verifier_runtime_seconds": f"{verifier_runtime:.6f}",
                "formal_runtime_seconds": f"{formal_runtime:.6f}",
                "total_runtime_seconds": f"{total_runtime:.6f}",
                "exact_vectors_checked": report["exact_vectors_checked"],
                "random_vectors_checked": report["random_vectors_checked"],
                "formal_equivalence": "passed",
                "verification_status": "passed",
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baselines-dir",
        type=Path,
        default=Path("results/baselines"),
    )
    parser.add_argument(
        "--generation-timings",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=Path("results/baseline_metrics.csv"),
    )
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--seed",
        type=lambda value: int(value, 0),
        default=DEFAULT_RANDOM_SEED,
    )
    args = parser.parse_args()
    if args.random_tests < DEFAULT_RANDOM_TESTS:
        parser.error(
            f"--random-tests must be at least {DEFAULT_RANDOM_TESTS} for acceptance"
        )

    try:
        timings = json.loads(args.generation_timings.read_text())
        if not isinstance(timings, dict):
            raise ValueError("generation timings must be a JSON object")
        rows = verify_baselines(
            args.baselines_dir,
            timings,
            args.random_tests,
            args.seed,
        )
        args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
        with args.metrics_output.open("w", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=FIELDNAMES,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, RuntimeError, ValueError, VerificationError) as error:
        parser.exit(1, f"baseline verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

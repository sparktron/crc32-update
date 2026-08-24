"""Materialize and verify the initial Phase 4 Candidate B and C artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from generator.baseline_generator import render_balanced
from generator.build_matrix import build_transformation_matrix
from optimizer.optimize import search_seed
from verifier.run_formal import run as run_formal
from verifier.verify_network import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    verification_report,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_record(log_path: Path, record: dict[str, object]) -> None:
    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    if any(record["attempt_id"] == existing.get("attempt_id") for existing in records):
        raise ValueError(f"search log already contains {record['attempt_id']}")
    with log_path.open("a") as output:
        output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _metrics_without_unreachable(report: dict[str, object]) -> dict[str, object]:
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise RuntimeError("verifier returned malformed metrics")
    return {key: value for key, value in metrics.items() if key != "unreachable_nodes"}


def _render_candidate_c() -> str:
    source = render_balanced(build_transformation_matrix())
    return source.replace(
        "module baseline_balanced(", "module candidate_c_min_depth(", 1
    )


def _verify_and_record(
    candidate_class: str,
    attempt_id: str,
    algorithm: str,
    parameters: dict[str, object],
    artifact: Path,
    source: str,
    log_path: Path,
    random_tests: int,
    random_seed: int,
) -> dict[str, object]:
    started = time.perf_counter()
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(source)
    report = verification_report(artifact, random_tests, random_seed)
    run_formal(artifact)
    metrics = _metrics_without_unreachable(report)
    if candidate_class == "B" and metrics["maximum_depth"] > 8:
        raise RuntimeError("Candidate B starting point violates depth bound 8")
    record = {
        "timestamp_utc": _timestamp(),
        "attempt_id": attempt_id,
        "algorithm": algorithm,
        "parameters": parameters,
        "seed": parameters.get("source_seed"),
        "runtime_seconds": round(time.perf_counter() - started, 6),
        "starting_metrics": None,
        "final_metrics": metrics,
        "verification_passed": True,
        "accepted": True,
        "rejection_reason": None,
        "artifact": str(artifact),
    }
    _append_record(log_path, record)
    return record


def materialize(
    output_dir: Path,
    log_path: Path,
    random_tests: int = DEFAULT_RANDOM_TESTS,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> list[dict[str, object]]:
    """Create initial valid representatives before their longer manual searches."""

    if random_tests < DEFAULT_RANDOM_TESTS:
        raise ValueError(f"random_tests must be at least {DEFAULT_RANDOM_TESTS}")
    candidate_b = search_seed(16564)
    records = [
        _verify_and_record(
            "B",
            "candidate-b-phase4-starting-point-seed-16564",
            "phase4-depth8-starting-point-v1",
            {
                "candidate_class": "B",
                "depth_bound": 8,
                "source_seed": 16564,
                "source_search": "phase4 Candidate A continuation",
            },
            output_dir / "candidate_b_depth8.v",
            candidate_b.render("candidate_b_depth8"),
            log_path,
            random_tests,
            random_seed,
        ),
        _verify_and_record(
            "C",
            "candidate-c-phase4-balanced-starting-point-v1",
            "phase4-balanced-depth-starting-point-v1",
            {
                "candidate_class": "C",
                "source_seed": None,
                "construction": "balanced per-output XOR2 trees",
            },
            output_dir / "candidate_c_min_depth.v",
            _render_candidate_c(),
            log_path,
            random_tests,
            random_seed,
        ),
    ]
    (output_dir / "candidate_starting_points.json").write_text(
        json.dumps({"schema_version": 1, "entries": records}, indent=2, sort_keys=True)
        + "\n"
    )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("results/phase4"))
    parser.add_argument("--search-log", type=Path, default=Path("results/search_log.jsonl"))
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument("--random-seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED)
    args = parser.parse_args()
    try:
        records = materialize(args.output_dir, args.search_log, args.random_tests, args.random_seed)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Phase 4 candidate setup failed: {error}\n")
    print(json.dumps(records, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

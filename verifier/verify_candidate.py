"""Verify Candidate A and cross-check its machine-readable result records."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from verifier.run_formal import run as run_formal
from verifier.verify_network import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    VerificationError,
    verification_report,
)


def _integer(row: dict[str, str], field: str) -> int:
    try:
        return int(row[field])
    except (KeyError, ValueError) as error:
        raise ValueError(f"metrics CSV has invalid {field}") from error


def _validate_frontier_verification(
    entry: dict[str, object],
    report: dict[str, object],
    random_tests: int,
    random_seed: int,
) -> None:
    expected = {
        "structural": "passed",
        "exact_vectors": report.get("exact_vectors_checked"),
        "random_vectors": random_tests,
        "random_seed": random_seed,
        "formal_equivalence": "passed",
    }
    if entry.get("verification") != expected:
        raise ValueError(
            "frontier verification record does not match performed checks"
        )


def verify_candidate_records(
    candidate_path: Path,
    frontier_path: Path,
    metrics_path: Path,
    checkpoint_path: Path,
    search_log_path: Path,
    random_tests: int,
    random_seed: int,
) -> dict[str, object]:
    report = verification_report(candidate_path, random_tests, random_seed)
    run_formal(candidate_path)
    measured = report["metrics"]
    if not isinstance(measured, dict):
        raise ValueError("verifier returned malformed metrics")

    frontier = json.loads(frontier_path.read_text())
    entries = frontier.get("entries") if isinstance(frontier, dict) else None
    if not isinstance(entries, list) or len(entries) != 1:
        raise ValueError("Candidate A frontier must contain exactly one entry")
    entry = entries[0]
    if not isinstance(entry, dict) or entry.get("candidate_class") != "A":
        raise ValueError("frontier entry is not Candidate A")
    if Path(str(entry.get("artifact"))).resolve() != candidate_path.resolve():
        raise ValueError("frontier artifact does not identify the submitted candidate")
    if entry.get("metrics") != {
        key: value for key, value in measured.items() if key != "unreachable_nodes"
    }:
        raise ValueError("frontier metrics do not match independent measurement")
    _validate_frontier_verification(entry, report, random_tests, random_seed)

    with metrics_path.open(newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != 1 or rows[0].get("candidate_class") != "A":
        raise ValueError("metrics CSV must contain exactly Candidate A")
    row = rows[0]
    if Path(row.get("artifact", "")).resolve() != candidate_path.resolve():
        raise ValueError("metrics CSV artifact does not identify the candidate")
    integer_fields = (
        "xor2_count",
        "maximum_depth",
        "maximum_fanout",
        "total_fanout",
        "total_excess_fanout_above_4",
        "intermediate_node_count",
        "direct_output_alias_count",
    )
    for field in integer_fields:
        if _integer(row, field) != measured[field]:
            raise ValueError(f"metrics CSV {field} does not match measurement")
    if json.loads(row.get("output_depths", "null")) != measured["output_depths"]:
        raise ValueError("metrics CSV output_depths do not match measurement")
    if _integer(row, "exact_vectors_checked") != 97:
        raise ValueError("metrics CSV exact-vector count is not 97")
    if _integer(row, "random_vectors_checked") != random_tests:
        raise ValueError("metrics CSV random-vector count does not match")
    if _integer(row, "random_seed") != random_seed:
        raise ValueError("metrics CSV random seed does not match")
    if row.get("formal_equivalence") != "passed":
        raise ValueError("metrics CSV does not record passing formal equivalence")

    candidate_seed = entry.get("seed")
    if not isinstance(candidate_seed, int) or _integer(row, "seed") != candidate_seed:
        raise ValueError("Candidate A seed disagrees between frontier and metrics CSV")
    checkpoint = json.loads(checkpoint_path.read_text())
    if not isinstance(checkpoint, dict) or checkpoint.get("status") != "completed":
        raise ValueError("Candidate A checkpoint is not complete")
    if checkpoint.get("completed_seeds") != checkpoint.get("seed_count"):
        raise ValueError("checkpoint did not complete its full seed budget")
    if checkpoint.get("incumbent_seed") != candidate_seed:
        raise ValueError("checkpoint incumbent seed does not match Candidate A")
    if checkpoint.get("incumbent_metrics") != measured:
        raise ValueError("checkpoint incumbent metrics do not match measurement")

    expected_count = checkpoint.get("seed_count")
    seed_start = checkpoint.get("seed_start")
    if not isinstance(expected_count, int) or not isinstance(seed_start, int):
        raise ValueError("checkpoint seed range is malformed")
    algorithm = checkpoint.get("algorithm")
    if not isinstance(algorithm, str) or not algorithm:
        raise ValueError("checkpoint algorithm is malformed")
    attempts = [
        record
        for line in search_log_path.read_text().splitlines()
        for record in [json.loads(line)]
        if record.get("algorithm") == algorithm
        and isinstance(record.get("seed"), int)
        and seed_start <= record["seed"] < seed_start + expected_count
    ]
    if len(attempts) != expected_count:
        raise ValueError("search log attempt count does not match checkpoint budget")
    attempt_ids = [attempt.get("attempt_id") for attempt in attempts]
    if len(set(attempt_ids)) != len(attempt_ids):
        raise ValueError("search log contains duplicate attempt IDs")
    seeds = [attempt.get("seed") for attempt in attempts]
    if seeds != list(range(seed_start, seed_start + expected_count)):
        raise ValueError("search log does not contain the complete ordered seed range")
    best = min(
        (
            attempt["final_metrics"]["xor2_count"],
            attempt["final_metrics"]["maximum_depth"],
            attempt["seed"],
        )
        for attempt in attempts
    )
    if best != (measured["xor2_count"], measured["maximum_depth"], candidate_seed):
        raise ValueError("frontier candidate is not the best logged Candidate A trial")
    final_attempt = attempts[candidate_seed - seed_start]
    if not final_attempt.get("accepted") or not final_attempt.get(
        "verification_passed"
    ):
        raise ValueError("winning search attempt was not verified and accepted")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate", type=Path, default=Path("results/candidate_a_min_area.v")
    )
    parser.add_argument(
        "--frontier", type=Path, default=Path("results/pareto_frontier.json")
    )
    parser.add_argument("--metrics", type=Path, default=Path("results/metrics.csv"))
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("results/checkpoints/candidate_a_checkpoint.json"),
    )
    parser.add_argument(
        "--search-log", type=Path, default=Path("results/search_log.jsonl")
    )
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED
    )
    args = parser.parse_args()
    if args.random_tests < DEFAULT_RANDOM_TESTS:
        parser.error(f"--random-tests must be at least {DEFAULT_RANDOM_TESTS}")
    try:
        report = verify_candidate_records(
            args.candidate,
            args.frontier,
            args.metrics,
            args.checkpoint,
            args.search_log,
            args.random_tests,
            args.seed,
        )
    except (OSError, RuntimeError, ValueError, VerificationError) as error:
        parser.exit(1, f"Candidate A verification failed: {error}\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

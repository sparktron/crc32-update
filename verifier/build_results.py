"""Regenerate the final metrics table and Pareto frontier from verified artifacts.

Every submitted candidate is re-run through the restricted parser, the 97 exact
vectors, the seeded randomized check, and formal equivalence. Its measured
metrics are then cross-checked against the completed Phase 4 checkpoints, the
append-only search log, and the Phase 5 exact-study records before any result
file is written. Nothing here searches or changes a candidate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from verifier.run_formal import run as run_formal
from verifier.search_logs import SEARCH_LOG_DIR, read_records
from verifier.verify_network import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    PRIMARY_INPUTS,
    VerificationError,
    parse_network_file,
    verification_report,
)

GENERATED_BY = "phase6-final-results-v1"
OBJECTIVES = (
    "xor2_count",
    "maximum_depth",
    "maximum_fanout",
    "total_excess_fanout_above_4",
)
MINIMUM_DISTINCT_PARETO_CANDIDATES = 3
REQUIRED_CANDIDATE_CLASSES = ("A", "B", "C")
CANDIDATE_B_DEPTH_BOUND = 8
CANDIDATE_A_ALGORITHM = "gf2-bp-cse-depth-stochastic-v1"
CANDIDATE_A_CHECKPOINTS = (
    Path("results/checkpoints/candidate_a_checkpoint.json"),
    Path("results/checkpoints/phase4_candidate_a_checkpoint.json"),
)
PHASE5_STUDY = Path("results/phase5/exact_exclusive_cone_study.json")
PHASE5_CHECKPOINT = Path("results/checkpoints/phase5_exact_exclusive_cones.json")
PHASE5_ALGORITHM = "phase5-exact-exclusive-cone-v2"
PHASE5_EXPLORATORY_ALGORITHM = "phase5-exact-single-cone-v1"
BASELINE_METRICS = Path("results/baseline_metrics.csv")
METRIC_FIELDS = (
    "xor2_count",
    "maximum_depth",
    "maximum_fanout",
    "total_fanout",
    "total_excess_fanout_above_4",
    "intermediate_node_count",
    "direct_output_alias_count",
)
CSV_HEADER = (
    "candidate_class",
    "artifact",
    "circuit_id",
    "on_pareto_frontier",
    "seed",
    "xor2_count",
    "maximum_depth",
    "output_depths",
    "maximum_fanout",
    "total_fanout",
    "total_excess_fanout_above_4",
    "intermediate_node_count",
    "direct_output_alias_count",
    "exact_vectors_checked",
    "random_vectors_checked",
    "random_seed",
    "formal_equivalence",
    "verification_status",
)


@dataclass(frozen=True)
class Refinement:
    search_class: str
    starting_algorithm: str
    starting_artifact: Path
    checkpoint: Path


@dataclass(frozen=True)
class BoundedBudget:
    depth_cap: int
    checkpoint: Path
    incumbent_dir: Path

    @property
    def algorithm(self) -> str:
        return f"kraft-bounded-bp-cse-depth{self.depth_cap}-v1"

    @property
    def module_name(self) -> str:
        return f"candidate_depth{self.depth_cap}_bounded"


@dataclass(frozen=True)
class Submission:
    candidate_class: str
    artifact: Path
    refinement: Refinement | None = None
    bounded: BoundedBudget | None = None


SUBMISSIONS = (
    Submission("A", Path("results/phase4/candidate_a_extended.v")),
    Submission(
        "B",
        Path("results/phase4/candidate_b_refined.v"),
        Refinement(
            "B",
            "phase4-depth8-starting-point-v1",
            Path("results/phase4/candidate_b_depth8.v"),
            Path("results/checkpoints/candidate_b_refinement.json"),
        ),
    ),
    # C0 is the Phase 4 minimum-depth starting point and its unimproved
    # refinement. It is kept for provenance; the depth-6 budget below supplies
    # the circuit that satisfies Candidate C's depth-then-gate-count objective.
    Submission(
        "C0",
        Path("results/phase4/candidate_c_refined.v"),
        Refinement(
            "C",
            "phase4-balanced-depth-starting-point-v1",
            Path("results/phase4/candidate_c_min_depth.v"),
            Path("results/checkpoints/candidate_c_refinement.json"),
        ),
    ),
    # Separately recorded Kraft-bounded budgets: B7 is a bounded-depth
    # (Candidate B family) search at depth 7, and C is the minimum-depth search
    # at depth 6, the lowest depth any XOR2 network for the widest output row
    # can reach.
    Submission(
        "B7",
        Path("results/phase6/candidate_depth7_bounded.v"),
        bounded=BoundedBudget(
            7,
            Path("results/checkpoints/depth7_bounded_search.json"),
            Path("results/checkpoints/depth7_bounded_incumbents"),
        ),
    ),
    Submission(
        "C",
        Path("results/phase6/candidate_depth6_bounded.v"),
        bounded=BoundedBudget(
            6,
            Path("results/checkpoints/depth6_bounded_search.json"),
            Path("results/checkpoints/depth6_bounded_incumbents"),
        ),
    ),
)


def _json(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text())
    if not isinstance(document, dict):
        raise ValueError(f"{path} is not a JSON object")
    return document


def _without_unreachable(metrics: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in metrics.items() if key != "unreachable_nodes"}


def dominates(left: dict[str, object], right: dict[str, object]) -> bool:
    """Return whether ``left`` is no worse on every objective and better on one."""
    return all(left[key] <= right[key] for key in OBJECTIVES) and any(
        left[key] < right[key] for key in OBJECTIVES
    )


def nondominated(points: dict[str, dict[str, object]]) -> list[str]:
    return sorted(
        name
        for name, metrics in points.items()
        if not any(
            dominates(other, metrics)
            for other_name, other in points.items()
            if other_name != name
        )
    )


def structural_fingerprint(path: Path) -> str:
    """Hash the normalized XOR2 DAG independently of module and wire names.

    Each node is labelled by the hash of its canonical input labels, so two
    netlists that differ only in naming share a fingerprint while separately
    instantiated duplicate gates remain distinct entries in the node multiset.
    """
    normalized = parse_network_file(path).normalize()
    labels = {signal: signal for signal in PRIMARY_INPUTS}
    node_labels = []
    for node in normalized.nodes:
        inputs = sorted(labels[signal] for signal in normalized.canonical_inputs[node.output])
        label = hashlib.sha256(json.dumps(["xor2", inputs]).encode()).hexdigest()
        labels[node.output] = label
        node_labels.append(label)
    document = {
        "nodes": sorted(node_labels),
        "outputs": [labels[source] for source in normalized.output_sources],
    }
    return hashlib.sha256(json.dumps(document).encode()).hexdigest()


def _log_records(search_log: Path) -> list[dict[str, object]]:
    """Read every per-experiment log in a directory, or one log file."""
    return read_records(search_log)


def _check_completed_checkpoint(checkpoint: dict[str, object], name: Path) -> None:
    if checkpoint.get("status") != "completed":
        raise ValueError(f"{name} is not complete")
    if checkpoint.get("completed_seeds") != checkpoint.get("seed_count"):
        raise ValueError(f"{name} did not complete its full seed budget")


def _seed_range_records(
    records: list[dict[str, object]], algorithm: str, checkpoint: dict[str, object]
) -> list[dict[str, object]]:
    seed_start = checkpoint.get("seed_start")
    seed_count = checkpoint.get("seed_count")
    if not isinstance(seed_start, int) or not isinstance(seed_count, int):
        raise ValueError(f"{algorithm} checkpoint seed range is malformed")
    attempts = [
        record
        for record in records
        if record.get("algorithm") == algorithm
        and isinstance(record.get("seed"), int)
        and seed_start <= record["seed"] < seed_start + seed_count
    ]
    if [record["seed"] for record in attempts] != list(
        range(seed_start, seed_start + seed_count)
    ):
        raise ValueError(f"{algorithm} log does not hold its complete ordered seed range")
    ids = [record.get("attempt_id") for record in attempts]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{algorithm} log contains duplicate attempt IDs")
    return attempts


def check_candidate_a(
    measured: dict[str, object],
    artifact: Path,
    records: list[dict[str, object]],
    checkpoints: tuple[Path, ...] = CANDIDATE_A_CHECKPOINTS,
) -> dict[str, object]:
    """Confirm the artifact is the best verified Candidate A trial across all budgets."""
    attempts: list[dict[str, object]] = []
    budgets = []
    for path in checkpoints:
        checkpoint = _json(path)
        _check_completed_checkpoint(checkpoint, path)
        if checkpoint.get("algorithm") != CANDIDATE_A_ALGORITHM:
            raise ValueError(f"{path} is not a Candidate A checkpoint")
        attempts.extend(_seed_range_records(records, CANDIDATE_A_ALGORITHM, checkpoint))
        budgets.append(
            {
                "checkpoint": str(path),
                "seed_start": checkpoint["seed_start"],
                "seed_count": checkpoint["seed_count"],
            }
        )
    best = min(
        (
            attempt["final_metrics"]["xor2_count"],
            attempt["final_metrics"]["maximum_depth"],
            attempt["seed"],
        )
        for attempt in attempts
    )
    if best[:2] != (measured["xor2_count"], measured["maximum_depth"]):
        raise ValueError("Candidate A is not the best logged Candidate A trial")
    winner = next(attempt for attempt in attempts if attempt["seed"] == best[2])
    if not winner.get("accepted") or not winner.get("verification_passed"):
        raise ValueError("winning Candidate A attempt was not verified and accepted")
    if _without_unreachable(winner["final_metrics"]) != _without_unreachable(measured):
        raise ValueError("winning Candidate A log metrics do not match measurement")
    incumbent = Path(str(winner.get("artifact")))
    if incumbent.read_bytes() != artifact.read_bytes():
        raise ValueError("Candidate A artifact differs from its accepted incumbent")
    owning = [
        path
        for path in checkpoints
        if _json(path).get("incumbent_seed") == winner["seed"]
    ]
    if len(owning) != 1 or _json(owning[0]).get("incumbent_metrics") != measured:
        raise ValueError("no completed checkpoint records the Candidate A incumbent")
    return {
        "algorithm": CANDIDATE_A_ALGORITHM,
        "budgets": budgets,
        "logged_attempts": len(attempts),
        "winning_attempt_id": winner["attempt_id"],
        "seed": winner["seed"],
    }


def check_refinement(
    submission: Submission,
    measured: dict[str, object],
    records: list[dict[str, object]],
) -> dict[str, object]:
    """Confirm a B/C artifact is its verified starting point after an unimproved budget."""
    refinement = submission.refinement
    assert refinement is not None
    starts = [
        record
        for record in records
        if record.get("algorithm") == refinement.starting_algorithm
    ]
    if len(starts) != 1:
        raise ValueError(f"Candidate {submission.candidate_class} needs one starting point")
    start = starts[0]
    if not start.get("accepted") or not start.get("verification_passed"):
        raise ValueError("starting point was not verified and accepted")
    if Path(str(start.get("artifact"))) != refinement.starting_artifact:
        raise ValueError("starting-point log record names a different artifact")
    if start.get("final_metrics") != _without_unreachable(measured):
        raise ValueError("starting-point log metrics do not match measurement")
    checkpoint = _json(refinement.checkpoint)
    _check_completed_checkpoint(checkpoint, refinement.checkpoint)
    if checkpoint.get("candidate_class") != refinement.search_class:
        raise ValueError(f"{refinement.checkpoint} is for another candidate class")
    if checkpoint.get("incumbent_metrics") != _without_unreachable(measured):
        raise ValueError("refinement incumbent metrics do not match measurement")
    algorithm = str(checkpoint.get("algorithm"))
    attempts = _seed_range_records(records, algorithm, checkpoint)
    accepted = [attempt for attempt in attempts if attempt.get("accepted")]
    if accepted:
        raise ValueError(
            f"Candidate {submission.candidate_class} refinement accepted an attempt "
            "that the submitted artifact does not reflect"
        )
    if submission.artifact.read_bytes() != refinement.starting_artifact.read_bytes():
        raise ValueError("unimproved refinement output differs from its starting point")
    return {
        "starting_point_attempt_id": start["attempt_id"],
        "starting_point_artifact": str(refinement.starting_artifact),
        "source_seed": start.get("seed"),
        "refinement": {
            "algorithm": algorithm,
            "checkpoint": str(refinement.checkpoint),
            "seed_start": checkpoint["seed_start"],
            "seed_count": checkpoint["seed_count"],
            "accepted_improvements": 0,
        },
    }


def _bounded_order(metrics: dict[str, object], seed: int) -> tuple[int, ...]:
    """Incumbent order for bounded budgets: SPEC objective order, then seed."""
    return (*(int(metrics[key]) for key in OBJECTIVES), seed)


def check_bounded_search(
    submission: Submission,
    measured: dict[str, object],
    records: list[dict[str, object]],
    random_tests: int,
    random_seed: int,
    replay: bool = True,
) -> dict[str, object]:
    """Confirm the artifact is the best verified trial of a completed bounded budget."""
    budget = submission.bounded
    assert budget is not None
    checkpoint = _json(budget.checkpoint)
    _check_completed_checkpoint(checkpoint, budget.checkpoint)
    expected = {
        "algorithm": budget.algorithm,
        "depth_cap": budget.depth_cap,
        "random_seed": random_seed,
    }
    if {key: checkpoint.get(key) for key in expected} != expected:
        raise ValueError(f"{budget.checkpoint} does not match the recorded budget")
    recorded_tests = checkpoint.get("random_tests")
    if not isinstance(recorded_tests, int) or recorded_tests < random_tests:
        raise ValueError(f"{budget.checkpoint} used fewer random vectors than required")
    if int(measured["maximum_depth"]) > budget.depth_cap:
        raise ValueError(f"{submission.artifact} exceeds depth cap {budget.depth_cap}")
    attempts = _seed_range_records(records, budget.algorithm, checkpoint)
    for attempt in attempts:
        metrics = attempt.get("final_metrics")
        if not attempt.get("verification_passed") or not isinstance(metrics, dict):
            raise ValueError(f"{attempt.get('attempt_id')} was not verified")
        if int(metrics["maximum_depth"]) > budget.depth_cap:
            raise ValueError(f"{attempt.get('attempt_id')} exceeds the depth cap")
    winner = min(
        attempts, key=lambda attempt: _bounded_order(attempt["final_metrics"], attempt["seed"])
    )
    accepted = [attempt for attempt in attempts if attempt.get("accepted")]
    if not accepted or accepted[-1] is not winner:
        raise ValueError("the best logged bounded trial is not the last accepted incumbent")
    if checkpoint.get("incumbent_seed") != winner["seed"]:
        raise ValueError("checkpoint incumbent seed is not the best logged trial")
    measured_metrics = _without_unreachable(measured)
    if winner["final_metrics"] != measured_metrics or checkpoint.get(
        "incumbent_metrics"
    ) != measured_metrics:
        raise ValueError("bounded incumbent metrics do not match measurement")
    incumbent = budget.incumbent_dir / f"seed_{winner['seed']}.v"
    if Path(str(winner.get("artifact"))) != incumbent:
        raise ValueError("winning log record names a different incumbent artifact")
    if incumbent.read_bytes() != submission.artifact.read_bytes():
        raise ValueError(f"{submission.artifact} differs from its accepted incumbent")
    if replay:
        # Reproducibility only: the metrics above come from the independent
        # verifier, never from optimizer code.
        from optimizer.depth_bounded import search_seed_bounded

        regenerated = search_seed_bounded(winner["seed"], budget.depth_cap)
        if regenerated.render(budget.module_name) != submission.artifact.read_text():
            raise ValueError(f"{submission.artifact} does not replay from its seed")
    return {
        "algorithm": budget.algorithm,
        "checkpoint": str(budget.checkpoint),
        "depth_cap": budget.depth_cap,
        "seed_start": checkpoint["seed_start"],
        "seed_count": checkpoint["seed_count"],
        "logged_attempts": len(attempts),
        "accepted_incumbents": len(accepted),
        "winning_attempt_id": winner["attempt_id"],
        "seed": winner["seed"],
        "replayed_from_seed": replay,
    }


def check_class_objectives(metrics_by_class: dict[str, dict[str, object]]) -> None:
    """Require each SPEC.md Section 4 class to win its objective among submissions.

    A minimizes XOR2 count; B minimizes XOR2 count within the depth-8 bound;
    C minimizes depth first, then XOR2 count. Ties are allowed.
    """
    missing = [label for label in REQUIRED_CANDIDATE_CLASSES if label not in metrics_by_class]
    if missing:
        raise ValueError(f"required candidate classes are missing: {', '.join(missing)}")
    points = list(metrics_by_class.values())

    def best(eligible, key, label: str, objective: str) -> None:
        candidates = [metrics for metrics in points if eligible(metrics)]
        if not eligible(metrics_by_class[label]):
            raise ValueError(f"Candidate {label} does not satisfy its class constraint")
        if any(key(metrics) < key(metrics_by_class[label]) for metrics in candidates):
            raise ValueError(f"Candidate {label} does not {objective} among submissions")

    best(lambda m: True, lambda m: m["xor2_count"], "A", "minimize XOR2 count")
    best(
        lambda m: m["maximum_depth"] <= CANDIDATE_B_DEPTH_BOUND,
        lambda m: m["xor2_count"],
        "B",
        f"minimize XOR2 count at depth {CANDIDATE_B_DEPTH_BOUND} or less",
    )
    best(
        lambda m: True,
        lambda m: (m["maximum_depth"], m["xor2_count"]),
        "C",
        "minimize depth, then XOR2 count,",
    )


def check_phase5(
    study: dict[str, object],
    checkpoint: dict[str, object],
    records: list[dict[str, object]],
    candidate_b: Path,
) -> dict[str, object]:
    """Confirm the completed exclusive-cone study changed no submitted network."""
    configuration = study.get("configuration")
    if study.get("status") != "completed" or not isinstance(configuration, dict):
        raise ValueError("Phase 5 v2 study is not complete")
    if Path(str(configuration.get("candidate"))) != candidate_b:
        raise ValueError("Phase 5 v2 study did not run on the submitted Candidate B")
    roots = configuration.get("roots")
    outcomes = study.get("outcomes")
    if not isinstance(roots, list) or not isinstance(outcomes, list):
        raise ValueError("Phase 5 v2 study roots or outcomes are malformed")
    if [outcome.get("root") for outcome in outcomes] != roots:
        raise ValueError("Phase 5 v2 outcomes do not cover the configured roots")
    if checkpoint.get("completed_roots") != roots or checkpoint.get("outcomes") != outcomes:
        raise ValueError("Phase 5 v2 checkpoint disagrees with the study output")
    for outcome in outcomes:
        if outcome.get("witness") is not None or outcome.get(
            "replacement_gate_count"
        ) is not None:
            raise ValueError(
                f"Phase 5 cone {outcome.get('root')} has a replacement witness; "
                "integrate and re-verify it before regenerating the frontier"
            )
    logged = [record for record in records if record.get("algorithm") == PHASE5_ALGORITHM]
    if [record.get("study_outcome") for record in logged] != outcomes:
        raise ValueError("Phase 5 v2 log records disagree with the study output")
    exploratory = [
        record
        for record in records
        if record.get("algorithm") == PHASE5_EXPLORATORY_ALGORITHM
    ]
    if any(record.get("accepted") for record in logged + exploratory):
        raise ValueError("a Phase 5 attempt was accepted but not integrated")
    status_counts: dict[str, int] = {}
    for outcome in outcomes:
        status = str(outcome.get("solver_status"))
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "algorithm": PHASE5_ALGORITHM,
        "study": str(PHASE5_STUDY),
        "input_candidate": str(candidate_b),
        "solver_version": study.get("solver_version"),
        "max_cone_nodes": configuration.get("max_cone_nodes"),
        "timeout_ms": configuration.get("timeout_ms"),
        "cones": len(outcomes),
        "solver_status_counts": dict(sorted(status_counts.items())),
        "accepted_replacements": 0,
        "exploratory_v1_attempts_not_used_as_evidence": len(exploratory),
        "scope": "UNSAT results apply only to their single-cone encodings",
    }


def _baseline_comparison(
    path: Path, frontier: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    with path.open(newline="") as source:
        rows = list(csv.DictReader(source))
    comparison = []
    for row in rows:
        metrics = {key: int(row[key]) for key in OBJECTIVES}
        comparison.append(
            {
                "baseline": row["baseline"],
                "metrics": metrics,
                "dominated_by": sorted(
                    circuit_id
                    for circuit_id, point in frontier.items()
                    if dominates(point, metrics)
                ),
            }
        )
    return comparison


def build_results(
    random_tests: int = DEFAULT_RANDOM_TESTS,
    random_seed: int = DEFAULT_RANDOM_SEED,
    search_log: Path = SEARCH_LOG_DIR,
) -> tuple[dict[str, object], str]:
    records = _log_records(search_log)
    submitted = []
    circuits: dict[str, dict[str, object]] = {}
    for submission in SUBMISSIONS:
        report = verification_report(submission.artifact, random_tests, random_seed)
        run_formal(submission.artifact)
        measured = report["metrics"]
        if not isinstance(measured, dict):
            raise ValueError("verifier returned malformed metrics")
        if measured.get("unreachable_nodes"):
            raise ValueError(f"{submission.artifact} has unreachable nodes")
        if submission.bounded is not None:
            provenance = check_bounded_search(
                submission, measured, records, random_tests, random_seed
            )
            seed = provenance["seed"]
        elif submission.refinement is None:
            provenance = check_candidate_a(measured, submission.artifact, records)
            seed = provenance["seed"]
        else:
            provenance = check_refinement(submission, measured, records)
            seed = provenance["source_seed"]
        fingerprint = structural_fingerprint(submission.artifact)
        circuit_id = fingerprint[:12]
        metrics = _without_unreachable(measured)
        circuits.setdefault(circuit_id, metrics)
        submitted.append(
            {
                "candidate_class": submission.candidate_class,
                "artifact": str(submission.artifact),
                "module": report["module"],
                "circuit_id": circuit_id,
                "structural_sha256": fingerprint,
                "seed": seed,
                "metrics": metrics,
                "verification": {
                    "structural": "passed",
                    "exact_vectors": report["exact_vectors_checked"],
                    "random_vectors": report["random_vectors_checked"],
                    "random_seed": report["random_seed"],
                    "formal_equivalence": "passed",
                },
                "provenance": provenance,
            }
        )

    by_class = {entry["candidate_class"]: entry for entry in submitted}
    if len(by_class) != len(submitted):
        raise ValueError("candidate class labels must be unique")
    check_class_objectives(
        {label: entry["metrics"] for label, entry in by_class.items()}
    )

    phase5 = check_phase5(
        _json(PHASE5_STUDY),
        _json(PHASE5_CHECKPOINT),
        records,
        Path(by_class["B"]["artifact"]),
    )

    frontier_ids = nondominated(circuits)
    for entry in submitted:
        entry["on_pareto_frontier"] = entry["circuit_id"] in frontier_ids
    entries = []
    for circuit_id in frontier_ids:
        members = [entry for entry in submitted if entry["circuit_id"] == circuit_id]
        entries.append(
            {
                "circuit_id": circuit_id,
                "structural_sha256": members[0]["structural_sha256"],
                "candidate_classes": [entry["candidate_class"] for entry in members],
                "artifacts": [entry["artifact"] for entry in members],
                "metrics": circuits[circuit_id],
            }
        )
    frontier = {
        "schema_version": 2,
        "generated_by": GENERATED_BY,
        "objectives": list(OBJECTIVES),
        "entries": entries,
        "submitted_candidates": submitted,
        "phase5_exact_study": phase5,
        "baseline_comparison": _baseline_comparison(
            BASELINE_METRICS, {circuit_id: circuits[circuit_id] for circuit_id in frontier_ids}
        ),
        "specification_checks": {
            "required_candidate_classes": list(REQUIRED_CANDIDATE_CLASSES),
            "required_candidate_classes_reported": all(
                label in by_class for label in REQUIRED_CANDIDATE_CLASSES
            ),
            "reported_candidate_classes": sorted(by_class),
            "candidate_b_depth_bound": CANDIDATE_B_DEPTH_BOUND,
            "minimum_distinct_pareto_candidates": MINIMUM_DISTINCT_PARETO_CANDIDATES,
            "distinct_pareto_candidates": len(entries),
            "minimum_distinct_pareto_candidates_met": (
                len(entries) >= MINIMUM_DISTINCT_PARETO_CANDIDATES
                and all(label in by_class for label in REQUIRED_CANDIDATE_CLASSES)
            ),
        },
    }
    return frontier, _render_metrics(submitted)


def _render_metrics(submitted: list[dict[str, object]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for entry in submitted:
        metrics = entry["metrics"]
        verification = entry["verification"]
        writer.writerow(
            [
                entry["candidate_class"],
                entry["artifact"],
                entry["circuit_id"],
                str(entry["on_pareto_frontier"]).lower(),
                "" if entry["seed"] is None else entry["seed"],
                metrics["xor2_count"],
                metrics["maximum_depth"],
                json.dumps(metrics["output_depths"], separators=(",", ":")),
                *(metrics[field] for field in METRIC_FIELDS[2:]),
                verification["exact_vectors"],
                verification["random_vectors"],
                verification["random_seed"],
                verification["formal_equivalence"],
                "passed",
            ]
        )
    return buffer.getvalue()


def render_frontier(frontier: dict[str, object]) -> str:
    return json.dumps(frontier, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontier", type=Path, default=Path("results/pareto_frontier.json")
    )
    parser.add_argument("--metrics", type=Path, default=Path("results/metrics.csv"))
    parser.add_argument(
        "--search-log",
        type=Path,
        default=SEARCH_LOG_DIR,
        help="directory of per-experiment logs, or one log file",
    )
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed files match regeneration instead of writing them",
    )
    parser.add_argument(
        "--require-spec-minimum",
        action="store_true",
        help="exit nonzero unless the SPEC.md distinct-Pareto-candidate minimum is met",
    )
    args = parser.parse_args()
    if args.random_tests < DEFAULT_RANDOM_TESTS:
        parser.error(f"--random-tests must be at least {DEFAULT_RANDOM_TESTS}")
    try:
        frontier, metrics = build_results(args.random_tests, args.seed, args.search_log)
    except (OSError, RuntimeError, ValueError, KeyError, VerificationError) as error:
        parser.exit(1, f"Result regeneration failed: {error}\n")
    frontier_text = render_frontier(frontier)
    if args.check:
        stale = [
            str(path)
            for path, text in ((args.frontier, frontier_text), (args.metrics, metrics))
            if not path.exists() or path.read_text() != text
        ]
        if stale:
            parser.exit(1, f"Result files do not match regeneration: {', '.join(stale)}\n")
    else:
        for path, text in ((args.frontier, frontier_text), (args.metrics, metrics)):
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(text)
            temporary.replace(path)
    checks = frontier["specification_checks"]
    print(
        f"{checks['distinct_pareto_candidates']} distinct Pareto candidate(s) from "
        f"{len(frontier['submitted_candidates'])} submitted candidate classes."
    )
    if not checks["minimum_distinct_pareto_candidates_met"]:
        print(
            "WARNING: SPEC.md requires at least "
            f"{checks['minimum_distinct_pareto_candidates']} distinct nondominated "
            "circuits; G6 cannot pass until another verified candidate is added.",
            file=sys.stderr,
        )
        if args.require_spec_minimum:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

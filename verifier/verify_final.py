"""Verify and regenerate the Phase 6 final Pareto-candidate records."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from verifier.run_formal import run as run_formal
from verifier.verify_network import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    VerificationError,
    parse_network_file,
    verification_report,
)


REQUIRED_CANDIDATE_CLASSES = frozenset({"A", "B", "C"})
OBJECTIVES = (
    "xor2_count",
    "maximum_depth",
    "maximum_fanout",
    "total_excess_fanout_above_4",
)
CSV_FIELDS = (
    "candidate_id",
    "candidate_classes",
    "role",
    "artifact",
    "structural_fingerprint",
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


def _structural_fingerprint(path: Path) -> str:
    """Hash normalized topology while ignoring only the top-module name."""

    network = parse_network_file(path).normalize()
    topology = {
        "nodes": [
            {
                "output": node.output,
                "inputs": list(network.canonical_inputs[node.output]),
            }
            for node in network.nodes
        ],
        "output_sources": list(network.output_sources),
    }
    encoded = json.dumps(topology, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _dominates(first: dict[str, object], second: dict[str, object]) -> bool:
    first_values = tuple(int(first[field]) for field in OBJECTIVES)
    second_values = tuple(int(second[field]) for field in OBJECTIVES)
    return all(a <= b for a, b in zip(first_values, second_values)) and any(
        a < b for a, b in zip(first_values, second_values)
    )


def validate_frontier_entries(entries: list[dict[str, object]]) -> None:
    """Enforce the frozen class, uniqueness, and nondominance requirements."""

    if len(entries) < 3:
        raise ValueError("final frontier must contain at least three candidates")
    candidate_ids = [entry.get("candidate_id") for entry in entries]
    if any(not isinstance(value, str) or not value for value in candidate_ids):
        raise ValueError("every final frontier entry needs a candidate_id")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("final frontier contains duplicate candidate IDs")

    fingerprints = [entry.get("structural_fingerprint") for entry in entries]
    if any(not isinstance(value, str) or not value for value in fingerprints):
        raise ValueError("every final frontier entry needs a structural fingerprint")
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("final frontier does not contain three distinct circuits")

    represented_classes: set[str] = set()
    for entry in entries:
        classes = entry.get("candidate_classes")
        if not isinstance(classes, list) or any(
            candidate_class not in REQUIRED_CANDIDATE_CLASSES
            for candidate_class in classes
        ):
            raise ValueError("candidate_classes must contain only A, B, or C")
        represented_classes.update(classes)
        metrics = entry.get("metrics")
        if not isinstance(metrics, dict) or any(
            type(metrics.get(field)) is not int for field in OBJECTIVES
        ):
            raise ValueError("final frontier entry has malformed objective metrics")
    missing_classes = sorted(REQUIRED_CANDIDATE_CLASSES - represented_classes)
    if missing_classes:
        raise ValueError(
            "final frontier does not represent candidate class(es): "
            + ", ".join(missing_classes)
        )

    for index, entry in enumerate(entries):
        metrics = entry["metrics"]
        assert isinstance(metrics, dict)
        for other_index, other in enumerate(entries):
            if index == other_index:
                continue
            other_metrics = other["metrics"]
            assert isinstance(other_metrics, dict)
            if _dominates(other_metrics, metrics):
                raise ValueError(
                    f"{entry['candidate_id']} is dominated by {other['candidate_id']}"
                )


def _load_manifest(path: Path) -> list[dict[str, object]]:
    document = json.loads(path.read_text())
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("final candidate manifest must use schema version 1")
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("final candidate manifest needs a candidates list")
    result: list[dict[str, object]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"manifest candidate {index} is not an object")
        candidate_id = candidate.get("candidate_id")
        role = candidate.get("role")
        artifact = candidate.get("artifact")
        classes = candidate.get("candidate_classes")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError(f"manifest candidate {index} has no candidate_id")
        if not isinstance(role, str) or not role:
            raise ValueError(f"manifest candidate {candidate_id} has no role")
        if not isinstance(artifact, str) or not artifact:
            raise ValueError(f"manifest candidate {candidate_id} has no artifact")
        if not isinstance(classes, list) or any(
            not isinstance(value, str) for value in classes
        ):
            raise ValueError(
                f"manifest candidate {candidate_id} has invalid candidate_classes"
            )
        result.append(candidate)
    return result


def verify_final_candidates(
    manifest_path: Path,
    random_tests: int,
    random_seed: int,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for candidate in _load_manifest(manifest_path):
        artifact = Path(str(candidate["artifact"]))
        report = verification_report(artifact, random_tests, random_seed)
        run_formal(artifact)
        metrics = report.get("metrics")
        if not isinstance(metrics, dict):
            raise RuntimeError("verifier returned malformed metrics")
        metrics = {
            key: value for key, value in metrics.items() if key != "unreachable_nodes"
        }
        entries.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_classes": candidate["candidate_classes"],
                "role": candidate["role"],
                "artifact": str(artifact),
                "provenance": candidate.get("provenance"),
                "structural_fingerprint": _structural_fingerprint(artifact),
                "metrics": metrics,
                "verification": {
                    "structural": "passed",
                    "exact_vectors": report["exact_vectors_checked"],
                    "random_vectors": report["random_vectors_checked"],
                    "random_seed": report["random_seed"],
                    "formal_equivalence": "passed",
                },
            }
        )
    validate_frontier_entries(entries)
    return entries


def _write_frontier(path: Path, entries: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "objective_order": list(OBJECTIVES),
                "entries": entries,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _write_metrics(path: Path, entries: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for entry in entries:
            metrics = entry["metrics"]
            verification = entry["verification"]
            assert isinstance(metrics, dict) and isinstance(verification, dict)
            writer.writerow(
                {
                    "candidate_id": entry["candidate_id"],
                    "candidate_classes": ",".join(entry["candidate_classes"]),
                    "role": entry["role"],
                    "artifact": entry["artifact"],
                    "structural_fingerprint": entry["structural_fingerprint"],
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
                    "direct_output_alias_count": metrics[
                        "direct_output_alias_count"
                    ],
                    "exact_vectors_checked": verification["exact_vectors"],
                    "random_vectors_checked": verification["random_vectors"],
                    "random_seed": verification["random_seed"],
                    "formal_equivalence": verification["formal_equivalence"],
                    "verification_status": "passed",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("results/phase6/candidates.json"),
    )
    parser.add_argument(
        "--frontier",
        type=Path,
        default=Path("results/phase6/pareto_frontier.json"),
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=Path("results/phase6/metrics.csv"),
    )
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED
    )
    args = parser.parse_args()
    if args.random_tests < DEFAULT_RANDOM_TESTS:
        parser.error(f"--random-tests must be at least {DEFAULT_RANDOM_TESTS}")
    try:
        entries = verify_final_candidates(
            args.manifest, args.random_tests, args.seed
        )
        _write_frontier(args.frontier, entries)
        _write_metrics(args.metrics, entries)
    except (OSError, RuntimeError, ValueError, VerificationError) as error:
        parser.exit(1, f"final candidate verification failed: {error}\n")
    print(f"Verified {len(entries)} distinct nondominated final candidates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Paired isolation of Kraft-slack scoring in sharing and finishing.

See docs/experiments/kraft_phase_isolation.md for the frozen protocol.
Historical builders and their random-number calls are used unchanged.
"""

from __future__ import annotations

import argparse
from functools import partial
import hashlib
import json
import math
from pathlib import Path
import statistics

from generator.build_matrix import build_transformation_matrix
from optimizer.depth_bounded import _kraft, logged_attempts, run_bounded_search
from optimizer.kraft_slack import _SlackBuilder
from optimizer.optimize import Candidate, _exclusive_search_lock, _prune_operations
from verifier.search_logs import log_file_for
from verifier.verify_network import DEFAULT_RANDOM_SEED, DEFAULT_RANDOM_TESTS

ARMS = {"baseline": (False, False), "sharing": (True, False),
        "finishing": (False, True), "both": (True, True)}
SEEDS = {("stage1", 7): (300_000, 1_000), ("stage1", 6): (320_000, 1_000),
         ("stage2", 7): (310_000, 10_000), ("stage2", 6): (330_000, 10_000)}
ROOT = Path("results/phase_isolation")
CHECKPOINTS = Path("results/checkpoints/phase_isolation")


def algorithm_name(arm: str, cap: int) -> str:
    return f"kraft-phase-isolation-{arm}-depth{cap}-v1"


def _digest(value: object) -> str:
    return hashlib.sha256(repr(value).encode()).hexdigest()


def build_trial(seed: int, cap: int, arm: str) -> tuple[Candidate, dict[str, object]]:
    sharing, finishing = ARMS[arm]
    rows = tuple(build_transformation_matrix())
    builder = _SlackBuilder(rows, cap, seed, use_slack=sharing)
    while True:
        builder.free_rewrites()
        pair = builder.choose_shared_pair()
        if pair is None:
            break
        builder._apply(pair)
    sharing_count = len(builder.operations)
    boundary = len(builder.vectors)
    diagnostics = {
        "seed": seed, "depth_cap": cap, "arm": arm,
        "sharing_created": sharing_count,
        "remaining_kraft_budget": [builder.limit - _kraft(row, builder.depths)
                                   for row in builder.expressions],
        "remaining_terms": [len(row) for row in builder.expressions],
        "sharing_state_sha256": _digest((builder.vectors, builder.depths,
                                         [sorted(row) for row in builder.expressions])),
        "finishing_rng_sha256": _digest(builder.generator.getstate()),
    }
    builder.use_slack = finishing
    outputs = builder.finish_outputs()
    if tuple(builder.vectors[source] for source in outputs) != rows:
        raise RuntimeError("GF(2) signal-vector check failed")
    if max(builder.depths[source] for source in outputs) > cap:
        raise RuntimeError("phase-isolation trial exceeded depth cap")
    operations = _prune_operations(builder.operations, outputs)
    diagnostics.update({
        "finishing_created": len(builder.operations) - sharing_count,
        "sharing_retained": sum(op.output < boundary for op in operations),
        "finishing_retained": sum(op.output >= boundary for op in operations),
        "xor2_count": len(operations),
    })
    return Candidate(seed=seed, operations=operations, output_sources=outputs,
                     vectors=tuple(builder.vectors), depths=tuple(builder.depths)), diagnostics


def search_seed_phase(seed: int, depth_cap: int, *, arm: str,
                      spool: Path | None = None) -> Candidate:
    candidate, diagnostics = build_trial(seed, depth_cap, arm)
    if spool is not None:
        spool.mkdir(parents=True, exist_ok=True)
        path = spool / f"seed_{seed}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(diagnostics, sort_keys=True) + "\n")
        temporary.replace(path)
    return candidate


def consolidate(run: str, records: list[dict[str, object]]) -> None:
    """Keep diagnostics only for logged trials; preserve them across resumes."""
    path = ROOT / f"{run}_diagnostics.jsonl"
    spool = ROOT / f"{run}_spool"
    previous = {row["seed"]: row for row in
                (json.loads(line) for line in path.read_text().splitlines())} if path.exists() else {}
    diagnostics = []
    for record in records:
        seed = record["seed"]
        pending = spool / f"seed_{seed}.json"
        row = json.loads(pending.read_text()) if pending.exists() else previous.get(seed)
        if row is None or row["xor2_count"] != record["final_metrics"]["xor2_count"]:
            raise ValueError(f"missing or inconsistent diagnostics for {run}, seed {seed}")
        if seed in previous and previous[seed] != row:
            raise ValueError(f"diagnostic replay differs for {run}, seed {seed}")
        diagnostics.append(row)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in diagnostics))
    temporary.replace(path)
    # These files are this run's disposable worker spool; the JSONL is authoritative.
    for row in diagnostics:
        (spool / f"seed_{row['seed']}.json").unlink(missing_ok=True)
    if spool.exists() and not any(spool.iterdir()):
        spool.rmdir()


def paired_difference(values: list[int], control: list[int]) -> dict[str, object]:
    if len(values) != len(control) or len(values) < 2:
        raise ValueError("paired samples must have equal lengths of at least two")
    differences = [a - b for a, b in zip(values, control)]
    mean = statistics.mean(differences)
    error = statistics.stdev(differences) / math.sqrt(len(differences))
    # Null z is explicit for a degenerate distribution, avoiding nonstandard JSON infinity.
    return {"n": len(values), "mean": mean, "standard_error": error,
            "z_normal_approximation": mean / error if error else None,
            "ci95_normal_approximation": [mean - 1.96 * error, mean + 1.96 * error]}


def summarize(stage: str, arms_by_cap: dict[int, list[str]], log: Path) -> dict[str, object]:
    summary: dict[str, object] = {"stage": stage, "caps": {}}
    for cap, arms in arms_by_cap.items():
        start, count = SEEDS[(stage, cap)]
        samples = {}
        stats = {}
        diagnostics = {}
        for arm in arms:
            records = logged_attempts(log, algorithm_name(arm, cap), start, count)
            if len(records) != count or not all(row["verification_passed"] for row in records):
                raise ValueError("incomplete or unverified experiment")
            samples[arm] = [int(row["final_metrics"]["xor2_count"]) for row in records]
            rows = [json.loads(line) for line in
                    (ROOT / f"{stage}_{arm}_depth{cap}_diagnostics.jsonl").read_text().splitlines()]
            if [row["seed"] for row in rows] != list(range(start, start + count)):
                raise ValueError("diagnostic seed coverage differs")
            diagnostics[arm] = rows
            stats[arm] = {"n": count, "mean": statistics.mean(samples[arm]),
                          "sd": statistics.stdev(samples[arm]), "best": min(samples[arm]),
                          "best_seed": start + samples[arm].index(min(samples[arm])),
                          "mean_sharing_created": statistics.mean(row["sharing_created"] for row in rows),
                          "mean_finishing_created": statistics.mean(row["finishing_created"] for row in rows),
                          "mean_sharing_retained": statistics.mean(row["sharing_retained"] for row in rows),
                          "mean_finishing_retained": statistics.mean(row["finishing_retained"] for row in rows),
                          "mean_remaining_kraft_budget": statistics.mean(
                              statistics.mean(row["remaining_kraft_budget"]) for row in rows)}
        if stage == "stage1":
            for a, b in (("baseline", "finishing"), ("sharing", "both")):
                for left, right in zip(diagnostics[a], diagnostics[b]):
                    for key in ("sharing_state_sha256", "finishing_rng_sha256"):
                        if left[key] != right[key]:
                            raise ValueError("finishing intervention changed sharing state or RNG")
        control = "baseline" if cap == 7 else "both"
        differences = {arm: paired_difference(values, samples[control])
                       for arm, values in samples.items() if arm != control}
        eligible = [arm for arm in ("sharing", "finishing") if arm in differences
                    and differences[arm]["mean"] <= -0.5
                    and differences[arm]["z_normal_approximation"] is not None
                    and differences[arm]["z_normal_approximation"] <= -3]
        selected = min(eligible, key=lambda arm: (differences[arm]["mean"], arm)) if eligible else None
        extra = {}
        if stage == "stage1":
            extra = {"sharing_vs_baseline": paired_difference(samples["sharing"], samples["baseline"]),
                     "finishing_vs_baseline": paired_difference(samples["finishing"], samples["baseline"]),
                     "both_vs_baseline": paired_difference(samples["both"], samples["baseline"])}
        summary["caps"][str(cap)] = {"arms": stats, "control": control,
                                     "paired_vs_control": differences,
                                     "selected_for_stage2": selected, **extra}
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("stage1", "stage2"), required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    log = log_file_for(algorithm_name("baseline", 7))
    arms_by_cap = {7: list(ARMS), 6: list(ARMS)}
    if args.stage == "stage2":
        first = json.loads((ROOT / "stage1_summary.json").read_text())
        arms_by_cap = {int(cap): [row["control"], row["selected_for_stage2"]]
                       for cap, row in first["caps"].items() if row["selected_for_stage2"]}
    with _exclusive_search_lock(log):
        for cap, arms in arms_by_cap.items():
            for arm in arms:
                run = f"{args.stage}_{arm}_depth{cap}"
                start, count = SEEDS[(args.stage, cap)]
                print(f"Starting/resuming {run}: {start}..{start + count - 1}", flush=True)
                run_bounded_search(
                    cap, start, count, args.workers, CHECKPOINTS / f"{run}_search.json",
                    ROOT / f"{run}.v", CHECKPOINTS / f"{run}_incumbents", log,
                    DEFAULT_RANDOM_TESTS, DEFAULT_RANDOM_SEED,
                    trial=partial(search_seed_phase, arm=arm, spool=ROOT / f"{run}_spool"),
                    algorithm=algorithm_name(arm, cap), module_name=f"candidate_phase_{arm}_depth{cap}",
                )
                consolidate(run, logged_attempts(log, algorithm_name(arm, cap), start, count))
                print(f"Completed {run}", flush=True)
        summary = summarize(args.stage, arms_by_cap, log)
        (ROOT / f"{args.stage}_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

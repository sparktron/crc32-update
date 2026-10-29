"""Frozen elite-prefix restart (heritability) experiment; historical builders unchanged.

A child trial replays the first k sharing decisions of a recorded parent seed
on the cap's control builder, then continues on a fresh RNG seeded with the
child seed. With no parent it is the control trial for that seed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import time

from generator.build_matrix import build_transformation_matrix
from optimizer.depth_bounded import _kraft, logged_attempts, run_bounded_search
from optimizer.kraft_slack import _SlackBuilder
from optimizer.optimize import (Candidate, _exclusive_search_lock, _prune_operations,
                                independently_check)
from optimizer.phase_isolation import _digest
from verifier.search_logs import SEARCH_LOG_DIR
from verifier.verify_network import DEFAULT_RANDOM_SEED, DEFAULT_RANDOM_TESTS

ROOT = Path("results/elite_prefix")
CHECKPOINTS = Path("results/checkpoints/elite_prefix")
LOG = Path("results/search_logs/elite_prefix.jsonl")
PARENTS = ROOT / "parents.json"
PROTOCOL = Path("docs/experiments/elite_prefix_restart.md")
GROUPS = ("elite", "median")
FRACTIONS = (25, 50, 75, 100)  # percent of the parent's sharing decisions replayed
PRIMARY_FRACTION = 50
PARENT_COUNT = 20
CHILDREN = 50
FRESH_COUNT = 2_000
SELECTION_SEED = 0xE117E
BASE = {7: 500_000, 6: 520_000}
TARGETS = {7: 437, 6: 461}
SCREEN_GATES = -2.0
SCREEN_Z = -3.0
# Historical budgets whose trials each cap's control builder reproduces exactly:
# bounded baseline at cap 7, both-phases Kraft slack (with fallback) at cap 6.
SOURCES = {
    7: (("kraft_bounded.jsonl", "kraft-bounded-bp-cse-depth7-v1", 40_000, 10_000),
        ("kraft_phase_isolation.jsonl", "kraft-phase-isolation-baseline-depth7-v1", 300_000, 1_000),
        ("sharing_lookahead.jsonl", "sharing-lookahead-control-depth7-v1", 400_000, 1_000)),
    6: (("kraft_slack_tiebreak.jsonl", "kraft-slack-tiebreak-depth6-v1", 240_000, 11_000),
        ("kraft_phase_isolation.jsonl", "kraft-phase-isolation-both-depth6-v1", 320_000, 1_000),
        ("sharing_lookahead.jsonl", "sharing-lookahead-control-depth6-v1", 420_000, 1_000)),
}


def algorithm_name(group: str, fraction: int, cap: int) -> str:
    if group == "fresh":
        return f"elite-prefix-fresh-depth{cap}-v1"
    return f"elite-prefix-{group}-f{fraction}-depth{cap}-v1"


def arms(cap: int) -> list[tuple[str, int, int, int]]:
    """Frozen (group, fraction, seed_start, seed_count) budgets for one cap, in run order."""
    size = PARENT_COUNT * CHILDREN
    layout = [(group, fraction) for group in GROUPS for fraction in FRACTIONS]
    rows = [(group, fraction, BASE[cap] + index * size, size)
            for index, (group, fraction) in enumerate(layout)]
    return rows + [("fresh", 0, BASE[cap] + len(layout) * size, FRESH_COUNT)]


def run_name(group: str, fraction: int, cap: int) -> str:
    return f"stage1_fresh_depth{cap}" if group == "fresh" else f"stage1_{group}_f{fraction}_depth{cap}"


def _control(rows, cap, seed):
    return _SlackBuilder(rows, cap, seed, use_slack=cap == 6)


def _step(builder) -> bool:
    """One historical sharing iteration; False once no shared pair remains."""
    builder.free_rewrites()
    pair = builder.choose_shared_pair()
    if pair is None:
        return False
    builder._apply(pair)
    return True


def _state_digest(builder) -> str:
    return _digest((builder.vectors, builder.depths,
                    [sorted(row) for row in builder.expressions], builder.generator.getstate()))


def prefix_decisions(sharing_decisions: int, fraction: int) -> int:
    return sharing_decisions * fraction // 100


def build_trial(seed, cap, parent=None, prefix=0):
    if cap not in (6, 7) or prefix < 0 or (parent is None and prefix):
        raise ValueError("unsupported cap or prefix")
    rows = tuple(build_transformation_matrix())
    builder = _control(rows, cap, seed if parent is None else parent)
    started = time.perf_counter()
    for _ in range(prefix):
        if not _step(builder):
            raise ValueError("prefix is longer than the parent's sharing phase")
    prefix_digest = None
    if parent is not None:
        prefix_digest = _state_digest(builder)
        builder.generator = random.Random(seed)
    decisions = prefix
    while _step(builder):
        decisions += 1
    sharing_count = len(builder.operations)
    boundary = len(builder.vectors)
    diagnostics = {
        "seed": seed, "depth_cap": cap, "parent_seed": parent,
        "prefix_decisions": prefix, "prefix_state_sha256": prefix_digest,
        "sharing_decisions": decisions, "sharing_created": sharing_count,
        "remaining_kraft_budget": [builder.limit - _kraft(row, builder.depths)
                                   for row in builder.expressions],
        "remaining_terms": [len(row) for row in builder.expressions],
    }
    outputs = builder.finish_outputs()
    if tuple(builder.vectors[source] for source in outputs) != rows:
        raise RuntimeError("GF(2) signal-vector check failed")
    if max(builder.depths[source] for source in outputs) > cap:
        raise RuntimeError("elite-prefix trial exceeded cap")
    operations = _prune_operations(builder.operations, outputs)
    diagnostics.update({
        "finishing_created": len(builder.operations) - sharing_count,
        "sharing_retained": sum(op.output < boundary for op in operations),
        "finishing_retained": sum(op.output >= boundary for op in operations),
        "xor2_count": len(operations),
    })
    # Timing is separate from deterministic diagnostic identities.
    diagnostics["runtime"] = {"build_seconds": time.perf_counter() - started}
    return Candidate(seed=seed, operations=operations, output_sources=outputs,
                     vectors=tuple(builder.vectors), depths=tuple(builder.depths)), diagnostics


def child_spec(seed, start, parents, fraction):
    """Map a child seed to (parent seed, replayed decisions); ``parents`` holds (seed, D)."""
    parent, sharing_decisions = parents[(seed - start) // CHILDREN]
    return parent, prefix_decisions(sharing_decisions, fraction)


def search_seed(seed, depth_cap, *, start=0, parents=(), fraction=0, spool=None):
    parent, prefix = child_spec(seed, start, parents, fraction) if parents else (None, 0)
    candidate, diagnostics = build_trial(seed, depth_cap, parent, prefix)
    if spool is not None:
        spool.mkdir(parents=True, exist_ok=True)
        path = spool / f"seed_{seed}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(diagnostics, sort_keys=True) + "\n")
        temporary.replace(path)
    return candidate


def replay_trial(seed, depth_cap, *, group, fraction):
    """Rebuild one logged stage-1 trial from its arm and the committed parent table."""
    start = next(row[2] for row in arms(depth_cap) if row[:2] == (group, fraction))
    parents = () if group == "fresh" else tuple(
        (p["seed"], p["sharing_decisions"])
        for p in json.loads(PARENTS.read_text())["caps"][str(depth_cap)][group])
    return search_seed(seed, depth_cap, start=start, parents=parents, fraction=fraction)


def replay_parent(seed, cap):
    """Rebuild a recorded parent, keeping the state digest after every decision."""
    rows = tuple(build_transformation_matrix())
    builder = _control(rows, cap, seed)
    states = [_state_digest(builder)]
    while _step(builder):
        states.append(_state_digest(builder))
    outputs = builder.finish_outputs()
    candidate = Candidate(seed=seed, operations=_prune_operations(builder.operations, outputs),
                          output_sources=outputs, vectors=tuple(builder.vectors),
                          depths=tuple(builder.depths))
    metrics = independently_check(candidate).to_dict()
    metrics.pop("unreachable_nodes")
    decisions = len(states) - 1
    prefixes = {str(fraction): {"decisions": prefix_decisions(decisions, fraction),
                                "state_sha256": states[prefix_decisions(decisions, fraction)]}
                for fraction in FRACTIONS}
    return {"seed": seed, "sharing_decisions": decisions, "final_metrics": metrics,
            "prefixes": prefixes}


def _source_records(log_name, algorithm, start, count):
    path = SEARCH_LOG_DIR / log_name
    records = [record for record in map(json.loads, filter(None, path.read_text().splitlines()))
               if record.get("algorithm") == algorithm and isinstance(record.get("seed"), int)
               and start <= record["seed"] < start + count]
    if (sorted(record["seed"] for record in records) != list(range(start, start + count))
            or not all(record["verification_passed"] for record in records)):
        raise ValueError(f"{algorithm} budget is incomplete or unverified")
    return records


def select_parents(cap):
    """Apply the frozen selection rule to the committed source logs (no replay)."""
    pool = [(record["seed"], record["algorithm"], record["final_metrics"])
            for source in SOURCES[cap] for record in _source_records(*source)]
    elite = sorted(pool, key=lambda item: (item[2]["xor2_count"],
                                           item[2]["total_excess_fanout_above_4"], item[0]))
    median = statistics.median_low(item[2]["xor2_count"] for item in pool)
    typical = sorted((item for item in pool if item[2]["xor2_count"] == median),
                     key=lambda item: item[0])
    chosen = random.Random(SELECTION_SEED + cap).sample(typical, PARENT_COUNT)
    counts = [item[2]["xor2_count"] for item in pool]
    return {
        "pool_size": len(pool), "pool_mean": statistics.mean(counts),
        "pool_sd": statistics.stdev(counts), "pool_median_low": median,
        "pool_median_count": len(typical),
        "elite": elite[:PARENT_COUNT], "median": sorted(chosen, key=lambda item: item[0]),
    }


def build_parent_table(workers):
    table = {"selection": {
        "sources": {str(cap): [list(source) for source in SOURCES[cap]] for cap in SOURCES},
        "parent_count": PARENT_COUNT, "elite_order": "xor2, excess fanout above 4, seed",
        "median_rule": "seed-sorted random.Random(SELECTION_SEED + cap).sample of pool_median_low trials",
        "selection_seed": SELECTION_SEED, "fractions": list(FRACTIONS)}, "caps": {}}
    jobs = []
    for cap in (7, 6):
        selected = select_parents(cap)
        table["caps"][str(cap)] = {key: value for key, value in selected.items()
                                   if key not in GROUPS}
        jobs += [(cap, group, item) for group in GROUPS for item in selected[group]]
    with ProcessPoolExecutor(max_workers=workers) as executor:
        replays = list(executor.map(replay_parent, [item[0] for _, _, item in jobs],
                                    [cap for cap, _, _ in jobs]))
    for (cap, group, (seed, algorithm, logged)), replay in zip(jobs, replays):
        if replay["final_metrics"] != logged:
            raise ValueError(f"parent {seed} at cap {cap} does not replay its logged metrics")
        replay["source_algorithm"] = algorithm
        table["caps"][str(cap)].setdefault(group, []).append(replay)
    return table


def _consolidate(run, records):
    """Append logged seed diagnostics; never rewrite prior evidence on replay."""
    path = ROOT / f"{run}_diagnostics.jsonl"
    spool = ROOT / f"{run}_spool"
    previous = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    if [row["seed"] for row in previous] != [r["seed"] for r in records[:len(previous)]]:
        raise ValueError("diagnostic prefix differs")
    with path.open("a") as stream:
        for record in records[len(previous):]:
            row = json.loads((spool / f"seed_{record['seed']}.json").read_text())
            if row["xor2_count"] != record["final_metrics"]["xor2_count"]:
                raise ValueError("diagnostic metrics differ")
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()
    for record in records:
        (spool / f"seed_{record['seed']}.json").unlink(missing_ok=True)
    if spool.exists() and not any(spool.iterdir()):
        spool.rmdir()


def difference(a_mean, a_error, b_mean, b_error):
    mean = a_mean - b_mean
    error = math.hypot(a_error, b_error)
    # Null z is explicit for a degenerate distribution, avoiding nonstandard JSON infinity.
    return {"mean": mean, "standard_error": error,
            "z_normal_approximation": mean / error if error else None,
            "ci95_normal_approximation": [mean - 1.96 * error, mean + 1.96 * error]}


def passes_screen(contrast):
    return (contrast["mean"] <= SCREEN_GATES and contrast["z_normal_approximation"] is not None
            and contrast["z_normal_approximation"] <= SCREEN_Z)


def _slope(xs, ys):
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread if spread else None


def summarize(table):
    result = {"stage": "stage1", "caps": {}}
    for cap in (7, 6):
        parents = table["caps"][str(cap)]
        stats, child_means = {}, {}
        for group, fraction, start, count in arms(cap):
            name = run_name(group, fraction, cap)
            records = logged_attempts(LOG, algorithm_name(group, fraction, cap), start, count)
            if len(records) != count or not all(row["verification_passed"] for row in records):
                raise ValueError(f"{name} is incomplete or unverified")
            values = [int(row["final_metrics"]["xor2_count"]) for row in records]
            diagnostics = [json.loads(line) for line in
                           (ROOT / f"{name}_diagnostics.jsonl").read_text().splitlines()]
            if [row["seed"] for row in diagnostics] != list(range(start, start + count)):
                raise ValueError(f"{name} diagnostic coverage differs")
            row = {
                "n": count, "mean": statistics.mean(values), "sd": statistics.stdev(values),
                "best_gates": min(values), "best_seed_by_gates": start + values.index(min(values)),
                "targets_met": sum(v <= TARGETS[cap] for v in values),
                "mean_worker_seconds": statistics.mean(r["runtime_seconds"] for r in records),
                "accepted_incumbents": sum(r["accepted"] for r in records),
                **{f"mean_{key}": statistics.mean(d[key] for d in diagnostics)
                   for key in ("sharing_retained", "finishing_retained", "sharing_decisions")},
            }
            if group == "fresh":
                row["standard_error"] = row["sd"] / math.sqrt(count)
            else:
                blocks = [values[i:i + CHILDREN] for i in range(0, count, CHILDREN)]
                for parent, block_rows in zip(parents[group], (
                        diagnostics[i:i + CHILDREN] for i in range(0, count, CHILDREN))):
                    expected = parent["prefixes"][str(fraction)]
                    if any(d["parent_seed"] != parent["seed"]
                           or d["prefix_decisions"] != expected["decisions"]
                           or d["prefix_state_sha256"] != expected["state_sha256"]
                           for d in block_rows):
                        raise ValueError(f"{name} prefix replay differs for parent {parent['seed']}")
                means = [statistics.mean(block) for block in blocks]
                child_means[(group, fraction)] = means
                row["standard_error"] = statistics.stdev(means) / math.sqrt(len(means))
                row["parents"] = [{
                    "seed": parent["seed"],
                    "parent_gates": parent["final_metrics"]["xor2_count"],
                    "child_mean": mean, "child_sd": statistics.stdev(block),
                    "child_best": min(block),
                    "children_matching_parent": sum(
                        v == parent["final_metrics"]["xor2_count"] for v in block),
                } for parent, mean, block in zip(parents[group], means, blocks)]
            stats[name] = row
        fresh = stats[run_name("fresh", 0, cap)]
        contrasts, slopes = {}, {}
        for fraction in FRACTIONS:
            elite = stats[run_name("elite", fraction, cap)]
            median = stats[run_name("median", fraction, cap)]
            contrasts[str(fraction)] = {
                "elite_minus_fresh": difference(elite["mean"], elite["standard_error"],
                                                fresh["mean"], fresh["standard_error"]),
                "elite_minus_median": difference(elite["mean"], elite["standard_error"],
                                                 median["mean"], median["standard_error"]),
                "median_minus_fresh": difference(median["mean"], median["standard_error"],
                                                 fresh["mean"], fresh["standard_error"]),
            }
            parent_gates = [p["final_metrics"]["xor2_count"]
                            for group in GROUPS for p in parents[group]]
            slopes[str(fraction)] = _slope(parent_gates, [m for group in GROUPS
                                                          for m in child_means[(group, fraction)]])
        primary = contrasts[str(PRIMARY_FRACTION)]
        result["caps"][str(cap)] = {
            "arms": stats, "contrasts": contrasts, "heritability_slope": slopes,
            "h8_passes": passes_screen(primary["elite_minus_fresh"])
            and passes_screen(primary["elite_minus_median"]),
        }
    return result


def check_provenance():
    """Freeze tracked sources and the parent table at the preregistration commit."""
    files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    files = [f for f in files if f.endswith(".py") or
             f in ("SPEC.md", "reference/crc32_reference.v", str(PROTOCOL), str(PARENTS))]
    if str(PARENTS) not in files or str(PROTOCOL) not in files:
        raise ValueError("protocol and parent table must be committed before the budget")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", *files], check=True,
                   stdout=subprocess.DEVNULL)
    hashes = {f: hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in files}
    path = ROOT / "run_manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text())
        if manifest["source_sha256"] != hashes:
            raise ValueError("frozen experimental sources differ")
        return
    manifest = {
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], text=True).strip(),
        "status_before_run": subprocess.check_output(["git", "status", "--porcelain"], text=True).splitlines(),
        "source_sha256": hashes, "fractions": list(FRACTIONS), "children": CHILDREN,
        "parent_count": PARENT_COUNT, "fresh_count": FRESH_COUNT,
        "arms": {str(cap): [list(arm) for arm in arms(cap)] for cap in (7, 6)},
        "random_tests": DEFAULT_RANDOM_TESTS, "verification_seed": DEFAULT_RANDOM_SEED,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _render_table(table):
    return json.dumps(table, indent=2, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("select", "stage1"), required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    if args.stage == "select":
        # Writes the table once; afterwards it only confirms the committed bytes.
        rendered = _render_table(build_parent_table(args.workers))
        if PARENTS.exists():
            if PARENTS.read_text() != rendered:
                raise ValueError("parent table does not reproduce")
            print(f"Parent table reproduces: {PARENTS}", flush=True)
        else:
            PARENTS.write_text(rendered)
            print(f"Wrote parent table: {PARENTS}", flush=True)
        return 0
    check_provenance()
    if _render_table(build_parent_table(args.workers)) != PARENTS.read_text():
        raise ValueError("parent table does not reproduce")
    table = json.loads(PARENTS.read_text())
    with _exclusive_search_lock(LOG):
        for cap in (7, 6):
            for group, fraction, start, count in arms(cap):
                name = run_name(group, fraction, cap)
                parents = () if group == "fresh" else tuple(
                    (p["seed"], p["sharing_decisions"]) for p in table["caps"][str(cap)][group])
                print(f"Starting/resuming {name}: {start}..{start + count - 1}", flush=True)
                run_bounded_search(
                    cap, start, count, args.workers, CHECKPOINTS / f"{name}_search.json",
                    ROOT / f"{name}.v", CHECKPOINTS / f"{name}_incumbents", LOG,
                    DEFAULT_RANDOM_TESTS, DEFAULT_RANDOM_SEED,
                    trial=partial(search_seed, start=start, parents=parents, fraction=fraction,
                                  spool=ROOT / f"{name}_spool"),
                    algorithm=algorithm_name(group, fraction, cap),
                    module_name=f"candidate_{name.removeprefix('stage1_')}",
                )
                _consolidate(name, logged_attempts(LOG, algorithm_name(group, fraction, cap),
                                                   start, count))
                print(f"Completed {name}", flush=True)
        summary = summarize(table)
        (ROOT / "stage1_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Frozen iterated elite-restart search against fresh seeds at matched trial budgets.

Each replicate starts from 400 fresh control trials (generation 0), which are
also the first 400 trials of its paired fresh replicate, so the iterated arm
pays for its own elite pool. Four generations of 400 children follow. A child
replays its parent's seed chain up to halfway through the parent's own
redrawn sharing decisions, then continues on a fresh RNG seeded with the
child seed. Historical builders are wrapped, not modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import time

from generator.build_matrix import basis_signal_names, build_transformation_matrix
from optimizer.depth_bounded import _kraft, logged_attempts, run_bounded_search
from optimizer.elite_prefix import _control, _state_digest, _step
from optimizer.optimize import Candidate, _exclusive_search_lock, _prune_operations
from verifier.verify_network import DEFAULT_RANDOM_SEED, DEFAULT_RANDOM_TESTS

ROOT = Path("results/iterated_elite")
CHECKPOINTS = Path("results/checkpoints/iterated_elite")
LOG = Path("results/search_logs/iterated_elite.jsonl")
PROTOCOL = Path("docs/experiments/iterated_elite_restart.md")
CAPS = (7, 6)
REPLICATES = 10
BUDGET = 2_000           # trials per replicate in each arm: the matched compute unit
GENERATION_SIZE = 400    # generation 0 and each child generation, per replicate
GENERATIONS = 4          # child generations: 400 + 4 * 400 = BUDGET
PARENT_COUNT = 20
CHILDREN = 20            # per parent: PARENT_COUNT * CHILDREN = GENERATION_SIZE
ROOT_LIMIT = 5           # parents per generation descending from one generation-0 trial
BASE = {7: 600_000, 6: 640_000}
TAIL = {7: 442, 6: 469}      # historical fresh rates 0.086% and 0.140% (frozen in the protocol)
TARGETS = {7: 436, 6: 459}   # existence targets, reported separately
BEST_GATES = -2.0
TAIL_RATIO = 2.0
SCREEN_Z = 3.0
TIME_RATIO_LIMIT = 1.10


def algorithm_name(name: str, cap: int) -> str:
    return f"iterated-elite-{name}-depth{cap}-v1"


def run_name(name: str, cap: int) -> str:
    return f"{name}_depth{cap}"


def budgets(cap: int) -> list[tuple[str, int, int]]:
    """Frozen (name, seed_start, seed_count) budgets for one cap, in run order."""
    size = REPLICATES * GENERATION_SIZE
    extra = REPLICATES * (BUDGET - GENERATION_SIZE)
    children = BASE[cap] + size + extra
    return ([("gen0", BASE[cap], size), ("fresh", BASE[cap] + size, extra)]
            + [(f"gen{g}", children + (g - 1) * size, size) for g in range(1, GENERATIONS + 1)])


def replicate_of(name: str, start: int, seed: int) -> int:
    width = BUDGET - GENERATION_SIZE if name == "fresh" else GENERATION_SIZE
    return (seed - start) // width


def structural_sha256(candidate: Candidate) -> str:
    """``verifier.build_results.structural_fingerprint`` of the rendered netlist, in memory."""
    labels = dict(enumerate(basis_signal_names()))
    nodes = []
    for operation in candidate.operations:
        inputs = sorted((labels[operation.input_a], labels[operation.input_b]))
        labels[operation.output] = hashlib.sha256(json.dumps(["xor2", inputs]).encode()).hexdigest()
        nodes.append(labels[operation.output])
    document = {"nodes": sorted(nodes),
                "outputs": [labels[source] for source in candidate.output_sources]}
    return hashlib.sha256(json.dumps(document).encode()).hexdigest()


def _check_lineage(segments, cap):
    if (cap not in CAPS or not segments or segments[0][1] != 0
            or any(later <= earlier for (_, earlier), (_, later) in zip(segments, segments[1:]))):
        raise ValueError("unsupported cap or lineage")


def build_trial(segments, cap):
    """Build one trial from its (seed, switch) chain; ``((seed, 0),)`` is the control trial.

    The control starts on the first seed. At each later switch, counted in
    sharing decisions, the RNG is replaced by ``random.Random(seed)``.
    """
    _check_lineage(segments, cap)
    rows = tuple(build_transformation_matrix())
    builder = _control(rows, cap, segments[0][0])
    started = time.perf_counter()
    decisions, prefix_digest = 0, None
    for seed, switch in segments[1:]:
        while decisions < switch:
            if not _step(builder):
                raise ValueError("switch is beyond the parent's sharing phase")
            decisions += 1
        prefix_digest = _state_digest(builder)
        builder.generator = random.Random(seed)
    while _step(builder):
        decisions += 1
    sharing_count = len(builder.operations)
    boundary = len(builder.vectors)
    diagnostics = {
        "seed": segments[-1][0], "depth_cap": cap, "lineage": [list(item) for item in segments],
        "parent_seed": segments[-2][0] if len(segments) > 1 else None,
        "switch": segments[-1][1], "prefix_state_sha256": prefix_digest,
        "sharing_decisions": decisions, "sharing_created": sharing_count,
        "remaining_kraft_budget": [builder.limit - _kraft(row, builder.depths)
                                   for row in builder.expressions],
        "remaining_terms": [len(row) for row in builder.expressions],
    }
    outputs = builder.finish_outputs()
    if tuple(builder.vectors[source] for source in outputs) != rows:
        raise RuntimeError("GF(2) signal-vector check failed")
    if max(builder.depths[source] for source in outputs) > cap:
        raise RuntimeError("iterated-elite trial exceeded cap")
    operations = _prune_operations(builder.operations, outputs)
    candidate = Candidate(seed=segments[-1][0], operations=operations, output_sources=outputs,
                          vectors=tuple(builder.vectors), depths=tuple(builder.depths))
    diagnostics.update({
        "finishing_created": len(builder.operations) - sharing_count,
        "sharing_retained": sum(op.output < boundary for op in operations),
        "finishing_retained": sum(op.output >= boundary for op in operations),
        "xor2_count": len(operations),
        "structural_sha256": structural_sha256(candidate),
    })
    # Timing is separate from deterministic diagnostic identities.
    diagnostics["runtime"] = {"build_seconds": time.perf_counter() - started}
    return candidate, diagnostics


def lineage_states(segments, cap):
    """State digest after every sharing decision of a trial (for prefix audits)."""
    _check_lineage(segments, cap)
    builder = _control(tuple(build_transformation_matrix()), cap, segments[0][0])
    switches = dict((switch, seed) for seed, switch in segments[1:])
    states, decisions = [_state_digest(builder)], 0
    while True:
        if decisions in switches:
            builder.generator = random.Random(switches[decisions])
        if not _step(builder):
            return states
        decisions += 1
        states.append(_state_digest(builder))


def child_switch(trial) -> int:
    """Halfway through the trial's own redrawn sharing decisions."""
    return trial["switch"] + (trial["sharing_decisions"] - trial["switch"]) // 2


def _rank(trial):
    return trial["xor2_count"], trial["total_excess_fanout_above_4"], trial["seed"]


def select_parents(trials):
    """Frozen rule: best by (XOR2, excess fanout above 4, seed); a circuit counts once,
    at most ROOT_LIMIT parents per generation-0 root, and two redrawn decisions needed."""
    ranked = sorted(trials, key=_rank)
    chosen, seen, roots = [], set(), Counter()
    for trial in ranked:
        duplicate = trial["structural_sha256"] in seen
        seen.add(trial["structural_sha256"])
        root = trial["lineage"][0][0]
        if (duplicate or roots[root] >= ROOT_LIMIT
                or trial["sharing_decisions"] - trial["switch"] < 2):
            continue
        roots[root] += 1
        chosen.append(trial)
        if len(chosen) == PARENT_COUNT:
            return chosen
    raise ValueError("fewer eligible parents than the frozen pool size")


def load_budget(name, start, count, cap):
    """Joined log record and diagnostics for every trial of one completed budget."""
    records = logged_attempts(LOG, algorithm_name(name, cap), start, count)
    if len(records) != count or not all(row["verification_passed"] for row in records):
        raise ValueError(f"{run_name(name, cap)} is incomplete or unverified")
    path = ROOT / f"{run_name(name, cap)}_diagnostics.jsonl"
    diagnostics = [json.loads(line) for line in path.read_text().splitlines()]
    if [row["seed"] for row in diagnostics] != [row["seed"] for row in records]:
        raise ValueError(f"{run_name(name, cap)} diagnostic coverage differs")
    trials = []
    for record, row in zip(records, diagnostics):
        if row["xor2_count"] != record["final_metrics"]["xor2_count"]:
            raise ValueError(f"{run_name(name, cap)} diagnostic metrics differ")
        trials.append({**row, "budget": name, "replicate": replicate_of(name, start, row["seed"]),
                       "total_excess_fanout_above_4":
                           record["final_metrics"]["total_excess_fanout_above_4"],
                       "runtime_seconds": record["runtime_seconds"]})
    return trials


def _prefix_digest(parent, cap):
    """Replay a parent's chain: it must reproduce its logged sharing decisions."""
    states = lineage_states(tuple(map(tuple, parent["lineage"])), cap)
    if len(states) - 1 != parent["sharing_decisions"]:
        raise ValueError(f"parent {parent['seed']} does not replay its sharing decisions")
    return states[parent["child_switch"]]


def parent_table(cap, generation, workers=1):
    """Parents of every replicate for one child generation, from logged earlier generations."""
    pools = [[] for _ in range(REPLICATES)]
    for name, start, count in budgets(cap):
        if name.startswith("gen") and int(name[3:]) < generation:
            for trial in load_budget(name, start, count, cap):
                pools[trial["replicate"]].append(trial)
    keys = ("seed", "lineage", "switch", "sharing_decisions", "xor2_count",
            "total_excess_fanout_above_4", "structural_sha256")
    replicates = [[{**{key: parent[key] for key in keys}, "child_switch": child_switch(parent)}
                   for parent in select_parents(pool)] for pool in pools]
    parents = [parent for rows in replicates for parent in rows]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            digests = list(executor.map(_prefix_digest, parents, [cap] * len(parents)))
    else:
        digests = [_prefix_digest(parent, cap) for parent in parents]
    for parent, digest in zip(parents, digests):
        parent["prefix_state_sha256"] = digest
    return {"depth_cap": cap, "generation": generation,
            "rule": {"parent_count": PARENT_COUNT, "children": CHILDREN, "root_limit": ROOT_LIMIT,
                     "order": "xor2, excess fanout above 4, seed; first of each structural_sha256",
                     "child_switch": "switch + (sharing_decisions - switch) // 2"},
            "pool_sizes": [len(pool) for pool in pools], "replicates": replicates}


def _render(document):
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def frozen_parent_table(cap, generation, workers=1):
    """Write the generation's parent table once; afterwards it must reproduce byte for byte."""
    path = ROOT / f"parents_depth{cap}_gen{generation}.json"
    rendered = _render(parent_table(cap, generation, workers))
    if path.exists():
        if path.read_text() != rendered:
            raise ValueError(f"{path} does not reproduce from the logged generations")
    else:
        path.write_text(rendered)
    return json.loads(rendered)


def child_segments(seed, start, parents):
    """Map a child seed to its full (seed, switch) chain; ``parents`` is a table's replicates."""
    offset = seed - start
    parent = parents[offset // GENERATION_SIZE][offset % GENERATION_SIZE // CHILDREN]
    return tuple(map(tuple, parent["lineage"])) + ((seed, parent["child_switch"]),)


def search_seed(seed, depth_cap, *, start=0, parents=None, spool=None):
    segments = ((seed, 0),) if parents is None else child_segments(seed, start, parents)
    candidate, diagnostics = build_trial(segments, depth_cap)
    if spool is not None:
        spool.mkdir(parents=True, exist_ok=True)
        path = spool / f"seed_{seed}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(diagnostics, sort_keys=True) + "\n")
        temporary.replace(path)
    return candidate


def _trial_parents(table):
    return tuple(tuple({"lineage": p["lineage"], "child_switch": p["child_switch"]} for p in rows)
                 for rows in table["replicates"])


def replay_trial(seed, depth_cap):
    """Rebuild one logged trial from the frozen layout and the written parent tables."""
    for name, start, count in budgets(depth_cap):
        if start <= seed < start + count:
            parents = None
            if name not in ("gen0", "fresh"):
                path = ROOT / f"parents_depth{depth_cap}_gen{name[3:]}.json"
                parents = _trial_parents(json.loads(path.read_text()))
            return search_seed(seed, depth_cap, start=start, parents=parents)
    raise ValueError(f"seed {seed} is outside the frozen layout")


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


def paired(differences, direction):
    """Paired normal-approximation statistics and the exact sign-flip p in ``direction`` (-1 or +1)."""
    n = len(differences)
    mean = statistics.mean(differences)
    sd = statistics.stdev(differences)
    error = sd / math.sqrt(n)
    flips = [statistics.mean(sign * d for sign, d in zip(signs, differences))
             for signs in itertools.product((1, -1), repeat=n)]
    extreme = sum(direction * value >= direction * mean - 1e-12 for value in flips)
    # Null z is explicit for a degenerate distribution, avoiding nonstandard JSON infinity.
    return {"n": n, "mean": mean, "sd": sd, "standard_error": error,
            "z_normal_approximation": mean / error if error else None,
            "ci95_normal_approximation": [mean - 1.96 * error, mean + 1.96 * error],
            "sign_flip_p_one_sided": extreme / len(flips)}


def best_passes(contrast):
    z = contrast["z_normal_approximation"]
    return contrast["mean"] <= BEST_GATES and z is not None and z <= -SCREEN_Z


def tail_passes(contrast, iterated_total, fresh_total):
    z = contrast["z_normal_approximation"]
    return (z is not None and z >= SCREEN_Z and iterated_total > fresh_total
            and iterated_total >= TAIL_RATIO * fresh_total)


def endpoints(trials, cap):
    """One replicate's best-of-N, distinct-circuit tail count and anytime best."""
    values = [t["xor2_count"] for t in trials]
    tail = [t for t in trials if t["xor2_count"] <= TAIL[cap]]
    lowest = min(trials, key=_rank)
    return {"n": len(trials), "best": lowest["xor2_count"], "best_seed": lowest["seed"],
            "mean": statistics.mean(values),
            "tail_distinct": len({t["structural_sha256"] for t in tail}),
            "tail_trials": len(tail),
            "target_trials": sum(v <= TARGETS[cap] for v in values),
            "best_after": [min(values[:end]) for end in
                           range(GENERATION_SIZE, len(values) + 1, GENERATION_SIZE)]}


def cap_summary(cap, by_budget):
    """Endpoints, frozen verdicts and descriptive diagnostics from one cap's joined trials."""
    replicates = range(REPLICATES)
    gen0 = [[t for t in by_budget["gen0"] if t["replicate"] == r] for r in replicates]
    fresh_arm = [gen0[r] + [t for t in by_budget["fresh"] if t["replicate"] == r]
                 for r in replicates]
    iterated_arm = [gen0[r] + [t for g in range(1, GENERATIONS + 1)
                               for t in by_budget[f"gen{g}"] if t["replicate"] == r]
                    for r in replicates]
    if any(len(arm) != BUDGET for arm in fresh_arm + iterated_arm):
        raise ValueError("replicate budgets are not matched")
    fresh = [endpoints(arm, cap) for arm in fresh_arm]
    iterated = [endpoints(arm, cap) for arm in iterated_arm]
    best = paired([i["best"] - f["best"] for i, f in zip(iterated, fresh)], -1)
    tail = paired([i["tail_distinct"] - f["tail_distinct"] for i, f in zip(iterated, fresh)], 1)
    iterated_tail = sum(i["tail_distinct"] for i in iterated)
    fresh_tail = sum(f["tail_distinct"] for f in fresh)
    seconds = {name: statistics.mean(t["runtime_seconds"] for t in rows)
               for name, rows in by_budget.items()}
    children = [t for g in range(1, GENERATIONS + 1) for t in by_budget[f"gen{g}"]]
    time_ratio = (statistics.mean(t["runtime_seconds"] for t in children)
                  / statistics.mean(t["runtime_seconds"] for t in by_budget["fresh"]))
    generations = {}
    starts = {name: start for name, start, _ in budgets(cap)}
    for g in range(1, GENERATIONS + 1):
        table = json.loads((ROOT / f"parents_depth{cap}_gen{g}.json").read_text())
        parents = {p["seed"]: p for rows in table["replicates"] for p in rows}
        rows = by_budget[f"gen{g}"]
        for t in rows:
            offset = t["seed"] - starts[f"gen{g}"]
            parent = table["replicates"][offset // GENERATION_SIZE][
                offset % GENERATION_SIZE // CHILDREN]
            if (t["parent_seed"] != parent["seed"] or t["switch"] != parent["child_switch"]
                    or t["lineage"][:-1] != parent["lineage"]
                    or t["prefix_state_sha256"] != parent["prefix_state_sha256"]):
                raise ValueError(f"gen{g} child {t['seed']} does not replay its parent's prefix")
        deltas = [t["xor2_count"] - parents[t["parent_seed"]]["xor2_count"] for t in rows]
        generations[str(g)] = {
            "child_mean": statistics.mean(t["xor2_count"] for t in rows),
            "child_sd": statistics.stdev(t["xor2_count"] for t in rows),
            "child_best": min(t["xor2_count"] for t in rows),
            "children_below_parent": sum(d < 0 for d in deltas),
            "children_equal_parent": sum(d == 0 for d in deltas),
            "mean_switch_fraction": statistics.mean(
                t["switch"] / parents[t["parent_seed"]]["sharing_decisions"] for t in rows),
            "parent_gates_mean": statistics.mean(p["xor2_count"] for p in parents.values()),
            "parent_lineage_depths": dict(sorted(Counter(
                len(p["lineage"]) - 1 for p in parents.values()).items())),
            "distinct_roots_per_replicate": [len({p["lineage"][0][0] for p in chosen})
                                             for chosen in table["replicates"]],
        }
    every = [t for rows in by_budget.values() for t in rows]
    lowest = min(every, key=_rank)
    return {
        "fresh": fresh, "iterated": iterated,
        "best_of_n_iterated_minus_fresh": best,
        "tail_distinct_iterated_minus_fresh": tail,
        "tail_distinct_totals": {"iterated": iterated_tail, "fresh": fresh_tail},
        "h9_best_passes": best_passes(best),
        "h9_tail_passes": tail_passes(tail, iterated_tail, fresh_tail),
        "mean_worker_seconds": seconds,
        "budget_means": {name: {key: statistics.mean(t[key] for t in rows) for key in
                                ("xor2_count", "sharing_decisions", "sharing_retained",
                                 "finishing_retained")}
                         for name, rows in by_budget.items()},
        "child_to_fresh_worker_seconds_ratio": time_ratio,
        "compute_matched_in_time": time_ratio <= TIME_RATIO_LIMIT,
        "generations": generations,
        "lowest_trial": {key: lowest[key] for key in
                         ("seed", "budget", "replicate", "xor2_count",
                          "total_excess_fanout_above_4", "lineage")},
    }


def summarize(caps):
    return {"stage": "stage1", "caps": {
        str(cap): cap_summary(cap, {name: load_budget(name, start, count, cap)
                                    for name, start, count in budgets(cap)})
        for cap in caps}}


def check_provenance():
    """Freeze tracked sources and the protocol at the preregistration commit."""
    files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    files = [f for f in files if f.endswith(".py") or
             f in ("SPEC.md", "reference/crc32_reference.v", str(PROTOCOL))]
    if str(PROTOCOL) not in files:
        raise ValueError("the protocol must be committed before the budget")
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
        "source_sha256": hashes, "replicates": REPLICATES, "budget": BUDGET,
        "generation_size": GENERATION_SIZE, "generations": GENERATIONS,
        "parent_count": PARENT_COUNT, "children": CHILDREN, "root_limit": ROOT_LIMIT,
        "tail_thresholds": {str(cap): TAIL[cap] for cap in CAPS},
        "budgets": {str(cap): [list(row) for row in budgets(cap)] for cap in CAPS},
        "random_tests": DEFAULT_RANDOM_TESTS, "verification_seed": DEFAULT_RANDOM_SEED,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _completed(cap):
    paths = [CHECKPOINTS / f"{run_name(name, cap)}_search.json" for name, _, _ in budgets(cap)]
    return all(path.exists() and json.loads(path.read_text())["status"] == "completed"
               for path in paths)


def run_cap(cap, workers):
    for name, start, count in budgets(cap):
        run = run_name(name, cap)
        parents = None
        if name not in ("gen0", "fresh"):
            parents = _trial_parents(frozen_parent_table(cap, int(name[3:]), workers))
        print(f"Starting/resuming {run}: {start}..{start + count - 1}", flush=True)
        run_bounded_search(
            cap, start, count, workers, CHECKPOINTS / f"{run}_search.json",
            ROOT / f"{run}.v", CHECKPOINTS / f"{run}_incumbents", LOG,
            DEFAULT_RANDOM_TESTS, DEFAULT_RANDOM_SEED,
            trial=partial(search_seed, start=start, parents=parents, spool=ROOT / f"{run}_spool"),
            algorithm=algorithm_name(name, cap), module_name=f"candidate_iterated_{run}",
        )
        _consolidate(run, logged_attempts(LOG, algorithm_name(name, cap), start, count))
        print(f"Completed {run}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("stage1",), required=True)
    parser.add_argument("--cap", type=int, choices=CAPS, action="append",
                        help="run one cap (repeatable); default both, cap 7 first")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    caps = tuple(args.cap or CAPS)
    ROOT.mkdir(parents=True, exist_ok=True)
    check_provenance()
    with _exclusive_search_lock(LOG):
        for cap in caps:
            run_cap(cap, args.workers)
        summary = summarize([cap for cap in CAPS if _completed(cap)])
        (ROOT / "stage1_summary.json").write_text(_render(summary))
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

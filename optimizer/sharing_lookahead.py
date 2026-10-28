"""Frozen two-move sharing lookahead experiment; historical builders unchanged."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import copy
from functools import partial
import hashlib
import json
from pathlib import Path
import random
import statistics
import subprocess
import time

from generator.build_matrix import build_transformation_matrix
from optimizer.depth_bounded import _kraft, logged_attempts, run_bounded_search
from optimizer.kraft_slack import _SlackBuilder
from optimizer.optimize import Candidate, _exclusive_search_lock, _prune_operations
from optimizer.phase_isolation import _digest, paired_difference
from verifier.verify_network import DEFAULT_RANDOM_SEED, DEFAULT_RANDOM_TESTS

ROOT = Path("results/sharing_lookahead")
CHECKPOINTS = Path("results/checkpoints/sharing_lookahead")
LOG = Path("results/search_logs/sharing_lookahead.jsonl")
SEEDS = {("stage1", 7): (400_000, 1_000), ("stage1", 6): (420_000, 1_000),
         ("stage2", 7): (410_000, 10_000), ("stage2", 6): (430_000, 10_000)}
SHORTLIST = 3
CONTINUATIONS = 1


def algorithm_name(arm: str, cap: int) -> str:
    return f"sharing-lookahead-{arm}-depth{cap}-v1"


class _LookaheadBuilder(_SlackBuilder):
    """Only sharing selection changes; finishing dispatch remains inherited."""
    def __init__(self, rows, cap, seed, enabled=True):
        super().__init__(rows, cap, seed, use_slack=cap == 6)
        self.enabled = enabled
        self.diagnostics = Counter()

    def snapshot(self):
        return (self.vectors, self.depths, self.vector_to_signal,
                [sorted(row) for row in self.expressions], self.operations,
                self.generator.getstate())

    def fork(self):
        probe = copy(self)
        probe.vectors = self.vectors.copy()
        probe.depths = self.depths.copy()
        probe.vector_to_signal = self.vector_to_signal.copy()
        probe.expressions = [row.copy() for row in self.expressions]
        probe.operations = self.operations.copy()
        probe.generator = random.Random()
        probe.generator.setstate(self.generator.getstate())
        probe.diagnostics = self.diagnostics.copy()
        return probe

    def ranked(self):
        # Identical deterministic keys to the designated control at each cap.
        if self.use_slack:
            frequencies, costs = self._frequencies_and_costs(new_only=True)
        else:
            frequencies = self._feasible_frequencies(new_only=True)
            costs = Counter()
        pairs = [pair for pair, frequency in frequencies.items() if frequency > 1]
        pairs.sort(key=lambda pair: (
            -frequencies[pair], costs[pair],
            1 + max(self.depths[pair[0]], self.depths[pair[1]]),
            (self.vectors[pair[0]] ^ self.vectors[pair[1]]).bit_count(), pair))
        return pairs

    def probe(self, pair):
        """Net singleton-completion saving after root + one future move/reuse.

        The future move is enumerated on the changed, Kraft-feasible state;
        its availability/frequency and free XOR-vector reuse are new information.
        No finishing simulation and no random calls occur in a probe.
        """
        probe = self.fork()
        initial_terms = sum(map(len, probe.expressions))
        initial_gates = len(probe.operations)
        probe._apply(pair)
        probe.free_rewrites()
        root_reward = initial_terms - sum(map(len, probe.expressions)) - (
            len(probe.operations) - initial_gates)
        for _ in range(CONTINUATIONS):
            ranked = probe.ranked()
            if not ranked:
                break
            probe._apply(ranked[0])
            probe.free_rewrites()
        reward = initial_terms - sum(map(len, probe.expressions)) - (
            len(probe.operations) - initial_gates)
        return reward, reward - root_reward

    def choose_shared_pair(self):
        # Consume exactly one historical proposal's draws on the real RNG.
        proposal = super().choose_shared_pair()
        if proposal is None or not self.enabled:
            return proposal
        shortlist = [proposal]
        for pair in self.ranked():
            if pair not in shortlist:
                shortlist.append(pair)
            if len(shortlist) == SHORTLIST:
                break
        scores = [self.probe(pair) for pair in shortlist]
        # First maximum: ties preserve proposal, then historical deterministic key.
        chosen = max(range(len(shortlist)), key=lambda i: scores[i][0])
        self.diagnostics.update({
            "sharing_decisions": 1, "probes": len(shortlist),
            "changed_proposals": int(chosen != 0),
            "reward_gain_vs_proposal": scores[chosen][0] - scores[0][0],
            "selected_future_reward": scores[chosen][1],
            "proposal_future_reward": scores[0][1],
            "tied_best_decisions": int(sum(s[0] == scores[chosen][0] for s in scores) > 1),
        })
        return shortlist[chosen]


def build_trial(seed, cap, arm):
    if arm not in ("control", "candidate") or cap not in (6, 7):
        raise ValueError("unsupported arm or cap")
    rows = tuple(build_transformation_matrix())
    builder = _LookaheadBuilder(rows, cap, seed, enabled=arm == "candidate")
    started = time.perf_counter()
    while True:
        builder.free_rewrites()
        pair = builder.choose_shared_pair()
        if pair is None:
            break
        builder._apply(pair)
    sharing_seconds = time.perf_counter() - started
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
        "lookahead": dict(builder.diagnostics),
    }
    outputs = builder.finish_outputs()
    if tuple(builder.vectors[source] for source in outputs) != rows:
        raise RuntimeError("GF(2) signal-vector check failed")
    if max(builder.depths[source] for source in outputs) > cap:
        raise RuntimeError("lookahead trial exceeded cap")
    operations = _prune_operations(builder.operations, outputs)
    diagnostics.update({
        "finishing_created": len(builder.operations) - sharing_count,
        "sharing_retained": sum(op.output < boundary for op in operations),
        "finishing_retained": sum(op.output >= boundary for op in operations),
        "xor2_count": len(operations),
    })
    # Timing is separate from deterministic diagnostic identities.
    diagnostics["runtime"] = {"sharing_seconds": sharing_seconds,
                              "build_seconds": time.perf_counter() - started}
    return Candidate(seed=seed, operations=operations, output_sources=outputs,
                     vectors=tuple(builder.vectors), depths=tuple(builder.depths)), diagnostics


def search_seed(seed, depth_cap, *, arm, spool=None):
    candidate, diagnostics = build_trial(seed, depth_cap, arm)
    if spool is not None:
        spool.mkdir(parents=True, exist_ok=True)
        path = spool / f"seed_{seed}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(diagnostics, sort_keys=True) + "\n")
        temporary.replace(path)
    return candidate


def consolidate(run, records):
    """Append logged seed diagnostics; never rewrite prior evidence on replay."""
    path = ROOT / f"{run}_diagnostics.jsonl"
    spool = ROOT / f"{run}_spool"
    previous = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    if [row["seed"] for row in previous] != [r["seed"] for r in records[:len(previous)]]:
        raise ValueError("diagnostic prefix differs")
    with path.open("a") as stream:
        for record in records[len(previous):]:
            pending = spool / f"seed_{record['seed']}.json"
            row = json.loads(pending.read_text())
            if row["xor2_count"] != record["final_metrics"]["xor2_count"]:
                raise ValueError("diagnostic metrics differ")
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()
    for record in records:
        (spool / f"seed_{record['seed']}.json").unlink(missing_ok=True)
    if spool.exists() and not any(spool.iterdir()):
        spool.rmdir()


def passes_screen(paired):
    return (paired["mean"] <= -0.5 and paired["z_normal_approximation"] is not None
            and paired["z_normal_approximation"] <= -3)


def summarize(stage, caps):
    result = {"stage": stage, "caps": {}}
    for cap in caps:
        start, count = SEEDS[(stage, cap)]
        values, stats = {}, {}
        for arm in ("control", "candidate"):
            records = logged_attempts(LOG, algorithm_name(arm, cap), start, count)
            if len(records) != count or not all(row["verification_passed"] for row in records):
                raise ValueError("incomplete or unverified budget")
            values[arm] = [int(row["final_metrics"]["xor2_count"]) for row in records]
            diagnostics = [json.loads(line) for line in
                           (ROOT / f"{stage}_{arm}_depth{cap}_diagnostics.jsonl").read_text().splitlines()]
            if [row["seed"] for row in diagnostics] != list(range(start, start + count)):
                raise ValueError("diagnostic coverage differs")
            stats[arm] = {
                "n": count, "mean": statistics.mean(values[arm]),
                "sd": statistics.stdev(values[arm]), "best_gates": min(values[arm]),
                "best_seed_by_gates": start + values[arm].index(min(values[arm])),
                "mean_worker_seconds": statistics.mean(r["runtime_seconds"] for r in records),
                "total_worker_seconds": sum(r["runtime_seconds"] for r in records),
                "accepted_incumbents": sum(r["accepted"] for r in records),
                "targets_met": sum(v <= (439 if cap == 7 else 461) for v in values[arm]),
                **{f"mean_{key}": statistics.mean(row[key] for row in diagnostics)
                   for key in ("sharing_retained", "finishing_retained")},
                "lookahead_totals": dict(sum((Counter(r["lookahead"]) for r in diagnostics), Counter())),
            }
        paired = paired_difference(values["candidate"], values["control"])
        result["caps"][str(cap)] = {
            "arms": stats, "paired_candidate_minus_control": paired,
            "runtime_ratio": stats["candidate"]["mean_worker_seconds"] / stats["control"]["mean_worker_seconds"],
            "passes_frozen_rule": passes_screen(paired),
        }
    return result


def check_provenance():
    """Freeze tracked sources at the preregistration commit before any trial."""
    files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    files = [f for f in files if f.endswith(".py") or
             f in ("SPEC.md", "reference/crc32_reference.v",
                   "docs/experiments/sharing_lookahead.md")]
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
        "source_sha256": hashes, "shortlist": SHORTLIST, "continuations": CONTINUATIONS,
        "seeds": {f"{stage}_depth{cap}": list(value) for (stage, cap), value in SEEDS.items()},
        "random_tests": DEFAULT_RANDOM_TESTS, "verification_seed": DEFAULT_RANDOM_SEED,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("stage1", "stage2"), required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    check_provenance()
    caps = [7, 6]
    if args.stage == "stage2":
        first = json.loads((ROOT / "stage1_summary.json").read_text())
        caps = [int(cap) for cap, row in first["caps"].items() if row["passes_frozen_rule"]]
    with _exclusive_search_lock(LOG):
        for cap in caps:
            start, count = SEEDS[(args.stage, cap)]
            for arm in ("control", "candidate"):
                run = f"{args.stage}_{arm}_depth{cap}"
                print(f"Starting/resuming {run}: {start}..{start + count - 1}", flush=True)
                run_bounded_search(
                    cap, start, count, args.workers, CHECKPOINTS / f"{run}_search.json",
                    ROOT / f"{run}.v", CHECKPOINTS / f"{run}_incumbents", LOG,
                    DEFAULT_RANDOM_TESTS, DEFAULT_RANDOM_SEED,
                    trial=partial(search_seed, arm=arm, spool=ROOT / f"{run}_spool"),
                    algorithm=algorithm_name(arm, cap), module_name=f"candidate_lookahead_{arm}_depth{cap}",
                )
                consolidate(run, logged_attempts(LOG, algorithm_name(arm, cap), start, count))
                print(f"Completed {run}", flush=True)
        summary = summarize(args.stage, caps)
        (ROOT / f"{args.stage}_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

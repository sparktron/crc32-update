# Experiment: iterated elite restart at matched compute (frozen protocol)

Preregistered 2026-10-29, before any experimental seed outcome. Base commit:
`1918092abb9510bad00676274387b3a93ca1981a` (elite-prefix frontier adopted).
Branch: `claude/iterated-elite-restart`, stacked on PR #14. The
implementation and this protocol must be committed before collecting
results; the run manifest records that commit. Results and interpretation
belong in `iterated_elite_restart_results.md`; this protocol remains
immutable. Previous experiment: `elite_prefix_restart_results.md`, whose
frozen next-decision rule (H8 passed at both caps) requires this protocol.

## Question

Does restarting from the prefixes of a search's own best trials, iterated
over generations, find better circuits than spending the same number of
trials on fresh seeds, once the iterated search pays for building its own
elite pool?

The precursor showed that elite prefixes carry quality, but its parents
were the 20 best of 12,000–13,000 earlier trials, which it did not charge.
Its 437 and 460 are therefore not evidence of a better method per unit of
compute. Here neither arm uses any historical trial.

## Hypotheses and outcomes

Each replicate pair is one fresh replicate and one iterated replicate of
2,000 trials each at the same cap (below). Each hypothesis is tested
separately at each cap.

- **H9b (best-of-N):** the iterated replicate's best XOR2 count averages
  at least **2.0 gates lower** than its paired fresh replicate's, with
  paired normal-approximation **z <= -3** over the 10 pairs. Failing either
  refutes H9b at that cap.
- **H9t (tail rate):** the iterated replicate produces more **distinct
  circuits** at or below the tail threshold, **442 XOR2 at depth 7** and
  **469 at depth 6**, than its paired fresh replicate. This requires a paired
  **z >= +3** on the per-replicate count differences, and the pooled
  iterated count must be **at least twice** the pooled fresh count (and
  strictly larger). Failing either refutes H9t at that cap.

The 2.0-gate threshold matches H8. It is 1.25 standard deviations of a
historical fresh best-of-2,000 at cap 7 and 0.8 at cap 6 (below). Distinct means a distinct
`structural_sha256`, so a child that rebuilds a circuit already counted
adds nothing.

Independent existence targets: **<=436** gates at depth 7 and **<=459** at
depth 6, one below the submitted A/B/B7 (437) and C (460). Report target
attainment, best circuits and fanout separately from H9. No submitted
frontier replacement is part of this experiment.

## Frozen design

Builders are each cap's designated control, unchanged from the lookahead
and elite-prefix experiments. Cap 7 uses the historical bounded baseline
(`_SlackBuilder` with `use_slack=False`). Cap 6 uses historical both-phases
Kraft slack, including the fresh-gate finishing fallback.
`optimizer.iterated_elite` wraps them through the precursor's
`_control`/`_step`/`_state_digest`.

**Trials and lineages.** A trial is a chain of (seed, switch) pairs,
starting with `(root, 0)`. The control is built with the root seed. At each
later switch, counted in sharing decisions, the RNG is replaced by
`random.Random(seed)`, as in the precursor's children. Sharing and
finishing then continue with the control code. Free rewrites draw no
randomness. A one-pair chain is exactly the control trial of its seed. A
two-pair chain is exactly a precursor child (a test checks both). A child
of parent P has P's chain plus `(child_seed, k)`, with

    k = s_P + floor((D_P - s_P) / 2)

where s_P is P's own switch (0 for a generation-0 trial) and D_P is P's
logged sharing-decision count. The child keeps half of the decisions its
parent redrew, then redraws the rest. Along a lineage that keeps improving,
switches fall at about 1/2, 3/4, 7/8 and 15/16 of the sharing phase.

**Replicates.** Per cap there are 10 replicate pairs. Pair r shares one
generation 0: 400 fresh control trials.

- **Fresh replicate:** generation 0 plus 1,600 more fresh control trials.
- **Iterated replicate:** generation 0 plus four child generations of 400
  each. Each child generation is 20 parents x 20 children.

Both arms therefore spend exactly 2,000 trials per replicate. The iterated
arm's elite pool is built from its own first 400 trials.

**Parents (pool-refresh rule).** Before generation g (1..4) of replicate r,
its parents are chosen from **all** of that replicate's trials so far:
generation 0 and generations 1..g-1. The parents can be any mix of
generations. Ranking is by XOR2, then total excess fanout above four,
then seed, which is the precursor's elite order. Going down the ranking,
a trial is skipped if:

- its `structural_sha256` equals that of a higher-ranked trial;
- 5 parents (`ROOT_LIMIT`) already descend from its generation-0 root; or
- it has fewer than two redrawn decisions (D - s < 2).

The first 20 remaining trials are the parents. The parent at rank i gets
children 20i..20i+19 of that replicate's block. A parent that stays in
the top 20 gets 20 new children at the same switch, from new seeds.

Each generation's table is `results/iterated_elite/parents_depth{cap}_gen{g}.json`.
It is computed from the logged earlier generations and written before that
generation's first child. Afterwards it must reproduce byte for byte. For
each parent the table records the chain, D, its switch, the children's
switch k, and the state digest after k decisions. That digest comes from
an independent replay of the parent's chain, which must reproduce D. The
summary checks every child's parent, chain, k and prefix digest against
the table.

**Design inputs, chosen from the precursor's descriptive results before
this protocol.**

- At f = 25, best-of-50 children beat their elite parent for only 2/20
  (cap 7) and 1/20 (cap 6) parents.
- At f = 50, 4.0%/15.5% of elite children were below their parent, and
  best-of-50 improved 15/20 and 12/20 parents. Improvements reached
  4 and 8 gates.
- At f = 75, 17.0%/31.7% of children were below their parent and
  21.9%/18.2% equal; best-of-50 improved 12/20 and 17/20 parents.
- At f = 100, no gate count ever changed.

A fixed fraction of D would not iterate. Every generation would redraw the
same final (1 - f) of the sharing phase and discard what the parent's own
redraw gained, so it reduces to more children of generation-0 roots.
Halving the parent's own redrawn segment applies the precursor's f = 50
(exploring) to roots and its f = 75 (refining) to their children. Later
generations refine further. The pool size of 20 matches the precursor. The
root limit exists because about one f = 75 child in five ties its parent,
so equal-count descendants of a single root could otherwise fill the
pool.

**Tail thresholds.** The precursor's parent pools plus its fresh arms give
14,000 cap-7 and 15,000 cap-6 historical control trials. In them, <=442
occurred 12 times (0.086%, about 1.7 per 2,000) and <=469 occurred 21
times (0.140%, about 2.8 per 2,000). Over seven disjoint historical blocks
of 2,000, the fresh best averaged 441.4 (SD 1.6) at cap 7 and 467.4
(SD 2.5) at cap 6. Over blocks of 400 it averaged 443.4 and 470.0. These
are design inputs; they are not this experiment's baseline.

## Matched compute

The compute unit is one trial: one complete control build plus the same
per-trial independent structural and exact check. Children re-execute
their whole chain rather than restoring a saved state, so each trial does
the same algorithmic work. The precursor measured flat mean worker time
across arms (3.40–3.70 s at cap 7, 4.02–4.21 s at cap 6). Both arms spend
2,000 trials per replicate, and the iterated arm's 400 pool-building trials
count against its budget.

No trial from any earlier log is a parent or a pool member, so no
historical computation enters either arm. The design was informed by
roughly 45,000 earlier trials (the fraction rule and thresholds above);
that knowledge is not charged, as a limitation. Not charged to either arm:
selecting parents (sorting at most 2,000 records), replaying parent
digests (verification, 200 parent replays per generation), and incumbent
formal acceptance. All of these are reported.

The mean worker-seconds per child (generations 1–4) and per fresh
continuation trial are reported. If their ratio exceeds 1.10 at a cap,
that cap's comparison is reported as matched in trials, not in measured
time.

## Seeds

All ranges are fresh. A test verifies that they are absent from every
historical log. Budgets run in this order:

| Budget | Algorithm | Cap 7 | Cap 6 | Replicate r |
| --- | --- | --- | --- | --- |
| gen0 | `iterated-elite-gen0-depth{cap}-v1` | 600000..603999 | 640000..643999 | start + 400r .. +399 |
| fresh | `iterated-elite-fresh-depth{cap}-v1` | 604000..619999 | 644000..659999 | start + 1600r .. +1599 |
| gen1 | `iterated-elite-gen1-depth{cap}-v1` | 620000..623999 | 660000..663999 | start + 400r .. +399 |
| gen2 | `iterated-elite-gen2-depth{cap}-v1` | 624000..627999 | 664000..667999 | start + 400r .. +399 |
| gen3 | `iterated-elite-gen3-depth{cap}-v1` | 628000..631999 | 668000..671999 | start + 400r .. +399 |
| gen4 | `iterated-elite-gen4-depth{cap}-v1` | 632000..635999 | 672000..675999 | start + 400r .. +399 |

Within a child block, offset j belongs to parent j // 20 of that
generation's table for replicate r. Per cap there are 36,000 trials: 4,000
shared, 16,000 fresh continuation and 16,000 children. Across both caps
there are **72,000 trials**. There is one stage, with no extension, early
stopping, seed reuse, or change to thresholds, rules or replicate counts
after results. Results do not depend on worker count. Each generation
depends only on logged earlier generations, and every trial is a
deterministic function of its seed and the frozen tables.

## Inference

The statistical unit is the replicate pair. For each pair r, compute:

- d_r(best) = iterated best minus fresh best;
- d_r(tail) = iterated distinct tail count minus fresh distinct tail count.

For each endpoint and cap, the paired SE is the sample SD of the 10
differences divided by sqrt(10), z = mean / SE, and the approximate 95%
interval is mean +/- 1.96 SE. Degenerate SE gives null z and cannot pass.
With 10 pairs, the z cutoffs are prespecified screening rules, not exact
significance claims. There are four tests in all: two endpoints at each of
two caps. Each cutoff has a one-sided normal tail of about 0.00135, under
0.0054 for the family by Bonferroni. Exact one-sided sign-flip
randomization p-values over all 1,024 sign assignments are reported
descriptively; the smallest possible value is 1/1024.

The shared generation 0 correlates each pair positively. That reduces
the variance of the paired difference and biases neither arm: each arm
contains it exactly once.

Descriptive only:

- the anytime best after 400, 800, ..., 2,000 trials per replicate and arm;
- trial-level (non-distinct) tail counts;
- trials at or below the existence targets;
- arm means;
- per generation:
  - child mean, SD and best;
  - children below and equal to their parent;
  - mean switch fraction k / D_P;
  - mean parent count;
  - parents by lineage depth;
  - distinct roots per replicate;
- per budget:
  - mean XOR2;
  - sharing decisions;
  - retained sharing and finishing gates;
  - worker seconds;
- the lowest trial and its lineage;
- best circuits with fanout.

## Next decision (frozen before results)

- **H9b and H9t pass at a cap:** iterated elite restart replaces fresh seeds
  as that cap's search and becomes the control for later method
  experiments there. The planned next experiment is multi-output window
  resynthesis of finished elite circuits. It is compared at matched compute
  against this search, not against fresh seeds.
- **Only H9t passes:** the search yields more good circuits per trial but
  no better best at N = 2,000. Use it to harvest secondary-objective
  circuits (fanout, F4). Before any best-circuit claim, preregister a
  longer-horizon test (more generations at larger N).
- **Only H9b passes:** use it for best-circuit search at that cap. Any
  diversity variant needs its own preregistration; none is tuned on these
  seeds.
- **Neither passes at a cap:** the precursor's elite advantage at that cap
  does not survive paying for the pool at this budget. Fresh seeds remain
  the default. The planned next experiment is multi-output window
  resynthesis of finished elite circuits.
- In every case, existence targets are reported separately, and frontier
  integration is separate work at the project owner's request.

## Timing and computational budget

No timing pilot was run, because every trial executes the control's code
path. The precursor measured mean worker times of 3.40–3.70 s at cap 7 and
4.02–4.21 s at cap 6, with 16 process workers on an i9-10900K (20 logical
CPUs, 10 cores).

Estimated wall time is 36,000 x 3.55 s + 36,000 x 4.12 s over 16 workers,
about 17,300 s (4.8 hours). Added to that are incumbent acceptance proofs,
eight per-generation parent replays (about a minute each) and eight
generation barriers, for roughly **5 hours** in total. The project owner
starts the budget manually. `--cap 7` and `--cap 6` split it into two runs
of about 2.5 hours.

## Replay, verification and evidence

Before collection, `optimizer.test_iterated_elite` must pass. Its tests
show the following:

- Generation-0 trials equal the historical builders byte for byte at both
  caps.
- One-switch chains equal precursor children byte for byte, including the
  prefix digest.
- Grandchildren reproduce the child's own state at their switch, replay
  deterministically and diverge across seeds.
- Malformed chains and switches past the parent's sharing phase are
  rejected.
- Parent prefix replay matches the precursor's committed digest.
- The in-memory structural hash equals
  `verifier.build_results.structural_fingerprint` of the rendered netlist.
- The selection rule ranks, deduplicates, limits roots and enforces
  eligibility.
- The layout uses fresh seeds absent from every log and matches the
  budgets of both arms.
- Paired statistics, sign-flip p-values and both verdict rules behave as
  specified on synthetic data.
- Parent tables and the summary are reproduced from synthetic logged
  generations, which includes refusing a rewritten table and a tampered
  child prefix.

`check_provenance` refuses uncommitted sources and freezes source and
protocol hashes in `run_manifest.json`.

Raw per-seed records append to `results/search_logs/iterated_elite.jsonl`
(registered prefix `iterated-elite-`; about 48 MB, below GitHub's 100 MB
file limit). Checkpoints and retained incumbents live under
`results/checkpoints/iterated_elite/`. Workers atomically spool seed
diagnostics, and logged ones append to per-budget JSONL in
`results/iterated_elite/` when the budget completes; unlogged spools are
not evidence. Parent tables, `stage1_summary.json`, the manifest and the
progress log are also kept there. Resume uses the contiguous authoritative
log prefix. `optimizer.iterated_elite.replay_trial` rebuilds any logged
trial from its seed and the written tables.

Every trial passes independent structural and exact checks and the cap.
Every retained incumbent passes 97 exact vectors, 100000 randomized vectors
(seed 0xC32A5EED) and Yosys/SMTBMC/Z3 formal equivalence before
acceptance.

After collection, run an audit in a detached checkout of the manifest
commit (`scripts.frozen_checkout`) covering:

- coverage and unique IDs;
- chains and prefix digests against the tables, and parent-table
  reproduction;
- phase gate sums and depth bounds;
- source identity;
- incumbent byte replay;
- completed-budget replay with unchanged evidence bytes and no new trials.

Then run the full tests and the submitted-result provenance check. Record
refutations, limitations and the next decision in the results record and
STATUS.

Commands, from the repository root, after committing this protocol:

```bash
python3 -B -m unittest optimizer.test_iterated_elite verifier.test_search_logs
python3 -B -m optimizer.iterated_elite --stage stage1 --workers 16 >> results/iterated_elite/stage1_progress.log 2>&1
python3 -B -m unittest discover
python3 -B -m verifier.build_results --check --require-spec-minimum
```

The stage command is resumable verbatim, and adding `--cap 7` or
`--cap 6` restricts it to one cap. Progress is in the append-only raw log,
the per-budget checkpoints and the written parent tables. Shell output goes
to `stage1_progress.log`.

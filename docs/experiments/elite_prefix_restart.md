# Experiment: elite-prefix restarts (frozen protocol)

Preregistered 2026-10-28, before any experimental seed outcome. Base commit:
`9798c231bfe404b0459e8876681324350e885919` (lookahead results recorded).
Branch: `claude/elite-prefix-restart`. The implementation, the parent table
and this protocol must be committed before collecting results; the run
manifest records that commit. Results and interpretation belong in
`elite_prefix_restart_results.md`; this protocol remains immutable. Previous
experiment: `sharing_lookahead_results.md`. That record proposes a residual
feasible-opportunity score next. The project owner chose this diagnostic
first, because it decides whether any per-decision score has leverage.

## Question

Is a trial's final gate count largely fixed by its early sharing decisions,
so that restarting from prefixes of the best recorded trials samples lower
counts than fresh seeds?

Recorded motivation, not evidence from this experiment: the lookahead tied
on 98.7–99.2% of decisions and changed 1.3–1.5% of proposals, yet 768 of
1,000 (cap 7) and 822 of 1,000 (cap 6) paired seeds ended at different
counts. Every new best circuit since Phase 6 (440, 465, 462, 438) was a
draw about four standard deviations below its family's mean. If prefixes carry
quality, sampling near elites beats fresh seeds, and rollout or beam methods
are worth building. If not, per-decision scoring has little leverage.

## Hypothesis and outcomes

H8, separately per cap: at prefix fraction 50%, children of elite parents
average at least 2.0 gates fewer than both (a) fresh control trials and
(b) children of median parents at the same fraction, each contrast with
normal-approximation z <= -3 using parent-clustered standard errors. Both
contrasts must pass; otherwise H8 is refuted at that cap. The 2.0-gate
threshold (about 0.4–0.5 SD) is fixed before results as a useful shift.

Independent existence targets: <=437 gates at depth 7; <=461 at depth 6.
Report target attainment, best circuits and fanout separately from H8.
No submitted frontier replacement is part of this experiment.

## Frozen design

Builders are each cap's designated control from the lookahead experiment,
unchanged: cap 7 is the historical bounded baseline (`_SlackBuilder` with
`use_slack=False`); cap 6 is historical both-phases Kraft slack, including
the fresh-gate finishing fallback. `optimizer.elite_prefix` wraps them.

Parent pools are the committed logs of budgets these builders reproduce:

- cap 7: `kraft-bounded-bp-cse-depth7-v1` 40000..49999,
  `kraft-phase-isolation-baseline-depth7-v1` 300000..300999 and
  `sharing-lookahead-control-depth7-v1` 400000..400999; 12,000 trials,
  mean 456.05, SD 4.27;
- cap 6: `kraft-slack-tiebreak-depth6-v1` 240000..250999,
  `kraft-phase-isolation-both-depth6-v1` 320000..320999 and
  `sharing-lookahead-control-depth6-v1` 420000..420999; 13,000 trials,
  mean 485.47, SD 5.29.

Other builders' trials (the 440 of ablation `rewrite`, the 465 of Kraft
adaptive) are excluded: their prefixes cannot replay on the control.
Elite: the 20 best by XOR2, then excess fanout above four, then seed.
Median: 20 trials at the pool's lower median (456 at cap 7, from 1,102;
485 at cap 6, from 968), sampled with `random.Random(0xE117E + cap)` and
listed by seed. Elite counts are 438–443 at cap 7 (seed 400800 first) and
462–470 at cap 6 (seed 320099 first).

`--stage select` wrote `results/elite_prefix/parents.json` and afterwards
only verifies its bytes. Every parent replayed its logged final metrics
exactly. The table records each parent's sharing-decision count D and the
SHA-256 of builder state after each prefix. Descriptively, elite parents
made more sharing decisions than median parents: mean D 189.0 versus 181.6
at cap 7, and 172.2 versus 165.4 at cap 6.

A child builds the control with the parent's seed, runs
k = floor(D * f / 100) historical sharing iterations (free rewrites,
selector draw, apply), records the state digest (vectors, depths,
expressions, RNG state), replaces the RNG with `random.Random(child_seed)`
and continues sharing and finishing with the control code. Free rewrites
draw no randomness. k = 0 is exactly the control trial of the child seed;
k = D keeps the parent's whole sharing phase and redraws only finishing.

Each cap has elite and median arms at f = 25, 50, 75 and 100, each with 20
parents x 50 children (1,000 trials), plus 2,000 fresh control trials:
10,000 trials per cap, 20,000 in total. Child seed s of an arm starting at
seed s0 belongs to parent (s - s0) // 50 in table order. Seeds are fresh,
and a test verifies they are absent from every historical log:

| Arm | Cap 7 | Cap 6 |
| --- | --- | --- |
| elite f25 / f50 / f75 / f100 | 500000 / 501000 / 502000 / 503000 | 520000 / 521000 / 522000 / 523000 |
| median f25 / f50 / f75 / f100 | 504000 / 505000 / 506000 / 507000 | 524000 / 525000 / 526000 / 527000 |
| fresh | 508000..509999 | 528000..529999 |

Each parent arm covers 1,000 seeds from its listed start. There is one
stage: no extension, early stopping, seed reuse, or threshold, arm or
parent change after results.

## Inference

An arm's mean is the mean of its children, equal to the mean of its parent
means. Its parent-clustered SE is the sample SD of the 20 parent means
divided by sqrt(20). Fresh SE is the sample SD divided by sqrt(2000). A
contrast's SE is sqrt(SE_a^2 + SE_b^2); z = mean / SE; report the
approximate 95% interval mean +/- 1.96 SE. Degenerate SE gives null z and
cannot pass. With 20 clusters the z cutoff is a prespecified screening rule,
not an exact significance claim; the two caps are tested separately.

Descriptive only: contrasts at every fraction, including median minus fresh
(replaying an unselected prefix should change nothing); the heritability
slope (least squares of child mean on parent count over the 40 parents) at
each fraction; per-parent child mean, SD, best and count equal to the
parent; arm SDs; best circuits and target counts; retained sharing and
finishing gates; sharing decisions; runtimes.

## Next decision (frozen before results)

- H8 passes at a cap: preregister an iterated elite-restart search at that
  cap against fresh seeds at matched compute, with tail-rate and best-of-N
  endpoints on new seeds. That protocol states which fraction it uses,
  chosen from this experiment's descriptive results.
- H8 refuted at both caps: the planned next experiment is multi-output
  window resynthesis of finished elite circuits. New per-decision scoring
  or lookahead variants need a rationale that addresses this result.
- Either way, existence targets are reported separately.

## Timing and computational budget

No timing pilot: children execute the control's code path. The lookahead
control measured mean worker times of 3.126 s (cap 7) and 3.653 s (cap 6)
with 16 process workers on an i9-10900K (20 logical CPUs, 10 cores).
Estimated wall time is 10,000 x (3.126 + 3.653) / 16, about 4,240 s
(71 minutes), plus incumbent verification and a parent re-verification of
about 20 seconds. The project owner starts the budget manually.

## Replay, verification and evidence

Before collection, `optimizer.test_elite_prefix` must pass. Its tests show
that fresh and k = 0 trials equal the historical builders byte for byte at
both caps, and that children reproduce the committed prefix digests, replay
deterministically and diverge across child seeds. k = D keeps the sharing
phase; k > D is rejected. The selection rule reproduces the committed table,
and the layout uses fresh seeds. The screen and the clustered analysis are
exercised on synthetic data, including rejection of a tampered prefix.
Stage 1 re-runs selection and replay and refuses to start unless the table
bytes match. `check_provenance` refuses uncommitted sources and freezes
source, protocol and parent-table hashes in `run_manifest.json`.

Raw per-seed records append to `results/search_logs/elite_prefix.jsonl`
(registered prefix `elite-prefix-`). Checkpoints and retained incumbents
live under `results/checkpoints/elite_prefix/`. Workers atomically spool
seed diagnostics; logged ones append to per-arm JSONL in
`results/elite_prefix/` at arm completion, and unlogged spools are not
evidence. The summary checks every child's parent, k and prefix digest
against the table. Resume uses the contiguous authoritative log prefix.

Every trial passes independent structural and exact checks and the cap.
Every retained incumbent passes 97 exact vectors, 100000 randomized vectors
(seed 0xC32A5EED) and Yosys/SMTBMC/Z3 formal equivalence before acceptance.
After collection, audit coverage, unique IDs, prefix digests, phase gate
sums, depth bounds, source identity and incumbent replay; replay completed
budgets and confirm unchanged evidence bytes with no new trials. Run the
full tests and submitted-result provenance check. Record refutations,
limitations and the next decision in the results record and STATUS.

Commands, from the repository root, after committing this protocol:

```bash
python3 -B -m unittest optimizer.test_elite_prefix verifier.test_search_logs
python3 -B -m optimizer.elite_prefix --stage select --workers 16
python3 -B -m optimizer.elite_prefix --stage stage1 --workers 16 >> results/elite_prefix/stage1_progress.log 2>&1
python3 -B -m unittest discover
python3 -B -m verifier.build_results --check --require-spec-minimum
```

The stage command is resumable verbatim. Progress is in the append-only raw
log and per-arm checkpoints; shell output goes to `stage1_progress.log`.

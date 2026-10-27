# Experiment: a cap-adaptive (tight-row) Kraft-slack tie-break

**Status:** pre-registered 2026-10-27, before any code for this variant was
written or run. Completed 2026-10-27.
- H1 refuted; H2 confirmed.
- **H3 confirmed at cap 6:** a verified 466-gate network that dominates C.
- Stage 2 stopped early at 3,862 of 10,000 seeds because of a trial failure
  on seed 284,862. See Observed.

**Log location.** The `results/search_log.jsonl` records cited below moved unchanged into
`results/search_logs/kraft_adaptive_tiebreak.jsonl` on 2026-10-27, when the log was split into one file
per experiment (`scripts/split_search_log.py`).


**Motivation.** `docs/experiments/kraft_slack_tiebreak.md` found that putting
the Kraft-slack cost ahead of the depth key:
- helps at cap 6: mean −5.05 against the baseline, and a verified 467;
- hurts at cap 7: mean +2.31.

Its untested interpretation was that slack-first pays only when the budget is
tight, and that depth-first is better while rows still have room.

## The variant

It is identical to the Kraft-slack variant (`optimizer/kraft_slack.py`)
except in how a pair's cost is summed:

    cost(a, b) = Σ over feasible rows containing a and b, with K_before ≥ θ·2^cap,
                 of (K_after − K_before)

- A row is **tight** once it has used at least the fraction θ of its Kraft
  budget. Only tight rows contribute to the cost.
- When none of a pair's rows is tight, the cost is 0, and the baseline's
  depth key decides.
- The ordering key is unchanged from the slack variant:
  (−frequency, cost, new-gate depth, result weight, pair) in the sharing
  phase. The finishing phase uses the slack variant's finishing key with the
  same cost.
- **θ = 1/2 is fixed in advance** ("the row has used half its budget"). It is
  the only setting tested. Other values are out of scope, and none will be
  tried within this record.

**How θ = 1/2 behaves on this matrix** (computed before any run): rows start
as 34–52 depth-0 inputs.
- Cap 7: the initial fill K/2^7 is 0.27–0.41, so 0 of 32 rows are tight at
  the start. The variant begins depth-first and turns slack-first per row as
  rows fill.
- Cap 6: the initial fill is 0.53–0.81, so all 32 rows are tight at the
  start. The variant should behave almost like the slack variant at cap 6.

## Hypotheses

The comparators are the best existing method at each cap:
- cap 7: the baseline, 10,000 seeds, mean 456.05;
- cap 6: the slack variant, 11,000 seeds (stages 1 and 2), mean 485.49.

Significance uses the tie-corrected Mann–Whitney normal approximation.

- **H1 (cap 7, primary).** At cap 7 the adaptive variant is significantly
  better than the slack variant (z ≤ −3 against its 1,000 cap-7 seeds, mean
  458.36). It is also not significantly worse than the baseline (z < +3
  against its 10,000 seeds).
  - **Refuted by** either condition failing.
- **H2 (cap 6).** At cap 6 the adaptive variant keeps the slack variant's
  gain: it is not significantly worse than the slack variant (z < +3 against
  its 11,000 seeds).
  - **Refuted by** z ≥ +3.
- **H3 (targets).** Within 10,000 stage-2 seeds at a cap, it finds ≤ 440 XOR2
  at depth ≤ 7 (beating B7, 441) or ≤ 466 at depth ≤ 6 (beating the 467).
  - It is tested only at caps that reach stage 2. Otherwise it is recorded as
    *not tested*.
  - **Refuted at a tested cap by** a best above the threshold there.

**Context, not a target.** A verified 440-gate depth-7 network already exists
from the ablation (seed 160,832). It is a tail draw from a baseline-equivalent
distribution. Results are also reported against it.

## Stages, decided now

- **Stage 1:** 1,000 seeds per cap; this tests H1 and H2.
- **Stage 2:** 10,000 more seeds at each cap where the stage-1 mean is not
  significantly worse than the best existing method at that cap (z < +3).
  - At cap 7 the comparator is the baseline; at cap 6, the slack variant.
  - Stage 2 tests H3.

**Determinism gates, checked before any stage runs.**
1. With θ = 0 every row is tight, so the code must reproduce the slack
   variant byte for byte:
   - the 467 network (seed 246,653),
   - the first 20 logged stage-1 seeds at each cap, with metrics equal to
     the log.
2. With θ = 2 no row is ever tight, so every cost is 0 and the code must
   reproduce the baseline byte for byte:
   - the B7 and C incumbents,
   - the first 20 logged baseline seeds at each cap, with metrics equal to
     the log.

## Configuration

| Stage | Cap 7 seeds | Cap 6 seeds |
| --- | --- | --- |
| 1 | 260,000–260,999 | 280,000–280,999 |
| 2 (if triggered) | 261,000–270,999 | 281,000–290,999 |

These ranges are disjoint from every logged range.

- Algorithm name: `kraft-adaptive-tiebreak-half-depth<cap>-v1`.
- Driver: `optimizer.depth_bounded.run_bounded_search`, with the same
  verification, logging, checkpoint and resume as all recorded budgets.
- Run names: `stage1_depth<cap>` and `stage2_depth<cap>`, giving:
  - `results/checkpoints/kraft_adaptive/<run>_search.json`
  - `results/checkpoints/kraft_adaptive/<run>_incumbents/`
  - `results/kraft_adaptive/<run>.v`
- Exact commands, run from the repository root. Each takes the search-log
  lock and resumes from its checkpoint.

```bash
python3 -m optimizer.kraft_adaptive --stage stage1 --depth-cap 7 --workers 16
python3 -m optimizer.kraft_adaptive --stage stage1 --depth-cap 6 --workers 16
# Stage 2, only at a cap whose stage-1 z against its comparator is < +3:
python3 -m optimizer.kraft_adaptive --stage stage2 --depth-cap <cap> --workers 16
```

## Baselines

These come from the recorded logs:

| Run | Seeds | n | Mean | SD | Best |
| --- | --- | ---: | ---: | ---: | ---: |
| baseline cap 7 | 40,000–49,999 | 10,000 | 456.05 | 4.29 | 441 |
| slack variant cap 7 (stage 1) | 220,000–220,999 | 1,000 | 458.36 | 4.32 | 445 |
| baseline cap 6 | 50,000–59,999 | 10,000 | 490.43 | 5.24 | 470 |
| slack variant cap 6 (stages 1 and 2) | 240,000–250,999 | 11,000 | 485.49 | 5.28 | 467 |

## Code version and environment

- **Code:** commit `6e1b731`, which adds `optimizer/kraft_adaptive.py`, on
  branch `crczero-verification`.
  - `python3 -m unittest optimizer.test_kraft_adaptive` passed: 6 tests.
  - The tree is clean apart from an untracked `docs/reviews/` directory that
    this experiment did not create and does not read.
- **Determinism gates, passed before any stage ran:**
  - θ = 0 reproduces the slack variant. Seeds 220,000–220,019 and
    240,000–240,019 give 40 of 40 identical renders, with metrics equal to
    the log. The 467 network (seed 246,653) reproduces byte for byte.
  - θ = 2 reproduces the baseline. Seeds 40,000–40,019 and 50,000–50,019
    give 40 of 40 identical renders, with metrics equal to the log. The B7
    and C incumbents reproduce byte for byte.
- **Smoke trials:** seeds 1–3 at each cap, which are not in any budget. They
  checked correctness, cap compliance and replay only. Their values were
  withheld and are not evidence.
- **Environment:** Python 3.10.12, i9-10900K (10 cores, 20 threads),
  Yosys 0.9, Z3 4.8.12, 16 workers. Trials are deterministic per seed.

## Observed

**Stage 1.**
- Run: 2026-10-27, 20:30:57–20:38:26 UTC, at `a46d292`, with a clean tree
  apart from the untracked `docs/reviews/`.
- Both caps completed 1,000 contiguous seeds. Every record has
  `verification_passed: true`, and every trial met its cap.
- Raw records:
  - `results/search_log.jsonl`, algorithm
    `kraft-adaptive-tiebreak-half-depth<cap>-v1`.
  - `results/checkpoints/kraft_adaptive/stage1_depth<cap>_*`.
  - `results/kraft_adaptive/stage1_depth<cap>.v`.

| Cap | Mean | SD | Median | p1 | p10 | Best (seed) | Against baseline: shift, z | Against slack variant: shift, z |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 7 | 458.45 | 4.34 | 458 | 448 | 453 | 445 (260,301) | +2.41, z = +16.01 | +0.10, z = +0.82 (n = 1,000) |
| 6 | 485.46 | 5.46 | 485 | 472 | 478 | 468 (280,995) | −4.97, z = −25.65 | −0.03, z = −0.06 (n = 11,000) |

- **Cap-6 low tail:** 468 ×1, 469 ×2, 470 ×3. The 468 (seed 280,995) has
  maximum fanout 6 and excess fanout 20.
- **H1 refuted.** Both conditions failed. Against the slack variant, z = +0.82
  where z ≤ −3 was needed. Against the baseline, z = +16.01 where z < +3 was
  needed.
- **H2 confirmed.** Against the slack variant at cap 6, z = −0.06 < +3.
- **Stage-2 rule, as pre-registered:**
  - Cap 7: z = +16.01 against the baseline, so not triggered. H3 at cap 7 is
    **not tested**.
  - Cap 6: z = −0.06 against the slack variant, so triggered: seeds
    281,000–290,999.

**Stage 2 (cap 6).**
- Command:
  `python3 -m optimizer.kraft_adaptive --stage stage2 --depth-cap 6 --workers 16`
- Code: the commit that records these stage-1 results. It changes no code
  after `6e1b731`.
- Run: 2026-10-27, 20:39:12–20:55:03 UTC, at `5db74e9`. **It stopped early,
  after 3,862 of 10,000 seeds.**
  - The search exited with status 1:
    `Adaptive search failed: no depth-feasible pair; Kraft invariant broken`.
  - The failing trial is seed **284,862**, the first seed missing from the
    contiguous logged prefix 281,000–284,861.
  - It was reproduced in a separate worktree at `5db74e9`. The seed raises
    the same RuntimeError under this variant *and* under the slack variant
    (`search_seed_slack(284862, 6)`), which shares the finishing code. The
    baseline completes the same seed.
  - The run was not resumed. Trials are deterministic, so a resume would hit
    the same seed again.
- **Where the raw records are:**
  - The log records went to `results/search_log.jsonl`. On 2026-10-27 they
    moved unchanged into `results/search_logs/kraft_adaptive_tiebreak.jsonl`.
  - Checkpoint: `results/checkpoints/kraft_adaptive/stage2_depth6_search.json`
    (`status: running`, 3,862 completed).
  - Incumbents: `results/checkpoints/kraft_adaptive/stage2_depth6_incumbents/`.
  - The run never wrote its final artifact (`results/kraft_adaptive/stage2_depth6.v`),
    because it stopped first.

Results over the 3,862 completed seeds (281,000–284,861), all verified and all
at depth ≤ 6:

| Run | n | Mean | SD | Median | p1 | p10 | Best |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive stage 2 (incomplete) | 3,862 | 485.51 | 5.25 | 486 | 473 | 479 | **466** |
| slack variant, cap 6 | 11,000 | 485.49 | 5.28 | 486 | — | — | 467 |

- Against the slack variant: z = +0.28.
- Low tail: 466 ×1, 467 ×1, 468 ×2, 469 ×2, 470 ×4.

**The 466 network.**
- Seed 281,125. Its file is
  `results/checkpoints/kraft_adaptive/stage2_depth6_incumbents/seed_281125.v`.
- Metrics: 466 XOR2, depth 6, maximum fanout 6, excess fanout 20, total
  fanout 964.
- It was re-verified separately. It replays byte for byte from its seed,
  passes 97 exact vectors and 100,000 random vectors, and Yosys/SMTBMC/Z3
  proves it equivalent.
- **It dominates Candidate C** (470, 6, 6, 20, 972) on every recorded
  objective.
- It also dominates the 467 (fanout 7) and the 468 (seed 249,452) from the
  slack variant.

**Hypothesis outcomes.**
- **H1 refuted.** This was settled at stage 1.
- **H2 confirmed.** This was settled at stage 1.
- **H3 confirmed at cap 6, with the run incomplete.** The pre-registered
  condition was "≤ 466 XOR2 within 10,000 stage-2 seeds". It was met at seed
  281,125, inside the 3,862 seeds that did run. A verified circuit's
  existence does not depend on the unrun seeds. The run's distribution
  statistics, however, cover only 3,862 seeds.
- **H3 at cap 7 not tested**, because stage 2 was not triggered there.

## Interpretation

Everything below is inference.

- **At θ = 1/2 the adaptive rule is indistinguishable from the slack
  variant at both caps.**
  - Cap 7: z = +0.82 against the slack variant.
  - Cap 6: z = −0.06 at stage 1 and z = +0.28 at stage 2.
- **At cap 7 it keeps the slack variant's 2.4-gate loss.** The rule behaves
  exactly like the baseline while no row is tight, so that loss is probably
  not made in the early phase. It is probably made in late moves or in the
  finishing pass, once rows are tight. This is untested.
- **At cap 6 the 466 is a tail draw from the slack-family distribution.** It
  is not evidence that the adaptive rule is better. Across 14,862 seeds of
  this family at cap 6 (11,000 slack and 3,862 adaptive), one 466 and two
  467s were found.
- **The trial failure is a latent bug in the slack-family finishing pass.**
  - It also hits the slack variant. It was simply not reached in that
    variant's 11,000 seeds.
  - The error message blames the Kraft invariant. The likely real cause:
    every feasible merge in the row being finished produces a vector that
    already exists as a deeper signal. The deduplicating `_target` then
    reports that deeper depth, so no pair fits.
  - The baseline shares the same code path but never hit the case in any of
    its recorded trials. This is undiagnosed.

## Next decision

- **Needs a decision by the project owner, not taken here.** Adopting the
  verified **466-gate depth-6 network**, which dominates C, on the frontier.
  It is better than every other depth-6 candidate found so far.
- **Required before any further slack-family run:** fix the finishing-pass
  failure on seed 284,862. For example, create a fresh gate when the existing
  signal for a vector is too deep. The fix must carry a regression test on
  that seed. Any run after the fix is a new algorithm version (`v2`) with its
  own record. The aborted stage 2 is not resumed.
- **Ruled out:** θ = 1/2 as a fix for cap 7. Other θ values were not tried,
  by design.
- **Not recommended:** further tie-break variants. The tie-break has been
  shown to carry the effect. The remaining cap-7 loss sits in the late or
  finishing phase.

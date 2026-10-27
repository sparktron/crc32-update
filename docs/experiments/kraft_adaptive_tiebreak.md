# Experiment: a cap-adaptive (tight-row) Kraft-slack tie-break

**Status:** pre-registered 2026-10-27, before any code for this variant was
written or run.

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

Not run yet.

## Interpretation

Not run yet.

## Next decision

Not run yet.

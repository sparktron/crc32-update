# Experiment: a Kraft-slack tie-break in the Kraft-bounded search

**Status:** pre-registered 2026-10-27, before any code for this variant was
written or run. Completed 2026-10-27.
- **H1 refuted:** cap 6 improved but cap 7 got worse.
- **H2 confirmed at cap 6:** 467 XOR2 at depth 6. H2 was not tested at
  cap 7.

**Motivation.** In `docs/experiments/ablation_toward_dclo.md`, replacing the
baseline's depth-aware tie-break with a uniform choice explained about 90–95%
of DCLO's deficit (+4.81 XOR2 mean at cap 7, +8.01 at cap 6). If the
tie-break matters that much, a tie-break aimed more directly at the depth
budget might do better than the baseline.

## The variant

The baseline (`kraft-bounded-bp-cse` v1) breaks frequency ties by:
1. the new gate's depth,
2. the result's weight,
3. the pair itself.

The variant inserts one key ahead of those: the **Kraft slack used**. For a
pair (a, b), that is the total increase in Kraft sum over every row the move
would be applied to:

    cost(a, b) = Σ over feasible rows containing a and b of (K_after − K_before)

- For a new gate this equals 2^(1+max(d_a, d_b)) − 2^d_a − 2^d_b per row. It
  is 0 for equal-depth inputs and positive otherwise.
- For a reuse of an existing signal, it is computed with `_kraft_after`, as
  in the baseline.

Lower cost is preferred. Ties fall back to the baseline's keys in their
original order. Everything else is unchanged in both phases:
- the frequency pools, the slack-pool rule, the weighted top-k sampling,
- the reuse and rewrite rules, the finishing order, and the RNG calls.

The new key goes first in both the sharing phase's pool ordering and the
finishing phase's pair ordering.

An example of where it differs from the baseline: merging two depth-2
signals gives a depth-3 gate at zero cost, while merging depth 0 and depth 1
gives a depth-2 gate at cost 1. The baseline prefers the shallower depth-2
gate; the variant prefers the zero-cost merge.

## Hypotheses

- **H1 (primary).** The slack tie-break lowers the mean XOR2 compared with
  the baseline at both caps: Mann–Whitney normal approximation, tie-corrected,
  z ≤ −3, comparing 1,000 variant seeds with the baseline's 10,000 seeds at
  each cap.
  - **Refuted by** z > −3 at either cap.
- **H2 (the target).** Within 10,000 seeds at a cap, the variant finds
  ≤ 440 XOR2 at depth ≤ 7 or ≤ 469 at depth ≤ 6. That beats the recorded B7
  (441) or C (470).
  - **Refuted by** bests ≥ 441 and ≥ 470.
  - H2 is tested only at caps that reach stage 2 (below). At a cap that does
    not, H2 is recorded as *not tested*, not as refuted.

**Context, not a target.** An ablation-arm circuit with 440 XOR2 at depth 7
(seed 160,832, `results/ablation/rewrite_depth7.v`) was verified on
2026-10-27. Its 10,000-seed follow-up was still running when this record was
written. Variant results are also reported against 440.

## Stages, decided now

- **Stage 1:** 1,000 seeds per cap; this tests H1.
- **Stage 2:** at each cap where the stage-1 mean is significantly lower
  (z ≤ −3), 10,000 more seeds at that cap; this tests H2. At other caps, no
  extension.

**Determinism gate, checked before any stage runs.** With the slack key
switched off, the variant code must reproduce `search_seed_bounded` byte for
byte:
- the B7 (seed 40,505) and C (seed 56,140) incumbents, and
- the first 20 logged seeds of each baseline budget.

## Configuration

| Stage | Cap 7 seeds | Cap 6 seeds |
| --- | --- | --- |
| 1 | 220,000–220,999 | 240,000–240,999 |
| 2 (if triggered) | 221,000–230,999 | 241,000–250,999 |

These ranges are disjoint from every logged range and from the running
follow-up (200,000–209,999).

- Algorithm name: `kraft-slack-tiebreak-depth<cap>-v1`.
- Driver: `optimizer.depth_bounded.run_bounded_search`, with the same
  verification, logging, checkpoint and resume as the recorded budgets.
- Verification: `independently_check` on every trial. Every improving
  incumbent also gets 97 exact vectors, 100,000 random vectors (seed
  0xC32A5EED) and formal equivalence.
- Run names: `stage1_depth<cap>` and `stage2_depth<cap>`, giving:
  - `results/checkpoints/kraft_slack/<run>_search.json`
  - `results/checkpoints/kraft_slack/<run>_incumbents/`
  - `results/kraft_slack/<run>.v`
- Exact commands, run from the repository root. Each takes the search-log
  lock and resumes from its checkpoint.

```bash
python3 -m optimizer.kraft_slack --stage stage1 --depth-cap 7 --workers 16
python3 -m optimizer.kraft_slack --stage stage1 --depth-cap 6 --workers 16
# Stage 2, only at a cap whose stage-1 z <= -3:
python3 -m optimizer.kraft_slack --stage stage2 --depth-cap <cap> --workers 16
```

## Baselines

These come from the recorded logs:

| Run | Seeds | Mean | SD | Median | p1 | Best |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| baseline cap 7 | 40,000–49,999 | 456.05 | 4.29 | 456 | 446 | 441 |
| baseline cap 6 | 50,000–59,999 | 490.43 | 5.24 | 490 | 478 | 470 |
| ablation `tiebreak` (uniform), cap 7 | 100,000–100,999 | 460.86 | 4.43 | 461 | 450 | 445 |
| ablation `tiebreak` (uniform), cap 6 | 110,000–110,999 | 498.44 | 5.12 | 498 | 487 | 483 |

## Code version and environment

- **Code:** commit `3281250`, which adds `optimizer/kraft_slack.py`, on
  branch `crczero-verification`.
  - `python3 -m unittest optimizer.test_kraft_slack` passed: 5 tests.
  - Stage 1 starts only after the running ablation follow-up has finished
    and been committed. The tree is then clean except for an untracked
    `docs/reviews/` directory, which this experiment did not create and does
    not read.
- **Determinism gate, passed before any stage ran:**
  - With `use_slack=False`, seeds 40,000–40,019 (cap 7), 50,000–50,019
    (cap 6) and the B7 and C seeds render identically to
    `search_seed_bounded`, 42 of 42. Their metrics equal the logged records.
  - The B7 and C incumbents reproduce byte for byte.
- **Smoke trials:** seeds 1–3 at each cap, which are not in any budget. They
  checked correctness and timing only, at about 5–7 s per trial with the CPU
  shared. Because they are not evidence, their values are not recorded here.
- **Environment:** as in `dclo_depth_bounded.md`.
  - Python 3.10.12, i9-10900K, Yosys 0.9, Z3 4.8.12.
  - 16 workers. Trials are deterministic per seed.

## Observed

**Stage 1.**
- Run: 2026-10-27, 19:16:14–19:24:58 UTC, at code `a1e0493`, with a clean
  tree apart from the untracked `docs/reviews/`.
- Both caps completed 1,000 contiguous seeds. Every record has
  `verification_passed: true`, and every trial met its cap.
- Raw records:
  - `results/search_log.jsonl`, algorithm `kraft-slack-tiebreak-depth<cap>-v1`.
  - `results/checkpoints/kraft_slack/stage1_depth<cap>_*`.
  - `results/kraft_slack/stage1_depth<cap>.v`.

Shift is the stage-1 mean minus the baseline's 10,000-seed mean. z is against
those 10,000 seeds.

| Cap | Mean | Shift | z | SD | Median | p1 | p10 | Best (seed) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 7 | 458.36 | **+2.31** | +15.04 | 4.32 | 458 | 449 | 453 | 445 (220,445) |
| 6 | 485.38 | **−5.05** | −26.20 | 5.35 | 485 | 474 | 478 | 470 (240,289) |

- **Cap-6 best (seed 240,289):** 470 XOR2, maximum fanout 6, excess fanout
  24. Candidate C (470, fanout 6, excess 20) still dominates it on excess
  fanout.
- **H1 refuted.** It required z ≤ −3 at both caps. Cap 7 moved the wrong way,
  z = +15.0.
- **Stage-2 rule, as pre-registered:**
  - Triggered at cap 6 (z = −26.2): seeds 241,000–250,999.
  - Not triggered at cap 7, so H2 at cap 7 is **not tested**.
- The cap-6 stage-2 command and code are recorded below before it starts.

**Stage 2 (cap 6).**
- Command:
  `python3 -m optimizer.kraft_slack --stage stage2 --depth-cap 6 --workers 16`
- Code: the commit that records these stage-1 results. It changes no code
  after `3281250`.
- Run: 2026-10-27, 19:25:35–20:06:09 UTC, at `6e7bf3d`. It completed
  10,000 contiguous seeds, every record verified, and every trial at
  depth ≤ 6.
- Raw records:
  - `results/search_log.jsonl`.
  - `results/checkpoints/kraft_slack/stage2_depth6_*`.
  - `results/kraft_slack/stage2_depth6.v`, the best network.
  - `results/kraft_slack/notable/`: two non-incumbent networks that
    dominate C, saved after the run by replaying their seeds.

| Run | Seeds | Mean | SD | Median | p1 | p10 | Best |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Kraft-slack, stage 2 | 241,000–250,999 | 485.50 | 5.28 | 486 | 473 | 479 | **467** |
| baseline cap 6 | 50,000–59,999 | 490.43 | 5.24 | 490 | 478 | 484 | 470 |

**Low tail, by XOR2 value.**
- Kraft-slack: 467 ×1, 468 ×4, 469 ×12, 470 ×10, 471 ×21, 472 ×34. That is
  **17 seeds at 469 or fewer**.
- Baseline: 470 ×1, 472 ×4. That is 0 seeds at 469 or fewer.

**Networks re-verified separately.** Each replays byte for byte from its
seed, passes 97 exact vectors and 100,000 random vectors, and is proved
equivalent by Yosys/SMTBMC/Z3.

| Seed | XOR2 | Depth | Max fanout | Excess > 4 | Total fanout | Compared with C (470, 6, 6, 20, 972) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 246,653 | **467** | 6 | 7 | 20 | 966 | fewer gates, higher maximum fanout; neither dominates |
| 249,452 | 468 | 6 | 6 | 20 | 968 | **dominates C** |
| 248,720 | 469 | 6 | 5 | 17 | 970 | **dominates C** |

**Hypothesis outcomes.**
- **H1 refuted**, because cap 7 got worse. This was settled at stage 1.
- **H2 confirmed at cap 6.** The best is 467, which is ≤ 469.
- **H2 at cap 7 not tested**, because stage 2 was not triggered there.

## Interpretation

Everything below is inference.

- **At cap 6, the slack key is a real improvement, not a tail draw.**
  - The whole distribution moved about 5 gates lower. The stage-1 and
    stage-2 means agree (485.38 and 485.50).
  - 17 of 10,000 seeds beat 470, against none of the baseline's 10,000.
- **At cap 7, the same key hurts by about 2.3 gates.**
  - A plausible but untested reason is the depth budget. With one more
    level of slack, it rarely binds early at cap 7. Preferring zero-cost
    merges then builds deeper gates (for example 2+2 → 3) earlier than the
    baseline's shallow-first rule would. That may close off sharing
    opportunities that only fit while gates stay shallow.
  - At cap 6 the budget binds from the start, so spending it carefully pays.
- **The best tie-break seems to depend on how tight the cap is.** A rule
  that switches on how much slack is left, such as the slack key only once
  rows are near their Kraft limit, might keep the cap-6 gain without the
  cap-7 loss. This is untested.
- **What the circuits show.** The 467, 468 and 469 networks show that
  verified depth-6 circuits below 470 gates exist. Unlike the 440 in the
  ablation, they come from a method whose whole distribution is lower.

## Next decision

- **Needs a decision by the project owner, not taken here.** These are
  frontier changes, which touch `report.md`, `STATUS.md` and the
  `build_results` submission set.
  - `SPEC.md` Section 4 defines Candidate C as minimum depth, then minimum
    XOR2. By that definition the 467-gate network
    (`results/kraft_slack/stage2_depth6.v`) would become Candidate C.
  - On the Pareto frontier:
    - The 468 (seed 249,452) and 469 (seed 248,720) networks each dominate
      the current C.
    - The 467 and the 469/fanout-5 networks are both non-dominated.
- **Not tested:**
  - H2 at cap 7.
  - A cap-adaptive tie-break.
- **Recommended next experiment:** a tie-break that switches from depth-first
  to slack-first as rows approach their Kraft limit, run at both caps.
- **Ruled out:** the slack key as a drop-in replacement at cap 7. Its mean is
  worse there (z = +15.0).

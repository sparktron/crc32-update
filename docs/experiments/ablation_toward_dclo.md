# Experiment: ablating the Kraft-bounded baseline toward DCLO

**Status:** pre-registered 2026-10-27, before any ablation code was written or
run.

**Background.** In `docs/experiments/dclo_depth_bounded.md`, DCLO did worse
than the Kraft-bounded baseline (`kraft-bounded-bp-cse` v1) over 10,000 seeds
per cap:
- Mean +5.37 XOR2 at cap 7 (461.42 against 456.05).
- Mean +8.47 at cap 6 (498.90 against 490.43).

The two algorithms differ in four components. This experiment switches each
one in the baseline to its DCLO form, one at a time, to find which carries the
baseline's advantage.

## Components

Each arm is the baseline (`optimizer/depth_bounded.py`, unchanged) with
exactly one component switched. Everything else, including the RNG and the
Kraft feasibility test, stays as in the baseline.

1. **`tiebreak`: depth-aware tie-break → uniform.**
   - Sharing phase: the baseline sorts equal-frequency pairs by new-gate
     depth, then result weight, then the pair, and samples from a weighted
     top-k list. The arm draws the frequency level exactly as the baseline
     would, then picks uniformly among all pool pairs at that level.
   - Finishing phase: the baseline picks among the first 4 of the
     depth-sorted best-frequency tier. The arm picks uniformly from the
     whole tier.
   - The order in which reuse rewrites are applied is unchanged; it belongs
     to component 4.
2. **`second_best`: second-tier rule → DCLO's.**
   - Baseline: with probability 1/4, when the top frequency is above 2, the
     pool also includes pairs one below the top.
   - Arm: with probability 0.02 the level is the second-largest frequency
     (when one exists), otherwise the largest. The pool is the pairs at that
     level, sampled with the baseline's depth-aware ordering and weighted
     top-k.
3. **`finish`: per-output finishing pass → DCLO's global greedy.**
   - After the sharing phase, the arm keeps running the baseline's selection
     loop (rewrites, then a gate choice) with pairs of frequency 1 allowed,
     until every row has weight 1.
   - The baseline's per-output, shuffled-order pass is skipped. If the loop
     stalls, because only infeasible reuse pairs remain, the remaining rows
     go to the baseline's finishing pass. Such fallbacks are counted and
     reported.
4. **`rewrite`: any-signal reuse → DCLO flips.**
   - New gates are never deduplicated by vector.
   - The baseline's rewrite step (any pair whose XOR equals any existing
     signal) is replaced by DCLO's flips over gate-input triples. A flip is
     made when it lowers the row's weight and keeps the Kraft test, as in
     `optimizer/dclo.py`.

**Control arm `all`:** all four components switched at once. Functionally this
should be DCLO, with a different RNG stream.

## Hypotheses

Comparisons use each arm's 1,000 seeds against the baseline's full 10,000
seeds at the same cap.

- **H1 (primary).** Switching only the tie-break (`tiebreak`) raises the mean
  XOR2 by at least half of DCLO's gap: at least +2.69 at cap 7 *and* at least
  +4.24 at cap 6.
  - **Refuted by** a mean shift below the threshold at either cap.
- **H2.** At each cap, `tiebreak` has the largest upward mean shift of the four
  single-component arms.
  - **Refuted by** any of `second_best`, `finish` or `rewrite` having a larger
    mean shift than `tiebreak` at either cap.

**Consistency check (not a hypothesis).** The `all` arm's mean should be within
±1.0 of DCLO's 10,000-seed mean at each cap (461.42 and 498.90). If it is not,
the decomposition or the implementation does not reproduce DCLO, and no
attribution conclusion will be drawn.

**Improvement rule, decided now.** An arm gets a separate follow-up run of
10,000 seeds if, at a cap, either condition holds:
- Its mean is significantly *lower* than the baseline's (Mann–Whitney normal
  approximation, z ≤ −3).
- Its best of 1,000 seeds is ≤ 440 at cap 7 or ≤ 469 at cap 6.

Otherwise there is no extension. With per-seed SDs of about 4.3–5.3, the
standard error of a 1,000-against-10,000 mean difference is about 0.15–0.17
gates, so the H1 thresholds are well resolved.

**Determinism gate, checked before any arm runs.** With no component switched,
the ablation code must reproduce `search_seed_bounded` byte-for-byte:
- the recorded B7 (seed 40,505) and C (seed 56,140) incumbents, and
- the first 20 logged seeds of each baseline budget.

## Configuration

Seed ranges are disjoint from each other and from every recorded budget. Each
range leaves room for a 10,000-seed extension.

| Arm | Cap 7 seeds | Cap 6 seeds |
| --- | --- | --- |
| `tiebreak` | 100,000–100,999 | 110,000–110,999 |
| `second_best` | 120,000–120,999 | 130,000–130,999 |
| `finish` | 140,000–140,999 | 150,000–150,999 |
| `rewrite` | 160,000–160,999 | 170,000–170,999 |
| `all` | 180,000–180,999 | 190,000–190,999 |

- Algorithm names: `ablation-<arm>-depth<cap>-v1`.
- Driver: `optimizer.depth_bounded.run_bounded_search` with the ablated trial,
  so verification, logging, checkpointing and resume are identical to the
  recorded budgets.
- Verification: every trial gets `independently_check`. Every improving
  incumbent also gets 97 exact vectors, 100,000 random vectors (seed
  0xC32A5EED) and formal equivalence.
- Log: `results/search_log.jsonl`.
- Checkpoints: `results/checkpoints/ablation/<arm>_depth<cap>_search.json`.
- Incumbents: `results/checkpoints/ablation/<arm>_depth<cap>_incumbents/`.
- Best artifacts: `results/ablation/<arm>_depth<cap>.v`.
- Exact commands, run from the repository root one after the other (each
  takes the search-log lock, and each resumes from its checkpoint):

```bash
for arm in tiebreak second_best finish rewrite all; do
  for cap in 7 6; do
    python3 -m optimizer.ablation --arm "$arm" --depth-cap "$cap" --seed-count 1000 --workers 16
  done
done
```

- **Finishing fallbacks:** counted after the run by replaying every seed of
  the `finish` and `all` arms with `optimizer.ablation.build_ablated` and
  reading `finish_fallback_rows`.

## Baselines

| Run | Seeds | Mean | SD | Median | p1 | Best |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| baseline cap 7 (all) | 40,000–49,999 | 456.05 | 4.29 | 456 | 446 | 441 |
| baseline cap 7 (first 1,000) | 40,000–40,999 | 455.91 | — | 456 | 446 | 441 |
| baseline cap 6 (all) | 50,000–59,999 | 490.43 | 5.24 | 490 | 478 | 470 |
| baseline cap 6 (first 1,000) | 50,000–50,999 | 490.51 | — | 491 | 478 | 472 |
| DCLO cap 7 (all) | 70,000–79,999 | 461.42 | 4.41 | 462 | 451 | 445 |
| DCLO cap 6 (all) | 80,000–89,999 | 498.90 | 5.34 | 499 | 486 | 477 |

The first-1,000-seed rows give a best-of-1,000 at an equal budget. B7's own
seed, 40,505, falls inside the first 1,000.

## Code version and environment

- **Code:** commit `fac8d3a` on branch `crczero-verification`, with a clean
  tree; this record is committed on top of it before the run.
  - `python3 -m unittest optimizer.test_ablation optimizer.test_dclo
    optimizer.test_depth_bounded` passed: 16 tests.
- **Determinism gate, passed before any arm ran:**
  - Arm `none` re-rendered seeds 40,000–40,019 (cap 7) and 50,000–50,019
    (cap 6), plus the B7 and C seeds. All 42 renders are identical to
    `search_seed_bounded`, and their metrics equal the logged records.
  - The B7 (seed 40,505) and C (seed 56,140) incumbents reproduce byte for
    byte.
- **Smoke trials:** one per arm and cap, at seed 1, which is not in any
  budget. These checked correctness and timing only, at about 1.6–3.5 s per
  trial.
- **Environment:** the same as `dclo_depth_bounded.md`.
  - Python 3.10.12, i9-10900K (10 cores, 20 threads), 31 GB RAM.
  - Yosys 0.9, yosys-smtbmc, Z3 4.8.12.
  - 16 workers. Trials are deterministic per seed, and the worker count
    does not affect results.

## Follow-up run (recorded before it starts)

**What triggered it.** The pre-registered improvement rule fired for one arm
and cap. The `rewrite` arm's best at cap 7 is 440 XOR2 (seed 160,832), which
meets the "≤ 440" condition. No arm met the z ≤ −3 condition. That 440
circuit was re-verified independently: it replays byte for byte, and passes
97 exact vectors, 100,000 random vectors and the formal proof.

**Configuration.**
- 10,000 *new* seeds, 200,000–209,999. The first 1,000 seeds are not
  re-counted, so the follow-up is an independent sample.
- Algorithm `ablation-rewrite-depth7-v1`; its seed range is disjoint from
  every logged range.
- Run name `rewrite_depth7_followup`, which gives:
  - `results/checkpoints/ablation/rewrite_depth7_followup_search.json`
  - `results/checkpoints/ablation/rewrite_depth7_followup_incumbents/`
  - `results/ablation/rewrite_depth7_followup.v`
- Command:

```bash
python3 -m optimizer.ablation --arm rewrite --depth-cap 7 --seed-start 200000 --seed-count 10000 --workers 16 --run-name rewrite_depth7_followup
```

- Code: the commit that adds `--run-name` (recorded in the log message).
  It changes paths only, not the trial.

**Follow-up question.** Is 440 a property of the `rewrite` arm, or a tail
draw? This is not a new hypothesis. The 1,000-seed means already show no
significant shift (+0.18, z = 1.1). The follow-up reports the arm's best of
10,000 seeds and its distribution next to the baseline's.

## Observed

Not run yet.

## Interpretation

Not run yet.

## Next decision

Not run yet.

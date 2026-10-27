# Experiment: DCLO on the frozen 32×96 matrix at depth caps 6 and 7

**Status:** pre-registered 2026-10-27, before any DCLO trial was run.

## Hypothesis

A faithful implementation of DCLO (Boyar, Find and Peralta, *Small Low-Depth
Circuits for Cryptographic Applications*, Cryptogr. Commun. 11(1), 2019,
Sects. 3.4–3.6), given the same 10,000-seed budget per cap as the recorded
Kraft-bounded searches, finds a verified network with **at most 440 XOR2 at
depth ≤ 7** or **at most 469 XOR2 at depth ≤ 6**. That would improve on B7
(441) or Candidate C (470).

**Refuted by:** a best verified result of ≥ 441 XOR2 at cap 7 *and* ≥ 470 XOR2
at cap 6 after the full budgets.

**Secondary question (not the claim):** whether DCLO's per-seed distribution
sits lower or higher than the baseline's. This is compared by median and by
the 1st and 10th percentiles, because a best-of-10,000 result depends on a
single seed.

## What "faithful" means here

Source: [PMC6463518](https://pmc.ncbi.nlm.nih.gov/articles/PMC6463518/), read
2026-10-27. The paper describes DCLO as RAND-GREEDY-ALG plus three
improvements.

- **RAND-GREEDY-ALG (Sect. 3.4).**
  - Each output row lists the base signals still to be XORed.
  - A candidate gate is a pair of signals. Its *improvement* is the number
    of rows that contain both signals and stay feasible after the update.
  - The next gate is chosen uniformly at random among the pairs with the
    largest improvement, and it is applied to every row where it is
    feasible.
- **Feasibility (Sect. 3.5, FEASIBLE).** The paper repeatedly merges the two
  lowest depths. That is equivalent to the Kraft test Σ 2^d_i ≤ 2^D used by
  `optimizer/depth_bounded.py`, so the same test is reused.
- **Preprocessing (Sect. 3.6).** If an output is the XOR of two other outputs,
  it is computed with one gate at the end. **Not applicable:** no pair of
  rows of the frozen matrix XORs to a third row (checked 2026-10-27), so this
  improvement is a no-op here.
- **Flips / Generalized Paar Operation (Sect. 3.6).**
  - For an existing gate c = c1 ⊕ c2, a flip toggles c, c1 and c2 in a row.
    It is done when the row's weight decreases, which happens when the row
    holds exactly two of the three (−1) or all three (−3).
  - The paper's footnote relaxes the weight condition in the authors' code
    but does not say how, so only the stated rule is implemented.
  - Flips are applied only when the row stays Kraft-feasible. The paper
    states no depth check for flips, but without one a flip could make an
    output miss its cap.
- **Second-best pairs (Sect. 3.6).** With probability 2%, the pair is chosen
  uniformly among those with the second-largest improvement.

The paper does not say when flips are applied. Here they run to exhaustion
before every gate choice, picking uniformly among the flips with the
largest weight decrease.

How this differs from the baseline (`kraft-bounded-bp-cse` v1):
- The baseline breaks ties by depth and vector weight and samples from a
  weighted top-12 list. DCLO breaks ties uniformly at random.
- The baseline takes a second-best pool about 25% of the time; DCLO, 2%.
- The baseline finishes each output with a separate per-output pass in
  shuffled order. DCLO runs the same greedy rule until every row has
  weight 1.
- The baseline's rewrite step uses any pair whose XOR equals any existing
  signal. DCLO flips only within gate-input triples.

## Configuration

- Algorithm names: `dclo-kraft-depth7-v1` and `dclo-kraft-depth6-v1`.
- Seed ranges, disjoint from every recorded budget:
  - cap 7: seeds 70,000–79,999
  - cap 6: seeds 80,000–89,999
- Verification and acceptance are the same as the recorded bounded budgets.
  - Every trial is checked by `independently_check`, which runs a GF(2)
    matrix check and the restricted netlist metrics.
  - Every improving incumbent also gets 97 exact vectors, 100,000 random
    vectors (seed 0xC32A5EED) and formal equivalence.
  - Score order: XOR2, depth, maximum fanout, excess fanout, seed.
- Log: `results/search_log.jsonl`, which is the canonical, CI-validated log.
- Checkpoints: `results/checkpoints/depth{6,7}_dclo_search.json`.
- Incumbents: `results/checkpoints/depth{6,7}_dclo_incumbents/`.
- Best artifacts: `results/phase7/candidate_depth{6,7}_dclo.v`.
- Exact commands, run from the repository root. Each takes the search-log
  lock, so they run one after the other. Each resumes from its checkpoint if
  interrupted.

```bash
python3 -m optimizer.dclo --depth-cap 7 --seed-count 10000 --workers 16
python3 -m optimizer.dclo --depth-cap 6 --seed-count 10000 --workers 16
```

- Other arguments are left at their defaults: seed start from
  `RECORDED_SEED_STARTS`, 100,000 random vectors, random seed 0xC32A5EED,
  and the default checkpoint, incumbent and artifact paths listed above.
- Each trial is deterministic in its seed. Results do not depend on the
  worker count or scheduling: workers only parallelize independent seeds, and
  the driver consumes results in seed order.

## Baselines

These come from the recorded logs, with 10,000 seeds per budget:

| Budget | Seeds | Best | p1 | p10 | Median | Mean | Max | Mean runtime |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `kraft-bounded-bp-cse-depth7-v1` (B7) | 40,000–49,999 | 441 | 446 | 450 | 456 | 456.05 | 472 | 4.84 s |
| `kraft-bounded-bp-cse-depth6-v1` (C) | 50,000–59,999 | 470 | 478 | 484 | 490 | 490.43 | 510 | 3.47 s |

In each budget, only one seed reached the best value.

## Code version and environment

- Code: commit `a8b7ca0` ("Add a DCLO depth-capped search over the frozen
  matrix") on branch `crczero-verification`.
  - The tree was clean apart from this untracked record, which is committed
    before the run.
  - `python3 -m unittest optimizer.test_dclo optimizer.test_depth_bounded`
    passed: 11 tests.
- Pilot before pre-registration: one seed per cap (70,000 at cap 7, 80,000 at
  cap 6), run only to check correctness and timing. They gave 456 XOR2 at
  depth 7 and 499 at depth 6, in about 1 s each. These seeds are part of the
  budgets and are re-run there.
- Environment:
  - Linux 6.8.0, Python 3.10.12.
  - Intel Core i9-10900K (10 cores, 20 threads), 31 GB RAM.
  - Formal toolchain: Yosys 0.9 (git 1979e0b) with yosys-smtbmc and Z3
    4.8.12, the same toolchain as the recorded budgets.

## Observed

Not run yet.

## Interpretation

Not run yet.

## Next decision

Not run yet.

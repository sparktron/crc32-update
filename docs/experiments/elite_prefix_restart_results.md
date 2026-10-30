# Results: elite-prefix restarts

Completed 2026-10-28. Frozen protocol: [elite_prefix_restart.md](elite_prefix_restart.md).
Implementation/preregistration: `5bacbb29f39276115aa14a5966fb726b0ccb4bbe`.
Branch: `claude/elite-prefix-restart`, PR #14 against `master`, stacked on
PR #13 (`9798c23`, the lookahead results).

## Observed

All 18 budgets completed: **20,000 unique, independently checked trials**,
every one within its depth cap, and **124 fully verified incumbent
acceptances** (63 at cap 7, 61 at cap 6). Seeds were 500000..509999 (cap 7)
and 520000..529999 (cap 6) in the frozen layout. The run manifest records
`5bacbb2`; tracked sources were clean at start, and the only untracked file
was the new progress log. Stage 1 re-derived the parent table byte for byte
before the first trial. No threshold, arm, parent or seed changed.

The first and last trial records span 22:17:44..23:37:16 UTC (79.5 minutes
of logging, including acceptance proofs; the estimate was 71). The sum of
worker elapsed times is 21.15 worker-hours, which includes contention and is
not measured CPU time. Concurrent work during collection: the PR #14 review
fix ran the lookahead audit (about 4 minutes, `nice 19`) and 11 regression
tests (about 96 seconds). Runtime is descriptive only. Mean worker time per
trial was flat across arms: 3.40–3.70 s at cap 7 and 4.02–4.21 s at cap 6.

### H8 at the primary fraction (f = 50)

| Cap | Elite children | Median children | Fresh |
| --- | --- | --- | --- |
| 7 | 446.97 (SD 3.52, clustered SE 0.57) | 455.68 (3.28, 0.47) | 456.13 (4.19, 0.09) |
| 6 | 472.26 (SD 4.18, clustered SE 0.71) | 485.87 (3.49, 0.43) | 485.46 (5.24, 0.12) |

| Cap | Contrast | Mean | SE | Approx. 95% interval | z |
| --- | --- | ---: | ---: | --- | ---: |
| 7 | elite − fresh | −9.16 | 0.58 | [−10.28, −8.03] | −15.9 |
| 7 | elite − median | −8.70 | 0.74 | [−10.15, −7.26] | −11.8 |
| 6 | elite − fresh | −13.20 | 0.72 | [−14.62, −11.79] | −18.3 |
| 6 | elite − median | −13.61 | 0.83 | [−15.24, −11.98] | −16.4 |

**H8 is confirmed at both caps** under the frozen rule: both contrasts are
at most −2.0 gates with z <= −3. The fresh arms reproduce the historical
control means (456.05 and 485.47 over the parent pools).

### All fractions (descriptive)

Elite parents average 442.20 (cap 7) and 468.40 (cap 6); median parents are
456 and 485. Slope is the least-squares slope of child mean on parent count
over all 40 parents.

| Cap | f | Elite mean | Median mean | Elite − fresh (z) | Median − fresh (z) | Slope |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| 7 | 25 | 453.51 | 455.83 | −2.62 (−5.6) | −0.30 (−0.7) | 0.17 |
| 7 | 50 | 446.97 | 455.68 | −9.16 (−15.9) | −0.45 (−0.9) | 0.64 |
| 7 | 75 | 443.14 | 455.64 | −12.99 (−33.4) | −0.49 (−1.4) | 0.91 |
| 7 | 100 | 442.20 | 456.00 | −13.93 (−50.8) | −0.13 (−1.4) | 1.00 |
| 6 | 25 | 481.35 | 485.37 | −4.12 (−8.3) | −0.10 (−0.2) | 0.25 |
| 6 | 50 | 472.26 | 485.87 | −13.20 (−18.3) | +0.41 (+0.9) | 0.82 |
| 6 | 75 | 469.05 | 485.48 | −16.42 (−33.3) | +0.01 (+0.0) | 0.99 |
| 6 | 100 | 468.40 | 485.00 | −17.06 (−44.4) | −0.46 (−4.0) | 1.00 |

- At f = 100 all 4,000 children (both groups, both caps) have exactly their
  parent's gate count. Redrawing only the finishing RNG never changed a
  gate count, consistent with the phase-isolation result.
- Replaying an unselected (median) prefix changes nothing: median − fresh is
  within ±0.5 gates with |z| <= 1.4 everywhere except cap 6, f = 100. There
  the children equal their parents (485, the pool's lower median), and the
  −0.46 reflects that selection against a fresh mean of 485.46.
- The early quarter carries little: slopes are 0.17 and 0.25 at f = 25.

### Phase diagnostics

Mean sharing decisions equal mean retained sharing gates. Mean retained
finishing gates fall as more of an elite prefix is kept:

| Cap | Arm | Sharing | Finishing |
| --- | --- | ---: | ---: |
| 7 | fresh | 182.0 | 274.1 |
| 7 | elite f50 / f75 / f100 | 184.5 / 188.1 / 189.0 | 262.5 / 255.1 / 253.2 |
| 6 | fresh | 165.0 | 320.5 |
| 6 | elite f50 / f75 / f100 | 168.9 / 171.6 / 172.2 | 303.3 / 297.5 / 296.2 |

Elite trajectories spend a few more gates in sharing and save many more in
finishing, the same pattern as cap-6 slack scoring in phase isolation.

### Best circuits and existence targets

Both existence targets were met, only in elite arms. Fresh and median arms'
bests were 442/443 at cap 7 and 469/469 at cap 6.

- **Depth 7, <=437:** four children reached 437, none lower. All are f = 75
  children of seed 400800 (the 438). Two were accepted and fully verified:
  seed **502021** (437 XOR2, maximum fanout 5, total fanout 906, excess
  fanout above four **2**) and seed 502008 (437, fanout 5, excess 4).
  Seeds 502034 and 502041 (437; excess 4 and 2) passed the per-trial
  structural and exact checks only.
- **Depth 6, <=461:** 13 children. Three reached **460**: 522004, 522007
  and 522027, all f = 75 children of seed 320099 (the 462). Seed **522004**
  (460, maximum fanout 6, total fanout 952, excess 19) was accepted and
  fully verified, as was 521005 (461, fanout 6, excess 17). At f = 50,
  children of three other elite parents also reached 461: 249452 (468),
  244690 (468) and 247584 (469). Seeds 522005 and 522032 are 461-gate
  depth-6 circuits with **maximum fanout 5** (excess 20 and 19); they passed
  only the per-trial structural and exact checks.

Best artifacts: `results/elite_prefix/stage1_elite_f75_depth7.v` (seed
502021) and `results/elite_prefix/stage1_elite_f75_depth6.v` (seed 522004).

Against the submitted frontier (A/B 439 at depth 8, fanout 5, excess 5; B7
440 at depth 7, fanout 5, excess 3; C 465 at depth 6, fanout 6, excess 19),
the 437 is no worse on all four objectives than A, B and B7 and better on
gates, and the 460 is likewise against C. The submitted frontier, metrics
and report are unchanged; integration is separate work (see below).

## Verification and evidence

Raw records: `results/search_logs/elite_prefix.jsonl`. Checkpoints and all
retained incumbents: `results/checkpoints/elite_prefix/`. Per-arm best
artifacts, diagnostics, `stage1_summary.json`, `run_manifest.json` and the
progress log: `results/elite_prefix/`.

- Before collection: 7 elite-prefix tests and the full suite (108 tests)
  passed, and `--stage select` reproduced `parents.json` byte for byte
  (`preflight_tests.log`). Every parent replayed its logged final metrics.
- All 20,000 trials passed independent structural and exact checks within
  their caps. All 124 incumbent acceptances passed 97 exact vectors, 100000
  random vectors (seed 0xC32A5EED) and Yosys/SMTBMC/Z3 formal equivalence;
  each accepted artifact has a proved formal target in `stage1_progress.log`.
- Post-collection audit, `python3 -B -m scripts.audit_elite_prefix`, run in a
  detached checkout of `5bacbb2` with the evidence copied in
  (`audit_progress.log`, `validation_summary.json`). **Passed:** frozen
  source set and hashes; unique IDs and full seed coverage; phase gate sums,
  depth bounds, nonnegative Kraft budgets; every child's parent, prefix
  length and prefix-state digest against the committed table; all 124
  incumbents replayed byte for byte. The completed stage-1 command replayed
  with no new trials and left all 182 evidence files byte-identical
  (`stage1_completed_replay.log`). All 18 best artifacts were rechecked on
  97 exact and 100000 random vectors and formally proved again, including
  the 437 and the 460 (`stage1_*_verification.json`).
- The first audit attempt ran every check above successfully, then stopped
  in the copy-back step. The helper compared its snapshot of
  `audit_progress.log` with the live log, which the audit itself was still
  writing. The helper now compares against the copied-in bytes, with a
  regression test, and the audit was re-run in full.
- `python3 -B -m unittest discover`: **111 tests passed** in 193.4 s
  (`regression_tests.log`).
- `python3 -B -m verifier.build_results --check --require-spec-minimum`:
  passed. The unchanged submitted circuits were re-proved, confirming three
  distinct Pareto circuits from five submitted classes
  (`submitted_provenance_check.log`).
- Full clean-clone rebuild was not repeated in this session. CI results are
  not inferred from local results.

## Interpretation

Everything in this section is inference.

- A trial's final gate count is largely inherited from its sharing prefix.
  Inheritance is weak after a quarter of the decisions (slope 0.17–0.25),
  strong at half (0.64–0.82) and nearly complete by three quarters
  (0.91–0.99). Finishing randomness contributes nothing to gate count.
- This fits the earlier pattern: scoring changes moved means by little while
  reshuffling most per-seed outcomes. A changed decision re-randomizes the
  rest of the trajectory, and no tested score systematically chose better
  mid-phase states.
- Elite prefixes are an effective sampler for the tail. In 1,000 trials each,
  the f = 75 elite arms produced 437 and 460, below every previously logged
  trial at those caps (438 and 462). Most f = 75 and f = 100 children only
  reproduce their parents; the gains came from a few children slightly
  below them, and at f = 50 from children of ordinary 468–469 parents
  reaching 461, which shows exploration beyond the parent.
- This is a diagnostic, not a matched-compute method claim. Parents were
  selected on outcome from about 25,000 earlier trials, so a fair comparison
  must charge for producing the elite pool.

## Next decision

Per the frozen rule, H8 passed at both caps: preregister an iterated
elite-restart search at each cap against fresh seeds at matched compute,
with tail-rate and best-of-N endpoints on new seeds, including the cost of
building the elite pool. Descriptively, f = 50 explores beyond its parents
while keeping most of their quality, and f = 75 gives the lowest means and
produced both bests; f = 25 keeps too little. That protocol must state its
fraction (or schedule) and the pool-refresh rule before results.

## Frontier integration (2026-10-29)

At the project owner's request, four elite-arm circuits became the submitted
frontier in `verifier/build_results.py`:

| Class | Seed | Arm | XOR2 | Depth | Max fanout | Excess >4 | Selection |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| A, B, B7 | 502021 | elite f = 75, depth 7 | 437 | 7 | 5 | 2 | budget incumbent |
| F4 | 500413 | elite f = 25, depth 7 | 445 | 7 | 4 | 0 | fewest XOR2 with fanout at most 4 |
| C | 522004 | elite f = 75, depth 6 | 460 | 6 | 6 | 19 | budget incumbent |
| C2 | 521005 | elite f = 50, depth 6 | 461 | 6 | 6 | 17 | budget incumbent |

- F4 is a new optional class, the fanout counterpart of Candidate B's depth
  bound. It is the fewest-gate trial with every fanout at most four in any
  log; the other three such trials have 449, 455 and 457 gates at depths 8–9.
- The Phase 4 A/B circuit (439, depth 8) stays submitted as A0 and B0,
  dominated, so the Candidate A search and Phase 5 study keep their checks.
- Each submission replays byte for byte through
  `optimizer.elite_prefix.replay_trial`, which rebuilds a logged trial from
  its arm and the committed parent table.
- Seeds 522005, 522032, 500413 and 521606 were fully verified before the
  choice (97 exact vectors, 100,000 random vectors, formal proof). Their
  netlists and reports are in `results/elite_prefix/notable/`. 522005
  (461/6/5/20) is dominated by 522032 (461/6/5/19). Neither 522032 nor 521606
  (463/6/5/14) reaches its budget's minimum gate count, so they would need a
  looser selection rule and were not submitted.

# CRC32 Superoptimization Status

Last updated: 2026-10-28

Current phase: Phase 6 — Final verification, comparison, and reporting complete

Current gate: G6 passed locally on 2026-10-24. The final report is in
`report.md`; all submitted artifacts, final metrics, provenance records, and
the three-circuit frontier agree. The recorded fresh-clone rebuild passed;
it was not repeated for this documentation-only closeout.

## Current Submitted Results

Candidate A is the best network found by the recorded 20,000-seed search. It is
not a claim of global optimality. The generated 1,390-XOR structural network
remains a Phase 1 validation fixture only, not a candidate or baseline.

Phase 4 completed its separate recorded Candidate A continuation over seeds
10,000 through 19,999 and its recorded Candidate B and Candidate C refinement
budgets.

The completed continuation logged 10,000 unique attempts. A prior overlapping
manual invocation created 7,125 duplicate records; they had identical outcomes
and were removed only after saving
`results/checkpoints/phase4_search_log_pre_dedup.jsonl`. The optimizer now
holds an exclusive checkpoint lock to reject overlapping invocations.

Candidate B and Candidate C starting points are recorded in
`results/phase4/candidate_starting_points.json` and the append-only search log.
Both passed structural, exact, 100,000-vector randomized, and formal checks.
Their refinements completed the configured 10,000-seed budgets for B
(20,000–29,999) and C (30,000–39,999), with no accepted improvement over the
verified starting incumbent in either class.

Phase 5's first 20-cone study is retained as an exploratory historical record,
but it counted shared fan-in nodes that cannot be removed during integration.
It is therefore not G5 evidence. The replacement v2 study cuts at shared
signals, counts only exclusively removable gates, and stores complete outcomes
in each append-only log record so resumed runs cannot discard prior results.

The v2 study (`phase5-exact-exclusive-cone-v2`) completed its 20-cone budget on
the Phase 4 refined Candidate B with a six-node cone limit, a 1,000 ms per-query
timeout, and Z3 4.8.12. Thirteen two- or three-gate cones returned UNSAT for a
strict gate reduction. The seven six-gate cones (roots n202, n226, n280, n294,
n309, n324, and n330) returned `unknown` at the timeout; these are not
certificates. Every attempt is logged with `accepted: false`. Outputs are in
`results/phase5/exact_exclusive_cone_study.json` and
`results/checkpoints/phase5_exact_exclusive_cones.json`. The UNSAT results apply
only to those single-cone encodings, not to the whole network. No Phase 5
replacement has been accepted or integrated.

| Candidate class | XOR2 count | Maximum depth | Verification | Status |
| --- | ---: | ---: | --- | --- |
| A — minimum gate-count search | 439 | 8 | Passed | Best found; seed 16,564 |
| B — depth at most 8 | 439 | 8 | Passed | Best found; no refinement improvement |
| C0 — Phase 4 minimum-depth starting point | 1,390 | 6 | Passed | Balanced-tree baseline; dominated by C |
| B7 — bounded depth at most 7 | 440 | 7 | Passed | Best found; seed 160,832, ablation `rewrite` arm (adopted 2026-10-27; was 441) |
| C — minimum-depth search (depth 6) | 465 | 6 | Passed | Submitted; seed 286,375 (adopted 2026-10-27). Research 462-gate witnesses have higher excess fanout; see below. |

Deterministic baseline metrics below were recomputed by the independent Phase 1
verifier. Runtime is the observed sum of generation, 100,000-vector
verification, and formal-equivalence time on the local toolchain.

| Network | XOR2 | Depth | Max fanout | Total fanout | Excess fanout >4 | Runtime (s) | Verification |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Independent per-output expansion | 1,390 | 51 | 20 | 2,812 | 1,038 | 4.805134 | Passed |
| Balanced per-output tree | 1,390 | 6 | 20 | 2,812 | 1,038 | 4.745530 | Passed |
| Greedy common-subexpression elimination | 454 | 9 | 6 | 940 | 11 | 3.868081 | Passed |
| Yosys/ABC normalized synthesis | 1,123 | 7 | 15 | 2,278 | 536 | 6.297098 | Passed |
| Candidate A (Phase 4, seed 16,564) | 439 | 8 | 5 | 910 | 5 | — | Passed |

`results/baseline_metrics.csv` contains every output-bit depth, intermediate and
alias counts, runtime components, exact/random vector counts, and formal status.

## Completed Work

- Frozen experiment semantics, circuit model, metrics, verifier requirements,
  search-log contract, and acceptance criteria are recorded in `SPEC.md`.
- Development phases and validation gates are recorded in `PLAN.md`.
- `results/search_log.jsonl` was initialized as an empty append-only log before
  optimization and now contains the completed Candidate A attempts.
- The repository README identifies the setup state and control documents.
- GitHub Actions CI validates required scaffolding, trailing whitespace, and the
  machine-readable search-log structure with read-only repository permissions.
- The metric model preserves separately instantiated XOR2 gates, resolving the
  conflict between structural merging and required fanout-aware duplication.
- The normative Python and independently written Verilog reference models use
  the frozen reflected IEEE CRC-32 semantics.
- The GF(2) generator builds the 32-by-96 transformation matrix in the frozen
  basis order and reproducibly emits an unoptimized structural validation
  fixture.
- The independent verifier parses the restricted XOR2 subset, propagates
  aliases, removes and reports unreachable nodes, preserves physical duplicate
  instances, evaluates networks, and recomputes every required metric.
- Exact all-zero plus 96 basis-vector checks, seeded bit-parallel randomized
  checks, and Yosys/ABC/Z3 formal equivalence are implemented.
- Deliberately malformed and functionally incorrect fixtures demonstrate
  nonzero verifier exits.
- GitHub Actions runs every Phase 1 acceptance command.
- Four deterministic baseline generators are implemented: serial independent
  equations, balanced no-sharing trees, greedy two-term CSE, and conventional
  Yosys/ABC synthesis normalized back to XOR2.
- Every committed baseline passes the Phase 1 structural, exact-basis,
  100,000-vector randomized, metric, and formal-equivalence checks.
- The baseline metrics table is produced exclusively from the independent
  verifier; Phase 2 created no optimization attempt or candidate.
- A reproducible Candidate A engine represents every signal as a 96-bit GF(2)
  vector and combines recursive common-subexpression extraction,
  Boyar–Peralta-style residual-distance reduction, free known-vector rewrites,
  depth-aware local pairing, and seeded stochastic tie-breaking.
- The Candidate A budget covered seeds 0 through 9,999. All 10,000 attempts are
  present in the append-only search log, and the checkpoint records completion.
- Every new count/depth incumbent was independently parsed, checked on 97 exact
  vectors and 100,000 seeded random vectors, and formally proved before
  acceptance. Twelve incumbents were accepted during the search.
- Seed 3,195 produced the best Phase 3 network: 439 XOR2, depth 9. The result
  artifact reproduces byte-for-byte from that seed. The Phase 4 continuation
  later found seed 16,564 (439 XOR2, depth 8), recorded in
  `results/phase4/candidate_a_extended.v` and
  `results/phase4/candidate_a_metrics.csv`.
- The Phase 3 Candidate A frontier and metrics records moved unchanged to
  `results/phase3/candidate_a_frontier.json` and
  `results/phase3/candidate_a_metrics.csv`; the Phase 3 optimizer and
  `verify_candidate` defaults now point there so a Phase 3 replay cannot
  overwrite the final results.
- Phase 6 regenerated `results/metrics.csv` and `results/pareto_frontier.json`
  with `python3 -m verifier.build_results`. All three submitted candidates
  passed the restricted parser, 97 exact vectors, 100,000 random vectors with
  seed `0xC32A5EED`, and Yosys SMTBMC/Z3 formal equivalence. Their metrics
  matched the completed checkpoints and search log; Candidate A is the best of
  all 20,000 logged Candidate A seeds, B and C are byte-identical to their
  accepted starting points after unimproved refinement budgets, and the Phase 5
  v2 study on Candidate B integrated no replacement.
- Phase 4 Candidate B (depth at most 8) and Candidate C (minimum depth) starting
  points passed structural, exact, randomized, and formal checks, and their
  10,000-seed refinement budgets completed with no accepted improvement.
- Completed-checkpoint replay recreates requested candidate, frontier, metrics,
  and search-log outputs while refusing conflicting append-only logs.
- Resume reconciles complete log records written immediately before an
  interrupted checkpoint update, avoiding duplicate attempt IDs.
- Candidate result verification checks the frontier's recorded structural,
  exact-vector, randomized-vector, seed, and formal-equivalence evidence against
  the acceptance checks actually performed.

## Files Created for Phase 1

- `.gitignore`
- `reference/__init__.py`
- `reference/crc32_reference.py`
- `reference/crc32_reference.v`
- `generator/__init__.py`
- `generator/build_matrix.py`
- `verifier/__init__.py`
- `verifier/verify_network.py`
- `verifier/run_formal.py`
- `verifier/formal_equivalence.ys`
- `verifier/test_verifier.py`
- `verifier/fixtures/valid_crc32_network.v`
- `verifier/fixtures/duplicate_instances.v`
- `verifier/fixtures/unreachable_node.v`
- `verifier/fixtures/invalid/chained_xor.v`
- `verifier/fixtures/invalid/cycle.v`
- `verifier/fixtures/invalid/forbidden_gate.v`
- `verifier/fixtures/invalid/forward_reference.v`
- `verifier/fixtures/invalid/missing_output.v`
- `verifier/fixtures/invalid/multiply_defined.v`
- `verifier/fixtures/invalid/undefined_signal.v`
- `verifier/fixtures/invalid/wrong_function.v`

## Files Created for Phase 2

- `generator/baseline_generator.py`
- `generator/test_baseline_generator.py`
- `verifier/verify_baselines.py`
- `results/baselines/independent_per_output.v`
- `results/baselines/balanced_per_output.v`
- `results/baselines/greedy_cse.v`
- `results/baselines/yosys_abc.v`
- `results/baseline_metrics.csv`

## Files Created for Candidate A

- `optimizer/__init__.py`
- `optimizer/optimize.py`
- `optimizer/test_optimize.py`
- `verifier/verify_candidate.py`
- `results/candidate_a_min_area.v`
- `results/pareto_frontier.json` (now `results/phase3/candidate_a_frontier.json`)
- `results/metrics.csv` (now `results/phase3/candidate_a_metrics.csv`)
- `results/checkpoints/candidate_a_checkpoint.json`
- `results/checkpoints/candidate_a_incumbents/*.v`

## Files Created for Phase 6

- `scripts/compare_crczero.py`
- `results/external/crczero_comparison.json`
- `report.md`
- `docs/comparison_research.md`
- `scripts/clean_rebuild.sh`
- `optimizer/depth_bounded.py`
- `optimizer/test_depth_bounded.py`
- `verifier/build_results.py`
- `verifier/test_build_results.py`
- `results/phase3/candidate_a_frontier.json` (moved from `results/`)
- `results/phase3/candidate_a_metrics.csv` (moved from `results/`)
- `results/phase6/candidate_depth7_bounded.v`
- `results/phase6/candidate_depth6_bounded.v`
- `results/checkpoints/depth7_bounded_search.json`
- `results/checkpoints/depth7_bounded_incumbents/*.v`
- `results/checkpoints/depth6_bounded_search.json`
- `results/checkpoints/depth6_bounded_incumbents/*.v`
- `results/pareto_frontier.json` (regenerated)
- `results/metrics.csv` (regenerated)

## Commands Executed

Required formal tools were installed with:

```bash
sudo apt-get install -y yosys berkeley-abc
sudo apt-get install -y z3
```

The final Phase 1 acceptance commands were:

```bash
python3 -m generator.build_matrix \
  --matrix-output /tmp/phase1_matrix_final.json \
  --network-output /tmp/phase1_network_final.v
cmp verifier/fixtures/valid_crc32_network.v /tmp/phase1_network_final.v
python3 -m unittest -v \
  verifier.test_verifier \
  generator.test_baseline_generator
python3 -m verifier.verify_network \
  verifier/fixtures/valid_crc32_network.v \
  --random-tests 100000 \
  --seed 0xC32A5EED \
  --output /tmp/phase1_verification_final.json
python3 -m verifier.run_formal \
  verifier/fixtures/valid_crc32_network.v \
  --module crc32_network
```

The Phase 2 baseline commands were:

```bash
python3 -m generator.baseline_generator \
  --output-dir results/baselines \
  --timings-output /tmp/baseline_generation_timings.json
python3 -m unittest -v \
  verifier.test_verifier \
  generator.test_baseline_generator
python3 -m verifier.verify_baselines \
  --baselines-dir results/baselines \
  --generation-timings /tmp/baseline_generation_timings.json \
  --metrics-output results/baseline_metrics.csv \
  --random-tests 100000 \
  --seed 0xC32A5EED
```

The Candidate A search and replay commands were:

```bash
python3 -m optimizer.optimize \
  --seed-start 0 \
  --seed-count 10000 \
  --workers 8
python3 -m optimizer.optimize \
  --replay-frontier results/phase3/candidate_a_frontier.json \
  --artifact /tmp/candidate_a_min_area.v
cmp results/candidate_a_min_area.v /tmp/candidate_a_min_area.v
python3 -m verifier.verify_candidate \
  --candidate results/candidate_a_min_area.v \
  --frontier results/phase3/candidate_a_frontier.json \
  --metrics results/phase3/candidate_a_metrics.csv \
  --random-tests 100000 \
  --seed 0xC32A5EED
```

The Phase 6 result regeneration commands were:

```bash
python3 -m verifier.build_results \
  --random-tests 100000 \
  --seed 0xC32A5EED
python3 -m verifier.build_results --check
```

Tool versions used locally:

- Python 3.10.12
- Yosys 0.9 (`git sha1 1979e0b`)
- Berkeley ABC 1.01 (compiled 2022-01-29)
- Z3 4.8.12

## Test Results

- Unit/rejection suite: 19 tests passed, 0 failed, 0 skipped.
- Matrix reconstruction: 1,000 seeded random pairs matched the Python reference.
- Exact network equivalence: all-zero plus 96 basis vectors passed (97 total).
- Random network equivalence: 100,000 pairs passed with seed `0xC32A5EED`
  (`3274333933`).
- Formal equivalence: Yosys built the combined 96-input miter, Berkeley ABC
  synthesized the explicitly submitted structural network, and Yosys
  SMTBMC/Z3 proved every output comparison for all inputs. A negative formal
  regression confirmed that `wrong_function.v` fails.
- Invalid-circuit CLI checks: all eight fixtures exited nonzero; seven failed
  structural parsing and `wrong_function.v` failed exact equivalence.
- Unreachable-node fixture: accepted structurally, reported `assign:dead`, and
  removed it before metrics.
- Duplicate-instance fixture: both identical physical gates were retained.
- Validation-fixture metrics: 1,390 XOR2 instances, maximum depth 51, maximum
  fanout 20, total fanout 2,812, and total excess fanout above four 1,038. These
  are not optimization or baseline results.
- Combined Phase 1, baseline, optimizer, and result-verifier suite: 30 tests
  passed, 0 failed, 0 skipped. The original Phase 1 suite remains 19 tests
  passed.
- All four baselines passed 97 exact vectors, 100,000 random vectors with seed
  `0xC32A5EED`, and Yosys SMTBMC/Z3 formal equivalence.
- Candidate A passed the restricted parser, 97 exact vectors, 100,000 random
  vectors with seed `0xC32A5EED`, and Yosys SMTBMC/Z3 formal equivalence.
- Candidate A metrics: 439 XOR2, depth 9, maximum fanout 6, total fanout 910,
  and total excess fanout above four 5.
- The winning seed replayed byte-for-byte, the frontier and metrics CSV matched
  independent recomputation, and the search log contains 10,000 unique attempt
  IDs with 12 retained-incumbent records.
- Phase 6 suite (`verifier.test_verifier`, `verifier.test_verify_candidate`,
  `verifier.test_build_results`, `generator.test_baseline_generator`,
  `optimizer.test_optimize`, `optimizer.test_phase5_exact`,
  `optimizer.test_depth_bounded`): 53 tests passed, 0 failed, 0 skipped.
- `scripts/clean_rebuild.sh` passed from a fresh clone in 73 seconds: 58 unit
  tests, the Phase 1 fixture and all four baselines (including Yosys/ABC on
  Yosys 0.9) regenerated byte-identically, every submitted artifact replayed
  byte-identically from its seed or construction, `build_results --check
  --require-spec-minimum` passed, and the clone was unchanged. A clone with a
  tampered `results/phase6/candidate_depth7_bounded.v` failed with a mismatch.
- Phase 6 regeneration re-verified Candidates A, B, and C (structural, 97 exact,
  100,000 random, formal) and `--check` confirmed the committed
  `results/metrics.csv` and `results/pareto_frontier.json` match it.
- Regression tests cover completed-checkpoint output recovery and rejection of
  stale frontier verification evidence, plus recovery when the log is ahead of
  its checkpoint.
- Bounded-search resume regression (`python3 -B -m unittest -v
  optimizer.test_depth_bounded`): 5 tests passed. Completed budgets restore
  missing, stale, and relocated output artifacts from the replay-validated
  incumbent without new trials or changes to the log and checkpoint bytes.

## Phase 6 Progress

The regenerated frontier (`schema_version` 2) has three distinct
nondominated circuits, meeting the `SPEC.md` Section 4 minimum;
`python3 -m verifier.build_results --check --require-spec-minimum` passes.

| Circuit | Classes | XOR2 | Depth | Max fanout | Excess fanout >4 |
| --- | --- | ---: | ---: | ---: | ---: |
| `1472a09886a8` | A, B | 439 | 8 | 5 | 5 |
| `ed4ed2ba71db` | B7 | 440 | 7 | 5 | 3 |
| `900a2989cbc1` | C | 465 | 6 | 6 | 19 |

Submitted but dominated: C0 (`0c80bfcc8e2b`, 1,390 XOR2, depth 6, maximum
fanout 20, excess 1,038), the Phase 4 minimum-depth starting point, which
Candidate C dominates on every objective.

- Candidates A and B are the same netlist apart from the module name: the
  seed-16,564 Candidate A already satisfies the depth-8 bound, and B's
  refinement found nothing better. The frontier lists that circuit once with
  both class labels.
- **B7 and C were replaced on 2026-10-27** by circuits from the follow-up
  experiments.
  - B7 is now the incumbent of the ablation `rewrite` arm's completed depth-7
    budget (seeds 160,000–160,999, seed 160,832): 440 XOR2, maximum fanout 5,
    excess 3.
  - C is now seed 286,375 of the completed Kraft-adaptive stage-2 rerun (v2,
    seeds 281,000–290,999): 465 XOR2, maximum fanout 6, excess 19.
  - That C is not its budget's incumbent. The incumbent, seed 288,438, also
    has 465 gates but wins only on maximum fanout. `build_results` accepts a
    selected trial only if it reaches the budget's minimum XOR2 count, is
    nondominated within the budget, matches its logged metrics, and replays
    byte for byte.
  - Both passed the restricted parser, 97 exact vectors, 100,000 random
    vectors, and formal equivalence.
  - Each dominates the circuit it replaced: the original B7 (`b65a4c2b615e`,
    441 XOR2, seed 40,505 of the depth-7 Kraft-bounded budget) and the
    original C (`b8edf279b361`, 470 XOR2, seed 56,140 of the depth-6 budget).
    Both originals stay in `results/phase6/` for provenance.
  - The 440 is a tail draw from a baseline-equivalent distribution. The 465
    is a tail draw from a search family whose depth-6 mean is about 5 gates
    lower than the original budget's.
- `SPEC.md` Section 4 defines Candidate C as minimum depth first, then
  minimum XOR2 count, so the 465-gate depth-6 circuit is Candidate C.
  The Phase 4 balanced-tree starting point, which has the same depth but 1,390
  gates, is reported as C0 for provenance and is not on the frontier. B7 is a
  bounded-depth (Candidate B family) search at depth 7; Candidate B remains
  the depth-8 circuit because it has fewer gates. `build_results` now rejects
  any submission set in which A, B, or C does not win its class objective.
- Every recorded baseline is now dominated by a frontier circuit, including
  Yosys/ABC (1,123 XOR2, depth 7) and `balanced_per_output`, which is
  structurally identical to C0. This comparison reads the recorded
  `results/baseline_metrics.csv`.
- The superseded Phase 3 Candidate A (439 XOR2, depth 9, maximum fanout 6) is
  dominated by the Phase 4 Candidate A and is not submitted.

## Remaining Work

No required final deliverable remains. Optional follow-up work is limited to
new search budgets, broader literature access, and toolchain pinning; the
limitations below remain in effect.

- **DCLO budget (2026-10-27), hypothesis refuted.** DCLO as published (Boyar,
  Find and Peralta, 2019) was run with 10,000 seeds per cap.
  - Seeds 70,000–79,999 at depth 7 and 80,000–89,999 at depth 6.
  - Algorithms `dclo-kraft-depth{7,6}-v1`, implemented in `optimizer/dclo.py`.
  - Best results: 445 XOR2 at depth 7 and 477 at depth 6. The original B7 and
    Candidate C dominate both, so DCLO did not change the frontier.
  - Per-seed medians were 462 and 499, against the baseline's 456 and 490.
  - The pre-registered record, raw-result paths and the open ablation are in
    `docs/experiments/dclo_depth_bounded.md`.
- **Ablation toward DCLO (2026-10-27).** Record:
  `docs/experiments/ablation_toward_dclo.md`.
  - The depth-aware tie-break accounts for 90–95% of DCLO's deficit. The
    other components each move the mean by at most 0.35 gates.
  - One ablation seed (160,832) gave a verified **440-gate depth-7 network**
    that dominates the original B7, and is now B7. A 10,000-seed follow-up
    showed it is a tail draw (mean 456.05, the same as the baseline).
- **Kraft-slack tie-break (2026-10-27).** Record:
  `docs/experiments/kraft_slack_tiebreak.md`.
  - Cap 6: the mean is 5 gates lower, and 17 of 10,000 seeds beat 470. The
    best is a verified **467-gate depth-6 network**. Seeds 249,452 (468) and
    248,720 (469) give verified networks that dominate the original
    Candidate C.
  - Cap 7: the mean is 2.3 gates worse.
- **Cap-adaptive tie-break (2026-10-27).** Record:
  `docs/experiments/kraft_adaptive_tiebreak.md`.
  - With θ = 1/2 it matches the slack variant at both caps, so it does not
    recover cap 7.
  - Stage 2 at cap 6 first stopped at 3,862 of 10,000 seeds because of a
    slack-family finishing bug on seed 284,862. It is now fixed with a
    fresh-gate fallback (`d37e628`), which leaves every recorded result
    unchanged.
  - The v1 run had already found a verified **466-gate depth-6 network**
    (seed 281,125, fanout 6, excess 20).
  - A full v2 rerun reproduced v1 exactly on those 3,862 seeds. Its best is
    **465**. Seed 286,375 gives a verified **465-gate depth-6 network**
    (fanout 6, excess 19), which is now Candidate C.
- **Search logs split (2026-10-27).** The single 81 MB
  `results/search_log.jsonl` is now one file per experiment under
  `results/search_logs/`. Every record is unchanged.
- **Frontier updated (2026-10-27, at the project owner's request).** The 440
  (seed 160,832) replaced B7 and the 465 (seed 286,375) replaced C.
  - `verifier/build_results.py` submits them.
  - `results/pareto_frontier.json` and `results/metrics.csv` are regenerated.
  - `report.md` is updated.
  - `python3 -m verifier.build_results --check --require-spec-minimum`
    passes with 3 distinct Pareto circuits: 439/depth 8, 440/depth 7,
    465/depth 6.

## Semantic Ambiguities or Discrepancies

- The permitted structural representation is intentionally a strict,
  non-ANSI Verilog subset: exact vector port declarations, scalar internal
  wires, direct aliases, one-XOR assignments, and named-port `xor2` instances.
  Equivalent behavioral Verilog is not accepted as a submitted network.
- Because every node must use previously defined inputs, any cycle necessarily
  contains a forward reference. Cycle detection runs first so the deliberate
  cycle fixture is diagnosed as a cycle; acyclic later-defined dependencies are
  diagnosed as forward references.
- “Dead output” is implemented as a missing or undriven `next_crc` bit.
  Unreachable internal XOR nodes are not malformed; they are reported and
  removed before metrics, as required by SPEC.md Section 6.
- `direct_output_alias_count` counts output bits whose submitted driver is an
  alias rather than an XOR instance. Internal alias chains are propagated before
  depth and fanout accounting.
- Under the physical-instance clarification in SPEC.md Revision 1,
  `intermediate_node_count` and `xor2_count` are equal. Separately instantiated
  identical XOR gates remain distinct.
- Direct ABC CEC and Yosys 0.9's gate-level SAT proof did not finish promptly
  after XOR logic was flattened to AIG/CNF form. The passing flow instead uses
  ABC as a structural-network synthesis check and Yosys SMTBMC with Z3 for the
  exhaustive bit-vector equivalence proof. This is consistent with the
  specification's SAT/SMT equivalence requirement; the unsuccessful trials are
  not reported as passes.
- The Verilog reference expresses the normative conditional polynomial update
  as the algebraically identical masked-feedback XOR recurrence. This avoids
  introducing mux layers while preserving the frozen bit-serial semantics; the
  exhaustive proof checks it against the Python-derived structural fixture.
- The local Yosys 0.9 `abc -g XOR` flow aborts because the mapper has no
  fallback cell. The baseline uses `-g XOR,AND`; ABC emitted 1,123 XOR cells,
  eight NOT cells, and no AND cells. Normalization propagates the NOT phases,
  rejects any non-XOR/non-NOT mapped cell, and requires all output phases to
  cancel before emitting the restricted XOR2 circuit.
- Yosys/ABC structure and all runtime columns are toolchain- and
  machine-dependent. The recorded result is directly comparable under the
  frozen XOR2 metric only after normalization and independent verification.
- These are local baselines using the frozen reflected IEEE CRC-32 semantics,
  64-bit parallel width, physical XOR2 gate model, and SPEC.md metrics. No
  external or arbitrary-width-XOR result is compared here.
- For dominated Candidate A trials, `verification_passed` in the search log
  records the independent restricted-parser and 97-vector exact check performed
  by each worker. `accepted: true` appears only on new incumbents, which also
  passed the 100,000-vector and formal acceptance flow before the record was
  written. Per-attempt runtime measures the worker search and exact-check time;
  formal-acceptance time is outside that field.
- The checkpoint's `elapsed_seconds` is the last uninterrupted resumed process,
  not aggregate wall time across deliberate worker-count restarts. The concrete
  reproducible compute budget is the completed ordered range of 10,000 seeds.

## Unresolved Issues

- C0 equals the balanced-tree baseline and is dominated by Candidate C.
  Reporting must not present it as a search-derived improvement.
- Comparison research (`docs/comparison_research.md`, 2026-10-24) found one
  directly comparable public figure: crcZero's unshared 1,390 XOR2 for
  reflected CRC-32 at D=64, equal to our unshared baseline. Running crcZero
  (commit `98c55152`) with `scripts/compare_crczero.py` confirmed it: all 32
  equations equal the frozen matrix, and its chained and balanced
  realizations pass exact, random, and formal checks and are structurally
  identical to `independent_per_output` and `balanced_per_output`
  (`results/external/crczero_comparison.json`). Zhang–Tang (ISCAS
  2021) report 469–503 XORs at CPD 6 for p = 64, but for a transformed
  remainder rather than the standard update, so those figures are context
  only. Campobello et al. (2003) was read on 2026-10-24 from the authors'
  archived preprint. All of its XOR2 figures are for w = 32, not 64: 452
  unshared and 370 with manual sharing, plus Shieh et al.'s 448 → 408 that it
  quotes. It reports no 64-bit count. Shieh et al. (JISE 2001) was read on
  2026-10-26. Its Type-I design is the standard update, but its widest case
  is r = 32: 448 XOR2 at 15 levels cascaded, and 408 at 7 levels after
  Synopsys. It reports no 64-bit count. Several older papers remain unread,
  so a lower published standard-function count cannot be ruled out. Depth 6
  is provably minimal (maximum row weight 52). No novelty or gate-count
  optimality claim is supported.
- B7 and Candidate C are best found for their recorded 10,000-seed budgets,
  not optimal circuits. The Kraft check makes the depth cap exact, but the
  sharing choices remain greedy and seeded.
- Seven v2 cones timed out as `unknown`. A larger timeout would be a new,
  separately recorded budget, not a continuation of the completed one.
- Dedicated simulated annealing, output-subset resynthesis, and separately
  budgeted fanout-duplication studies are not established as completed
  experiments. The report explicitly limits its claims to the recorded
  heuristic and exact-cone budgets.
- Pinning or containerizing the Yosys/ABC toolchain is deferred; a different
  release may produce a different valid conventional-synthesis baseline.

## Gate G0 Checklist

- [x] `SPEC.md` exists and freezes the experiment contract.
- [x] `PLAN.md` exists and serves as the development roadmap.
- [x] `STATUS.md` reports no unearned results or validation claims.
- [x] `results/search_log.jsonl` exists and contains no fabricated attempt.
- [x] README reflects the structure-only setup state.
- [x] GitHub Actions CI enforces the Phase 0 structure checks.
- [x] Phase 0 introduced no implementation or optimization work.

## Gate G1 Checklist

- [x] Python and Verilog semantics agree exhaustively through the generated
  structural network and formal miter.
- [x] Matrix reconstruction matches the normative bit-serial reference.
- [x] Every deliberately invalid fixture exits nonzero through the verifier CLI.
- [x] The known-correct structural fixture passes exact and randomized checks.
- [x] Metrics cover aliases, duplicate instances, unreachable nodes, depth,
  fanout, and excess fanout.
- [x] Formal equivalence passes with Yosys, Berkeley ABC, and Z3.
- [x] Clean-checkout Phase 1 commands are documented in `README.md`.
- [x] CI contains every Phase 1 acceptance gate.
- [x] Phase 1 still passes unchanged after adding Phase 2 baseline tooling.

## Gate G2 Checklist

- [x] Independent serial expansion, balanced no-sharing trees, greedy CSE, and
  normalized Yosys/ABC baselines are reproducibly generated.
- [x] Every baseline passes the restricted structural parser and independent
  metric calculator.
- [x] Every baseline passes all 97 exact vectors and 100,000 seeded random
  vectors.
- [x] Every baseline passes Yosys SMTBMC/Z3 formal equivalence after Berkeley
  ABC synthesis.
- [x] Reproduction commands and local tool versions are recorded.
- [x] No deterministic candidate optimization or stochastic search has begun.

## Gate G3 Candidate A Checklist

- [x] GF(2)-vector CSE, Boyar–Peralta-style heuristics, depth-aware rewrites,
  multi-seed stochastic tie-breaking, replay, and checkpointing are implemented.
- [x] Exactly 10,000 seeded attempts are recorded with unique IDs.
- [x] Every new incumbent passed structural, exact, random, and formal checks
  before acceptance.
- [x] Candidate A reproduces byte-for-byte from seed 3,195.
- [x] Candidate A, its independently recomputed metrics, and the one-entry
  frontier agree.
- [x] Candidates B and C were not started before G3 closed (they were run
  in Phase 4).

## Gate G5 Checklist

- [x] The corrected exclusive-cone v2 budget completed: 20 cones from the
  Phase 4 refined Candidate B, six-node cone limit, 1,000 ms per-query timeout.
- [x] The input candidate passed 100,000 seeded random vectors and formal
  equivalence before any cone query ran.
- [x] Every replacement has exact local-function evidence and full-network
  verification. No replacement was found, accepted, or integrated, and the
  submitted networks are unchanged.
- [x] The Z3 version, cone constraints, timeout, selected roots, and every
  outcome are recorded in the checkpoint, output JSON, and append-only search
  log.
- [x] Thirteen UNSAT results are claimed only for their single-cone encodings.
  The seven `unknown` timeouts are recorded as negative results, not
  certificates.
- [x] No global or whole-network optimality is claimed.


## Gate G6 Checklist

- [x] Final structural artifacts, independent metrics, frontier JSON, canonical
  search log, checkpoints, comparison research, and `report.md` exist.
- [x] All five submitted artifacts passed structural, 97-vector exact,
  100,000-vector seeded random, and formal-equivalence checks in the final
  result-builder check; required A/B/C labels and three distinct nondominated
  circuits are present.
- [x] Report candidate/baseline tables, circuit IDs, seeds, scalar metrics,
  frontier membership, Phase 5 outcomes, and search budgets agree with the
  result files and provenance. The matrix has 1,422 ones and maximum row
  weight 52, supporting the depth-6 lower bound.
- [x] README reproduction commands have recorded fresh-clone evidence:
  `scripts/clean_rebuild.sh` passed 58 tests and artifact replay checks.
  That full rebuild was not repeated during this documentation closeout.
- [x] `report.md` covers semantics, methodology, results, failed approaches,
  comparison limitations, publishability, and reproduction. No gate-count
  optimality, physical-performance, or research-novelty claim is made.

### Final closeout validation (2026-10-24)

- `python3 -B -m verifier.build_results --check --require-spec-minimum`:
  passed; all five submitted artifacts formally proved and three distinct
  Pareto circuits confirmed. The read-only sandbox attempt could not create
  temporary files; the rerun with temporary-file access passed.
- `python3 -B -m unittest discover`: passed, 58 tests in 21.566 seconds.
- Final report/artifact consistency check: passed; candidate and baseline
  tables match CSV rows, frontier entries match CSV metrics and circuit IDs,
  all 60,042 log IDs are unique, budgets and Phase 5 counts match the JSON,
  and the recomputed matrix supports the stated depth bound.
- `git diff --check` and the report trailing-whitespace check: passed.
- The hours-long search budgets and full clean-clone rebuild were not rerun.
  No numerical result or circuit was changed for this closeout.

Next: review and commit the final documentation on `phase6-final-results`.
New optimization or stronger publication claims require a separate experiment
and updated comparison evidence.


### PR #11 review fixes (2026-10-27)

- Integrated master’s corrected Campobello input-factoring comparison while
  preserving the verified 465/440-gate frontier.
- The current adaptive runner rejects historical v1 stages before locking or
  writing logs. Its v2 finishing fallback must not continue the aborted v1
  experiment; the registered `stage2_rerun` retains its v2 algorithm name.
- Regression validation: `python3 -m unittest optimizer.test_kraft_adaptive
  optimizer.test_depth_bounded verifier.test_search_logs`: 21 tests passed
  in 29.596 seconds. `git diff --check` passed. Full clean rebuild remains
  a CI check.

### Kraft phase-isolation experiment (2026-10-28)

- Completed the preregistered four-arm comparison at caps 6 and 7: 1,000
  matched seeds per arm/cap, 8,000 unique verified trials, 52 fully verified
  incumbent acceptances. Code/protocol were committed before the budget at
  `7dcc2fb`; full results: `docs/experiments/kraft_phase_isolation.md`.
- H1 refuted: the cap-7 penalty comes from sharing, rather than finishing
  scoring. Sharing-only and both average 458.102 XOR2; baseline and
  finishing-only average 456.125. Changing finishing leaves every paired
  cap-7 gate count unchanged, although fanout can change.
- H2 confirmed: sharing-only retains the full cap-6 gain (485.493 mean XOR2
  versus baseline 490.305). Neither hybrid improves on its designated best
  control enough to qualify for the frozen confirmation rule; H3 refuted.
  The stage-2 command selected no runs and performed no additional trials.
- Found two independently verified **462-XOR2, depth-6** witnesses at seed
  320099, in the sharing-only and both arms. Both have maximum fanout 6,
  total fanout 956 and excess fanout 22. They save three gates versus C but
  have higher excess fanout (C: 19), so the submitted 439/440/465 frontier
  and `report.md` remain unchanged. The witnesses and their separate exact,
  randomized and formal evidence are retained under
  `results/checkpoints/phase_isolation/` and `results/phase_isolation/`.
- Validation: all 97 unit tests passed; completed-budget replay preserved 78
  result files byte-for-byte with no new trials; `build_results --check
  --require-spec-minimum` passed. All 8,000 diagnostic records have valid
  phase gate sums and nonnegative remaining Kraft budgets. Full clean-clone
  rebuild was not repeated in this session.
- Next: preregister a sharing-phase scoring experiment that accounts for
  residual completion cost. The finishing-phase gate-count explanation is
  contradicted by this experiment. The 462 witnesses demonstrate existence,
  rather than an improvement in the hybrid search distribution.

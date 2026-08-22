# CRC32 Superoptimization Status

Last updated: 2026-08-22

Current phase: Phase 3 — Candidate A optimization complete

Current gate: G3 passed locally for the requested Candidate A-only scope; CI
integration added

## Current Best Results

Candidate A is the best network found by the recorded 10,000-seed search. It is
not a claim of global optimality. The generated 1,390-XOR structural network
remains a Phase 1 validation fixture only, not a candidate or baseline.

| Candidate class | XOR2 count | Maximum depth | Verification | Status |
| --- | ---: | ---: | --- | --- |
| A — minimum gate-count search | 439 | 9 | Passed | Best found; seed 3,195 |
| B — depth at most 8 | — | — | Not run | Not started |
| C — minimum-depth search | — | — | Not run | Not started |

Deterministic baseline metrics below were recomputed by the independent Phase 1
verifier. Runtime is the observed sum of generation, 100,000-vector
verification, and formal-equivalence time on the local toolchain.

| Network | XOR2 | Depth | Max fanout | Total fanout | Excess fanout >4 | Runtime (s) | Verification |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Independent per-output expansion | 1,390 | 51 | 20 | 2,812 | 1,038 | 4.805134 | Passed |
| Balanced per-output tree | 1,390 | 6 | 20 | 2,812 | 1,038 | 4.745530 | Passed |
| Greedy common-subexpression elimination | 454 | 9 | 6 | 940 | 11 | 3.868081 | Passed |
| Yosys/ABC normalized synthesis | 1,123 | 7 | 15 | 2,278 | 536 | 6.297098 | Passed |
| Candidate A | 439 | 9 | 6 | 910 | 5 | — | Passed |

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
- Seed 3,195 produced the best-found 439-XOR, depth-9 network. The result
  artifact reproduces byte-for-byte from that seed.
- `results/metrics.csv` and `results/pareto_frontier.json` contain Candidate A
  only and match the independent verifier. Candidates B and C were not run.
- Completed-checkpoint replay recreates requested candidate, frontier, metrics,
  and search-log outputs while refusing conflicting append-only logs.
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
- `results/pareto_frontier.json`
- `results/metrics.csv`
- `results/checkpoints/candidate_a_checkpoint.json`
- `results/checkpoints/candidate_a_incumbents/*.v`

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
  --replay-frontier results/pareto_frontier.json \
  --artifact /tmp/candidate_a_min_area.v
cmp results/candidate_a_min_area.v /tmp/candidate_a_min_area.v
python3 -m verifier.verify_candidate \
  --candidate results/candidate_a_min_area.v \
  --frontier results/pareto_frontier.json \
  --metrics results/metrics.csv \
  --random-tests 100000 \
  --seed 0xC32A5EED
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
- Combined Phase 1, baseline, optimizer, and result-verifier suite: 29 tests
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
- Regression tests cover completed-checkpoint output recovery and rejection of
  stale frontier verification evidence.

## Not Started

- Candidates B and C, broader stochastic/local optimization, depth-bounded
  search, and exact-subcircuit search
- A final multi-candidate Pareto frontier and final report
- Literature and open-source comparison research

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

- Candidate A used the fixed 10,000-seed budget. Set and record separate budgets
  for Candidates B and C and solver-backed searches before those phases begin.
- Batch orchestration for formally checking multiple future candidates belongs
  to later phases; the Phase 1 runner already requires one explicit network per
  invocation and validates its module name.
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
- [x] Candidates B and C were not started.

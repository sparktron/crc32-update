# CRC32 Update Circuit Optimization

This repository is the workspace for a reproducible search for optimized
combinational XOR2 networks implementing a 64-bit parallel reflected IEEE
CRC-32 state update.

Phase 1 reference, matrix-generation, structural verification, metric, random,
and formal-equivalence infrastructure is implemented. Phase 2 deterministic
baselines are generated and verified. Phase 3 has produced and verified
Candidate A with a reproducible multi-seed minimum-area search. Candidates B
and C have not begun.

Experiment control documents:

- [`SPEC.md`](SPEC.md) freezes semantics, the permitted circuit model, metrics,
  and candidate acceptance criteria.
- [`PLAN.md`](PLAN.md) is the development roadmap and defines phase validation
  gates.
- [`STATUS.md`](STATUS.md) records completed work, current best results, and
  unresolved issues.
- [`results/search_log.jsonl`](results/search_log.jsonl) contains one
  machine-readable record for every optimization attempt.

## Continuous Integration

GitHub Actions runs the `CI` workflow for pull requests, pushes to `master`, and
manual dispatches. It checks the control files and search log, regenerates the
Phase 1 fixture, runs the unit and rejection suite, checks 97 exact plus 100,000
seeded random vectors, runs formal equivalence, and regenerates then validates
the deterministic Phase 2 baselines. The generation timings and measurement
results in that CI check always refer to the same generated artifacts.

Phase 1 reference, matrix, parser, metric, equivalence, rejection, and formal
tests run in the same CI gate. CI also replays Candidate A from its recorded
seed, compares it byte-for-byte, and repeats its structural, exact, random,
metric-record, and formal checks. CI does not rerun the 10,000-seed search.

## Circuit Metric Model

Each separately instantiated XOR2 node is a distinct physical gate, even when
another node has the same inputs. Metric normalization preserves those instances
so fanout-aware duplication can trade additional gates for reduced fanout.
Common-subexpression merging is measured as an explicit optimization that emits
a different circuit, not as an automatic verifier rewrite.

## Phase 1 Commands

Install the formal tools on Ubuntu/Debian:

```bash
sudo apt-get install -y yosys z3
```

The distribution's `yosys` package must provide or depend on the `yosys-abc`
executable. Ubuntu 24.04 packages it as `yosys-abc`; Ubuntu 22.04 uses the
`berkeley-abc` dependency name.

Evaluate the normative Python reference:

```bash
python3 -m reference.crc32_reference 0x12345678 0x0123456789abcdef
```

Regenerate the GF(2) matrix and the unoptimized structural validation fixture:

```bash
python3 -m generator.build_matrix \
  --matrix-output /tmp/crc32_matrix.json \
  --network-output /tmp/valid_crc32_network.v
cmp verifier/fixtures/valid_crc32_network.v /tmp/valid_crc32_network.v
```

Run the unit tests, including every deliberately invalid circuit:

```bash
python3 -m unittest -v verifier.test_verifier
```

Run the acceptance verifier. Its JSON report includes independently recomputed
metrics, the 97 exact-vector result, random seed, and random-vector count:

```bash
python3 -m verifier.verify_network \
  verifier/fixtures/valid_crc32_network.v \
  --random-tests 100000 \
  --seed 0xC32A5EED \
  --output /tmp/phase1_verification.json
python3 -m json.tool /tmp/phase1_verification.json
```

Run exhaustive formal equivalence between the independently generated
structural fixture and the Verilog reference:

```bash
python3 -m verifier.run_formal \
  verifier/fixtures/valid_crc32_network.v \
  --module crc32_network
```

The network path is mandatory. The runner parses that submitted file, derives
its module name, copies it to an isolated temporary directory, and renders the
formal script for that exact file. `--module` is optional but, when supplied,
must match the parsed module declaration.

`verifier/fixtures/valid_crc32_network.v` is an unoptimized Phase 1 validation
fixture, not a candidate, Pareto result, or measured Phase 2 baseline.

## Phase 2 Baseline Commands

Generate the four baseline circuits and record generation timings:

```bash
python3 -m generator.baseline_generator \
  --output-dir results/baselines \
  --timings-output /tmp/baseline_generation_timings.json
```

Run the complete Phase 1 verifier and formal flow for every baseline, then
write the independently measured table:

```bash
python3 -m verifier.verify_baselines \
  --baselines-dir results/baselines \
  --generation-timings /tmp/baseline_generation_timings.json \
  --metrics-output results/baseline_metrics.csv \
  --random-tests 100000 \
  --seed 0xC32A5EED
```

The Yosys/ABC baseline starts from the independent expansion, runs conventional
Yosys optimization and ABC mapping, and accepts only XOR/NOT output cells. NOT
phases are propagated algebraically and must cancel at every primary output;
the resulting committed circuit contains only permitted XOR2 gates and aliases.
Observed runtimes are machine-dependent. No command in Phase 2 performs
stochastic optimization or creates an optimization candidate.

## Candidate A Commands

Run the recorded 10,000-seed, unrestricted-depth Candidate A search. The search
uses GF(2) signal vectors, common-subexpression extraction, Boyar–Peralta-style
distance reduction, depth-aware rewrites, and seeded stochastic tie-breaking.
It appends one JSONL record per seed and atomically updates a resumable
checkpoint every 25 seeds:

```bash
python3 -m optimizer.optimize \
  --seed-start 0 \
  --seed-count 10000 \
  --workers 8
```

Re-running against a completed checkpoint validates the recorded search
configuration, recreates the requested candidate, frontier, and metrics files,
and restores the append-only search log from the checkpoint's recorded log.
It refuses to overwrite a conflicting log.
On resume, a complete logged seed prefix takes precedence over a stale
checkpoint counter, preventing duplicate attempts after interruption between a
log append and checkpoint update.

Replay only the verified winning seed recorded in the frontier and compare the
result byte-for-byte:

```bash
python3 -m optimizer.optimize \
  --replay-frontier results/pareto_frontier.json \
  --artifact /tmp/candidate_a_min_area.v
cmp results/candidate_a_min_area.v /tmp/candidate_a_min_area.v
```

Re-run the complete Candidate A acceptance flow and cross-check
`results/metrics.csv` and `results/pareto_frontier.json` against the independent
measurement:

```bash
python3 -m verifier.verify_candidate \
  --candidate results/candidate_a_min_area.v \
  --frontier results/pareto_frontier.json \
  --metrics results/metrics.csv \
  --random-tests 100000 \
  --seed 0xC32A5EED
```

Every improving incumbent is independently parsed, checked on all 97 exact
vectors and 100,000 recorded random vectors, and formally proved before it is
accepted. Candidate A has no hard depth cap. This work does not run or create
Candidates B or C.

## Phase 4 Continuation

Phase 4 broadens the seeded local search without changing the completed Phase 3
Candidate A checkpoint. It uses seeds 10,000 through 19,999, appends records to
the same canonical search log, and can safely resume after interruption:

```bash
python3 -m optimizer.optimize \
  --seed-start 10000 \
  --seed-count 10000 \
  --workers 8 \
  --checkpoint results/checkpoints/phase4_candidate_a_checkpoint.json \
  --artifact results/phase4/candidate_a_extended.v \
  --frontier results/phase4/candidate_a_frontier.json \
  --metrics results/phase4/candidate_a_metrics.csv \
  --search-log results/search_log.jsonl
```

The configured Candidate A continuation and Candidate B/C refinement budgets
have completed. Candidate B (seeds 20,000–29,999) and Candidate C (seeds
30,000–39,999) found no accepted improvement over their verified starting
incumbents. Gate G4 passed locally for those recorded budgets; this is not a
global-optimality claim.

## Candidate B and C Starting Points

Phase 4 records a depth-8 Candidate B starting point from the completed seeded
continuation and a depth-6 Candidate C balanced-tree starting point. Both are
independently checked on 97 exact vectors, 100,000 seeded random vectors, and
formal equivalence before being accepted into the search log:

```bash
python3 -m optimizer.phase4_candidates \
  --output-dir results/phase4 \
  --search-log results/search_log.jsonl \
  --random-tests 100000 \
  --random-seed 0xC32A5EED
```

The command records each starting point once; it intentionally refuses to
append a duplicate attempt. The documented depth-bounded and minimum-depth
refinement budgets below have completed without an accepted improvement.

The following completed budgets were run manually, one at a time. Both commands resume
from their checkpoints after interruption and reject concurrent access to the
canonical search log:

```bash
python3 -m optimizer.refine_candidates B \
  --seed-start 20000 \
  --seed-count 10000 \
  --workers 8 \
  --output-dir results/phase4 \
  --search-log results/search_log.jsonl \
  --checkpoint results/checkpoints/candidate_b_refinement.json

python3 -m optimizer.refine_candidates C \
  --seed-start 30000 \
  --seed-count 10000 \
  --workers 8 \
  --output-dir results/phase4 \
  --search-log results/search_log.jsonl \
  --checkpoint results/checkpoints/candidate_c_refinement.json
```

Run Candidate B first, then Candidate C. Candidate B retains only trials at
depth 8 or less and minimizes XOR2 count; Candidate C minimizes depth first,
then XOR2 count.

Because this search can exceed Codex's command-execution time limit, run the
continuation manually rather than asking Codex to start it. The checkpoint and
append-only log make that manual command safe to resume.

## Phase 5 Exact Cone Study

Phase 5 begins with an exact Z3 study of small Candidate B cones. Each query
uses GF(2) coefficient vectors for the cone's cut leaves, so a SAT witness or
UNSAT result applies to all local input assignments. Internally shared signals
are cut leaves, not removable gates, so a strict reduction can be compared to
the actual replaceable subcircuit. The study does not alter a candidate: any
witness still requires explicit integration and complete independent
verification.

Run the initial budget manually because up to 20 cones and several bounded SMT
queries per cone can exceed Codex's command limit:

```bash
python3 -m optimizer.phase5_exact \
  --candidate results/phase4/candidate_b_refined.v \
  --checkpoint results/checkpoints/phase5_exact_exclusive_cones.json \
  --search-log results/search_log.jsonl \
  --output results/phase5/exact_exclusive_cone_study.json \
  --max-cone-nodes 6 \
  --limit 20 \
  --timeout-ms 1000
```

The previous non-exclusive study is retained as an exploratory record but is
not evidence of a whole-network reduction because its cones included shared
fan-in gates. The corrected command above records each complete outcome in the
canonical log and preserves all outcomes when resumed after interruption. Run
it alone because it locks the shared canonical search log.

Run only one invocation for a checkpoint at a time; the optimizer now rejects a
second active invocation. If an older interrupted concurrent run left duplicate
records, repair only after preserving a recovery copy and confirming that every
duplicate has the same outcome:

```bash
python3 -m optimizer.repair_search_log \
  --log results/search_log.jsonl \
  --backup results/checkpoints/phase4_search_log_pre_dedup.jsonl
```

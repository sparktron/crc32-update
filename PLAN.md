# CRC32 Superoptimization Development Plan

This document is the repository development roadmap. Work proceeds in order;
later phases do not begin until the preceding validation gate passes. The
current phase is tracked in `STATUS.md`.

## Phase 0 — Experiment Structure

Scope:

- Freeze CRC semantics, circuit restrictions, metrics, and acceptance criteria.
- Define phased work and validation gates.
- Establish a status record and append-only optimization search log.
- Point the repository README at the experiment control documents.
- Establish a least-privilege GitHub Actions workflow for structure checks.

Validation gate G0:

- `SPEC.md`, `PLAN.md`, `STATUS.md`, and `results/search_log.jsonl` exist.
- The search log is valid as an empty JSONL stream and contains no fabricated
  attempts.
- Status reports no candidate metrics or validation claims.
- GitHub Actions checks required files, trailing whitespace, and JSONL search-log
  structure on pull requests and pushes to `master`.
- No reference, verifier, generator, optimizer, or candidate implementation has
  begun.

## Phase 1 — Reference, Matrix, Format, and Independent Verifier

Scope:

- Implement the normative Python bit-serial reference.
- Implement an independent reference RTL model.
- Generate the 32-by-96 GF(2) transformation matrix from the normative model.
- Define and parse the restricted structural XOR2 network format.
- Independently evaluate networks, canonicalize them, and recompute all frozen
  metrics.
- Preserve separately instantiated XOR2 nodes so fanout-aware physical
  duplication remains measurable.
- Check all-zero and 96 basis-vector exact equivalence.
- Add seeded testing over at least 100,000 random pairs.
- Add SAT/equivalence checking with Yosys or ABC.
- Test the verifier against deliberately broken circuits before optimization.

Validation gate G1:

- Python and RTL references agree on basis vectors and the seeded random corpus.
- Matrix reconstruction agrees with the normative bit-serial reference.
- Every required malformed-network fixture is rejected with a nonzero exit.
- A known-correct structural fixture passes exact, random, and formal checks.
- Metric unit tests cover alias propagation, preservation of intentional
  duplicate instances, dead-node removal/reporting, depth, fanout, and excess
  fanout.
- Clean-checkout commands are documented in the README.
- Reference, verifier, metric, randomized, and formal checks are integrated into
  the existing CI gate.
- Formal verification requires an explicit submitted-network path and validates
  the requested module against that parsed file.

Phase 1 implementation does not include baseline generation or any optimization
algorithm; those remain gated by G1 and begin in later phases.

## Phase 2 — Comparable Baselines

Scope:

- Generate independently expanded per-output equations.
- Generate balanced per-output XOR2 trees with no sharing.
- Normalize conventional Yosys/ABC synthesis output to the frozen XOR2 model.
- Implement greedy common-subexpression elimination.
- Verify and measure every baseline identically.

Validation gate G2:

- Every baseline passes the structural parser, 97 exact checks, at least 100,000
  seeded random tests, and formal equivalence.
- Metrics are produced only by the independent verifier from the generated
  artifacts whose timings they report.
- Reproduction commands and tool versions are recorded.
- External baseline metadata captures convention, width, gate model, metric
  definitions, and comparability.

The four local baselines are implemented as deterministic Phase 2 artifacts.
The Yosys/ABC flow rejects non-linear mapped cells and propagates paired NOT
phases while normalizing its output to the restricted XOR2 model. Phase 2 stops
after identical independent verification and does not begin Phase 3 search.

## Phase 3 — Deterministic Optimization

Scope:

- Implement GF(2)-vector-aware two-term and multi-term extraction.
- Implement Boyar–Peralta-style straight-line-program heuristics.
- Add depth-aware common-subexpression elimination.
- Treat common-subexpression merging as an explicit candidate transformation,
  never as metric normalization.
- Explore sharing versus depth and selected output-subset re-synthesis.
- Preserve the best verified candidate after every stage.
- Complete Candidate A with a bounded multi-seed stochastic tie-breaking pass
  over the deterministic GF(2)/CSE/Boyar–Peralta engine. This explicit
  Candidate A work package does not begin Candidates B or C.

Validation gate G3:

- Each attempt is appended to `results/search_log.jsonl` with parameters,
  runtime, starting/final metrics, verification outcome, and disposition.
- All retained candidates pass periodic independent verification.
- Candidate A, its checkpoint, and its one-candidate frontier are reproducible.
- A completed checkpoint can recover every requested result artifact and
  rejects conflicting append-only search logs.
- Resume reconciles an append-only log prefix that is ahead of its checkpoint
  without duplicating completed attempts.
- No invalid or unverified candidate appears on the valid frontier.

## Phase 4 — Stochastic and Local Search

Scope:

- Run broader simulated annealing or other stochastic local search beyond the
  bounded Candidate A tie-breaking pass completed in Phase 3.
- Run iterated local improvement from multiple recorded seeds.
- Re-synthesize selected output subsets.
- Investigate fanout-aware duplication and sharing/depth tradeoffs.
- Search depth bounds 8, and bounds 9 and 10 when required by the specification.

Phase 4 begins with a separate 10,000-seed Candidate A continuation over seeds
10,000 through 19,999. Its checkpoint and generated artifacts are kept under
`results/checkpoints/phase4_candidate_a_checkpoint.json` and `results/phase4/`
so the completed Phase 3 Candidate A result remains reproducible unchanged.
Long-running configured searches are executed manually when they may exceed
Codex's command-execution time limit; their checkpoint and append-only log
remain the source of resumable progress.
Each checkpoint accepts only one active optimizer process. A repair operation
may remove duplicate records only after checking that their functional outcomes
match and saving an explicit recovery copy.
Candidate B began from a verified depth-8 point found in the continuation;
Candidate C began from a verified depth-6 balanced-tree point. The recorded
manual refinement budgets completed sequentially: B used seeds 20,000 through
29,999 and C used seeds 30,000 through 39,999. Neither search found an
accepted improvement, so each class retains its verified starting incumbent.

Validation gate G4:

- Random seeds and compute budgets are recorded and reproducible.
- Candidate A, Candidate B, and Candidate C classes have verified best-found
  representatives or an explicit documented failure to find one.
- Depth-bounded candidates satisfy their claimed bounds under independent
  recomputation.
- The nondominated frontier is regenerated from verified metrics only.

G4 passed locally after the configured Candidate A continuation and Candidate
B/C budgets completed. This is a best-found result for the recorded searches,
not a global-optimality claim.

## Phase 5 — Exact Small-Subcircuit Improvement

The bounded single-cone SMT study over the verified Candidate B artifact is
complete. It selected 20 small high-fanout cones and searched only for strict
gate-count reductions. Seventeen cones were proven UNSAT for every smaller
implementation; three six-gate cones reached the one-second per-query limit
and remain inconclusive rather than negative certificates. No replacement was
found or integrated. The Z3 version, timeout, selected roots, candidate
verification evidence, and outcomes are recorded in the checkpoint, output
JSON, and append-only search log.

Scope:

- Select bounded, high-value subcircuits from verified candidates.
- Apply SAT/SMT search for gate removal, depth reduction, or constrained
  replacement.
- Integrate only exact, independently verified replacements.
- Record timeouts and negative results without treating them as certificates.

Validation gate G5:

- Every replacement has exact local-function evidence and full-network
  verification.
- Solver versions, constraints, limits, and outcomes are recorded.
- Any optimality claim is limited to the exact encoded problem and accompanied
  by a checkable certificate or unsatisfiability result.

G5 passed locally for this bounded study. Its negative results apply only to
the stated single-output cone encodings and timeout; they do not establish
global or whole-network optimality.

## Phase 6 — Final Verification, Comparison, and Reporting

Scope:

- Rebuild all artifacts from a clean checkout.
- Re-run structural, exact-basis, randomized, metric, and formal checks for all
  submitted candidates.
- Generate the Pareto frontier and metrics table.
- Research relevant published approaches and open-source generators.
- Document failed or misleading approaches and comparison limitations.
- Assess publishability without overstating novelty or optimality.

Validation gate G6:

- All required deliverables exist and are generated by documented commands.
- Every submitted candidate satisfies all acceptance criteria in `SPEC.md`.
- Candidate files, frontier JSON, metrics CSV, search log, and report agree.
- README commands work from a clean checkout.
- The report includes all required methodology, results, limitations, and
  reproduction sections.

## Planned Deliverable Layout

Implementation phases will populate the following structure; Phase 0 creates
only the experiment control files requested for setup:

```text
crc32-superopt/
├── README.md
├── reference/
│   ├── crc32_reference.py
│   └── crc32_reference.v
├── verifier/
│   ├── verify_network.py
│   ├── formal_equivalence.ys
│   └── test_verifier.py
├── generator/
│   ├── build_matrix.py
│   └── baseline_generator.py
├── optimizer/
│   ├── optimize.py
│   └── search_config.yaml
├── results/
│   ├── candidate_a_min_area.v
│   ├── candidate_b_depth8.v
│   ├── candidate_c_min_depth.v
│   ├── pareto_frontier.json
│   ├── metrics.csv
│   └── search_log.jsonl
└── report.md
```

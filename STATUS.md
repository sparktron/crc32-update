# CRC32 Superoptimization Status

Last updated: 2026-08-22

Current phase: Phase 0 — Experiment Structure

Current gate: G0

## Current Best Results

No circuits have been generated, measured, optimized, or accepted. There is no
current Pareto frontier and no best-found result.

| Candidate class | XOR2 count | Maximum depth | Verification | Status |
| --- | ---: | ---: | --- | --- |
| A — minimum gate-count search | — | — | Not run | Not started |
| B — depth at most 8 | — | — | Not run | Not started |
| C — minimum-depth search | — | — | Not run | Not started |

No baseline metrics exist yet.

## Completed Work

- Frozen experiment semantics, circuit model, metrics, verifier requirements,
  search-log contract, and acceptance criteria are recorded in `SPEC.md`.
- Development phases and validation gates are recorded in `PLAN.md`.
- `results/search_log.jsonl` has been initialized as an empty append-only log;
  there have been no optimization attempts to record.
- The repository README identifies the setup state and control documents.
- GitHub Actions CI validates required scaffolding, trailing whitespace, and the
  machine-readable search-log structure with read-only repository permissions.

## Not Started

- Normative reference implementation
- Independent RTL reference
- GF(2) transformation-matrix generator
- Structural-network parser and evaluator
- Independent metric calculator
- Deliberately broken verifier fixtures and verifier tests
- Randomized and formal equivalence infrastructure
- Baseline generation and measurement
- Deterministic, stochastic, depth-bounded, and exact-subcircuit searches
- Candidate netlists, Pareto frontier, metrics table, and final report
- Literature and open-source comparison research

## Unresolved Issues

- Confirm the available versions and capabilities of Yosys, ABC, and any SAT/SMT
  solver before choosing the formal-equivalence and exact-search command lines.
- Set and record concrete compute budgets for deterministic, stochastic, and
  solver-backed searches before those phases begin.
- Select reproducible random seeds and record the random generator/version before
  creating randomized verification corpora or search attempts.
- Confirm final artifact naming conventions before Phase 1. The
  `crc32-superopt/` label in the requested deliverable tree is treated as the
  repository root, not as a nested directory.

## Gate G0 Checklist

- [x] `SPEC.md` exists and freezes the experiment contract.
- [x] `PLAN.md` exists and serves as the development roadmap.
- [x] `STATUS.md` reports no unearned results or validation claims.
- [x] `results/search_log.jsonl` exists and contains no fabricated attempt.
- [x] README reflects the structure-only setup state.
- [x] GitHub Actions CI enforces the Phase 0 structure checks.
- [x] No implementation or optimization work has begun.

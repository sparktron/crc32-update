# CRC32 Update Circuit Optimization

This repository is the workspace for a reproducible search for optimized
combinational XOR2 networks implementing a 64-bit parallel reflected IEEE
CRC-32 state update.

The experiment is currently in the structure-only setup phase. No reference
implementation, verifier, optimizer, circuit candidate, or benchmark result has
been produced yet.

Experiment control documents:

- [`SPEC.md`](SPEC.md) freezes semantics, the permitted circuit model, metrics,
  and candidate acceptance criteria.
- [`PLAN.md`](PLAN.md) is the development roadmap and defines phase validation
  gates.
- [`STATUS.md`](STATUS.md) records completed work, current best results, and
  unresolved issues.
- [`results/search_log.jsonl`](results/search_log.jsonl) will contain one
  machine-readable record for every optimization attempt.

Regeneration, optimization, verification, and measurement commands will be
added only after the corresponding tools exist and have been validated.

## Continuous Integration

GitHub Actions runs the `CI` workflow for pull requests, pushes to `master`, and
manual dispatches. During the structure-only phase it checks that the required
control files exist, rejects trailing whitespace, and validates every nonempty
record in `results/search_log.jsonl` against the required log fields.

Circuit verification and optimization tests will be added to the same CI gate
when their implementations pass the corresponding phases in `PLAN.md`.

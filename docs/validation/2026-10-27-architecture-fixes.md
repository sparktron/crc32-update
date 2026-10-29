# Architecture fix validation — 2026-10-27

Validated locally in the isolated managed worktree
`/home/mythos/.codex/worktrees/architecture-fixes/crc32-update`, branch
`codex/architecture-fixes`, based on `890d136`. This records local validation before integration with later experiment
commits; it is not a CI or target-hardware result.

## Final command outcomes

- `python3 -B -m unittest discover`: **109 passed**, 0 failed, 0 skipped,
  **143.936 seconds**. The review baseline was 69 tests; all existing suites,
  including DCLO, ablation and Kraft-slack, remain discovered.
- `python3 -B -m verifier.build_results --check --require-spec-minimum`:
  **passed**, exit 0. All five submissions and all four committed baselines
  passed structural/exact/random/formal verification; three distinct Pareto
  circuits matched the committed derived files.
- `python3 -m black --check` on the eight modified/new Python source and test
  files: **passed**. Those files are `optimizer/{search_lifecycle,depth_bounded,
  optimize,refine_candidates,test_search_lifecycle,test_runner_lifecycle}.py`
  and `verifier/{build_results,test_build_results}.py`.
- `python3 -m ruff check --no-cache` on the same files: **passed**.
- `bash -n scripts/clean_rebuild.sh`: **passed**.
- `git diff --check` and a trailing-whitespace scan including untracked new
  documentation/source files: **passed**.

The final suite and publication check were repeated after the final source
edit. Earlier runs exposed and resolved the historical DCLO log-only recovery
case and the expected C0 identity-metadata mismatch. Those failed checks were
investigated rather than treated as numerical-result changes.

## Historical replay and baseline provenance

Replay into a temporary directory reproduced these committed artifacts
byte-for-byte, without appending search attempts:

- Phase 3 Candidate A, using
  `python3 -B -m optimizer.optimize --replay-frontier results/phase3/candidate_a_frontier.json --artifact <temporary-file>`.
- Phase 4 Candidate A, using the corresponding Phase 4 frontier.
- B and C0 starting points, using
  `python3 -B -m optimizer.phase4_candidates --replay-dir <temporary-directory>`.
- B7, using
  `python3 -B -m optimizer.depth_bounded --depth-cap 7 --replay-seed 40505 --artifact <temporary-file>`.
- Candidate C, using cap 6 and seed 56140.

`generator.baseline_generator` regenerated all four baselines into a temporary
directory with generation timings. Each was byte-identical to its committed
artifact on this host, including ABC. `verifier.verify_baselines` then verified
those fresh files with 97 exact vectors, 100,000 random vectors using seed
`0xC32A5EED`, and formal equivalence. The publication check separately measured
and proved the committed artifacts and checked every stable metric against
`results/baseline_metrics.csv`, excluding runtime columns.

The published objective tuples below are `(XOR2, depth, max fanout, excess >4)`:

- `independent_per_output`: `(1390, 51, 20, 1038)`.
- `balanced_per_output`: `(1390, 6, 20, 1038)`.
- `greedy_cse`: `(454, 9, 6, 11)`.
- `yosys_abc`: `(1123, 7, 15, 536)`.

All five submissions' independently measured metrics were also compared with
their existing records and were unchanged. The physical-identity correction
changes only C0's hash from `0c80bfcc8e2b` to `103832014152`; the report, CSV and
JSON identity references were updated together. Its 1,390 gates, depth 6,
fanouts and dominated status did not change. The three frontier IDs, metrics
and memberships did not change. No numerical experiment history was rewritten.

## Regression evidence

- F1: duplicate `n31` in the committed depth-6 circuit, retain six consumers,
  and move one versus three to the duplicate. Both circuits pass all 97 exact
  vectors, have 471 gates and excess fanout 21 versus 20, receive distinct
  identities, and retain the correct frontier membership. Renaming and XOR pin
  reversal preserve identity. Conflicting measurements and shortened-ID
  collisions are rejected.
- F2: running/completed missing or conflicting logs, stale counters,
  journal-prefix conflicts, incumbent conflicts, output restoration and
  validated completed-log copying are covered. Invalid resumes preserve
  checkpoint bytes. Completed runners restore outputs without seed execution.
  The historical DCLO complete-log/no-checkpoint recovery path remains valid.
- F3: discovery includes every suite. The existing invalid-circuit and formal
  rejection tests passed; the rebuild's subsequent formal checks remain.
- F4: a temporary CSV with a false baseline gate count is rejected after
  actually measuring and proving the committed netlist. Runtime changes do
  not invalidate structural provenance. Fresh ABC output is kept separate from
  the committed artifact behind the published comparison.
- F5: every public seeded runner is exercised with worker failure, formal-tool
  failure and inconsistent verifier metrics. Journals retain failure reasons,
  false acceptance/verification status and nullable metrics. Retries have
  distinct IDs and do not inflate the completed prefix. SIGKILL recovery uses
  a real child process. Checkpoint-replacement and partial-terminal-write
  failures recover without rewriting earlier history. Candidate A rejects a
  worker source differing from the replayed source that receives the proof.
- F6: a real two-process pool with twelve seeds fails on the first parent
  acceptance and dispatches at most two trials. A separate real-pool test
  confirms ordered seed processing and incumbent selection. Cancellation stops
  refilling, cancels pending futures and waits only for the dispatched cohort.
- Additional risks: incomplete final records are backed up before recovery;
  interior and complete malformed records are rejected; source/configuration,
  matrix, strategy inputs and tool-version identity changes reject resume.

## Toolchain and remaining limits

Observed versions: Python **3.10.12**; Yosys **0.9**, git SHA `1979e0b`;
UC Berkeley ABC **1.01**, compiled **2022-01-29 01:26:07**; Z3 **4.8.12**.
New run manifests persist these versions. Pinning/containerization and
portability across untested releases remain unvalidated.

Completed historical checkpoints remain readable, but an unfinished legacy
budget without an immutable manifest cannot establish its old source identity
and is refused by this implementation. Existing processes in the untouched
original checkout can continue with their already loaded historical code.
A stuck dispatched worker may delay cancellation; forced termination of
individual process-pool workers is not attempted. SIGKILL is detected on the
next valid resume. Filesystem/power-loss recovery and hardware performance are
not established by these tests.

**Not run:** hours-long search budgets, the complete clean-clone rebuild for
this uncommitted patch, remote CI, or hardware validation. The component tests,
formal/result checks, baseline rebuild and historical replays above were run.

After reviewing and committing this branch, run the remaining clean-clone gate
manually from this worktree:

```bash
set -o pipefail
scripts/clean_rebuild.sh codex/architecture-fixes 2>&1 | tee /tmp/crc32-architecture-clean-rebuild.log
```

The branch revision must include the fixes first. Progress is recorded in
`/tmp/crc32-architecture-clean-rebuild.log`; the script regenerates into an
automatically removed temporary checkout. The validation command is safe to
rerun from the beginning and does not run or resume optimization seed budgets.

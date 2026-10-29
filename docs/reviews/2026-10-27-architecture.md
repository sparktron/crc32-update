# REPOSITORY AUDIT: `crc32-update`

## 1. Executive Summary

- **What it is:** A reproducible research pipeline for reflected IEEE CRC-32 updates over 64 data bits, optimizing physical XOR2 networks and publishing independently verified metrics and a Pareto frontier.
- **Stack:** Python standard library, structural Verilog, Yosys/ABC, SMTBMC/Z3, Bash, GitHub Actions, JSONL checkpoints and result records.
- **Maturity:** Research tooling with strong candidate verification and remaining experiment-lifecycle defects. Hardware implementation and physical performance were not evaluated.
- **Size:** The opening index contained 210 source/data files, including 30 Python and 151 Verilog files; generated results dominate the file count. LOC was not measured.
- **Review date:** 2026-10-27. Review started at `a07cf1a`; another session committed `5a235d5` during the review. The inspected core verifier, runner, and rebuild files were unchanged between those commits. The ablation suite was repeated after that commit.
- **Top 5 findings:**
  1. **P1:** Physical circuits with different fanout objectives can receive the same structural fingerprint.
  2. **P2:** Resuming a bounded search with a different log path resets a completed checkpoint and repeats completed seeds.
  3. **P2:** CI's rebuild command executes only 58 of the 69 available tests.
  4. **P2:** Regenerated baseline metrics are not checked against the baseline metrics used in the published comparison.
  5. **P2:** Failed search attempts can exit without an attempt record. A separate confirmed shutdown issue can also finish an entire queued budget after verification has failed.

**Validation performed:**

- `python3 -B -m unittest discover`: **69 tests passed**, 111.141 seconds.
- `python3 -B -m verifier.build_results --check --require-spec-minimum`: **passed**. All five submitted artifacts were formally proved, and regeneration matched the recorded three-circuit frontier.
- `python3 -B -m unittest optimizer.test_ablation`: **5 tests passed**, 54.557 seconds, after the concurrent ablation commit.
- Recomputed all four committed baselines' four Pareto objective metrics from their actual netlists: all matched the CSV.
- Isolated fault-injection reproductions confirmed the fingerprint collision, checkpoint reset, missing failed-attempt record, and queued-work shutdown behavior.

**Scope:** Source review covered the restricted parser, normalized evaluation and metrics, formal runner, Candidate A and bounded search orchestration, result builder, CI, rebuild script, and control documentation. The tests exercised generators and the experimental searches. This was not a line-by-line audit of every DCLO, ablation, local-refinement, or SMT encoding. The hours-long search budgets and the complete clean-clone rebuild were not rerun. Passing checks establish the current candidate results, not absence of all bugs.

## 2. Architecture & Codebase Assessment

**Stack and structure.** The reference defines the frozen function, the generator derives its 32-by-96 GF(2) matrix, and optimizers build candidate DAGs. The independent parser/evaluator recomputes structure, exact linear equivalence, and metrics. Incumbents additionally undergo random testing and a proof against the separate RTL reference. JSONL attempts and checkpoints support replay; the result builder checks provenance and regenerates publication artifacts. See [verification_report](/home/mythos/repos/crc32-update/verifier/verify_network.py:553), [formal runner](/home/mythos/repos/crc32-update/verifier/run_formal.py:46), and [result builder](/home/mythos/repos/crc32-update/verifier/build_results.py:547).

**Strengths.** The restricted XOR2 language makes zero plus all 96 basis vectors an exact functional check. The metric calculator preserves physical gate instances and counts actual pin consumers. Formal verification targets the submitted file in an isolated temporary directory. Published candidates undergo fresh verification and provenance checks rather than trusting optimizer-reported metrics. Required candidate classes are checked against their actual objective ordering. See [normalized metrics](/home/mythos/repos/crc32-update/verifier/verify_network.py:241) and [class objectives](/home/mythos/repos/crc32-update/verifier/build_results.py:435).

**Weaknesses.** Lifecycle policy is distributed across large runner functions. Candidate A validates its recorded log path; the bounded runner does not. Failure journaling, cancellation, and recovery are coupled to incumbent verification. Circuit identity collapses information that the physical metric model deliberately preserves. CI uses a manual test list that has fallen behind the repository.

**Maintainability.** The major boundaries are sound. A focused refactor of search persistence and orchestration is justified; replacing the verifier or reorganizing all algorithms is not justified by this review. Preserve the separation between optimizer construction and independent measurement.

## 3. Confirmed Bugs

### F1 — [P1] The structural fingerprint loses physical consumer identity

- **Confidence:** Confirmed by an isolated reproduction using the committed depth-6 CRC circuit.
- **Location:** [structural_fingerprint](/home/mythos/repos/crc32-update/verifier/build_results.py:193), especially labels derived solely from child labels; [circuit deduplication](/home/mythos/repos/crc32-update/verifier/build_results.py:577).
- **Description:** Identical gate instances receive identical labels. The sorted node-label multiset preserves the number of duplicate gates but loses which duplicate drives each consumer. Different physical fanout distributions therefore hash identically.
- **Evidence:** Duplicated `n31` in the 470-gate depth-6 candidate. Routing one of its six consumers to the duplicate versus routing three produced two 471-gate circuits. Both passed the restricted parser and all 97 exact checks. Their excess fanout was **21 versus 20**, but their full SHA-256 structural fingerprints were identical. This is a representation collision, not a cryptographic collision.
- **Why it matters:** `circuits.setdefault(circuit_id, metrics)` keeps the first metric object for a fingerprint. A later physical circuit with a better fanout objective can be collapsed into it, losing a valid Pareto point or assigning the wrong frontier membership. The current submitted set still passed its complete verification; this reproduction does not demonstrate an error in the present three published points.
- **Fix:** Define identity over the instance-level DAG, including consumer connectivity and ordered primary outputs. Use a graph representation or canonicalization that preserves sharing and duplication. A conservative first step is to retain separate artifacts unless physical equivalence is established, and reject a repeated fingerprint with conflicting objective metrics. Adding metrics to the key alone is not a complete structural-identity fix.

### F2 — [P2] A different log path silently resets bounded-search progress

- **Confidence:** Confirmed with a temporary completed checkpoint and an empty replacement log.
- **Location:** [run_bounded_search](/home/mythos/repos/crc32-update/optimizer/depth_bounded.py:310), checkpoint configuration validation and reconstruction from `logged_attempts`.
- **Description:** Existing checkpoint configuration is checked, but its `search_log_path` is ignored. Progress is reconstructed entirely from the newly supplied path and immediately written back to the checkpoint.
- **Evidence:** Requested the same completed one-seed budget with a different, absent log path. The checkpoint changed from `completed`, one seed, and an incumbent to `running`, zero seeds, and no incumbent; the already completed seed was dispatched again. The original log remained intact elsewhere.
- **Why it matters:** A typo or attempted log relocation can discard the checkpoint's progress metadata and repeat expensive work without warning.
- **Fix:** Resolve and validate the recorded log before any checkpoint write. Refuse a conflicting path, or provide an explicit completed-run relocation operation that checks/copies the recorded log before restoring artifacts. Candidate A already contains a useful pattern in [run_search](/home/mythos/repos/crc32-update/optimizer/optimize.py:550).

### F3 — [P2] The CI gate omits the DCLO and ablation suites

- **Confidence:** Confirmed by loading both test inventories without running them a second time.
- **Location:** [manual unit-test list](/home/mythos/repos/crc32-update/scripts/clean_rebuild.sh:72), invoked by [CI](/home/mythos/repos/crc32-update/.github/workflows/ci.yml:140).
- **Description:** The rebuild explicitly lists seven test modules. It omits `optimizer.test_dclo` and `optimizer.test_ablation`.
- **Evidence:** The listed modules contain **58 tests**; discovery contains **69 tests**. All 69 passed locally, but the additional 11 are outside the checked-in CI command.
- **Why it matters:** Regressions in the newer experiment code can pass the repository's normal gate.
- **Fix:** Use `python3 -B -m unittest discover` in the rebuild script. If any future test intentionally belongs to a slower tier, define that tier explicitly and verify that ordinary discovery is covered by CI.

### F4 — [P2] Published baseline comparisons are not tied to rebuilt baseline measurements

- **Confidence:** Confirmed validation gap; no current incorrect baseline objective metric found.
- **Location:** [baseline generation and verification](/home/mythos/repos/crc32-update/scripts/clean_rebuild.sh:98), [CSV comparison reader](/home/mythos/repos/crc32-update/verifier/build_results.py:525), and [use of committed baseline metrics](/home/mythos/repos/crc32-update/verifier/build_results.py:634).
- **Description:** The clean rebuild verifies fresh baselines and writes a temporary metrics CSV, but never compares its stable metric columns with `results/baseline_metrics.csv`. Final results instead read the committed CSV. Consequently a stale committed baseline CSV and consistently regenerated frontier can agree with each other while disagreeing with the verified baseline artifacts.
- **Evidence:** `_baseline_comparison` accepted an isolated CSV row reporting one gate and depth one without any artifact measurement. Inspection of the rebuild confirms the missing comparison. Independently recomputing the four objective fields from all four current committed netlists found **no mismatch**.
- **Why it matters:** The gate does not fully support the claim that published baseline comparisons are regenerated from the artifacts checked during that rebuild.
- **Fix:** Compare deterministic baseline metrics against freshly verified netlists, excluding runtime columns. For the intentionally toolchain-dependent ABC baseline, separately verify the committed netlist used by the published table and report the regenerated tool-version-dependent baseline as a separate observation.

### F5 — [P2] Failed attempts can disappear from the search journal

- **Confidence:** Confirmed with injected worker and verifier failures.
- **Location:** [bounded runner](/home/mythos/repos/crc32-update/optimizer/depth_bounded.py:401), verification before record construction and append; related policy in [Candidate A runner](/home/mythos/repos/crc32-update/optimizer/optimize.py:629).
- **Description:** Worker iteration and incumbent verification can raise before an attempt record is constructed. The `finally` block only shuts down the executor; it does not record the failed attempt.
- **Evidence:** Both injected failures propagated with no attempt log created. This conflicts with the explicit failed/interrupted-attempt requirement in [SPEC Section 9](/home/mythos/repos/crc32-update/SPEC.md).
- **Why it matters:** Failure evidence and consumed effort vanish; a resumed run can repeatedly encounter the same failing seed without a durable explanation.
- **Fix:** Give trial execution and acceptance a structured outcome, and record ordinary worker/verification failures with `verification_passed=false`, `accepted=false`, an error reason, and nullable metrics. Define retry identifiers and resume semantics explicitly so a failure record cannot be confused with a successful completed seed. Handle user cancellation separately and preserve its reason.

### F6 — [P2] Parent-side verification failure drains queued search work before exit

- **Confidence:** Confirmed with eight lightweight worker tasks and two processes.
- **Location:** [bounded executor and shutdown](/home/mythos/repos/crc32-update/optimizer/depth_bounded.py:382), [Candidate A executor and shutdown](/home/mythos/repos/crc32-update/optimizer/optimize.py:608).
- **Description:** The executor receives the seed range through `map`; parent-side verification can fail while the result iterator still owns queued tasks. The unconditional `executor.shutdown()` waits for those tasks.
- **Evidence:** Failed verification of the first returned candidate. All **eight of eight** instrumented workers still executed before the exception returned, while no failed-attempt record was written. Worker-result exceptions can behave differently because the map iterator itself may cancel pending futures; the confirmed case is a failure in the parent verifier.
- **Why it matters:** A failed run can continue consuming its queued compute budget and hold its caller's resources during shutdown. With the documented large budgets this can delay recovery substantially.
- **Fix:** Keep a bounded number of futures in flight, cancel work that has not started on parent-side failure/cancellation, and define how running workers are stopped or allowed to finish. Merely adding `cancel_futures=True` to a very large eagerly submitted process queue is not a complete cancellation strategy.

## 4. Likely Bugs / Risk Areas

- **Possible — interrupted JSONL writes block recovery.** [The append helper](/home/mythos/repos/crc32-update/optimizer/refine_candidates.py:104) uses ordinary buffered file appends; [the bounded reader](/home/mythos/repos/crc32-update/optimizer/depth_bounded.py:285) parses every line with no tail recovery. A kill or storage failure during a large record write could leave a partial last record. Preserve the damaged stream and test a recovery policy that handles only an incomplete final record while continuing to reject interior corruption. Normal post-append checkpoint interruption is already tested.
- **Possible — mixed code versions across a resumed budget.** [Bounded checkpoint configuration](/home/mythos/repos/crc32-update/optimizer/depth_bounded.py:340) captures algorithm/version labels and numeric settings but not a source or matrix digest. Replaying the winning seed catches some changes, not changes affecting only previously rejected seeds. Bind future runs to an immutable experiment manifest and refuse incompatible resumes. This review did not demonstrate that any recorded experiment mixed versions.
- **Unverified toolchain portability.** [CI installs distribution tool packages](/home/mythos/repos/crc32-update/.github/workflows/ci.yml:133), and [the rebuild explicitly tolerates a different ABC baseline](/home/mythos/repos/crc32-update/scripts/clean_rebuild.sh:108). Pin or record Python, Yosys, ABC, and Z3 versions for publication-grade reproduction. No toolchain-induced failure was observed here.

## 5. Test Coverage Gaps

**Critical**

- **Target:** `verifier/build_results.py`. Add an integration regression using duplicate physical gates with different consumer splits and different fanout objectives. Require distinct circuit identity and correct frontier membership. The parser's existing duplicate-instance tests do not exercise result deduplication.
- **Target:** `optimizer/depth_bounded.py`. Test completed and running resumes with missing, relocated, conflicting, and truncated logs. Require that invalid resumes leave the original checkpoint byte-for-byte intact.
- **Target:** `scripts/clean_rebuild.sh` and `verifier/build_results.py`. Change a baseline metric in a temporary result set and assert the gate rejects it after measuring the associated netlist.

**Medium**

- **Target:** search runners. Inject worker exceptions, exact-verification failures, formal-tool failures, and parent cancellation. Assert failure journaling, correct resume behavior, and bounded work after cancellation. Include a real small process-pool test because mocks alone miss shutdown semantics.
- **Target:** CI test selection. Ensure newly added `test_*.py` modules are discovered automatically.

**Long-tail**

- **Target:** journal/checkpoint helpers. Exercise partial final writes, malformed interior records, storage errors during replacement, and recovery from each ordering boundary. These are reliability tests, not a reason to weaken fail-closed validation of corrupted provenance.

## 6. Improvement Opportunities

**Quick wins — under one day**

- **Discover all tests. Impact: High. Effort: Low.** Replace the manual module list in [clean_rebuild.sh](/home/mythos/repos/crc32-update/scripts/clean_rebuild.sh:72).
- **Reject mismatched log paths before mutation. Impact: High. Effort: Low.** Bring [bounded resume](/home/mythos/repos/crc32-update/optimizer/depth_bounded.py:310) in line with Candidate A's recorded-log policy.
- **Fail on conflicting metrics for one circuit fingerprint. Impact: High. Effort: Low.** Add a guard at [result deduplication](/home/mythos/repos/crc32-update/verifier/build_results.py:577), while implementing the complete identity fix. Keep distinct physical artifacts conservatively.
- **Verify the published baseline table. Impact: Medium. Effort: Low.** Compare stable measured fields, not machine-dependent timing strings.

**Medium refactors — roughly one to three days each**

- **Correct physical circuit identity. Impact: High. Effort: Medium.** Give instance connectivity a faithful representation, test rename and input-order invariance, and test that consumer redistribution remains distinct. Keep metric recomputation independent.
- **Extract a shared search lifecycle. Impact: High. Effort: Medium.** Share configuration validation, recorded-log resolution, structured outcomes, incumbent acceptance, persistence, and bounded scheduling across [Candidate A](/home/mythos/repos/crc32-update/optimizer/optimize.py:510) and [bounded search](/home/mythos/repos/crc32-update/optimizer/depth_bounded.py:310). Keep trial construction and objective ordering strategy-specific. Migrate one runner at a time and retain compatibility with historical records.
- **Version the journal schema. Impact: Medium. Effort: Medium.** Distinguish trial generation, exact checks, full incumbent acceptance, failures, and retries. Make the append-only journal authoritative and the checkpoint a recoverable summary.

**Strategic upgrades — only as experiment volume grows**

- **Immutable run manifests. Impact: Medium. Effort: Medium to High.** Record source revision/dirty digest, frozen-matrix digest, strategy version, seed budget, validation parameters, and tool versions once per run. Reference that identity from both checkpoints and records. A service or database migration is not required for the current repository size.

## 7. Feature Recommendations

- **Read-only resume preflight.** Fits the existing manually launched searches and benefits the operator of long budgets. Resolve the recorded log, validate its prefix/configuration and incumbent artifact, and print what would be resumed or restored without rewriting state. Implement around the shared lifecycle. **Priority: High.** [Target](/home/mythos/repos/crc32-update/optimizer/depth_bounded.py:310).
- **Machine-readable gate summary.** Fits the existing reproduction workflow and benefits reviewers. Report discovered test count, artifact hashes, measured baseline consistency, formal outcomes, and run identities in one generated validation record. Treat it as evidence from a particular execution, not a hand-maintained success flag. **Priority: Medium.** [Target](/home/mythos/repos/crc32-update/scripts/clean_rebuild.sh:72).

## 8. Security / Reliability / DX Findings

**Security.** No critical security issue was identified in the reviewed local verification/orchestration paths. The formal runner uses argument lists, validates the requested module, and copies the submitted file into an isolated temporary directory. This was not a dependency or complete external-generator security audit. [Evidence](/home/mythos/repos/crc32-update/verifier/run_formal.py:46).

**Reliability.** The main weaknesses are physical circuit identity, checkpoint/log association, unrecorded failures, eager work scheduling, and the baseline gate gap described above. Existing exact and formal candidate validation remains strong.

**Developer Experience.** The control documents explain semantics, replay, and long-running manual commands well. CI's manual test list contradicts the README's claim that the clean rebuild runs every unit/rejection test. Toolchain-dependent baseline handling should clearly separate verification of published artifacts from observing fresh synthesis output.

## 9. Prioritized Action Plan

**Phase 1 — Fix now**

1. Correct or conservatively disable circuit deduplication that loses physical connectivity; add the fanout regression.
2. Reject a bounded resume against a different/missing recorded log before any checkpoint mutation.
3. Replace CI's explicit test module list with discovery.
4. Tie published baseline metrics to verified committed baseline artifacts.

**Phase 2 — Next improvements**

1. Record failed and interrupted attempts with explicit retry semantics.
2. Bound in-flight work and implement failure/cancellation cleanup.
3. Add real process-pool and persistence fault-injection tests, including malformed final-log records.

**Phase 3 — Strategic upgrades**

1. Extract the shared search lifecycle while retaining independent strategy and verifier boundaries.
2. Introduce immutable run manifests for new experiments, preserving historical logs.
3. Add preflight and machine-readable gate summaries when the shared lifecycle exists.

## 10. Top Patch Targets

1. [verifier/build_results.py](/home/mythos/repos/crc32-update/verifier/build_results.py:193) — physical identity, deduplication safety, and baseline measurement provenance.
2. [optimizer/depth_bounded.py](/home/mythos/repos/crc32-update/optimizer/depth_bounded.py:310) — resume validation, failure records, and bounded scheduling.
3. [scripts/clean_rebuild.sh](/home/mythos/repos/crc32-update/scripts/clean_rebuild.sh:72) — discovery and stable baseline metric checks.
4. [optimizer/optimize.py](/home/mythos/repos/crc32-update/optimizer/optimize.py:510) — share the corrected lifecycle and cancellation policy without altering trial mathematics.
5. [verifier/test_build_results.py](/home/mythos/repos/crc32-update/verifier/test_build_results.py) and [optimizer/test_depth_bounded.py](/home/mythos/repos/crc32-update/optimizer/test_depth_bounded.py:45) — add regressions at the failing boundaries.

## 11. Overall Verdict

- **What's solid:** Frozen semantics, restricted structural validation, independently recomputed metrics, exact linear checking, formal equivalence, deterministic winning-seed replay, and the current five submitted artifacts.
- **What's fragile:** Physical DAG deduplication and the surrounding search/reproduction lifecycle.
- **Production-ready today?** **With caveats for controlled research use.** The current result check passes. The process is not ready to be treated as unattended, interruption-safe experiment infrastructure.
- **Must change before broader use:** Fix physical identity and resume mutation, include every test in CI, verify published baseline metrics from their artifacts, and define durable failure/cancellation behavior.

No implementation fix was made during this review. The unresolved findings are recorded here for continuation; the active experiment status and results were left untouched. Start a follow-up with F1's physical-instance regression, then F2 and CI discovery.

## 12. Implementation follow-up — 2026-10-27

The review above is retained as the historical finding record. F1–F6 and the
three additional reliability risks have now been addressed on the isolated
`codex/architecture-fixes` worktree, based on `890d136`. The original checkout's
active ablation processes, search log, checkpoints and results were not edited.
See [validation evidence](../validation/2026-10-27-architecture-fixes.md),
[lifecycle policy](../search_lifecycle.md), and the
[decision record](../decisions/2026-10-27-search-lifecycle.md).

- **F1 — resolved.** Duplicate-labelled circuits use an exact instance-graph
  canonicalization that retains consumer edges and ordered outputs. Circuits
  with unique recursive labels retain their safe historical encoding. The
  reproduced 471-gate `n31` splits measure excess fanout **21 versus 20**, have
  distinct identities and the correct frontier membership. Renaming and XOR
  input ordering remain cosmetic. Conflicting measurements for one identity
  and shortened-ID collisions fail closed. C0's derived ID changes from
  `0c80bfcc8e2b` to `103832014152`; all its metric values and its dominated status
  are unchanged. The three frontier IDs and objective values are unchanged.
- **F2 — resolved.** Shared read-only preflight validates configuration,
  recorded log location/contents, counters, retained incumbent and manifest
  before persistent changes. Missing/conflicting logs preserve checkpoint
  bytes. The journal can advance a stale summary, but a summary ahead of its
  journal is rejected. Completed budgets restore outputs without seed
  execution. Completed-log relocation is a validated copy that preserves the
  checkpoint's original association; running-log relocation is refused.
  Historical complete log-only bounded/DCLO recovery remains supported.
- **F3 — resolved.** `clean_rebuild.sh` uses `python3 -B -m unittest discover`.
  All existing formal and rejection checks remain. The final discovered suite
  passed **109 tests**, including DCLO, ablation and Kraft-slack.
- **F4 — resolved.** Published baseline comparisons independently measure and
  prove the actual committed netlists and compare all stable structural fields,
  including per-output depths, with the CSV. Timing values are excluded. A
  regression rejects an actually measured baseline with a stale CSV count.
  Fresh ABC synthesis is a separate observation; the committed ABC artifact
  behind the table is verified explicitly. All four committed baseline
  objective tuples matched, and fresh generation was byte-identical on this
  host, including ABC.
- **F5 — resolved within the documented recovery boundary.** Started and
  terminal events are synced with distinct IDs, retry numbers and immutable run
  identity. Worker/verification failures retain a reason, false verification
  and acceptance status, and nullable metrics. Only successful terminals count
  toward a seed budget. All three public seeded runners have failure
  regressions. SIGTERM/KeyboardInterrupt are journaled; a real SIGKILL
  regression demonstrates detection of an open start on resume. Partial
  journal-write and checkpoint-replacement failures preserve recoverable
  evidence. Historical rows and checkpoints are not rewritten.
- **F6 — resolved with an explicit running-worker policy.** The shared scheduler
  dispatches at most one future per worker and processes results in seed order.
  Refill occurs after parent verification and persistence. Failure/cancellation
  stops submission, cancels pending futures and lets dispatched workers finish
  their bounded cohort. A real two-process, twelve-seed regression fails the
  first parent acceptance and dispatches at most two trials. A separate real
  process test confirms deterministic processing and incumbent selection.

The additional risks are addressed as follows:

- **Incomplete final JSONL record:** preserve the entire damaged stream in a
  digest-named backup before atomic recovery of its valid prefix. Interior
  corruption, malformed terminated records and complete malformed final
  objects remain errors. A valid final object missing only a newline receives
  a separator. Failed appends stop subsequent writes so damaged tails do not
  become interior corruption.
- **Mixed implementation budgets:** new manifests bind source, configuration,
  frozen matrix, bound strategy inputs and tool versions; new events reference
  that identity. Incompatible resumes are rejected before mutation. Completed
  legacy budgets remain restorable. Unfinished legacy budgets lacking source
  identity cannot be extended under changed code; use the original loaded
  process or a separately named, disjoint new budget.
- **Toolchain provenance:** new manifests and rebuild output record Python,
  Yosys, ABC and Z3 versions. This host used Python 3.10.12, Yosys 0.9
  (`1979e0b`), ABC 1.01 (2022-01-29 build), and Z3 4.8.12. Pinning and
  portability across untested releases remain outside this validation.

Final validation: **109 tests passed in 143.936 seconds**;
`python3 -B -m verifier.build_results --check --require-spec-minimum` passed
with all five submissions and all four committed baselines formally proved
and three distinct Pareto circuits. Historical artifact replays and fresh
baseline regeneration were byte-identical. Black, Ruff, shell syntax,
`git diff --check` and new-file trailing-whitespace checks passed. No circuit,
objective value, seed, checkpoint or historical attempt row was changed.

Remaining limits: no clean-clone gate or remote CI run for this uncommitted
patch, no hours-long search rerun, and no target-hardware validation. A stuck
dispatched worker may delay shutdown. Process-interruption tests do not prove
power-loss or destroyed-journal recovery. The validation document gives the
exact manual clean-clone command to run after committing this branch. These
checks support the stated fixes and current results; they do not establish
that the system is bug-free.

## 13. PR integration — 2026-10-29

The patch was committed as `b87659c` and reconciled with master `4221a33`.
The combined tree passed **136 discovered tests in 237.961 seconds** and
`python3 -B -m verifier.build_results --check --require-spec-minimum`.
All five submissions and four committed baselines were proved, and three
distinct Pareto circuits matched publication data. The current 440-gate B7
and 465-gate C, split experiment logs, fresh-gate fallback and selected-trial
provenance were preserved. Only C0's derived identity metadata differs from
master; no numerical history, checkpoint or circuit was changed.

See [current validation](../validation/2026-10-29-architecture-pr.md).
The full clean-clone gate was not run locally; the PR's CI executes the
existing rebuild workflow. The lifecycle and hardware-validation limits above
remain in effect.

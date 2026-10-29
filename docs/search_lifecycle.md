# Seeded search lifecycle

Applies to Candidate A, Kraft-bounded search, DCLO, ablation, Kraft-slack, and
the B/C local-refinement runners. Trial construction, objective ordering, exact
worker checks, and full incumbent verification remain separate callbacks.

## Journal and retries

Historical JSONL rows and checkpoint formats are read without rewriting them.
New rows use `schema_version: 2`. Before dispatch, a synced `started` event has
an ID ending in `-started` and a shared `trial_id`. The terminal event has that
trial ID as its unique `attempt_id`. Its status is `succeeded`, `failed`,
`cancelled`, or `interrupted`. An incrementing `attempt_number` distinguishes
retries of the same seed. IDs are unique within the experiment journal.

Only successful terminals count toward `completed_seeds`; those seeds must form
a contiguous, unique prefix in processing order. Failed attempts do not consume
a seed from that prefix. Resume retries them with a higher attempt number.
The result builder understands both historical rows and new event/retry rows.

Workers perform independent structural and exact verification. Successful
non-incumbents report `verification_stage: exact`. Accepted incumbents must
additionally pass the random-vector and formal checks and agree with the worker
metrics; they report `verification_stage: full`. Failures have
`verification_passed: false`, `accepted: false`, an `error_reason`, and nullable
metrics. Worker failures and parent-verification failures identify their stage.
Unobserved runtimes remain null. Accepted artifacts have a content SHA-256.

The append helper flushes and fsyncs each event before checkpoint replacement.
The journal takes precedence over a stale checkpoint. A checkpoint ahead of
the journal is rejected. New checkpoints also bind the exact recorded journal
prefix with a byte count and SHA-256, while permitting later appended events.
A partial write error stops subsequent appends; recovery can then preserve and
repair the tail instead of embedding that partial record in the journal.

## Read-only resume validation

Configuration, recorded log location and contents, prefix completeness,
checkpoint counters, immutable identity, and the retained incumbent are checked
before checkpoint writes or journal recovery. A missing log, conflicting
replacement, counter ahead of the log, corrupt interior record, incompatible
identity, or altered retained artifact leaves the checkpoint intact.

New relative log paths are relative to the checkpoint directory and explicitly
marked as such. Historical Candidate A paths retain that convention; historical
bounded paths retain their original working-directory convention. Older
refinement/early bounded checkpoints lacking a recorded path use the supplied
path and their historical seed-prefix evidence. They cannot claim the stronger
path/digest guarantees available to new runs.

A running budget must resume with the same recorded log path. For a completed
budget, supplying a different log path means **copy**, not move/rebind: the
recorded source must exist and validate; an existing destination must be byte
identical, or the operation fails. An absent destination receives the validated
log. The checkpoint keeps its original association. Saved output artifacts are
restored independently of output location, without dispatching or replaying any
completed seed. Independent historical seed replay remains available through
the explicit replay CLI options and the publication result builder.

## Interruption and cancellation

The scheduler dispatches at most `workers` futures. Results are processed in
seed order. It refills only after parent verification, the terminal append, and
the checkpoint update. This keeps incumbent selection deterministic across
worker counts.

On worker failure, parent verification failure, KeyboardInterrupt, or SIGTERM,
submission stops. Pending futures are cancelled. Already dispatched workers may
finish; shutdown waits for this bounded cohort, discards its results, and never
drains the remaining seed budget. Python does not provide a portable safe kill
operation for individual process-pool futures. A stuck dispatched worker can
therefore still delay shutdown and may require operator intervention.

SIGTERM is converted to normal cancellation in the parent main thread. SIGKILL
cannot be caught: a synced start without a terminal is recorded as interrupted
on the next valid resume, then retried. An interruption before dispatch can
leave the same open start; the reason accurately says that no terminal was
observed. This is process-interruption recovery, not a guarantee against power
loss, filesystem failure, or destruction of the journal. CLI locks remain the
concurrency boundary; direct Python callers must provide exclusive ownership.

An incomplete, unterminated final JSONL record can be removed only after a
byte-for-byte copy of the entire damaged stream is fsynced to
`<log>.damaged-<sha256>`. The valid prefix replaces the log atomically. Interior
corruption, malformed newline-terminated records, and complete malformed final
objects are rejected. A complete final JSON object lacking only its newline
gets a separator before the next append.

## Immutable experiment identity

New checkpoint manifests record configuration, source SHA-256 over optimizer,
generator, reference, and verifier implementation files, the derived frozen
matrix SHA-256, strategy inputs (including trial identity/module name or the
refinement starting-artifact digest), and Python/Yosys/ABC/Z3 versions.
Every new event references the manifest identity. Workers may be changed in
number without changing a deterministic budget; verification settings, trial
inputs, source, matrix, and tools must match to resume.

Completed legacy budgets can restore their outputs using their existing
evidence. The early bounded/DCLO log-only recovery path also accepts a complete
historical successful prefix plus its retained incumbent and reconstructs a
completed checkpoint without dispatching seeds or rewriting history. An
incomplete or new-schema journal without its checkpoint is rejected.
If an unfinished legacy budget lacks a manifest, its original source
identity cannot be established retrospectively. This implementation refuses to
extend it. Keep an already loaded historical process in its original checkout;
new implementation work requires a separately named, disjoint seed budget and
new checkpoint. Do not add a guessed manifest or rewrite old experiment rows.

## Published baseline provenance

The result builder measures every committed baseline netlist with structural,
exact, random, and formal checks, then compares every stable structural metric
with the published CSV, including per-output depths. Runtime columns are
excluded. All baseline names must appear exactly once. A stale metric fails
before publication regeneration can accept it.

The clean rebuild regenerates and verifies fresh baselines as a separate
observation. Deterministic generators must reproduce committed files exactly.
Fresh ABC output may differ by tool version; the committed ABC netlist is
separately verified as the artifact behind the published table. Fresh ABC
output never replaces its published metrics implicitly. The rebuild prints
tool versions; each new search manifest also records them. Toolchain pinning is
still optional, and portability across untested tool releases is not claimed.

# Search lifecycle and historical provenance

Date: 2026-10-27. Status: implemented on `codex/architecture-fixes`.

## Context

Architecture review F2, F5 and F6 reproduced progress loss on resume,
unrecorded failures and eager process-pool draining. Existing experiments have
valuable append-only evidence but lack an immutable implementation identity.

## Decision

Use one shared journal/checkpoint/scheduler implementation for the seeded
runners. Sync started and terminal events with distinct IDs; count only
successful terminals and give retries increasing attempt numbers. Keep
construction, strategy objective ordering and independent acceptance checks
outside that lifecycle. The journal is authoritative over stale summaries.

Validate recorded paths, journal contents, retained artifacts and immutable
source/configuration/matrix/tool identity before writes. Permit completed-log
copying after validation, while preserving the original association. Preserve a
full damaged stream before recovering only an incomplete final record.

Dispatch at most one future per worker, process seeds in order, and refill
after parent acceptance. Cancel pending work on failure and let dispatched
workers finish their bounded cohort. Avoid private executor process internals
and forced worker termination.

Keep historical rows and checkpoints intact. Restore completed legacy budgets,
including the prior bounded/DCLO complete-log recovery path. Refuse to extend
unfinished legacy budgets when their original implementation cannot be proved;
use a new, separately named, disjoint budget instead of guessing provenance.

## Consequences and evidence

Retries and abrupt interruption become observable without conflating failures
with completed seeds. A real two-process regression fails the first parent
verification and observes at most two dispatched tasks from a twelve-seed
budget. Fault injection covers worker/formal failure, SIGKILL, checkpoint lag,
partial terminal writes, damaged-tail recovery and invalid-resume immutability.

There is extra fsync overhead per event. A stuck dispatched worker can delay
shutdown, and process-crash recovery does not guarantee resilience to power
loss or destruction of journal evidence. Legacy compatibility does not invent
missing historical identities. Tool versions are recorded rather than pinned;
hardware and untested toolchain portability remain outside this validation.

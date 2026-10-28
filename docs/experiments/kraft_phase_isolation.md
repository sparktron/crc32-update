# Experiment: isolate Kraft-slack scoring by search phase

Pre-registered 2026-10-28 before any new-arm results were inspected.
Base: `d50c4257d2de831ca99a24d7ce177423cf1cabf4`.
Branch: `codex/kraft-phase-isolation`; the implementation and this protocol
will be committed before the budget starts. The run manifest records that SHA.

## Question and hypotheses

Does the depth-7 penalty of slack scoring arise during sharing or finishing,
and can a hybrid improve on the best existing scoring rule at each depth cap?

- H1: at cap 7, finishing-only accounts for at least half of the both-minus-
  baseline mean penalty, while sharing-only loses less than 0.5 gates against
  baseline. Refuted if either condition fails, or both has no positive penalty.
- H2: at cap 6, sharing-only retains at least half of the baseline-minus-both
  mean gain. Refuted if it does not, or both has no positive gain.
- H3: at least one hybrid qualifies for stage 2 and confirms a mean improvement
  of at least 0.5 gates with paired normal-approximation z <= -3 against its
  comparator on fresh seeds. Refuted if none qualifies or none confirms.
- Frontier target, separate from H3: <=439 XOR2 at depth 7 or <=464 at depth 6.
  Missing this target does not refute a distributional improvement.

## Frozen design

Four arms, with all other code and random-number calls unchanged:
`baseline` = depth-first in both phases; `sharing` = slack only in sharing;
`finishing` = slack only in finishing; `both` = slack in both phases.
All use the current fresh-gate finishing fallback, including the controls.
Historical algorithms and artifacts are unchanged.

Stage 1 uses the same 1,000 seeds for every arm at a cap:
cap 7 = 300000..300999; cap 6 = 320000..320999. These are fresh ranges.
Matched seeds control initial RNG state, not every subsequent decision:
different sharing trajectories may consume different numbers of draws.
Finishing-only must enter finishing with exactly baseline's sharing state and
RNG state; both must match sharing-only at that boundary, for every trial.
No extra draws, phase resets or threshold tuning are allowed.

Stage-2 comparator: baseline at cap 7, both at cap 6. A hybrid qualifies only
if its paired mean difference is <=-0.5 gates and paired z <=-3 in stage 1.
At most one hybrid per cap advances: lowest mean difference, then arm name.
The chosen hybrid and its comparator each run the same 10,000 fresh seeds:
cap 7 = 310000..319999; cap 6 = 330000..339999. No winner means no stage 2.
Normal approximations are selection criteria, not exact probability claims;
report paired standard errors and approximate 95% intervals as well.
The fresh-seed confirmation is required before claiming a method improvement.

## Provenance, diagnostics and verification

Environment: Python 3.10.12, Linux x86_64, Intel i9-10900K (20 logical CPUs),
Yosys 0.9 (`1979e0b`), Z3 4.8.12, 16 process workers.
Each trial is deterministic per arm/seed/cap; worker count does not change it.
Verification RNG: `0xC32A5EED`, 100000 vectors.
Before any budget: tests must show baseline and both reproduce their existing
builders byte-for-byte, with matching sharing states for the intervention pairs.

`optimizer.phase_isolation` wraps existing builders and the existing resumable
bounded runner. Every trial is independently checked. Every retained incumbent
passes exact-basis, 100000-vector randomized and formal equivalence checks.
Record created and retained gates per phase, per-row remaining Kraft budget
and term counts after sharing, and SHA256 digests of sharing and RNG states.
Created gates include subsequently pruned gates; retained phase counts sum to
the final gate count. These counts describe attribution, not a causal proof
that a phase's local decisions caused the entire final difference.

Raw append-only records: `results/search_logs/kraft_phase_isolation.jsonl`.
Checkpoints and retained incumbents: `results/checkpoints/phase_isolation/`.
Final artifacts, seed diagnostics and summaries: `results/phase_isolation/`.
Worker JSON spools are consolidated into ordered diagnostic JSONL files; only
logged trials are included. Interrupted runs resume from authoritative logs.
Spool diagnostics for speculative unlogged workers are not evidence.

Exact commands, from the repository root, in order:

```bash
python3 -B -m unittest optimizer.test_phase_isolation verifier.test_search_logs
python3 -B -m optimizer.phase_isolation --stage stage1 --workers 16
python3 -B -m optimizer.phase_isolation --stage stage2 --workers 16
```

## Observed

Pending. No budget has run at registration.

## Interpretation

Pending. Hypotheses and selection rules will not be changed after the run.

## Next decision

Use the phase attribution to choose the next algorithm change. Keep hypotheses
that fail as explicit negative evidence. Adopt no frontier replacement without
the repository's full provenance and independent verification requirements.

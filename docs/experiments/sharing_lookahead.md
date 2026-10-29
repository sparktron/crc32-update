# Experiment: bounded lookahead in sharing (frozen protocol)

Preregistered 2026-10-28, before experimental seed outcomes. Base commit:
`0026959e2c4a8bd3e8a3c260a247ab4b1b523d97`, the open PR #12 head.
Branch: `codex/sharing-lookahead`. This implementation and protocol must be
committed before collecting results. The run manifest records that commit.
Results and interpretation belong in `sharing_lookahead_results.md`; this
protocol remains immutable. Previous experiment: `kraft_phase_isolation.md`.

## Hypotheses and outcomes

H7 and H6, separately: the candidate improves mean retained physical XOR2 count
by at least 0.5 gates against the designated best existing scoring control,
with paired normal-approximation z <= -3, on a fresh confirmation budget.
Failure to screen or confirm refutes the respective hypothesis under this
operational definition. Overall H: at least one of H7/H6 confirms. A lower
best circuit alone cannot confirm a better search distribution.

Independent existence targets: <=439 gates at depth 7; <=461 at depth 6.
Report target attainment, best circuits and fanout separately from method
quality. No submitted frontier replacement is part of this experiment.

## Exactly one variant

Implementation: `optimizer.sharing_lookahead`, shortlist size **3**, continuation
depth **1** after the proposed root (two sharing moves total). No sweep.
Cap-7 control is historical bounded baseline; cap-6 control is historical
both-phases Kraft-slack, including the existing fresh-gate finishing fallback.
Controls delegate sharing selection and finishing to those builders unchanged.

At each sharing decision, first draw one historical control proposal, using
exactly that selector's RNG calls on the live builder. Form the shortlist:
proposal first, then the top distinct alternatives in the control's full
feasible new-pair ranking until size 3 (or exhaustion). Ranking is frequency
descending, then at cap 6 total Kraft increase ascending, then new gate depth,
result-vector weight, and pair. Cap 7 omits the Kraft key (equivalently zero).
Alternatives are not restricted to the proposal's randomly sampled width.

For each root, copy vectors, depths, vector map, expressions, operations,
diagnostics and RNG into independent state. Apply the root, then exhaust the
historical feasible free-rewrite closure. Enumerate feasible new sharing pairs
in that changed state, choose the first under the deterministic control
ranking, apply it and exhaust free rewrites again. If no shared pair exists,
stop early. Probes never call a random selector or finishing. A probe neither
mutates the live builder nor consumes its RNG. The copied RNG is unused.

Let T0/T2 be total expression terms before/after the probe, and G0/G2 the
created gates. Maximize `(T0 - T2) - (G2 - G0)`. Ties keep the earlier shortlist
entry: the historical proposal, then deterministic alternatives. Apply only
the winning root to the real builder; continue the usual sharing loop.

**Additional information:** unlike the immediate frequency benefit, the score
uses a second pair's *feasible frequency after the root*, its potential reuse
and free GF(2) cancellations, including opportunities created or destroyed by
the first move and its Kraft effects. The second move is actually simulated;
conflicting opportunities cannot both claim the same row terms. A regression
fixture has equal root rewards but different future rewards. This finite
horizon still cannot predict the full residual completion cost. Its horizon,
ranking, shortlist, reward and tie rule are frozen regardless of results.

Finishing remains the cap's designated control implementation, entered with
the evolved real RNG state. Divergent trajectories can have different numbers
of sharing decisions/draws; matched seeds align initial state, not every draw.
CRC semantics, physical XOR2 accounting, pruning, caps and verification do not
change. Historical source files remain byte-identical.

## Timing and computational budget

Timing-only pilots: seeds 390010 and 390011 at both caps, both arms; no final
gate counts inspected or retained. Identity/replay fixtures use 390000..390002.
Pilot raw measurements: `results/sharing_lookahead/pilot_timing.json`.
Cap 7 mean control 1.573 s, candidate 7.994 s (5.08x); cap 6 mean control
1.935 s, candidate 9.122 s (4.71x). These include some overlap with preflight
checks, so they estimate order of magnitude, not an isolated benchmark.

Retain **1,000 matched seeds per arm per cap**. Estimated serial build time
~20,624 s (5.73 CPU hours); 16 process workers, 20 logical CPUs / 10 physical
cores. Formal incumbent checks add overhead. This is practical under the
user's explicit long-experiment authorization; no budget reduction is needed.
No pilot can be admitted to inference or extension decisions.

Fresh ranges (verified absent from all historical logs before the budget):

- Screen cap 7: 400000..400999; cap 6: 420000..420999.
- Confirmation cap 7: 410000..419999; cap 6: 430000..439999.

For each cap separately, extend **only** if the screening candidate-minus-
control mean <=-0.5 and paired z <=-3. A passing cap runs both arms over its
fresh **10,000 seeds each**. Confirmation requires the same mean and z rule.
No passing cap means zero extension trials. No early stopping, seed reuse,
threshold changes, or alternative variant selection after results.

Paired SE = sample SD of per-seed gate differences / sqrt(n), z = mean / SE;
report mean, SE and approximate 95% interval mean +/-1.96 SE. Degenerate SE
produces null z and cannot pass. The z cutoff is a prespecified screening and
confirmation criterion, not an exact significance claim; two cap hypotheses
and adaptive selection are explicit. Fresh confirmation is required before
claiming method improvement. Also report arm SDs, runtime means/ratios,
phase gate counts, shortlist/probe counts, changed proposals, reward gains,
future reward and ties. These diagnostics are descriptive, not extra tests.

## Replay, verification and evidence

Before collection, control outputs must match the historical builders byte for
byte at both caps; repeated candidate trials and deterministic diagnostics
(excluding clocks) must match; forward/reverse probe ordering must preserve
all live state/RNG and return identical scores. Run the registered preflight
unit tests. Scoring source/protocol hashes and actual committed SHA are frozen
in `run_manifest.json` before the first seed. Unrelated `docs/reviews/` remains
untracked and excluded from commits and source hashes; the implementation
sources and protocol are clean at start. Record environment and commands.

Use the existing resumable bounded runner. Raw per-seed records append to
`results/search_logs/sharing_lookahead.jsonl`; checkpoints and all retained
incumbents live under `results/checkpoints/sharing_lookahead/`. Diagnostic
workers atomically spool seed JSON under `results/sharing_lookahead/`; those
for logged trials append to authoritative diagnostic JSONL at arm completion.
Unlogged speculative worker spools are not experimental evidence. Resume uses
the contiguous authoritative log prefix; never rerun historical budgets.

Every trial passes independent structural/exact checks and the cap. Every
retained incumbent must pass 97 exact vectors, 100000 randomized vectors
(seed 0xC32A5EED), and Yosys/SMTBMC/Z3 formal equivalence before acceptance.
Record per-trial runtime; save final artifacts, progress, diagnostics, raw
logs and summaries. After collection, audit unique IDs/coverage, per-phase
accounting, depth bounds, source identity, incumbent provenance and replay;
replay completed budgets and verify unchanged evidence bytes/no new trials.
Run relevant regressions and submitted-result provenance checks. Record
refutations, limitations and a concrete next decision in results and STATUS.

Commands, from repository root, after committing this protocol:

```bash
python3 -B -m unittest optimizer.test_sharing_lookahead optimizer.test_phase_isolation verifier.test_search_logs
python3 -B -m optimizer.sharing_lookahead --stage stage1 --workers 16
python3 -B -m optimizer.sharing_lookahead --stage stage2 --workers 16
python3 -B -m unittest discover
python3 -B -m verifier.build_results --check --require-spec-minimum
```

The stage commands are resumable verbatim. Progress is in the append-only raw
log and per-arm checkpoints; shell output is saved to stage progress logs.

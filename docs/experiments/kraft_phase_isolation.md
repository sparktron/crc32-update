# Experiment: isolate Kraft-slack scoring by search phase

Pre-registered 2026-10-28 before any new-arm results were inspected.
Completed 2026-10-28. H1 refuted; H2 confirmed; H3 refuted. The depth-6
existence target was met by two verified 462-gate circuits.
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

Code: `7dcc2fb009a1cd9a50860d738674a586355539d4`. The tracked tree was
clean before the budget. An unrelated untracked `docs/reviews/` directory was
present, was not read, and was not part of this experiment. Environment and
commands are captured in `results/phase_isolation/run_manifest.json`.

All eight 1,000-seed budgets completed: 8,000 unique attempt IDs, every trial
verified and within its depth cap, and 52 retained-incumbent acceptances.
Each acceptance ran the exact, randomized and formal verification gates.
All 4,000 matched sharing-boundary state/RNG comparisons passed.

Cap 7, mean XOR2 (sample SD), best of 1,000:

- baseline: 456.125 (4.189), best 443;
- sharing: 458.102 (4.260), best 445;
- finishing: 456.125 (4.189), best 443;
- both: 458.102 (4.260), best 445.

Cap 6, mean XOR2 (sample SD), best of 1,000:

- baseline: 490.305 (5.387), best 473;
- sharing: 485.493 (5.272), best 462;
- finishing: 490.304 (5.388), best 473;
- both: 485.493 (5.272), best 462.

Paired sharing-minus-baseline differences:

- cap 7: +1.977 gates, SE 0.18777, approximate 95% interval
  [+1.609, +2.345], z = +10.529;
- cap 6: -4.812 gates, SE 0.23069, approximate 95% interval
  [-5.264, -4.360], z = -20.860.

Changing finishing alone changed no gate count in either cap-7 comparison
(1,000 seeds each), or in the cap-6 sharing-versus-both comparison. In cap-6
baseline-versus-finishing, five seeds changed by one gate, for a net change of
-1 gate across 1,000 trials (mean -0.001, z = -0.447). This is a gate-count
result: finishing changed complete metrics in 500 cap-7 baseline/finishing
pairs and 757 cap-7 sharing/both pairs, through fanout differences.
Zero-variance comparisons have `z: null`, not a claimed infinite statistic.

Phase attribution, mean gates created (all were retained):

- cap 7 baseline: sharing 182.190, finishing 273.935;
- cap 7 sharing-only: sharing 180.639, finishing 277.463;
- cap 6 baseline: sharing 163.175, finishing 327.130;
- cap 6 sharing-only: sharing 164.960, finishing 320.533.

H1 is refuted: finishing explains none of the cap-7 gate-count penalty, and
sharing-only loses 1.977 gates, above the allowed 0.5. H2 is confirmed:
sharing-only retains the entire 4.812-gate cap-6 gain. Neither hybrid qualifies
for stage 2 against its designated best control. H3 is therefore refuted under
the frozen definition. The stage-2 command ran, selected no caps, and performed
zero additional trials; `stage2_summary.json` records this. No threshold was
changed to extend a run after seeing its best circuit.

**New circuits.** Seed 320099 produces 462 XOR2 at depth 6 in sharing-only
and both. Their netlists differ, but both have maximum fanout 6, total fanout
956 and excess fanout above four 22. They are saved at:

- `results/checkpoints/phase_isolation/stage1_sharing_depth6_incumbents/seed_320099.v`;
- `results/checkpoints/phase_isolation/stage1_both_depth6_incumbents/seed_320099.v`.

Both witnesses were separately checked on 97 exact vectors and 100,000 random
vectors and proved equivalent by Yosys/SMTBMC/Z3. Reports and formal logs are
in `results/phase_isolation/seed_320099_{sharing,both}_{verification.json,formal.log}`.
The sharing witness also replayed byte for byte in an independent invocation.
Both best artifacts replayed through the completed-budget replay below.

Compared with submitted C (465, depth 6, maximum fanout 6, excess 19), these
save three XORs but add three excess-fanout units. They do not dominate C on
every objective. The submitted frontier and final report were not changed.
No depth-7 circuit met the <=439 target.

Validation:

- `python3 -B -m unittest optimizer.test_phase_isolation verifier.test_search_logs`:
  7 tests passed before the budget;
- `python3 -B -m unittest discover`: 97 tests passed in 208.384 seconds;
- completed stage-1 command replay: all 78 logs, diagnostic files, summaries,
  checkpoints and artifacts were byte-identical, with no new trials;
- `python3 -B -m verifier.build_results --check --require-spec-minimum`: passed;
  all five submitted classes were re-proved and three Pareto circuits confirmed;
- raw coverage, unique IDs, diagnostic gate sums and nonnegative remaining
  Kraft budgets passed; see `validation_summary.json`;
- full clean-clone rebuild: not repeated in this session.

## Interpretation

Everything in this section is inference.

- The cap-7 gate-count penalty arises from the sharing decisions, rather than
  the finishing scoring rule. The earlier finishing-phase explanation is
  contradicted by the paired intervention.
- At cap 7, saving 1.551 sharing gates leaves 3.528 more finishing gates,
  accounting for the net +1.977. At cap 6, spending 1.785 more sharing gates
  saves 6.597 finishing gates. Remaining completion cost matters more than
  the number of gates created during sharing alone.
- The 462s establish a better gate-count witness at minimal depth. They do
  not establish a better hybrid search: the existing both-phases scoring
  found the same gate count at the same seed, and the paired distributions
  provide no improvement over the designated controls. This is consistent
  with a rare draw from the existing slack-family search; its rarity is not
  estimated from this small sample.
- Finishing scoring can still affect fanout and wiring. These results do
  not prove a universal gate-count invariance outside the sampled seeds.

## Next decision

The next algorithm experiment should target sharing decisions and the residual
completion cost they leave, with a fresh preregistered protocol. Further
finishing-scoring changes have no material gate-count support in this sample.
Keep the 462 witnesses as additional research results with their explicit
fanout tradeoff. Integrating them into the submitted frontier would require
updating the submission/provenance checks and report together.

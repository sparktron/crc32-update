# Results: bounded sharing lookahead

Completed 2026-10-28. Frozen protocol: [sharing_lookahead.md](sharing_lookahead.md).
Implementation/preregistration: `29704bf2d217096b4aae696e25c764dfa2744c0b`.
Parent: [PR #12](https://github.com/sparktron/crc32-update/pull/12),
commit `0026959` (open when the branch was created, now merged).
Branch: `codex/sharing-lookahead`; the new PR targets `master`.

## Observed

All four 1,000-seed budgets completed: **4,000 unique, independently checked
trials** and **32 fully verified incumbent acceptances**. Cap 7 compared with
the historical baseline; cap 6 compared with both-phases Kraft-slack.
Seeds were 400000..400999 and 420000..420999 respectively, matched across
candidate/control. The source and protocol hashes remained frozen. The
tracked sources were clean at collection start; unrelated `docs/reviews/`
and the newly opened progress log were untracked and recorded in the manifest.
No historical budget was rerun, and no threshold or variant changed.
The first/last trial records span 20:59:33..21:43:39 UTC (44.1 minutes of
logging, including acceptance pauses). Sum of worker elapsed times is 11.747
worker-hours, which includes contention and is not measured CPU time.

The candidate shortlists three roots and simulates each root plus one future
feasible sharing move, with free-rewrite closure after each. It scores realized
term reduction minus created gates across that continuation. Future feasible
frequencies, vector reuse and cancellation are evaluated on the changed state.
Probes use isolated copies and consume no real-trial RNG. Finishing is inherited
unchanged. The full rule, including ranking and ties, is in the immutable protocol.

### Paired gate counts and screening

Candidate-minus-control differences; negative favors lookahead. Each comparison
has n=1,000. Intervals and z values use the registered paired normal approximation.

- **Depth 7:** control mean 456.035 (SD 4.094); candidate mean 455.881
  (SD 4.122). Difference **-0.154 gates**, SE 0.14990, approximate 95% interval
  **[-0.448, +0.140]**, z=-1.027. Fails both the -0.5 mean threshold and z<=-3.
- **Depth 6:** control mean 485.180 (SD 5.335); candidate mean 485.845
  (SD 5.341). Difference **+0.665 gates**, SE 0.18289, approximate 95% interval
  **[+0.307, +1.023]**, z=+3.636. Fails the frozen screen, in the worse direction.

**H7 and H6 are refuted under the preregistered operational definition; overall
H is refuted.** The stage-2 command selected zero caps and ran zero trials.
Neither fresh 10,000-seed extension was opened. Confirmation is not claimed.

### Runtime and phase diagnostics

Mean worker elapsed seconds include construction and independent exact checks;
parent randomized/formal acceptance is outside those measurements:

- Cap 7: control 3.126 s, candidate 18.184 s, ratio **5.817x**.
- Cap 6: control 3.653 s, candidate 17.324 s, ratio **4.742x**.

The timing-only pilots had ratios 5.083x and 4.714x. Arms ran sequentially with
16 workers on the same i9-10900K, 10-core/20-thread host. Regression and
submitted-provenance checks overlapped part of cap-7 candidate collection.
Consequently the observed ratios include scheduling, concurrent load and thermal
effects; they are descriptive overhead measurements, not isolated benchmarks.
Equal seed budgets are not equal compute budgets. Environment, commands and
pilot observations are saved in the result directory.

Mean sharing/finishing retained gates (these sum to each arm's final mean):

- Cap 7 control: 182.202 / 273.833; candidate: 182.152 / 273.729.
- Cap 6 control: 165.035 / 320.145; candidate: 164.594 / 321.251.

Phase accounting is descriptive attribution, not a separate causal experiment.
At cap 6 the candidate saves 0.441 sharing gates and leaves 1.106 additional
finishing gates, for net +0.665.

Lookahead diagnostics over 1,000 candidate trials per cap:

- Cap 7: 182,152 sharing decisions, 543,854 probes, 2,435 changed proposals;
  180,629 decisions tie for best probe reward. Selected/proposal future-reward
  totals are 917,218 / 917,079; total two-move reward gain is 2,457.
- Cap 6: 164,594 sharing decisions, 491,237 probes, 2,526 changed proposals;
  162,399 decisions tie for best reward. Selected/proposal future-reward totals
  are 887,290 / 887,098; total two-move reward gain is 2,537.

The best reward tied for 99.164% of cap-7 decisions and 98.666% of cap-6
decisions; only 1.337% and 1.535% changed the control proposal.

These reward units are local probe predictions, not measured final gate savings.
The future component can change rankings (the preflight fixture demonstrates it),
but its aggregate selected-minus-proposal contribution is only 139 and 192.
The corresponding root/reuse contributions are 2,318 and 2,345. All deterministic
per-seed diagnostics, including phase boundary and RNG digests, remain available.

### Best circuits and existence targets

Best circuits from each 1,000-seed arm, with separately recomputed metrics:

- Cap-7 **control**, seed **400800**: **438 XOR2, depth 7**, maximum fanout 5,
  total fanout 908, excess fanout above four 6.
- Cap-7 candidate, seed 400628: 442 XOR2, depth 7, maximum fanout 5,
  total fanout 916, excess 4.
- Cap-6 control, seed 420247: 471 XOR2, depth 6, maximum fanout 6,
  total fanout 974, excess 21.
- Cap-6 candidate, seed 420316: 468 XOR2, depth 6, maximum fanout 6,
  total fanout 968, excess 22.

The **<=439 depth-7 target is met by the control**, once in this budget.
The <=461 depth-6 target is not met by either arm. The candidate's lower best
cap-6 count coexists with a worse cap-6 mean; it does not establish better search.
The previous 462-gate depth-6 witnesses remain better gate-count witnesses than
either new cap-6 best.

The new 438 is the lowest recorded physical XOR2 count in this repository and
also meets depth 7. It establishes circuit existence from the existing search.
It does not establish global optimality or a lookahead method improvement.
Compared with submitted B7 (440/depth 7, maximum fanout 5, excess 3), it saves
two gates and adds three excess-fanout units. Compared with submitted A/B
(439/depth 8, maximum fanout 5, excess 5), it saves one gate and one depth level
but adds one excess-fanout unit. It does not dominate either on every metric.
The submitted frontier and `report.md` remain unchanged, as preregistered.

The best artifacts are `results/sharing_lookahead/stage1_{control,candidate}_depth{7,6}.v`.
Every accepted intermediate incumbent is retained under
`results/checkpoints/sharing_lookahead/`; the 438 witness is
`stage1_control_depth7_incumbents/seed_400800.v` there.

## Verification and evidence

Raw append-only trials: `results/search_logs/sharing_lookahead.jsonl`.
Raw diagnostics, summaries, progress/formal logs, manifests and verification
reports: `results/sharing_lookahead/`. Resumable checkpoints and all 32 retained
incumbents: `results/checkpoints/sharing_lookahead/`.

- Before collection: 11 identity/replay/statistics/log tests passed; the final
  four candidate tests passed again after implementation completion. Controls
  reproduced their historical builders byte for byte; candidate replay and
  deterministic diagnostics matched at both caps. Probe order did not affect
  scores or any live builder/RNG state.
- All 4,000 trials passed independent structural/exact checks and their caps.
  All 32 incumbent acceptances passed 97 exact vectors, 100000 random vectors
  with seed 0xC32A5EED, and formal equivalence. The formal target/proof trace
  matches every accepted artifact; see `acceptance_trace_audit.json`.
- `python3 -B -m unittest discover`: **101 tests passed**, 346.024 s.
- `python3 -B -m verifier.build_results --check --require-spec-minimum`: passed;
  the submitted circuits were re-proved and three distinct Pareto circuits
  from five submitted classes confirmed.
- Diagnostic resume fixture: partial append preserved the existing prefix;
  completed replay appended nothing; inconsistent seed order was rejected.
- Post-collection audit command:
  `python3 -B -m scripts.audit_sharing_lookahead`.
  **Passed:** raw coverage/accounting and source identity against the
  preregistration commit; all 32 incumbents replayed byte for byte; completed
  stage commands preserved all 48 budget evidence files with no new trials.
  All four best artifacts were independently checked on 97 exact and 100000
  random vectors and formally proved again, including the 438 witness.
  See `validation_summary.json`, four `*_verification.json` reports and
  `audit_progress.log` for the proof traces.
- Full clean-clone rebuild was not repeated in this session. CI results are
  not inferred from local regression results.

## Interpretation

Everything in this section is inference.

- This two-move variant does not justify its additional computation: cap 7
  misses the meaningful-improvement screen, while cap 6 worsens the average.
  These results refute this specific variant, not every possible lookahead.
- Most shortlisted roots tie under the shallow score. Changed proposals and
  aggregate future-reward gains are small. A two-move horizon often appears
  to exchange locally similar sharing moves rather than distinguish their
  longer-term residual completion cost.
- The intervention combines the future score with a shortlist/proposal policy.
  It therefore cannot isolate a pure causal effect of future information from
  the effects of selecting more greedily among the shortlisted roots.
- The 438-gate witness is a rare draw from the unchanged baseline search, not
  evidence that lookahead improves its distribution. Similarly, the candidate's
  468 versus control's 471 at cap 6 cannot override the paired mean result.
- Finding a better circuit and finding a better search method are separate
  outcomes. Here the existence target succeeds in the control while the
  operational method hypotheses fail.

## Next decision

Do not extend or tune this frozen variant. Retain the verified 438-gate witness
with its fanout tradeoff; frontier integration would be separate work updating
submission provenance and the report together. Before another large search,
preregister a residual feasible-opportunity score that distinguishes competing
roots more often, and include a one-step shortlist control so any gain can be
attributed to future information. Use disjoint fresh seeds and measure runtime
again. Do not rerun these completed budgets to seek a different conclusion.

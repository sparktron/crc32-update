# Final report: 64-bit parallel IEEE CRC-32 XOR2 optimization

Date: 2026-10-24. Results and implementation baseline: `ec07920`.
Updated 2026-10-27: B7 and C were replaced by verified circuits from later
search experiments. Updated 2026-10-29: circuits from the elite-prefix restart
experiment replaced A, B, B7 and C and added C2 and F4. See "Submitted
candidates" and [docs/experiments/](docs/experiments).
Experiment contract: [SPEC.md](SPEC.md). Development gates: [PLAN.md](PLAN.md).

## Outcome

The completed experiment produced four distinct nondominated circuits for
one raw reflected IEEE CRC-32 state update:
- 437 XOR2 gates at depth 7 (Candidates A and B, and B7);
- 445 at depth 7 with every fanout at most four (F4);
- 460 at depth 6 (Candidate C, the minimum-depth point);
- 461 at depth 6 with lower excess fanout than C (C2).

All pass independent structural, exact-linear, randomized, and
formal-equivalence checks.

Depth 6 is provably minimal for this function. The gate counts are best found
under the recorded budgets; neither gate-count optimality nor research novelty
has been established. The result is a reproducible engineering improvement
over the four local baselines, with a documented area/depth/fanout tradeoff.

## Function and measurement model

The function maps a raw 32-bit CRC state and 64 data bits to the raw updated
32-bit state. It uses IEEE polynomial `0x04C11DB7`, reflected polynomial
`0xEDB88320`, right shifts, and `data[0]` first. There is no initial or final
XOR. This is not a complete packet-checksum wrapper or a CRC-32C update.

The normative bit-serial Python reference and independent Verilog recurrence
are in `reference/`. Expanding the reference on the input basis ordered as
`crc[0..31], data[0..63]` gives a 32-by-96 GF(2) matrix with 1,422 ones.
Its output row weights range from 34 to 52. Independent per-output expansion
therefore requires 1,422 minus 32 = 1,390 XOR2 gates.

Submitted circuits contain only two-input XOR gates, wires, and aliases.
The parser rejects hidden multi-XOR expressions, forbidden gates, forward
references, undefined or multiply defined signals, cycles, and missing outputs.
Before measurement it propagates aliases and removes unreachable nodes.
Separately instantiated gates remain distinct, including duplicate input
pairs, because physical duplication changes gate count and fanout.

Input depth is zero; a gate adds one to its maximum input depth. Fanout counts
each consuming gate input and primary output. Excess fanout is the sum of
`max(0, fanout - 4)` across primary inputs and retained gate outputs. The four
Pareto objectives are XOR2 count, maximum depth, maximum fanout, and excess
fanout above four; no weighted score replaces their separate reporting.
These are structural metrics, not placed-and-routed area or physical delay.

## Methodology and search history

### Baselines and heuristic construction

Four deterministic baselines establish identical-function comparisons:
serial independent equations, balanced independent trees, greedy two-term
common-subexpression elimination (CSE), and Yosys/ABC synthesis normalized
back to XOR2. On Yosys 0.9, `abc -g XOR` lacks a fallback cell; the recorded
baseline uses `-g XOR,AND`. Its mapped network contains XOR and NOT cells;
normalization propagates the NOT phases and rejects nonlinear cells or
uncancelled output phases.

The Candidate A engine represents signals as exact 96-bit GF(2) vectors.
It combines recursive CSE, Boyar–Peralta-style residual-distance reduction,
free known-vector rewrites, depth-aware pairing, and seeded stochastic
tie-breaking. This is a heuristic construction, not an implementation of
an exhaustive whole-network search. A separate continuation and B/C
refinement budgets explore additional seeds and starting points.

The later bounded constructor enforces a per-output Kraft condition,
`sum(2 ** signal_depth) <= 2 ** depth_cap`, throughout sharing and rewriting.
For the current terms, this is the feasibility condition for finishing an
XOR2 tree within the cap. It makes the depth constraint exact, but does not
make greedy sharing choices optimal. Post-filtering the earlier search had
not produced a depth-7 circuit; enforcing the constraint during construction
produced the two additional frontier points. The original Kraft-bounded
budgets found 441 at depth 7 and 470 at depth 6.

On 2026-10-27, four follow-up experiments, each pre-registered in
[docs/experiments/](docs/experiments), varied the depth-capped search:
- DCLO (Boyar, Find and Peralta) did worse than the Kraft-bounded search.
- An ablation toward DCLO showed that the baseline's depth-aware tie-break
  carries its advantage. One ablation seed gave the 440-gate depth-7
  circuit, but that arm's distribution matches the baseline's, so the circuit
  is a tail draw.
- A tie-break that prefers the merge using the least Kraft slack lowered the
  mean depth-6 gate count by about 5. It was worse at depth 7.
- A variant of it that counts slack only in rows near their Kraft limit
  produced the 465-gate depth-6 circuit.

On 2026-10-28, a pre-registered elite-prefix restart experiment
([docs/experiments/elite_prefix_restart.md](docs/experiments/elite_prefix_restart.md))
replayed the first quarter, half, three quarters, or all of the sharing
decisions of the 20 best recorded seeds at each depth cap, then continued
each child on a fresh random seed.
- At half the decisions, elite children averaged 9.2 gates fewer than fresh
  seeds at depth 7 and 13.2 fewer at depth 6. Children of median parents
  matched fresh seeds.
- Its elite arms produced all four current frontier circuits.
- Parents were selected on outcome from about 25,000 earlier trials, so these
  circuits are verified tail draws from a sampler seeded with the best earlier
  results. The experiment does not show a better method at matched compute.

Two other experiments that day, phase isolation and bounded sharing
lookahead, did not change the frontier.

Recorded stochastic budgets are:

| Budget | Seeds (inclusive) | Attempts | Outcome |
| --- | --- | --- | --- |
| Phase 3 A | 0–9,999 | 10,000 | Seed 3,195: 439 gates, depth 9 |
| Phase 4 A continuation | 10,000–19,999 | 10,000 | Seed 16,564: 439 gates, depth 8 |
| Phase 4 B refinement | 20,000–29,999 | 10,000 | No improvement over its depth-8 starting point |
| Phase 4 C refinement | 30,000–39,999 | 10,000 | No improvement over the balanced depth-6 starting point |
| Depth-7 bounded | 40,000–49,999 | 10,000 | Seed 40,505: 441 gates, 6 accepted incumbents |
| Depth-6 bounded | 50,000–59,999 | 10,000 | Seed 56,140: 470 gates, 10 accepted incumbents |
| Ablation `rewrite` arm, depth 7 | 160,000–160,999 | 1,000 | Seed 160,832: 440 gates (B7 from 2026-10-27 to 2026-10-29) |
| Kraft-adaptive stage-2 rerun (v2), depth 6 | 281,000–290,999 | 10,000 | Seed 286,375: 465 gates (C from 2026-10-27 to 2026-10-29); incumbent seed 288,438: 465 gates, max fanout 5 |
| Elite-prefix elite arm, f = 25, depth 7 | 500,000–500,999 | 1,000 | Seed 500,413: 445 gates, max fanout 4 (now F4); incumbent seed 500,505: 440 gates |
| Elite-prefix elite arm, f = 75, depth 7 | 502,000–502,999 | 1,000 | Seed 502,021: 437 gates (now A, B, B7) |
| Elite-prefix elite arm, f = 50, depth 6 | 521,000–521,999 | 1,000 | Seed 521,005: 461 gates (now C2) |
| Elite-prefix elite arm, f = 75, depth 6 | 522,000–522,999 | 1,000 | Seed 522,004: 460 gates (now C) |

The table lists only the budgets that produced current or earlier submitted
circuits. Every other budget (DCLO, the other ablation arms, the Kraft-slack
variant, the remaining Kraft-adaptive stages, and the other elite-prefix arms)
is recorded in its experiment record.

The append-only search log originally had 60,042 unique attempt IDs: 60,000
seeded trials, two verified starting points, and 40 exact-study records
across v1 and v2.
- With the 2026-10-27 experiments it held 127,904 records; with the
  2026-10-28 experiments it holds 159,904.
- It is now split, without changing any record, into one file per experiment
  under `results/search_logs/`, to stay under GitHub's file-size limit.

Checkpoints record the completed budgets. A historical overlapping
A continuation produced 7,125 identical duplicate records; these were removed
after a recovery copy was saved. Exclusive checkpoint/search-log locks now
reject overlapping invocations. The reproducible compute budget is the seed
range, not a claim about aggregate wall time: checkpoint elapsed time does
not aggregate all interrupted runs, and worker attempt time excludes formal
incumbent acceptance.

### Exact small-cone study

The first 20-cone study counted shared fan-in nodes as removable and is
retained only as exploratory history. The corrected
`phase5-exact-exclusive-cone-v2` cuts at shared signals and counts only
exclusively removable gates from the verified Candidate B network.

Using Z3 4.8.12, a six-node limit, and 1,000 ms per query, all 20 selected
cones completed their configured queries. Thirteen two- or three-gate cones
returned UNSAT for a strict gate reduction. Seven six-gate cones returned
`unknown` at the timeout. No replacement was accepted or integrated.
UNSAT applies only to the encoded single-cone problem; `unknown` is
inconclusive. Neither outcome establishes whole-network gate optimality.
The study, checkpoint, and full per-attempt outcomes agree.

### Independent acceptance and reproduction

Each retained incumbent passes the restricted parser, independent metric
recomputation, the zero vector and 96 basis vectors, 100,000 random vectors
with seed `0xC32A5EED` (3274333933), and formal equivalence against the
independent reference. Basis checks are exhaustive for the permitted linear
function class; random testing is an additional sanity check.

The formal flow runs Berkeley ABC as a structural synthesis check and
Yosys SMTBMC with Z3 as the exhaustive equivalence proof. ABC CEC and
flattened gate-level SAT trials did not finish promptly and are not counted
as passes. Dominated heuristic attempts may have only the parser and exact
basis check; a log's `verification_passed` field alone must not be read as
full incumbent acceptance.

The final result builder checks completed checkpoints, seed ranges,
accepted incumbents, bounded-seed replay, class objectives, and Phase 5
records before comparing regenerated CSV and JSON with committed results.
A submission may be a logged trial other than its budget's incumbent; F4 is
one. Such a trial is accepted only if:
- it reaches the budget's minimum XOR2 count, or for F4 the minimum among
  the budget's trials with every fanout at most four;
- no trial in the budget dominates it;
- its logged metrics equal the independent measurement;
- the artifact replays byte for byte from its seed.
Structural fingerprints deduplicate the A/B/B7 and A0/B0 circuits
independently of module and wire names.

## Results

### Submitted candidates

The following values are transcribed directly from `results/metrics.csv`.
`A0`, `B0` and `C0` preserve the dominated Phase 4 circuits for provenance:
the Candidate A search and the Phase 5 exact study are checked against A0
and B0.

| Class | Circuit ID | Seed | XOR2 | Depth | Max fanout | Total fanout | Excess >4 | Frontier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A0 | 1472a09886a8 | 16564 | 439 | 8 | 5 | 910 | 5 | false |
| B0 | 1472a09886a8 | 16564 | 439 | 8 | 5 | 910 | 5 | false |
| C0 | 103832014152 |  | 1390 | 6 | 20 | 2812 | 1038 | false |
| A | aa77c6d02bb6 | 502021 | 437 | 7 | 5 | 906 | 2 | true |
| B | aa77c6d02bb6 | 502021 | 437 | 7 | 5 | 906 | 2 | true |
| B7 | aa77c6d02bb6 | 502021 | 437 | 7 | 5 | 906 | 2 | true |
| C | d48641ffe21f | 522004 | 460 | 6 | 6 | 952 | 19 | true |
| C2 | 546dcc441532 | 521005 | 461 | 6 | 6 | 954 | 17 | true |
| F4 | 2773dcc0ddb0 | 500413 | 445 | 7 | 4 | 922 | 0 | true |

Every row has 32 direct output aliases; its intermediate count equals its
XOR2 count. Ordered per-output depths and verification evidence remain in the
CSV and JSON rather than being replaced by only these summaries.

The four frontier IDs are `aa77c6d02bb6`, `2773dcc0ddb0`, `d48641ffe21f`, and
`546dcc441532`.
- A/B/B7 has the fewest gates found, at depth 7. It satisfies B's
  depth-at-most-8 bound, with maximum fanout 5 and excess fanout 2.
- F4 spends 8 more gates at the same depth to keep every fanout at most four,
  so it has no excess fanout. It is the fewest-gate circuit of the four
  logged trials that meet that bound; the others have 449, 455 and 457 gates
  at depths 8 to 9.
- C spends 23 gates over A to reach depth 6, with maximum fanout 6 and
  excess 19.
- C2 spends one more gate than C for excess 17.
- No one point dominates another across the four objectives.
- A0/B0 is dominated by A. C0 is structurally the balanced baseline and is
  dominated by C and C2.
- The superseded Phase 3 A circuit is also dominated and is not submitted.

All four frontier circuits come from the elite arms of the elite-prefix
experiment, whose children replay prefixes of parents selected on outcome.
They are verified tail draws, not evidence of a better method at matched
compute.

Superseded submissions, adopted 2026-10-29:
- The 2026-10-27 B7 (`ed4ed2ba71db`, seed 160,832, 440 XOR2, maximum fanout 5,
  excess 3) and the Phase 4 A/B (`1472a09886a8`, 439 XOR2 at depth 8) are
  dominated by A/B/B7. The 440 remains in `results/ablation/`.
- The 2026-10-27 C (`900a2989cbc1`, seed 286,375, 465 XOR2, maximum fanout 6,
  excess 19) is dominated by C. It remains in `results/kraft_adaptive/notable/`.

Superseded submissions, adopted 2026-10-27:
- The original B7 (`b65a4c2b615e`, seed 40,505, 441 XOR2, maximum fanout 5,
  excess 5) and the original C (`b8edf279b361`, seed 56,140, 470 XOR2,
  maximum fanout 6, excess 20) remain in `results/phase6/` for provenance.

Artifacts are `results/phase4/candidate_a_extended.v` (A0),
`results/phase4/candidate_b_refined.v` (B0),
`results/phase4/candidate_c_refined.v` (C0),
`results/elite_prefix/stage1_elite_f75_depth7.v` (A, B, B7),
`results/elite_prefix/stage1_elite_f75_depth6.v` (C),
`results/elite_prefix/stage1_elite_f50_depth6.v` (C2), and
`results/elite_prefix/notable/seed_500413_depth7.v` (F4).

### Local baseline comparison

| Baseline | XOR2 | Depth | Max fanout | Total fanout | Excess >4 |
| --- | --- | --- | --- | --- | --- |
| independent_per_output | 1390 | 51 | 20 | 2812 | 1038 |
| balanced_per_output | 1390 | 6 | 20 | 2812 | 1038 |
| greedy_cse | 454 | 9 | 6 | 940 | 11 |
| yosys_abc | 1123 | 7 | 15 | 2278 | 536 |

A/B/B7 reduces gate count by 68.6% from unshared expansion and 3.7% from
greedy CSE, while improving greedy CSE's depth and fanout. It also reduces the
recorded Yosys/ABC count by 61.1% at the same depth 7. C reduces the balanced
baseline by 66.9% at the same depth 6. Each local baseline is dominated by at least
one frontier circuit, as recorded in `baseline_comparison` in the JSON.
Recorded baseline generation/verification/formal totals are about 3.9–6.3
seconds on the original host; these are not search runtimes or portable
performance guarantees.

### Minimum-depth certificate

The heaviest matrix row has 52 independent input dependencies. A depth-d
network of two-input gates can depend on at most 2**d inputs, even with
sharing. Since 32 < 52 <= 64, depth is at least 6. Candidate C and C2 attain
6, so their depth is optimal. This argument does not bound the minimum number
of gates at that depth or the global minimum gate count.

## Published methods, generators, and publishability

The dated source inventory and detailed comparability analysis are in
[comparison_research.md](docs/comparison_research.md). Its recorded evidence
is summarized here; this report does not claim that every external generator
was executed or every cited paper was accessible.

crcZero (commit `98c55152`, version 1.2.0) was run for CRC-32/ISO-HDLC at
D=64 with `scripts/compare_crczero.py`. All 32 emitted equations equal the
frozen matrix, and they contain 1,390 two-input XOR operators, matching its
[package metadata](https://pypi.org/pypi/crczero/json). Converted to the
restricted XOR2 subset, both realizations passed 97 exact vectors, 100,000
random vectors, and formal equivalence. Chained as written, the netlist has
1,390 XOR2 at depth 51 and is structurally identical to
`independent_per_output`. As balanced trees, it has 1,390 XOR2 at depth 6 and
is structurally identical to `balanced_per_output` (C0). The record is
`results/external/crczero_comparison.json`. Against this directly comparable
generator, A/B/B7, F4, C, and C2 use 31.4%, 32.0%, 33.1%, and 33.2% of the
gates.
XAPP209's cancellation within output equations and the OpenCores/CRC generator
inventory provide context for equation generation; a missing resource count
is not evidence of a competitive optimized circuit.

Zhang and Tang, ISCAS 2021, report 469–503 XORs at critical path 6 for
64-bit parallel CRC-32 constructions. Their input-tap/remainder mappings
change the data transformation relative to the frozen standard update;
the totals and critical-path conventions therefore do not establish a
head-to-head win for either implementation. See their
[author manuscript](https://par.nsf.gov/servlets/purl/10225256) and
[DOI](https://doi.org/10.1109/ISCAS51556.2021.9401679).
The source research records 485 ones in their state block, matching ours,
but 484 in their data preprocessing block versus our 937. This is useful
context, not a directly comparable whole-function gate count.

Depth-constrained linear optimization is an existing research direction:
Boyar, Find, and Peralta describe DCLO with arrival-depth and output-depth
constraints in
[Small Low-Depth Circuits for Cryptographic Applications](https://csrc.nist.gov/pubs/journal/2018/03/small-lowdepth-circuits-for-cryptographic-applicat/final).
The local heuristic draws on established CSE/BP ideas; beating local
baselines does not show a new optimization method.

Campobello, Patanè, and Russo, "Parallel CRC Realization"
([DOI](https://doi.org/10.1109/TC.2003.1234528)), read from the authors'
[archived preprint](https://web.archive.org/web/20060510231352/http://ai.unime.it/~gp/publications/full/tccrc.pdf),
report two-input XOR counts for CRC-32 only at a 32-bit data width:
- 452 XORs as unshared binary trees.
- 370 XORs after manual sharing of common subexpressions, with no depth
  given.
- 448 → 408 XORs after Synopsys optimization, quoted from Shieh et al.

Shieh, Sheu, Chen, and Lo, "A Systematic Approach for Parallel CRC
Computations" (J. Inf. Sci. Eng. 17(3):445–461, 2001,
[journal record](https://jise.iis.sinica.edu.tw/JISESearch/pages/View/PaperView.jsf?keyId=84_1287)),
compute the standard CRC-32 remainder at widths up to r = 32. At r = 32 they
report 448 two-input XORs at 15 levels with cascaded blocks, and 408 at
7 levels after Synopsys optimization.

A 32-bit update has 64 inputs, against 96 here, so these numbers from both
papers are reference points at a smaller width, not a comparison with our
circuits. Neither paper gives a 64-bit count.

Several older papers remain unread, and their results could change the
assessment. The Zhang–Tang manuscript could not be fetched again during
report preparation; its numerical summary relies on the dated repository
research record.

The supported publication claim is a reproducible, independently verified
engineering result and a documented tradeoff frontier for this frozen
function. A novel or state-of-the-art gate-count claim needs a fuller
same-function comparison and evidence beyond the current searches.

## Limitations and failed approaches

- Seeded greedy construction and bounded local searches do not exhaust
  possible circuits. Gate-count optimality and fanout optimality are unknown.
- Simulated annealing, a dedicated output-subset resynthesis study, and a
  separately budgeted fanout-duplication optimizer are not established as
  completed experiments here. The broad SPEC Section 8 investigation list
  must not be read as an assertion that every named technique was implemented.
  Those are extensions beyond the concrete completed search budgets.
- The seven v2 timeouts do not prove irreducibility. Larger limits or
  multi-output encodings would be new experiments. The nonexclusive v1
  study cannot justify an integrated gate reduction.
- The Phase 4 B/C refinement budgets found nothing better; the balanced
  depth-6 starting point was a baseline, not a search-derived improvement.
- No technology mapping, routing, buffering, power, or target-hardware
  measurement establishes physical performance. Fanout metrics are proxies;
  the minimum-depth proof concerns XOR2 levels only.
- Yosys/ABC output and measured runtime depend on toolchain and host. The
  toolchain is documented but not container-pinned. Independent normalization
  and verification remain necessary on another release.
- Literature coverage is incomplete. Arbitrary-width XORs, LUTs, cell-area
  figures, changed widths, and transformed remainders are not interchangeable
  with our XOR2 model and raw update function.

## Reproduction

Use the repository revision containing this report for the completed
submission; `ec07920` identifies the unchanged numeric-result baseline used
while writing it. From the repository root on Ubuntu 22.04, install the
recorded toolchain and run:

```bash
sudo apt-get install -y yosys berkeley-abc z3
python3 -B -m verifier.build_results --check --require-spec-minimum
```

The recorded environment is Python 3.10.12, Yosys 0.9 (git `1979e0b`),
Berkeley ABC 1.01 (2022-01-29 build), and Z3 4.8.12. The check re-verifies
all submitted candidates, cross-checks provenance, and compares regenerated
results without overwriting them. To intentionally regenerate result files:

```bash
python3 -B -m verifier.build_results --random-tests 100000 --seed 0xC32A5EED
```

For full clean-checkout reproduction, run this manually (the 2026-10-29 run
took 5 minutes 43 seconds and can exceed an agent command limit):

```bash
scripts/clean_rebuild.sh
```

It clones HEAD, runs every unit/rejection test module, regenerates the fixture
and baselines, replays submitted circuits, checks final results and the
three-point minimum, and requires an unchanged checkout. A Yosys/ABC baseline
difference on another toolchain is reported separately. It does not repeat the
hours-long search budgets or SMT study; those are validated from complete
records. The 2026-10-29 fresh-clone run of `796631c` passed 117 tests,
byte-for-byte local baseline and artifact comparisons, and the four-circuit
frontier check. It predates the documentation-only commit that records it.

For focused replay without adding optimization attempts:

```bash
python3 -B -m optimizer.phase4_candidates --replay-dir /tmp/phase4_replay
python3 -B -m optimizer.depth_bounded --depth-cap 7 --replay-seed 40505 --artifact /tmp/depth7.v
python3 -B -m optimizer.depth_bounded --depth-cap 6 --replay-seed 56140 --artifact /tmp/depth6.v
```

The two `depth_bounded` commands replay the superseded original B7 and C.
`build_results --check` replays the four current frontier circuits from their
seeds and the committed elite-prefix parent table. To replay them directly:

```bash
python3 -B -c "from optimizer.elite_prefix import replay_trial as r; print(r(502021, 7, group='elite', fraction=75).render('candidate_elite_f75_depth7'), end='')" > /tmp/a.v
python3 -B -c "from optimizer.elite_prefix import replay_trial as r; print(r(500413, 7, group='elite', fraction=25).render('candidate_elite_f25_depth7'), end='')" > /tmp/f4.v
python3 -B -c "from optimizer.elite_prefix import replay_trial as r; print(r(522004, 6, group='elite', fraction=75).render('candidate_elite_f75_depth6'), end='')" > /tmp/c.v
python3 -B -c "from optimizer.elite_prefix import replay_trial as r; print(r(521005, 6, group='elite', fraction=50).render('candidate_elite_f50_depth6'), end='')" > /tmp/c2.v
```

The 2026-10-27 B7 and C replay with
`optimizer.ablation.search_seed_ablated(160832, 7, 'rewrite')` and
`optimizer.kraft_adaptive.search_seed_adaptive(286375, 6)`.

[README.md](README.md) contains the full resumable search commands, checkpoint
paths, locks, and seed ranges. Run budgets sequentially because they share the
canonical log. Completed checkpoint replay is distinct from performing a new
search; changing a budget or timeout requires a separately recorded experiment.

## Artifact agreement and G6 acceptance

`results/metrics.csv` and `results/pareto_frontier.json` are authoritative
machine-readable result records. The report's candidate and baseline tables
were constructed from those CSV files. Circuit IDs, seeds, all scalar table
metrics, frontier membership, Phase 5 counts, and search budgets are checked
against the JSON, checkpoints, and log. The matrix row-weight certificate is
recomputed from the generator. The result-builder check is the independent
network/metric/formal validation; copying a table alone is not validation.

G6 closure means the specified final deliverables and acceptance evidence
exist and agree, with the limitations above preserved. It does not promote
inconclusive solver results, incomplete research coverage, or unrun search
techniques into successful experiments. The final closeout commands and their
actual outcomes are recorded in [STATUS.md](STATUS.md).

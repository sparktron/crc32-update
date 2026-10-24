# Final report: 64-bit parallel IEEE CRC-32 XOR2 optimization

Date: 2026-10-24. Results and implementation baseline: `ec07920`.
Experiment contract: [SPEC.md](SPEC.md). Development gates: [PLAN.md](PLAN.md).

## Outcome

The completed experiment produced three distinct nondominated circuits for
one raw reflected IEEE CRC-32 state update: 439 XOR2 gates at depth 8,
441 at depth 7, and 470 at depth 6. All pass independent structural,
exact-linear, randomized, and formal-equivalence checks. Candidate A and
Candidate B share one circuit; B7 supplies a distinct bounded-depth point,
and Candidate C supplies the minimum-depth point.

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
produced the two additional frontier points.

Recorded stochastic budgets are:

| Budget | Seeds (inclusive) | Attempts | Outcome |
| --- | --- | --- | --- |
| Phase 3 A | 0–9,999 | 10,000 | Seed 3,195: 439 gates, depth 9 |
| Phase 4 A continuation | 10,000–19,999 | 10,000 | Seed 16,564: 439 gates, depth 8 |
| Phase 4 B refinement | 20,000–29,999 | 10,000 | No improvement over its depth-8 starting point |
| Phase 4 C refinement | 30,000–39,999 | 10,000 | No improvement over the balanced depth-6 starting point |
| Depth-7 bounded | 40,000–49,999 | 10,000 | Seed 40,505: 441 gates, 6 accepted incumbents |
| Depth-6 bounded | 50,000–59,999 | 10,000 | Seed 56,140: 470 gates, 10 accepted incumbents |

The canonical append-only log has 60,042 unique attempt IDs: 60,000 seeded
trials, two verified starting points, and 40 exact-study records across v1
and v2. Checkpoints record the completed budgets. A historical overlapping
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
Structural fingerprints deduplicate the A/B circuit independently of module
and wire names.

## Results

### Submitted candidates

The following values are transcribed directly from `results/metrics.csv`.
`C0` preserves the dominated Phase 4 starting point for provenance.

| Class | Circuit ID | Seed | XOR2 | Depth | Max fanout | Total fanout | Excess >4 | Frontier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 1472a09886a8 | 16564 | 439 | 8 | 5 | 910 | 5 | true |
| B | 1472a09886a8 | 16564 | 439 | 8 | 5 | 910 | 5 | true |
| C0 | 0c80bfcc8e2b |  | 1390 | 6 | 20 | 2812 | 1038 | false |
| B7 | b65a4c2b615e | 40505 | 441 | 7 | 5 | 914 | 5 | true |
| C | b8edf279b361 | 56140 | 470 | 6 | 6 | 972 | 20 | true |

Every row has 32 direct output aliases; its intermediate count equals its
XOR2 count. Ordered per-output depths and verification evidence remain in the
CSV and JSON rather than being replaced by only these summaries.

The three frontier IDs are `1472a09886a8`, `b65a4c2b615e`, and `b8edf279b361`.
A/B minimizes the found gate count and satisfies B's depth-at-most-8 bound.
B7 spends two additional gates to remove one depth level with unchanged
maximum and excess fanout. C spends another 29 gates to reach depth 6, with
maximum fanout 6 and excess 20. No one point dominates another across the
four objectives. C0 is structurally the balanced baseline and is dominated
by C. The superseded Phase 3 A circuit is also dominated and is not submitted.

Artifacts are `results/phase4/candidate_a_extended.v`,
`results/phase4/candidate_b_refined.v`,
`results/phase4/candidate_c_refined.v` (C0),
`results/phase6/candidate_depth7_bounded.v`, and
`results/phase6/candidate_depth6_bounded.v`.

### Local baseline comparison

| Baseline | XOR2 | Depth | Max fanout | Total fanout | Excess >4 |
| --- | --- | --- | --- | --- | --- |
| independent_per_output | 1390 | 51 | 20 | 2812 | 1038 |
| balanced_per_output | 1390 | 6 | 20 | 2812 | 1038 |
| greedy_cse | 454 | 9 | 6 | 940 | 11 |
| yosys_abc | 1123 | 7 | 15 | 2278 | 536 |

A/B reduces gate count by 68.4% from unshared expansion and 3.3% from greedy
CSE, while improving greedy CSE's depth and fanout. B7 reduces the recorded
Yosys/ABC count by 60.7% at the same depth 7. C reduces the balanced baseline
by 66.2% at the same depth 6. Each local baseline is dominated by at least
one frontier circuit, as recorded in `baseline_comparison` in the JSON.
Recorded baseline generation/verification/formal totals are about 3.9–6.3
seconds on the original host; these are not search runtimes or portable
performance guarantees.

### Minimum-depth certificate

The heaviest matrix row has 52 independent input dependencies. A depth-d
network of two-input gates can depend on at most 2**d inputs, even with
sharing. Since 32 < 52 <= 64, depth is at least 6. Candidate C attains 6,
so its depth is optimal. This argument does not bound the minimum number
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
generator, A/B, B7, and C use 31.6%, 31.7%, and 33.8% of the gates.
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
baselines does not show a new optimization method. Campobello et al. and
several older papers remain unread, and their results could change the
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

For full clean-checkout reproduction, run this manually (the recorded run
took 73 seconds and can exceed an agent command limit):

```bash
scripts/clean_rebuild.sh
```

It clones HEAD, runs unit/rejection tests, regenerates the fixture and
baselines, replays submitted circuits, checks final results and the three-point
minimum, and requires an unchanged checkout. A Yosys/ABC baseline difference
on another toolchain is reported separately. It does not repeat the hours-long
search budgets or SMT study; those are validated from complete records.
The prior fresh-clone run passed 58 tests and byte-for-byte local baseline
and artifact comparisons. That evidence predates this documentation-only
closeout; it is not a claim of a fresh full rebuild of the report revision.

For focused replay without adding optimization attempts:

```bash
python3 -B -m optimizer.phase4_candidates --replay-dir /tmp/phase4_replay
python3 -B -m optimizer.depth_bounded --depth-cap 7 --replay-seed 40505 --artifact /tmp/depth7.v
python3 -B -m optimizer.depth_bounded --depth-cap 6 --replay-seed 56140 --artifact /tmp/depth6.v
```

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

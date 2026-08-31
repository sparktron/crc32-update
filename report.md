# CRC32 Update XOR2 Superoptimization Report

Status: Phase 6 draft; G6 is not complete

## Summary

This experiment searches for combinational XOR2 networks implementing one
64-bit reflected IEEE CRC-32 update of a raw 32-bit state. The frozen semantics,
structural restrictions, objectives, and acceptance criteria are defined in
`SPEC.md`. The best recorded area-oriented implementation uses 439 XOR2 gates
at depth 8. A normalized conventional-synthesis result provides a depth-7
tradeoff at 1,123 gates, and the minimum-depth search retains a 1,390-gate,
depth-6 balanced implementation.

These are best-found and locally verified results. They are not global
optimality claims.

## Methodology

The normative Python reference processes `data[0]` first with reflected
polynomial `0xEDB88320`. A separately written Verilog reference and a generated
32-by-96 GF(2) transformation matrix provide independent cross-checks.

Submitted circuits use only two-input XOR gates and aliases. The verifier
propagates aliases, removes unreachable gates, preserves separately instantiated
physical XOR2 nodes, recomputes every metric, checks all-zero plus 96 basis
vectors, evaluates 100,000 deterministic random vectors, and proves formal
equivalence with Yosys, Berkeley ABC, Yosys SMTBMC, and Z3.

The optimization campaign combined GF(2)-vector common-subexpression
extraction, Boyar–Peralta-style distance reduction, depth-aware rewrites, and
seeded stochastic tie-breaking. Phase 4 extended Candidate A and ran recorded
10,000-seed refinement budgets for Candidates B and C.

## Final-Frontier Draft

| Frontier entry | Candidate classes | XOR2 | Depth | Max fanout | Excess fanout >4 |
| --- | --- | ---: | ---: | ---: | ---: |
| Area/depth-8 implementation | A, B | 439 | 8 | 5 | 5 |
| Normalized Yosys/ABC tradeoff | — | 1,123 | 7 | 15 | 536 |
| Minimum-depth implementation | C | 1,390 | 6 | 20 | 1,038 |

Candidate A and Candidate B use the same physical seed-16,564 implementation.
The specification permits one circuit to satisfy multiple required classes but
still requires three distinct frontier circuits. The normalized Yosys/ABC
network is retained as the independently verified intermediate tradeoff. None
of the three entries dominates another across XOR2 count, depth, maximum
fanout, and excess fanout.

Machine-readable records are generated from `results/phase6/candidates.json`
by `python3 -m verifier.verify_final`.

## Exact Small-Cone Study

The corrected Phase 5 study cut internally shared nodes at the cone boundary so
only exclusively removable gates were compared with a possible replacement.
For the selected 20 Candidate B roots, 13 searches proved that no smaller
implementation exists within the exact encoded single-output cone problem and
seven reached the 1,000 ms per-query timeout. No replacement witness was found.

The negative results do not establish whole-network optimality, and the timeout
results establish no lower bound.

## Validation Status

All three Phase 6 frontier entries passed restricted parsing, 97 exact vectors,
100,000 random vectors with seed `0xC32A5EED`, independent metric
recomputation, and formal equivalence. The completed Phase 5 output reconciles
with its checkpoint and 20 append-only search-log records.

G6 remains open pending clean-checkout reproduction of all deliverables and
completion of the external comparison.

## Limitations

- Search budgets are finite and do not prove global optimality.
- The exact study covers bounded single-output cones and a fixed timeout.
- Tool versions and conventional synthesis structure can affect the Yosys/ABC
  baseline, although every emitted artifact is normalized and reverified under
  the frozen XOR2 model.
- Comparisons with work using different CRC conventions, input widths,
  arbitrary-fanin XORs, or technology-mapped cell costs are not directly valid.

## External Comparison and Publishability

Literature and open-source generator research has not yet been completed. This
section must be finished with primary sources and convention-compatible metrics
before drawing novelty or publishability conclusions.

## Reproduction

The phase-specific commands are documented in `README.md`. The current Phase 6
frontier is regenerated with:

```bash
python3 -m verifier.verify_final
```

A final clean-checkout reproduction record remains required before G6 passes.

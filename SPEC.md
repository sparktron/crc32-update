# CRC32 Superoptimization Experiment Specification

Status: frozen for implementation

Frozen on: 2026-08-22

## 1. Objective and Scope

Design and verify combinational circuits for one 64-bit parallel update of a
raw 32-bit IEEE CRC-32 state:

```text
next_crc[31:0] = CRC32_UPDATE(crc[31:0], data[63:0])
```

The optimization objectives are separate and must not be collapsed into one
arbitrary weighted score:

1. XOR2 gate count
2. Maximum XOR depth
3. Maximum fanout
4. Total excess fanout above four

Results may be described as candidates, improvements, Pareto candidates, or
best found. Global optimality must not be claimed without a valid optimality
certificate.

## 2. Frozen CRC Semantics

The experiment uses standard reflected IEEE CRC-32 with these exact
conventions:

| Property | Frozen value |
| --- | --- |
| Polynomial, normal form | `0x04C11DB7` |
| Polynomial, reflected form | `0xEDB88320` |
| Data order | `data[0]` processed first |
| State shift direction | Right |
| CRC input | Raw internal 32-bit state |
| CRC output | Raw updated internal state |
| Initial XOR | None |
| Final XOR | None |
| Reflection inside update | Already represented by the reflected algorithm |

The following Python function is the normative reference:

```python
POLY = 0xEDB88320

def crc32_update_reference(crc: int, data: int) -> int:
    crc &= 0xFFFFFFFF
    data &= 0xFFFFFFFFFFFFFFFF

    for i in range(64):
        feedback = (crc ^ (data >> i)) & 1
        crc >>= 1
        if feedback:
            crc ^= POLY

    return crc & 0xFFFFFFFF
```

CRC-32C, CRC-32/MPEG-2, left-shifting updates, complemented states, reversed
byte order, and unreconciled library CRC conventions are not substitutes for
this definition.

## 3. Circuit Model

### 3.1 Interface

Primary inputs:

```text
crc[31:0]
data[63:0]
```

Primary outputs:

```text
next_crc[31:0]
```

The 96 primary inputs have a stable GF(2) basis-vector order:

```text
crc[0], ..., crc[31], data[0], ..., data[63]
```

Every signal's function may therefore be represented exactly as a 96-bit GF(2)
vector.

### 3.2 Permitted elements

- Two-input XOR gates
- Wires and direct aliases
- Signal fanout
- Direct input-to-output connections

### 3.3 Forbidden elements

- XOR gates with more than two inputs
- AND, OR, NAND, NOR, XNOR, muxes, lookup tables, or arithmetic operators
- Sequential logic, clocks, latches, registers, or memories
- Technology-specific compound cells
- Behavioral loops in an optimized netlist
- Expressions that hide more than one XOR operation in one counted node
- Cycles, undefined signals, multiply defined signals, or outputs without a
  driver
- Any unverified change to the frozen CRC convention

### 3.4 Structural-network rules

Every XOR node must have exactly two previously defined inputs. XOR input order
is canonicalized for structural comparison. The graph must be combinational and
acyclic.

Accepted structural forms must be equivalent to either:

```verilog
wire n0;
xor2 g0 (.a(crc[0]), .b(data[0]), .y(n0));
```

or a plain assignment containing exactly one binary XOR:

```verilog
assign n0 = crc[0] ^ data[0];
```

Direct aliases may contain no operation:

```verilog
assign next_crc[0] = n0;
```

Multi-XOR expressions such as `assign n0 = a ^ b ^ c;` are prohibited. Each
internal node must be defined before use, except that primary inputs are always
defined. Each output must resolve to one primary input or reachable XOR node.

## 4. Required Candidate Classes

At least three valid Pareto candidates are required:

- **Candidate A — minimum gate-count search:** minimize XOR2 count without a
  hard depth bound and report the resulting depth.
- **Candidate B — bounded-depth search:** minimize XOR2 count with maximum XOR
  depth at most 8. If no competitive depth-8 candidate is found, also retain
  and report distinct searches at bounds 9 and 10.
- **Candidate C — minimum-depth search:** minimize maximum XOR depth first, then
  minimize XOR2 count at that achieved depth.

The final reported set must contain at least three distinct, structurally valid
nondominated circuits over the measured objectives. Required candidate-class
labels must still be reported; one circuit may satisfy more than one class, but
that does not waive the requirement for at least three distinct Pareto
candidates.

## 5. Metric Definitions

For each primary input:

```text
depth(input) = 0
```

For each XOR node:

```text
depth(node) = 1 + max(depth(input_a), depth(input_b))
```

An output alias has the depth of its source. Circuit depth is the maximum depth
of the 32 outputs.

Metrics are computed only after:

1. Direct aliases are propagated.
2. XOR input order is canonicalized.
3. Structurally identical XOR nodes are merged.
4. Nodes unreachable from primary outputs are removed.

The independent verifier must report:

- XOR2 count: number of remaining unique two-input XOR nodes
- Maximum depth: maximum of all output depths
- Output depths: an ordered 32-element list for `next_crc[0]` through
  `next_crc[31]`
- Maximum fanout
- Total fanout
- Total excess fanout above 4
- Intermediate-node count
- Direct-output-alias count

Fanout of a signal is its number of consumers after canonicalization, including
primary outputs as consumers. Each XOR input pin is one consumer occurrence;
each direct primary-output connection is one consumer occurrence.

For signal set `S`, with fanout `fo(s)`:

```text
total_fanout = sum(fo(s) for s in S)
total_excess_fanout_above_4 = sum(max(0, fo(s) - 4) for s in S)
```

`S` contains all primary inputs and all retained XOR nodes. Fanout buffers are
not counted or inferred unless a separate explicit physical-library model is
introduced; such a model is outside the default experiment.

An intermediate node is a retained XOR node. A direct-output alias is an output
whose final driver is a primary input or XOR node without a dedicated XOR node
created solely for the output connection.

## 6. Independent Verification Requirements

Before optimization begins, an independent verifier must:

1. Evaluate the normative bit-serial reference.
2. Parse the submitted structural network.
3. Reject prohibited gates and expressions, cycles, forward or undefined
   signals, multiply defined signals, and missing or dead outputs. Unreachable
   internal nodes are reported and removed before metric computation.
4. Recompute all metrics independently of generation and optimization code.
5. Check exact functional equivalence over GF(2).
6. Exit nonzero on every failure.

Exact linear equivalence requires evaluation of:

- The all-zero 96-bit input vector
- Each of the 96 independent input basis vectors

The verifier must additionally run at least 100,000 randomized `(crc, data)`
pairs as a parser and implementation sanity check, using a recorded seed.

Each accepted candidate must also pass SAT-based or combinational-equivalence
checking against an independently generated reference RTL implementation using
an established tool such as Yosys SAT/equivalence or ABC CEC. Random testing is
never sufficient by itself.

Verifier tests must include deliberately broken circuits covering, at minimum:

- Wrong CRC semantics or output function
- Multi-input or chained XOR expression
- Forbidden gate type
- Undefined signal
- Multiply defined signal
- Forward reference
- Combinational cycle
- Missing or undriven output
- Unreachable-node reporting and removal

## 7. Required Baselines

All baselines use the same frozen semantics, structural restrictions, and
independent metric accounting:

1. Independently expanded Boolean equation for every output
2. Balanced XOR tree per output with no cross-output sharing
3. Conventional Yosys/ABC synthesis output normalized to the XOR2 model
4. Greedy common-subexpression elimination
5. Best verified optimized network

External baselines must record source, CRC convention, parallel width, gate
model, metric definitions, and direct comparability. Arbitrary-width XOR counts
must not be compared directly with XOR2 counts.

## 8. Search Requirements

The implementation must investigate multiple reproducible approaches:

- GF(2) transformation-matrix generation
- Common two-term and multi-term subexpression extraction
- Boyar–Peralta-style XOR straight-line-program heuristics
- Depth-aware common-subexpression elimination
- Simulated annealing or stochastic local search
- Iterated local improvement from multiple recorded seeds
- Re-synthesis of selected output subsets
- SAT/SMT search for bounded improvements in small subcircuits
- Sharing-versus-depth tradeoffs
- Fanout-aware duplication of intermediate terms

Candidate transformations are accepted only after exact comparison of their
96-bit GF(2) signal vectors and periodic independent verification. Invalid
results may be retained as debugging artifacts but never placed on the valid
Pareto frontier.

## 9. Search Log Contract

`results/search_log.jsonl` is append-only during optimization. It begins empty;
documentation setup and non-search implementation work are not optimization
attempts. Each line represents exactly one completed or interrupted
optimization attempt and is a standalone JSON object with at least:

```json
{
  "timestamp_utc": "RFC-3339 timestamp",
  "attempt_id": "stable unique identifier",
  "algorithm": "algorithm name and version",
  "parameters": {},
  "seed": 0,
  "runtime_seconds": 0.0,
  "starting_metrics": null,
  "final_metrics": null,
  "verification_passed": false,
  "accepted": false,
  "rejection_reason": "required when accepted is false",
  "artifact": null
}
```

Metric objects use the names and definitions in Section 5. `seed` may be `null`
only for a provably deterministic algorithm. A failed attempt is logged even
when it produces no candidate. A passing attempt is not automatically accepted
if it is dominated or fails a phase-specific requirement.

## 10. Candidate Acceptance Criteria

A candidate is accepted only when all of the following are true:

- It conforms to the restricted XOR2 circuit model.
- The independent structural parser accepts it.
- All-zero plus 96 basis-vector checks pass.
- At least 100,000 seeded randomized tests pass.
- SAT or combinational equivalence passes.
- All metrics are independently recomputed.
- The candidate is reproducible from committed source, configuration, and
  recorded seeds.
- Its search attempt is recorded in `results/search_log.jsonl`.

Acceptance establishes validity under this specification, not global
optimality or novelty.

## 11. Publication and Comparison Discipline

Published CRC XOR-network methods and open-source generators must be researched
before novelty claims are made. Comparisons must state convention, width, gate
model, metric definitions, and limitations. A result is not novel merely
because it beats a locally generated baseline. Any publishability assessment
must distinguish reproducible engineering improvement from certified optimality
or demonstrated research novelty.

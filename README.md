# CRC32 Update Circuit Optimization

This repository is the workspace for a reproducible search for optimized
combinational XOR2 networks implementing a 64-bit parallel reflected IEEE
CRC-32 state update.

Phase 1 reference, matrix-generation, structural verification, metric, random,
and formal-equivalence infrastructure is implemented. Phase 2 deterministic
baselines are generated and verified. No optimizer, stochastic search,
candidate, or Pareto frontier has been produced.

Experiment control documents:

- [`SPEC.md`](SPEC.md) freezes semantics, the permitted circuit model, metrics,
  and candidate acceptance criteria.
- [`PLAN.md`](PLAN.md) is the development roadmap and defines phase validation
  gates.
- [`STATUS.md`](STATUS.md) records completed work, current best results, and
  unresolved issues.
- [`results/search_log.jsonl`](results/search_log.jsonl) will contain one
  machine-readable record for every optimization attempt.

Optimization commands will be added only after the corresponding Phase 3 tools
exist and have been validated.

## Continuous Integration

GitHub Actions runs the `CI` workflow for pull requests, pushes to `master`, and
manual dispatches. It checks the control files and search log, regenerates the
Phase 1 fixture, runs the unit and rejection suite, checks 97 exact plus 100,000
seeded random vectors, runs formal equivalence, and validates the deterministic
Phase 2 baselines.

Phase 1 reference, matrix, parser, metric, equivalence, rejection, and formal
tests run in the same CI gate. Baseline checks do not run any stochastic or
candidate optimization.

## Circuit Metric Model

Each separately instantiated XOR2 node is a distinct physical gate, even when
another node has the same inputs. Metric normalization preserves those instances
so fanout-aware duplication can trade additional gates for reduced fanout.
Common-subexpression merging is measured as an explicit optimization that emits
a different circuit, not as an automatic verifier rewrite.

## Phase 1 Commands

Install the formal tools on Ubuntu/Debian:

```bash
sudo apt-get install -y yosys z3
```

The distribution's `yosys` package must provide or depend on the `yosys-abc`
executable. Ubuntu 24.04 packages it as `yosys-abc`; Ubuntu 22.04 uses the
`berkeley-abc` dependency name.

Evaluate the normative Python reference:

```bash
python3 -m reference.crc32_reference 0x12345678 0x0123456789abcdef
```

Regenerate the GF(2) matrix and the unoptimized structural validation fixture:

```bash
python3 -m generator.build_matrix \
  --matrix-output /tmp/crc32_matrix.json \
  --network-output /tmp/valid_crc32_network.v
cmp verifier/fixtures/valid_crc32_network.v /tmp/valid_crc32_network.v
```

Run the unit tests, including every deliberately invalid circuit:

```bash
python3 -m unittest -v verifier.test_verifier
```

Run the acceptance verifier. Its JSON report includes independently recomputed
metrics, the 97 exact-vector result, random seed, and random-vector count:

```bash
python3 -m verifier.verify_network \
  verifier/fixtures/valid_crc32_network.v \
  --random-tests 100000 \
  --seed 0xC32A5EED \
  --output /tmp/phase1_verification.json
python3 -m json.tool /tmp/phase1_verification.json
```

Run exhaustive formal equivalence between the independently generated
structural fixture and the Verilog reference:

```bash
python3 -m verifier.run_formal \
  verifier/fixtures/valid_crc32_network.v \
  --module crc32_network
```

The network path is mandatory. The runner parses that submitted file, derives
its module name, copies it to an isolated temporary directory, and renders the
formal script for that exact file. `--module` is optional but, when supplied,
must match the parsed module declaration.

`verifier/fixtures/valid_crc32_network.v` is an unoptimized Phase 1 validation
fixture, not a candidate, Pareto result, or measured Phase 2 baseline.

## Phase 2 Baseline Commands

Generate the four baseline circuits and record generation timings:

```bash
python3 -m generator.baseline_generator \
  --output-dir results/baselines \
  --timings-output /tmp/baseline_generation_timings.json
```

Run the complete Phase 1 verifier and formal flow for every baseline, then
write the independently measured table:

```bash
python3 -m verifier.verify_baselines \
  --baselines-dir results/baselines \
  --generation-timings /tmp/baseline_generation_timings.json \
  --metrics-output results/baseline_metrics.csv \
  --random-tests 100000 \
  --seed 0xC32A5EED
```

The Yosys/ABC baseline starts from the independent expansion, runs conventional
Yosys optimization and ABC mapping, and accepts only XOR/NOT output cells. NOT
phases are propagated algebraically and must cancel at every primary output;
the resulting committed circuit contains only permitted XOR2 gates and aliases.
Observed runtimes are machine-dependent. No command in Phase 2 performs
stochastic optimization or creates an optimization candidate.

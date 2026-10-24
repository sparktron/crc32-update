# Research: how do our CRC-32 XOR2 networks compare with published methods and open-source generators?

**Date:** 2026-10-24 · **Decision this feeds:** the comparison, novelty, and
publishability sections of the final report (`SPEC.md` Section 11, gate G6) ·
**Out of scope:** FPGA LUT or ASIC cell-area comparisons, pipelined or
multi-cycle architectures, CRC polynomials other than IEEE CRC-32, and any
claim of global optimality.

**Question.** For the frozen function in `SPEC.md` — one 64-bit parallel
update of a raw 32-bit reflected IEEE CRC-32 state, as a combinational
network of physical two-input XOR gates — which published methods and
open-source generators report XOR2 counts or XOR depths, and which of those
numbers can be compared directly with ours?

Our measured results (independent verifier, `results/metrics.csv`):

| Circuit | XOR2 | Depth | Max fanout | Excess fanout >4 |
| --- | ---: | ---: | ---: | ---: |
| A / B (seed 16,564) | 439 | 8 | 5 | 5 |
| B7 (depth-7 budget, seed 40,505) | 441 | 7 | 5 | 5 |
| C (depth-6 budget, seed 56,140) | 470 | 6 | 6 | 20 |
| Yosys/ABC baseline (Yosys 0.9) | 1,123 | 7 | 15 | 536 |
| Unshared per-output trees | 1,390 | 6 (balanced) / 51 (serial) | 20 | 1,038 |

Comparability rule used below: a number is **directly comparable** only if it
counts two-input XOR gates for the same Boolean function (the 32 outputs of
the standard CRC-32 update as a function of the 32 state bits and 64 data
bits). Bit reflection is not an obstacle: the reflected and non-reflected
forms differ only by permuting inputs and outputs, which leaves XOR2 count,
depth, and fanout unchanged (see Inference).

## Facts

### Open-source generators

- crcZero 1.2.0 (MIT, uploaded 2026-03-23) derives per-output XOR equations by
  "GF(2) iterative symbolic unrolling" and emits them "directly as HDL
  assigns". Its resource table counts "Minimum 2-input XOR operations per clock
  cycle (actual gate count after synthesis may be lower due to sharing)" and
  lists CRC-32/ISO-HDLC (the reflected Ethernet CRC) at D=64 as **1390**. It
  gives no logic depth. —
  [PyPI JSON for crczero](https://pypi.org/pypi/crczero/json), read
  2026-10-24; repository linked from it:
  [bard0-design/crcZero](https://github.com/bard0-design/crcZero).
- Xilinx XAPP209 v1.0 (Chris Borrelli, 2001-03-23) generates CRC-32 XOR
  equations with `crcgen.pl`; its optimization step "looks for an even number"
  of occurrences of a variable and removes it (for example "A XOR A XOR B"
  becomes "B"). That is GF(2) term cancellation within each equation, not
  sharing across outputs. —
  [XAPP209 PDF (York mirror)](https://www.cs.york.ac.uk/rts/docs/Xilinx-datasource-2003-q1/appnotes/xapp209.pdf),
  sections "Generate XOR Equations" and "Optimize XOR equations".
- The OpenCores `parallelcrcgen` project (Evgeni Stavinov, LGPL, page last
  updated 2014-07-30) generates Verilog or VHDL "for a parallel CRC of any data
  width between 1 and 1024". The project page reports no XOR counts and does
  not describe any sharing. —
  [OpenCores parallelcrcgen](https://opencores.org/projects/parallelcrcgen).
- crcgen 2.6 (Michael Büsch, GPLv2+, uploaded 2023-10-13) generates
  "synthesizable and combinatorial" HDL that "runs in one clock cycle". Its
  package description reports no XOR counts and mentions no sharing. —
  [PyPI JSON for crcgen](https://pypi.org/pypi/crcgen/json).

### Published parallel-CRC complexity results

- Zhang and Tang, "Low-Complexity Parallel Cyclic Redundancy Check", Proc.
  IEEE ISCAS 2021, DOI
  [10.1109/ISCAS51556.2021.9401679](https://doi.org/10.1109/ISCAS51556.2021.9401679)
  ([NSF PAR record](https://par.nsf.gov/biblio/10225256);
  [author manuscript](https://par.nsf.gov/servlets/purl/10225256), read
  2026-10-24):
  - They model a p-parallel LFSR as r(t+p) = A^p·r(t) + B_p·u_p(t) (their
    Eq. 2) and evaluate the IEEE CRC-32 generator polynomial (their Table I).
  - Table II (p = 2(n−k) = 64 for CRC-32) reports, for the non-transformed
    least-significant-tap (LST) input design of their reference [11]: 485 ones
    in the feedback matrix A^p, implemented with 221 XORs at critical path
    5; 484 ones in the pre-processing matrix B_p, with 250 XORs at critical
    path 5; and **503 XORs total at critical path 6**.
  - The same table reports **469 XORs total at critical path 6** for their
    proposed state-transformed design, and 581 XORs at critical path 6 for the
    transformed design of [11].
  - Table III (p = 4(n−k) = 128) reports 939 XORs at critical path 7 (LST,
    non-transformed) and 873 at critical path 7 (proposed). That width is not
    ours.
  - XOR counts were obtained with "the substructure sharing method that can
    set the critical path delay (CPD) constraint in [10]", after minimizing
    the number of ones by searching for transformations.
  - Inserting the input at the j-th tap makes the LFSR compute the remainder
    of u(x)·x^j / g(x) rather than u(x)·x^(n−k) / g(x). They argue that error
    detection is unaffected when encoder and decoder use the same mapping, and
    that the post-processing multiplication by T can therefore be removed.
- Brenningmeyer, Göttsche and Ruckelshausen, "Enhanced Reliability Design
  Automation Methodology considering the Generation of Parallel CRC Modules
  based on arbitrary CRC Polynomials and unlimited Data-Word Widths" (Osnabrück
  University of Applied Sciences and Intel, PDF dated 2009-03-09), Table 1:
  at a 64-bit data width their Perl-generated netlist synthesized to **4
  levels of logic** and a normalized area of 4.5 (8-bit = 1.0). The table
  does not name a polynomial, cell library, or gate model. —
  [PDF](https://www.hs-osnabrueck.de/fileadmin/HSOS/Homepages/COALA/Veroeffentlichungen/2009-Intel.pdf).

### XOR-count minimization methods

- Boyar and Peralta, "On the Shortest Linear Straight-Line Program for
  Computing Linear Forms" (MFCS 2008): "SLP is shown to be NP-hard", a special
  case of the decision problem "is shown to be Max SNP-Complete", and
  cancellation-free heuristics "have approximation ratios of at least 3/2". —
  [author page](https://www.imada.sdu.dk/u/joan/mfcs08.html).
- Tan and Peyrin, "Improved Heuristics for Short Linear Programs" (TCHES
  2020, ePrint 2019/847): randomized Boyar–Peralta-style heuristics that
  "outperform state-of-the-art algorithms such as Paar or Boyar-Peralta (or
  open synthesis tools such as Yosys)" and apply "on matrices of reasonable
  sizes (up to about 32 x 32)". —
  [ePrint 2019/847](https://eprint.iacr.org/2019/847).
- Boyar, Find and Peralta, "Small Low-Depth Circuits for Cryptographic
  Applications", Cryptography and Communications 11(1):109–127 (online
  2018-03-24), DOI
  [10.1007/s12095-018-0296-3](https://doi.org/10.1007/s12095-018-0296-3):
  introduces DCLO, a heuristic "used to create small linear circuits given
  depth constraints", where the constraints specify input arrival depths and
  per-output depth limits. —
  [NIST CSRC record](https://csrc.nist.gov/pubs/journal/2018/03/small-lowdepth-circuits-for-cryptographic-applicat/final).

### Observed in this repository

- Our frozen 32×96 transformation matrix (`generator/build_matrix.py`) has 485
  ones in its 32 CRC-state columns and 937 ones in its 64 data columns, for
  1,422 in total. Its row weights range from 34 to 52. Each `crc[i]` column
  equals the `data[i]` column for i < 32. — computed 2026-10-24 at commit
  `bc951f1`.
- Unshared XOR trees need (row weight − 1) gates per output, which gives
  1,422 − 32 = 1,390 for our matrix. That matches our `independent_per_output`
  and `balanced_per_output` baselines (`results/baseline_metrics.csv`).

## Inference

- **crcZero's 1,390 is directly comparable and equals our unshared baseline.**
  Its table counts two-input XOR operations for reflected CRC-32 at a 64-bit
  data width, it emits per-output equations without sharing, and 1,390 is
  exactly the unshared count for our matrix. Against that generator's own
  figure, A/B uses 31.6% of the XOR2 gates (439/1,390), B7 31.7%, and C 33.8%.
  crcZero gives no depth. A balanced realization of its equations would have
  depth 6, the same as Candidate C.
- **The Zhang–Tang feedback matrix is our state block.** Their A^p has 485
  ones, exactly the number in our 32 CRC-state columns. A^64 is the
  state-transition part of every 64-bit parallel CRC-32 update, so up to the
  bit-reflection permutation it is the same matrix.
- **The Zhang–Tang totals (503 and 469 XORs at depth 6) are not directly
  comparable.** Their LST-input and state-transformed designs compute a
  different function: their pre-processing matrix has 484 ones, against 937
  in our data columns, because the data is inserted at a different tap and
  the remainder is bijectively remapped. Those designs fit a CRC
  encoder/decoder whose two ends share the mapping. They do not implement the
  raw CRC-32 state update frozen in `SPEC.md`, which any standard CRC-32
  implementation must interoperate with. At the same depth of 6, our
  Candidate C (470) is close to their 469–503. Ours solves the harder,
  standard function, but that is a caution against claiming novelty, not a
  head-to-head win, because the function and the CPD counting conventions
  differ.
- **Their sub-block counts are partially comparable.** For the identical
  A^64 block alone, they report 221 XORs at depth 5. We have not measured our
  networks' cost for that block in isolation, because our circuits share
  gates across the state and data blocks, so no comparison is drawn.
- **Bit reflection does not affect any of our metrics.** Reflection reverses
  bit order in the inputs and outputs. Relabelling inputs and outputs is a
  graph isomorphism of the XOR network, so XOR2 count, depth, and fanout are
  preserved. Normal and reflected CRC-32 counts can therefore be compared
  once the function is otherwise identical.
- **Depth 6 is provably minimal for this function.** The heaviest output row
  has 52 ones, so that output depends on 52 inputs. In any circuit of
  two-input gates, a signal at depth d depends on at most 2^d inputs, so that
  output needs depth at least ⌈log2 52⌉ = 6. Candidate C (as well as C0 and
  the balanced baseline) therefore attains the minimum possible depth. The
  certificate is the row weight, which anyone can recompute from
  `generator/build_matrix.py`. This is an optimality statement about depth
  only, not about gate count.
- **Gate-count optimality cannot be claimed.** The general problem is NP-hard
  (Boyar–Peralta 2008). Our searches are seeded heuristics, and no lower bound
  near 439 has been established. The randomized Tan–Peyrin heuristics were
  evaluated up to about 32×32, while our matrix is 32×96, so they were not
  shown to apply here and were not run.
- **The 2009 Osnabrück figures are not comparable.** "4 levels of logic" for
  synthesized standard cells at an unstated polynomial says nothing about
  XOR2 depth or count, since a library cell may implement a multi-input XOR.
- **XAPP209-style generators reduce to the unshared count.** Term
  cancellation alone produces per-output equations, so its XOR2 cost before
  synthesis equals the unshared 1,390 (or the serial 51-deep chain if the
  equations are realized left to right).

## Speculation

- Applying the Zhang–Tang state transformation to an encoder/decoder pair
  that controls both ends would likely give gate counts below ours. That would
  be a different, non-interoperable function and outside this experiment.
- Depth-constrained heuristics such as DCLO might find depth-6 or depth-7
  networks below 470 or 441 gates. They have not been run on this matrix.

## Unresolved

- **Campobello, Patanè and Russo, "Parallel CRC Realization", IEEE Trans.
  Computers 52(10), 2003** (DOI 10.1109/TC.2003.1234528) is the most-cited
  parallel-CRC paper. Search snippets attribute two-input XOR counts and XOR
  levels for CRC-32 to it, but the full text was not accessible (ResearchGate
  returned HTTP 403), so no number from it is used here. It needs institutional
  IEEE Xplore access; check whether its data width equals the polynomial
  degree (32) rather than 64.
- **Pei and Zukowski (IEEE Trans. Commun., 1992), Glaise (IBM J. R&D, 1997),
  Spachmann (IEEE D&T, 2001), and Zhang's reference [10]** (IEEE TCAS-II,
  2019) were not read. [10] defines the substructure-sharing method and CPD
  convention behind the Zhang–Tang counts. Whether its XOR counts are
  strictly two-input, and how it treats the final state-plus-data XOR, is
  inferred from context only.
- **The crcZero repository and generator were not downloaded or run.** Its
  1,390 comes from its package description. Running it and normalizing its
  output through our verifier would confirm the figure and its depth. That
  needs approval to download and execute third-party code.
- **The OutputLogic whitepaper** (OpenCores doc 1247248105, dated 2009-06-28)
  contained no extractable text, so whether that generator shares
  subexpressions is unconfirmed.
- **No lower bound on XOR2 count** has been computed. The gap between 439 and
  the true minimum is unknown. SAT/SMT certification at this size (96 inputs,
  hundreds of gates) is far beyond the exact six-node cone study of Phase 5.

## Recommendation

Report the comparison in two tiers.

1. **Direct comparison.** Use crcZero (1,390 XOR2, reflected CRC-32, D=64) and
   our own unshared and Yosys/ABC baselines. Against these, A/B, B7, and C use
   about one third of the gates, at depths 8, 7, and 6.
2. **Context only.** Cite Zhang–Tang (469–503 XORs at CPD 6) with an explicit
   statement that it computes a transformed, non-standard remainder, that its
   state block matches ours exactly, and that its totals are close to ours.

State that depth 6 is proven minimal by the row-weight bound. Make no
gate-count optimality or novelty claim.

Main risk: an unread paper (Campobello et al. or a later one) may report a
standard-function 64-bit CRC-32 XOR2 count at or below ours, which would turn
our result into a reproduction rather than an improvement.

Strongest case against: the closest published work (Zhang–Tang) reaches
roughly the same gate counts at the same depth for a closely related problem.
A reviewer could reasonably call our result unsurprising for a CSE/BP-style
search.

Reverse this if a source with full text available gives a directly comparable
(standard function, XOR2, 64-bit) count. If it is lower, report ours as not
improving on it. If the crcZero figure does not reproduce when run through
our verifier, drop it from tier 1.

## Verify

- [x] Every Facts line links a source opened this session, with a date or
  version. (Search snippets that were not opened are excluded from Facts and
  listed under Unresolved.)
- [x] Nothing under Facts is inference. The repository observations are
  direct computations at commit `bc951f1`.
- [x] Unresolved is non-empty.
- [x] The recommendation names what would reverse it.
- Not run: crcZero execution and normalization through our verifier, which
  needs approval to download and run third-party code. Paywalled papers were
  not read because no access was available.

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
- Campobello, Patanè and Russo, "Parallel CRC Realization", IEEE Trans.
  Computers 52(10):1312–1319, 2003, DOI
  [10.1109/TC.2003.1234528](https://doi.org/10.1109/TC.2003.1234528). Read
  2026-10-24 from the authors' own copy, archived by the Wayback Machine on
  2006-05-10:
  [tccrc.pdf](https://web.archive.org/web/20060510231352/http://ai.unime.it/~gp/publications/full/tccrc.pdf).
  This is a 20-page dvips manuscript created 2004-11-12, not IEEE's typeset
  version. Its SHA-1 (base32 `KD43KIJXI75J2SFQLZTCF75OI5GAYVCO`) matches the
  digest in the archive's index. Page and section numbers below are the
  manuscript's.
  - The method allows the parallel width w to differ from the degree m. For
    the w = m case, each next-state bit is an XOR over the bits (x_j ⊕ d_j),
    and the paper notes that each x_j occurs at most once per equation. For
    CRC-32 (Sect. IV-B, p. 13) it prints only the 32×32 matrix F^32, as hex
    rows.
  - Sect. V (pp. 15–16) compares with Shieh et al. [14] (J. Inf. Sci. Eng.,
    May 2001) at **m = w = 32**:
    - [14] reports 448 2-input XORs at 15 XOR levels for the matrix
      realization before optimization, and 408 2-input XORs at 7 gate levels
      after Synopsys optimization.
    - Campobello et al. count the ones in F^32 and build each multi-input
      XOR as a binary tree. That gives **452 2-input XORs** with "only 5
      levels" before optimization.
    - Sharing common XOR subexpressions by hand reduces this to **370 gates**,
      with no depth stated. The authors had no Synopsys and give no
      tool-optimized count.
  - Table I (p. 16) reports FPGA LUTs and delays for w = m only. For CRC-32
    it gives 162 LUTs and 7.3 ns.
  - The paper gives **no XOR2 count or depth for w = 64**, and no XOR2 count
    for any w ≠ m.
- Shieh, Sheu, Chen and Lo, "A Systematic Approach for Parallel CRC
  Computations", J. Inf. Sci. Eng. 17(3):445–461, 2001, DOI
  10.1688/JISE.2001.17.3.6. Read 2026-10-26 from the journal's free PDF,
  downloaded by hand from the
  [JISE paper record](https://jise.iis.sinica.edu.tw/JISESearch/pages/View/PaperView.jsf?keyId=84_1287)
  (17 pages, SHA-1 `09061b5a78a4c1d0094d7bf259b6c6c4b8e1eaac`).
  - The "Type-I" design computes the standard remainder
    S(x) = x^(n−k)·M(x) mod G(x) with a shift register over r message bits
    per clock (Sects. 2–3.1). Sect. 3.1 assumes r is less than the polynomial
    degree.
  - Table 3 (Sect. 4.2, p. 459) gives Type-I results for the CRC-32
    polynomial at r = 1, 2, 4, 8, 16 and 32. It counts 2-input XORs, and
    critical path delay (CPD) as 2-input XOR levels. Values come from
    Synopsys, and gate count (GC) is in 2-input NAND equivalents from the
    COMPASS library.
    - Cascaded blocks: (N_z − 2)·r + r XORs, where N_z is the number of
      nonzero polynomial coefficients (15 for CRC-32). At r = 16 that is
      224 XORs at CPD 8; at **r = 32, 448 XORs at CPD 15**.
    - Flattened blocks, optimized by Synopsys for area and timing: 177 XORs
      at CPD 4 for r = 16, and **408 XORs at CPD 7 for r = 32**.
    - Multi-width designs: 354 XORs for the r ∈ {16, 32} block (CPD 8 at
      r = 32) and 384 for r ∈ {4, 8, 16, 32} (CPD 13 at r = 32). Both also
      need 32 multiplexers.
  - The largest width is r = 32. There is **no 64-bit result**. The test
    chip (TSMC 0.6 µm) supports r = 1, 2, 4 or 8.
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

- crcZero commit `98c55152fa9724990eac47aa8a0107557c7396ef` (version 1.2.0),
  run 2026-10-24 in isolation by `scripts/compare_crczero.py` for
  CRC-32/ISO-HDLC at D=64: its self-test passed, its 32 emitted `assign`
  equations equal the frozen matrix bit-for-bit, and they contain 1,390 XOR
  operators. Converted to the restricted XOR2 subset, the operators chained as
  written give 1,390 XOR2 at depth 51 (maximum fanout 20, excess 1,038), and
  balanced trees give 1,390 XOR2 at depth 6. Both passed 97 exact vectors,
  100,000 random vectors with seed `0xC32A5EED`, and formal equivalence. Their
  structural hashes equal those of `independent_per_output` and
  `balanced_per_output` respectively. —
  `results/external/crczero_comparison.json`.

- Our frozen 32×96 transformation matrix (`generator/build_matrix.py`) has 485
  ones in its 32 CRC-state columns and 937 ones in its 64 data columns, for
  1,422 in total. Its row weights range from 34 to 52. Each `crc[i]` column
  equals the `data[i]` column for i < 32. — computed 2026-10-24 at commit
  `bc951f1`.
- Unshared XOR trees need (row weight − 1) gates per output, which gives
  1,422 − 32 = 1,390 for our matrix. That matches our `independent_per_output`
  and `balanced_per_output` baselines (`results/baseline_metrics.csv`).
- The CRC-32 F^32 rows printed by Campobello et al. contain 452 ones in
  total, with row weights from 12 to 17. Recomputing F^32 for polynomial
  0x04C11DB7 from the shift-register companion matrix reproduces the
  published rows exactly once bit indices are reversed (their x_0 is our
  x_31). Then 32 (x_j ⊕ d_j) gates plus Σ(row weight − 1) = 420 give 452,
  which is the paper's count. — computed 2026-10-24 in a scratch script, not
  committed.

## Inference

- **crcZero's 1,390 is directly comparable and equals our unshared baseline.**
  Running it confirmed that it computes exactly the frozen function and
  emits per-output equations without sharing. Its circuits are our two
  unshared baselines. Against that generator's own
  figure, A/B uses 31.6% of the XOR2 gates (439/1,390), B7 31.7%, and C 33.8%.
  crcZero states no depth. Its output read literally is a depth-51 chain, and
  balanced it has depth 6, the same as Candidate C.
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
- **Campobello et al. do not report a directly comparable count.** All of
  their XOR2 figures (452 unshared, 370 with manual sharing, and the 448/408
  they quote from Shieh et al.) are for w = 32 data bits. That is a different
  function: 64 inputs, against 96 in ours. Their 452 is the w = 32 analogue
  of our 1,390 unshared baseline. Manual sharing removes about 18% of it
  (370/452), while our searched networks remove about 68% at w = 64
  (439/1,390). The functions differ, so this shows their sharing was not
  systematic. It is not a head-to-head comparison. The main risk below is
  closed for this paper.
- **Their "5 levels" omits the input XOR level.** Their heaviest F^32 row
  has 17 ones, so that output depends on 34 inputs (17 x_j and 17 d_j). By
  the 2^d bound used below, it needs depth ⌈log2 34⌉ = 6. A 17-input tree has
  depth ⌈log2 17⌉ = 5, so the paper's figure must leave out the level that
  forms x_j ⊕ d_j. Their 5 is therefore not a 2-input depth in our sense.
- **Shieh et al. do not report a directly comparable count either.** Their
  Type-I function is the standard CRC-32 update, but only up to r = 32
  (64 inputs, against 96 in ours). Campobello et al. quote its r = 32
  figures (448 at 15 levels, 408 at 7) correctly. The cascaded formula gives
  14·32 = 448, and CRC-32's 0x04C11DB7 has 14 nonzero bits plus x^32, so
  N_z = 15. At r = 32, the 408 after Synopsys is below Campobello's
  unshared 452 but above their 370 with manual sharing. The 354-XOR
  multi-width block is smaller still, at depth 8. None of these numbers
  says anything directly about w = 64. The main risk below is closed for
  this paper too.
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

- **Campobello et al. was read from the authors' preprint,** not IEEE's
  typeset version, so the published article's numbers could differ slightly.
- **Pei and Zukowski (IEEE Trans. Commun., 1992), Glaise (IBM J. R&D, 1997),
  Spachmann (IEEE D&T, 2001), and Zhang's reference [10]** (IEEE TCAS-II,
  2019) were not read. [10] defines the substructure-sharing method and CPD
  convention behind the Zhang–Tang counts. Whether its XOR counts are
  strictly two-input, and how it treats the final state-plus-data XOR, is
  inferred from context only.
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
   Cite Campobello et al. (452 XOR2 unshared and 370 with manual sharing, at
   w = 32) and Shieh et al. (448 cascaded at 15 levels and 408 after
   Synopsys at 7 levels, at r = 32) as the standard 32-bit-width reference
   points, and say that none of them is at our width.

State that depth 6 is proven minimal by the row-weight bound. Make no
gate-count optimality or novelty claim.

Main risk: an unread paper (one listed under Unresolved, or a later one) may
report a standard-function 64-bit CRC-32 XOR2 count at or below ours, which
would turn our result into a reproduction rather than an improvement.
Campobello et al. and Shieh et al. have now been read, and neither reports
a 64-bit count.

Strongest case against: the closest published work (Zhang–Tang) reaches
roughly the same gate counts at the same depth for a closely related problem.
A reviewer could reasonably call our result unsurprising for a CSE/BP-style
search.

Reverse this if a source with full text available gives a directly comparable
(standard function, XOR2, 64-bit) count. If it is lower, report ours as not
improving on it.

## Verify

- [x] Every Facts line links a source opened this session, with a date or
  version. (Search snippets that were not opened are excluded from Facts and
  listed under Unresolved.)
- [x] Nothing under Facts is inference. The repository observations are
  direct computations at commit `bc951f1`.
- [x] Unresolved is non-empty.
- [x] The recommendation names what would reverse it.
- Not run: the paywalled papers still listed under Unresolved were not read
  because no access was available. (crcZero was run and verified on
  2026-10-24 with the user's approval; see Observed in this repository.
  Campobello et al. was read on 2026-10-24 from the authors' archived
  preprint, also with the user's approval. Shieh et al. was read on
  2026-10-26 from a PDF the user downloaded by hand.)

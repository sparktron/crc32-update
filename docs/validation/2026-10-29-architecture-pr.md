# Architecture PR integration validation — 2026-10-29

The architecture patch was committed as `b87659c` on
`codex/architecture-fixes` and integrated with `master` at `4221a33` before
publication as a pull request. The original 2026-10-27 evidence remains in
`2026-10-27-architecture-fixes.md`; this record describes the combined tree.

## Validation

- `python3 -B -m unittest discover`: **136 tests passed**, 0 failed,
  0 skipped, in **237.961 seconds**.
- `python3 -B -m verifier.build_results --check --require-spec-minimum`:
  **passed**, exit 0. All five submitted artifacts and four committed
  baselines passed structural, exact, random and formal verification;
  three distinct Pareto circuits matched the recorded publication files.
- The focused lifecycle, result-builder and split-log suites passed
  **62 tests in 7.679 seconds** during conflict resolution.
- Black checks, Ruff checks, shell syntax and diff whitespace checks passed
  for the resolved source changes.

The final full-suite and result-check output was saved locally to
`/tmp/crc32-architecture-pr-tests-2026-10-29.log` and
`/tmp/crc32-architecture-pr-results-2026-10-29.log`. Each corresponding
`.status` file contains `0`.

## PR #15 review follow-up: truncated journal literals

The remaining P2 finding (`discussion_r4414619399`) is addressed by
recognizing exact, nonempty proper prefixes of `true`, `false`, and `null`
at the decoder's expected-value position. Only an unterminated final line
can be recovered; malformed literals and newline-terminated or interior
partial records still fail before persistent changes.

- The new recovery regression failed on all **20 subcases** before the fix:
  every literal prefix in both ordinary fields and nested values after
  Unicode text.
- `python3 -B -m unittest optimizer.test_search_lifecycle optimizer.test_runner_lifecycle`:
  **32 tests passed** in **3.512 seconds** after the fix. Coverage includes
  read-only inspection, byte-for-byte damaged backups and repaired logs,
  checkpoint preservation, resume without seed dispatch, and nine corrupt
  tails that must remain untouched without backups.
- Black, Ruff and diff whitespace checks passed for the follow-up changes.
- The full clean rebuild remains delegated to the PR CI gate.

## Preserved integration contracts

The merge retains the per-experiment files in `results/search_logs/`, their
algorithm mappings, CLI defaults and checkpoint paths. The fresh-gate finishing
fallback and frozen historical adaptive implementations are preserved. AST
comparison confirmed that the bounded builder, trial construction, Candidate A
construction and strategy objective ordering match the integrated master.

The current submitted B7 has 440 gates at depth 7 and Candidate C has
465 gates at depth 6. Their artifacts, measurements, selected-seed provenance
and IDs remain those of master. The later lookahead experiment's evidence is
also retained. No numerical result, netlist, historical journal or checkpoint
was changed by the architecture patch relative to this master.

The only publication metadata correction is C0's physical circuit identity:
`0c80bfcc8e2b` becomes `103832014152`. Its 1,390 gates, depth 6, fanouts and
dominated status are unchanged. CSV and JSON were compared field-for-field
against master with only those C0 identity fields allowed to differ.

The original working checkout and its experiments were not modified. All merge
and validation work took place in the managed architecture-fixes worktree.

## Limits

The complete clean-clone gate was **not run locally**, and no hours-long search
budget or hardware validation was launched. The PR's existing CI workflow
runs `scripts/clean_rebuild.sh --in-place`; its result is separate from the
local checks above. An operator can also run the committed branch manually:

```bash
set -o pipefail
scripts/clean_rebuild.sh codex/architecture-fixes 2>&1 | tee /tmp/crc32-architecture-clean-rebuild.log
```

The lifecycle limits documented in `../search_lifecycle.md` remain: unbound
unfinished legacy budgets cannot be extended, dispatched workers may finish
after cancellation, and tool versions are recorded rather than pinned.

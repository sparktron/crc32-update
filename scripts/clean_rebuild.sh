#!/usr/bin/env bash
# Rebuild and re-verify every committed result from a clean checkout.
#
# Usage: scripts/clean_rebuild.sh [--in-place] [REVISION]
#
# By default the given revision (HEAD) is cloned into a temporary directory and
# every documented command runs there, so local edits and untracked files
# cannot influence the outcome. --in-place runs in the current checkout
# instead, which must be clean (CI uses this on its fresh checkout).
#
# Each submitted artifact is regenerated from its recorded seed or
# construction and compared byte-for-byte with the committed file. Every
# candidate is then re-verified (parser, 97 exact vectors, 100,000 random
# vectors, formal equivalence) and the committed frontier and metrics must
# match regeneration. The seeded search budgets and the Phase 5 SMT study are
# not re-executed, because they take hours; build_results cross-checks their
# checkpoints and complete search-log records instead. Finally the checkout
# must be unchanged.

set -euo pipefail

in_place=false
revision=HEAD
for argument in "$@"; do
  case "${argument}" in
    --in-place) in_place=true ;;
    -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "unknown option: ${argument}" >&2; exit 2 ;;
    *) revision="${argument}" ;;
  esac
done

repository="$(git rev-parse --show-toplevel)"
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
output="${work}/out"
mkdir -p "${output}"

if "${in_place}"; then
  cd "${repository}"
  if [ -n "$(git status --porcelain)" ]; then
    echo "--in-place requires a clean checkout" >&2
    exit 1
  fi
else
  commit="$(git -C "${repository}" rev-parse --verify "${revision}^{commit}")"
  git clone --quiet --no-local "${repository}" "${work}/checkout"
  git -C "${work}/checkout" checkout --quiet --detach "${commit}"
  cd "${work}/checkout"
fi
echo "Rebuilding $(git rev-parse --short HEAD) in $(pwd)"

seed="0xC32A5EED"
random_tests=100000

step() {
  printf '\n== %s\n' "$*"
}

same() {
  if ! cmp --silent "$1" "$2"; then
    echo "MISMATCH: $1 differs from regenerated $2" >&2
    exit 1
  fi
  echo "identical: $1"
}

checkpoint_seed() {
  python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["incumbent_seed"])' "$1"
}

step "Unit and rejection tests"
python3 -m unittest \
  verifier.test_verifier \
  verifier.test_verify_candidate \
  verifier.test_build_results \
  generator.test_baseline_generator \
  optimizer.test_optimize \
  optimizer.test_phase5_exact \
  optimizer.test_depth_bounded

step "Phase 1 matrix, structural fixture, and formal check"
python3 -m generator.build_matrix \
  --matrix-output "${output}/matrix.json" \
  --network-output "${output}/valid_crc32_network.v"
same verifier/fixtures/valid_crc32_network.v "${output}/valid_crc32_network.v"
python3 -m verifier.verify_network verifier/fixtures/valid_crc32_network.v \
  --random-tests "${random_tests}" --seed "${seed}" \
  --output "${output}/phase1_verification.json"
python3 -m verifier.run_formal verifier/fixtures/valid_crc32_network.v \
  --module crc32_network

step "Phase 2 baselines"
python3 -m generator.baseline_generator \
  --output-dir "${output}/baselines" \
  --timings-output "${output}/baseline_timings.json"
for baseline in independent_per_output balanced_per_output greedy_cse; do
  same "results/baselines/${baseline}.v" "${output}/baselines/${baseline}.v"
done
if cmp --silent results/baselines/yosys_abc.v "${output}/baselines/yosys_abc.v"; then
  echo "identical: results/baselines/yosys_abc.v"
else
  echo "NOTE: yosys_abc.v differs; this baseline depends on the Yosys/ABC release"
fi
python3 -m verifier.verify_baselines \
  --baselines-dir "${output}/baselines" \
  --generation-timings "${output}/baseline_timings.json" \
  --metrics-output "${output}/baseline_metrics.csv" \
  --random-tests "${random_tests}" --seed "${seed}"

step "Phase 3 Candidate A replay and record check"
python3 -m optimizer.optimize \
  --replay-frontier results/phase3/candidate_a_frontier.json \
  --artifact "${output}/phase3_candidate_a.v"
same results/candidate_a_min_area.v "${output}/phase3_candidate_a.v"
python3 -m verifier.verify_candidate \
  --candidate results/candidate_a_min_area.v \
  --frontier results/phase3/candidate_a_frontier.json \
  --metrics results/phase3/candidate_a_metrics.csv \
  --random-tests "${random_tests}" --seed "${seed}" > /dev/null
echo "Phase 3 records verified"

step "Phase 4 Candidate A replay"
python3 -m optimizer.optimize \
  --replay-frontier results/phase4/candidate_a_frontier.json \
  --artifact "${output}/phase4_candidate_a.v"
same results/phase4/candidate_a_extended.v "${output}/phase4_candidate_a.v"

step "Phase 4 Candidate B and C0 starting points"
python3 -m optimizer.phase4_candidates --replay-dir "${output}/phase4"
for name in candidate_b_depth8 candidate_c_min_depth; do
  same "results/phase4/${name}.v" "${output}/phase4/${name}.v"
done
# The refinement budgets accepted no improvement, so their outputs are the
# starting points unchanged.
same results/phase4/candidate_b_refined.v "${output}/phase4/candidate_b_depth8.v"
same results/phase4/candidate_c_refined.v "${output}/phase4/candidate_c_min_depth.v"

# These are the original Kraft-bounded B7 and C, superseded on 2026-10-27.
# They are replayed for provenance. build_results --check below replays the
# current B7 and C from their recorded seeds.
step "Superseded Kraft-bounded B7 and C replays"
for cap in 7 6; do
  best="$(checkpoint_seed "results/checkpoints/depth${cap}_bounded_search.json")"
  python3 -m optimizer.depth_bounded --depth-cap "${cap}" \
    --replay-seed "${best}" \
    --artifact "${output}/candidate_depth${cap}_bounded.v"
  same "results/phase6/candidate_depth${cap}_bounded.v" \
    "${output}/candidate_depth${cap}_bounded.v"
done

step "Re-verify submitted candidates and final result records"
python3 -m verifier.build_results --check --require-spec-minimum \
  --random-tests "${random_tests}" --seed "${seed}"

step "Checkout unchanged"
if [ -n "$(git status --porcelain)" ]; then
  git status --short >&2
  echo "the rebuild modified or created files in the checkout" >&2
  exit 1
fi
echo "No tracked or untracked file changed."

printf '\nClean rebuild passed for %s.\n' "$(git rev-parse --short HEAD)"

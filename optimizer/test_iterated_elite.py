"""Prerun identity, lineage replay, frozen layout, selection and analysis tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from optimizer import elite_prefix, iterated_elite
from optimizer.depth_bounded import search_seed_bounded
from optimizer.iterated_elite import (BASE, BUDGET, GENERATION_SIZE, REPLICATES, budgets,
                                      build_trial, child_segments, child_switch, endpoints,
                                      lineage_states, paired, replicate_of, select_parents,
                                      structural_sha256)
from optimizer.kraft_slack import search_seed_slack
from optimizer.optimize import independently_check
from verifier.build_results import structural_fingerprint
from verifier.search_logs import read_records


def _trial(seed, gates, *, excess=0, root=None, switch=0, decisions=180, digest=None):
    return {"seed": seed, "xor2_count": gates, "total_excess_fanout_above_4": excess,
            "lineage": [[root or seed, 0]] + ([[seed, switch]] if switch else []),
            "switch": switch, "sharing_decisions": decisions,
            "structural_sha256": digest or f"circuit-{seed}"}


class IteratedEliteTests(unittest.TestCase):
    def test_generation_zero_matches_historical_controls(self):
        for cap, seed, historical in ((7, 390040, search_seed_bounded),
                                      (6, 390041, search_seed_slack)):
            candidate, diagnostics = build_trial(((seed, 0),), cap)
            self.assertEqual(candidate.render(), historical(seed, cap).render())
            self.assertIsNone(diagnostics["prefix_state_sha256"])
            self.assertIsNone(diagnostics["parent_seed"])
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "trial.v"
                path.write_text(candidate.render("any_module_name"))
                self.assertEqual(structural_fingerprint(path), diagnostics["structural_sha256"])

    def test_single_switch_equals_the_elite_prefix_child(self):
        for cap, parent, seed, prefix in ((7, 400800, 390042, 95), (6, 320099, 390044, 86)):
            child, diagnostics = build_trial(((parent, 0), (seed, prefix)), cap)
            reference, recorded = elite_prefix.build_trial(seed, cap, parent, prefix)
            self.assertEqual(child.render(), reference.render())
            self.assertEqual(diagnostics["prefix_state_sha256"], recorded["prefix_state_sha256"])
            self.assertEqual(diagnostics["sharing_decisions"], recorded["sharing_decisions"])

    def test_grandchild_replays_the_childs_own_trajectory_then_diverges(self):
        child_chain = ((400800, 0), (390042, 95))
        _, child = build_trial(child_chain, 7)
        states = lineage_states(child_chain, 7)
        self.assertEqual(len(states) - 1, child["sharing_decisions"])
        self.assertEqual(states[95], child["prefix_state_sha256"])
        switch = child_switch(child)
        self.assertEqual(switch, 95 + (child["sharing_decisions"] - 95) // 2)
        first, diagnostics = build_trial(child_chain + ((390043, switch),), 7)
        again, repeated = build_trial(child_chain + ((390043, switch),), 7)
        other, sibling = build_trial(child_chain + ((390045, switch),), 7)
        for row in (diagnostics, repeated, sibling):
            self.assertEqual(row["prefix_state_sha256"], states[switch])
            row.pop("runtime")
        self.assertEqual(diagnostics, repeated)
        self.assertEqual(first.render(), again.render())
        self.assertNotEqual(first.render(), other.render())
        self.assertEqual(diagnostics["lineage"], [[400800, 0], [390042, 95], [390043, switch]])
        self.assertLessEqual(independently_check(first).maximum_depth, 7)
        with self.assertRaises(ValueError):
            build_trial(((400800, 0), (390046, 95), (390047, 95)), 7)
        with self.assertRaises(ValueError):
            build_trial(((400800, 0), (390046, child["sharing_decisions"] + 50)), 7)

    def test_parent_prefix_digest_matches_the_committed_precursor_replay(self):
        committed = json.loads(elite_prefix.PARENTS.read_text())["caps"]["7"]["elite"][0]
        half = committed["prefixes"]["50"]
        parent = {"seed": 400800, "lineage": [[400800, 0]], "child_switch": half["decisions"],
                  "sharing_decisions": committed["sharing_decisions"]}
        self.assertEqual(iterated_elite._prefix_digest(parent, 7), half["state_sha256"])
        with self.assertRaisesRegex(ValueError, "does not replay"):
            iterated_elite._prefix_digest({**parent, "sharing_decisions": 1}, 7)

    def test_child_switch_halves_the_redrawn_suffix(self):
        self.assertEqual(child_switch({"switch": 0, "sharing_decisions": 185}), 92)
        self.assertEqual(child_switch({"switch": 92, "sharing_decisions": 190}), 141)
        self.assertEqual(child_switch({"switch": 141, "sharing_decisions": 188}), 164)

    def test_selection_ranks_dedupes_and_limits_roots(self):
        with mock.patch.multiple(iterated_elite, PARENT_COUNT=3, ROOT_LIMIT=2):
            trials = [_trial(10, 440, root=1, switch=90), _trial(11, 440, root=1, switch=90),
                      _trial(12, 439, root=1, switch=90), _trial(13, 441, excess=2),
                      _trial(14, 441, excess=1, digest="circuit-12"),
                      _trial(15, 441, excess=3), _trial(16, 438, switch=179, decisions=180)]
            chosen = [t["seed"] for t in select_parents(trials)]
            # 16 cannot redraw two decisions, 14 repeats 12's circuit, root 1 is full after 12 and 10.
            self.assertEqual(chosen, [12, 10, 13])
            with self.assertRaises(ValueError):
                select_parents(trials[:3])

    def test_frozen_layout_matches_budgets_and_uses_fresh_seeds(self):
        spans = []
        for cap in (7, 6):
            rows = budgets(cap)
            self.assertEqual([name for name, _, _ in rows],
                             ["gen0", "fresh", "gen1", "gen2", "gen3", "gen4"])
            expected = BASE[cap]
            for _, start, count in rows:
                self.assertEqual(start, expected)
                expected += count
                spans.append(range(start, start + count))
            self.assertEqual(expected - BASE[cap], 36_000)
            fresh = sum(count for name, _, count in rows if name in ("gen0", "fresh"))
            iterated = sum(count for name, _, count in rows if name != "fresh")
            self.assertEqual((fresh, iterated), (REPLICATES * BUDGET,) * 2)
        self.assertFalse(any(isinstance(r.get("seed"), int) and any(r["seed"] in s for s in spans)
                             for r in read_records()))
        self.assertEqual(replicate_of("gen0", 600_000, 600_399), 0)
        self.assertEqual(replicate_of("fresh", 604_000, 605_600), 1)
        self.assertEqual(replicate_of("gen2", 624_000, 627_999), 9)
        parents = [[{"lineage": [[r * 1000 + p, 0]], "child_switch": 90 + p} for p in range(20)]
                   for r in range(REPLICATES)]
        self.assertEqual(child_segments(620_000 + 400 + 47, 620_000, parents),
                         ((1002, 0), (620_447, 92)))

    def test_paired_statistics_and_frozen_verdicts(self):
        best = paired([-3, -2, -4, -1, -3, -2, -3, -2, -4, -3], -1)
        self.assertAlmostEqual(best["mean"], -2.7)
        self.assertLess(best["z_normal_approximation"], -3)
        self.assertAlmostEqual(best["sign_flip_p_one_sided"], 1 / 1024)
        self.assertTrue(iterated_elite.best_passes(best))
        self.assertFalse(iterated_elite.best_passes(paired([-2, -1] * 5, -1)))
        degenerate = paired([-3] * 10, -1)
        self.assertIsNone(degenerate["z_normal_approximation"])
        self.assertFalse(iterated_elite.best_passes(degenerate))
        tail = paired([5, 6, 4, 7, 5, 6, 4, 5, 6, 5], 1)
        self.assertTrue(iterated_elite.tail_passes(tail, 70, 17))
        self.assertFalse(iterated_elite.tail_passes(tail, 70, 36))
        self.assertFalse(iterated_elite.tail_passes(paired([1, -1] * 5, 1), 10, 10))

    def test_endpoints_count_distinct_tail_circuits(self):
        trials = [dict(_trial(seed, gates), structural_sha256=digest) for seed, gates, digest in
                  ((1, 450, "a"), (2, 442, "b"), (3, 441, "c"), (4, 441, "c"), (5, 436, "d"))]
        with mock.patch.object(iterated_elite, "GENERATION_SIZE", 2):
            result = endpoints(trials, 7)
        self.assertEqual((result["best"], result["best_seed"]), (436, 5))
        self.assertEqual((result["tail_distinct"], result["tail_trials"]), (3, 4))
        self.assertEqual((result["target_trials"], result["best_after"]), (1, [442, 441]))

    def test_parent_tables_and_summary_from_logged_generations(self):
        # Two replicates of four trials per generation: two parents, two children each.
        sizes = dict(REPLICATES=2, BUDGET=12, GENERATION_SIZE=4, GENERATIONS=2,
                     PARENT_COUNT=2, CHILDREN=2, ROOT_LIMIT=1)
        # Synthetic lineages cannot be replayed, so prefix digests are stand-ins.
        with tempfile.TemporaryDirectory() as directory, mock.patch.multiple(
                iterated_elite, ROOT=Path(directory), LOG=Path(directory) / "log.jsonl",
                _prefix_digest=lambda parent, cap: f"d{parent['seed']}", **sizes):
            log = []

            def record(name, cap, start, seed, gates, lineage, decisions=10):
                run = iterated_elite.run_name(name, cap)
                log.append({"algorithm": iterated_elite.algorithm_name(name, cap), "seed": seed,
                            "verification_passed": True, "accepted": False,
                            "runtime_seconds": 1.0,
                            "final_metrics": {"xor2_count": gates,
                                              "total_excess_fanout_above_4": 0}})
                parent = lineage[-2][0] if len(lineage) > 1 else None
                row = {"seed": seed, "xor2_count": gates, "lineage": lineage,
                       "parent_seed": parent, "switch": lineage[-1][1],
                       "prefix_state_sha256": parent and f"d{parent}",
                       "sharing_decisions": decisions, "sharing_retained": 1,
                       "finishing_retained": gates - 1, "structural_sha256": f"c{seed}"}
                with (Path(directory) / f"{run}_diagnostics.jsonl").open("a") as stream:
                    stream.write(json.dumps(row) + "\n")
                (Path(directory) / "log.jsonl").write_text(
                    "".join(json.dumps(r) + "\n" for r in log))

            cap = 7
            layout = {name: start for name, start, _ in iterated_elite.budgets(cap)}
            for offset in range(8):
                seed = layout["gen0"] + offset
                record("gen0", cap, layout["gen0"], seed, 450 - offset % 4, [[seed, 0]])
            for offset in range(16):
                record("fresh", cap, layout["fresh"], layout["fresh"] + offset, 449, [[0, 0]])
            for generation in (1, 2):
                table = iterated_elite.frozen_parent_table(cap, generation)
                self.assertEqual(table["pool_sizes"], [4 * generation] * 2)
                parents = iterated_elite._trial_parents(table)
                start = layout[f"gen{generation}"]
                for offset in range(8):
                    seed = start + offset
                    lineage = [list(item) for item in child_segments(seed, start, parents)]
                    record(f"gen{generation}", cap, start, seed, 440 - generation, lineage)
            first = json.loads((Path(directory) / "parents_depth7_gen1.json").read_text())
            # The best two generation-0 trials of replicate 0, at half their sharing phase.
            self.assertEqual([(p["seed"], p["child_switch"]) for p in first["replicates"][0]],
                             [(600_003, 5), (600_002, 5)])
            second = iterated_elite.frozen_parent_table(cap, 2)
            self.assertEqual(second["replicates"][0][0]["lineage"],
                             [[600_003, 0], [layout["gen1"], 5]])
            self.assertEqual(second["replicates"][0][0]["child_switch"], 7)
            by_budget = {name: iterated_elite.load_budget(name, start, count, cap)
                         for name, start, count in iterated_elite.budgets(cap)}
            summary = iterated_elite.cap_summary(cap, by_budget)
            self.assertEqual([r["best"] for r in summary["iterated"]], [438, 438])
            self.assertEqual([r["best"] for r in summary["fresh"]], [447, 447])
            self.assertEqual(summary["generations"]["1"]["children_below_parent"], 8)
            self.assertEqual(first["replicates"][1][0]["prefix_state_sha256"], "d600007")
            by_budget["gen2"][3]["prefix_state_sha256"] = "tampered"
            with self.assertRaisesRegex(ValueError, "does not replay its parent's prefix"):
                iterated_elite.cap_summary(cap, by_budget)
            # Rewriting a frozen table is refused.
            (Path(directory) / "parents_depth7_gen1.json").write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "does not reproduce"):
                iterated_elite.frozen_parent_table(cap, 1)


if __name__ == "__main__":
    unittest.main()

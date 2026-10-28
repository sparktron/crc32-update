"""Prerun identity, prefix replay, frozen layout, selection and analysis tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from optimizer import elite_prefix
from optimizer.depth_bounded import search_seed_bounded
from optimizer.elite_prefix import (BASE, CHILDREN, FRACTIONS, PARENTS, arms, build_trial,
                                    child_spec, difference, passes_screen, prefix_decisions,
                                    replay_parent, select_parents)
from optimizer.kraft_slack import search_seed_slack
from optimizer.optimize import independently_check
from verifier.search_logs import read_records


class ElitePrefixTests(unittest.TestCase):
    def test_fresh_and_empty_prefix_match_historical_controls(self):
        for cap, seed, parent in ((7, 390000, 400800), (6, 390001, 320099)):
            historical = search_seed_bounded(seed, cap) if cap == 7 else search_seed_slack(seed, cap)
            fresh, diagnostics = build_trial(seed, cap)
            empty, _ = build_trial(seed, cap, parent, 0)
            self.assertEqual(fresh.render(), historical.render())
            self.assertEqual(empty.render(), historical.render())
            self.assertIsNone(diagnostics["prefix_state_sha256"])

    def test_children_replay_the_parent_prefix_then_diverge(self):
        table = json.loads(PARENTS.read_text())["caps"]["7"]["elite"][0]
        replay = replay_parent(400800, 7)
        self.assertEqual(replay["final_metrics"]["xor2_count"], 438)
        self.assertEqual(replay, {k: v for k, v in table.items() if k != "source_algorithm"})
        half = replay["prefixes"]["50"]
        first, diagnostics = build_trial(390020, 7, 400800, half["decisions"])
        again, repeated = build_trial(390020, 7, 400800, half["decisions"])
        other, sibling = build_trial(390021, 7, 400800, half["decisions"])
        for row in (diagnostics, repeated, sibling):
            self.assertEqual(row["prefix_state_sha256"], half["state_sha256"])
            row.pop("runtime")
        self.assertEqual(first.render(), again.render())
        self.assertEqual(diagnostics, repeated)
        self.assertNotEqual(first.render(), other.render())
        self.assertLessEqual(independently_check(first).maximum_depth, 7)
        whole = replay["sharing_decisions"]
        _, full = build_trial(390022, 7, 400800, whole)
        self.assertEqual((full["sharing_decisions"], full["sharing_created"]), (whole, whole))
        self.assertEqual(full["prefix_state_sha256"], replay["prefixes"]["100"]["state_sha256"])
        with self.assertRaises(ValueError):
            build_trial(390023, 7, 400800, whole + 1)

    def test_cap6_child_replays_the_committed_prefix(self):
        parent = json.loads(PARENTS.read_text())["caps"]["6"]["elite"][0]
        self.assertEqual((parent["seed"], parent["final_metrics"]["xor2_count"]), (320099, 462))
        quarter = parent["prefixes"]["25"]
        candidate, diagnostics = build_trial(390024, 6, 320099, quarter["decisions"])
        self.assertEqual(diagnostics["prefix_state_sha256"], quarter["state_sha256"])
        self.assertLessEqual(independently_check(candidate).maximum_depth, 6)

    def test_selection_rule_reproduces_committed_parents(self):
        table = json.loads(PARENTS.read_text())
        for cap in (7, 6):
            selected = select_parents(cap)
            for group in ("elite", "median"):
                committed = table["caps"][str(cap)][group]
                self.assertEqual([(seed, algorithm, metrics) for seed, algorithm, metrics in selected[group]],
                                 [(p["seed"], p["source_algorithm"], p["final_metrics"]) for p in committed])

    def test_frozen_layout_uses_fresh_seeds(self):
        ranges = []
        for cap in (7, 6):
            expected = BASE[cap]
            for _, _, start, count in arms(cap):
                self.assertEqual(start, expected)
                expected += count
                ranges.append(range(start, start + count))
            self.assertEqual(expected, BASE[cap] + 10_000)
        historical = [r for r in read_records() if not str(r.get("algorithm")).startswith("elite-prefix-")]
        self.assertFalse(any(isinstance(r.get("seed"), int) and any(r["seed"] in span for span in ranges)
                             for r in historical))
        parents = ((400800, 190), (40505, 185))
        self.assertEqual(child_spec(500_000, 500_000, parents, 50), (400800, 95))
        self.assertEqual(child_spec(500_000 + CHILDREN, 500_000, parents, 100), (40505, 185))
        self.assertEqual(prefix_decisions(185, 25), 46)

    def test_frozen_screen(self):
        self.assertTrue(passes_screen(difference(-2.0, 0.5, 0.0, 0.0)))
        for mean, error in ((-1.99, 0.1), (-3.0, 1.1), (-3.0, 0.0)):
            self.assertFalse(passes_screen(difference(mean, error, 0.0, 0.0)))

    def test_summary_clusters_by_parent_and_checks_prefixes(self):
        # Two parents x two children per arm; elite children are 7 gates better.
        gates = {"elite": [[449, 451], [447, 449]], "median": [[456, 456], [455, 457]],
                 "fresh": [456, 457, 455, 456]}
        with tempfile.TemporaryDirectory() as directory, mock.patch.multiple(
                elite_prefix, ROOT=Path(directory), LOG=Path(directory) / "log.jsonl",
                PARENT_COUNT=2, CHILDREN=2, FRESH_COUNT=4):
            table = {"caps": {}}
            log = []
            for cap in (7, 6):
                parents = {group: [{"seed": cap * 10 + i, "final_metrics": {"xor2_count": 450},
                                    "prefixes": {str(f): {"decisions": f, "state_sha256": f"{cap}{i}{f}"}
                                                 for f in FRACTIONS}} for i in range(2)]
                           for group in ("elite", "median")}
                table["caps"][str(cap)] = parents
                for group, fraction, start, count in elite_prefix.arms(cap):
                    values = gates[group] if group == "fresh" else sum(gates[group], [])
                    rows = []
                    for offset, value in enumerate(values):
                        parent = None if group == "fresh" else parents[group][offset // 2]
                        prefix = parent["prefixes"][str(fraction)] if parent else None
                        log.append({"algorithm": elite_prefix.algorithm_name(group, fraction, cap),
                                    "seed": start + offset, "verification_passed": True,
                                    "accepted": False, "runtime_seconds": 1.0,
                                    "final_metrics": {"xor2_count": value}})
                        rows.append({"seed": start + offset, "xor2_count": value,
                                     "parent_seed": parent and parent["seed"],
                                     "prefix_decisions": prefix and prefix["decisions"],
                                     "prefix_state_sha256": prefix and prefix["state_sha256"],
                                     "sharing_retained": 1, "finishing_retained": 1,
                                     "sharing_decisions": 1})
                    name = elite_prefix.run_name(group, fraction, cap)
                    (Path(directory) / f"{name}_diagnostics.jsonl").write_text(
                        "".join(json.dumps(row) + "\n" for row in rows))
            (Path(directory) / "log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in log))
            summary = elite_prefix.summarize(table)
            for cap in ("7", "6"):
                result = summary["caps"][cap]
                primary = result["contrasts"]["50"]
                self.assertAlmostEqual(result["arms"][f"stage1_elite_f50_depth{cap}"]["standard_error"], 1.0)
                self.assertAlmostEqual(primary["elite_minus_median"]["mean"], -7.0)
                self.assertAlmostEqual(primary["elite_minus_median"]["z_normal_approximation"], -7.0)
                self.assertAlmostEqual(primary["elite_minus_fresh"]["mean"], -7.0)
                self.assertTrue(result["h8_passes"])
            table["caps"]["6"]["elite"][1]["prefixes"]["75"]["state_sha256"] = "tampered"
            with self.assertRaisesRegex(ValueError, "prefix replay differs"):
                elite_prefix.summarize(table)


if __name__ == "__main__":
    unittest.main()

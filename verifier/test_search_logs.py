"""Tests for the per-experiment search logs and the one-time split."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.split_search_log import migrate_checkpoints, split
from verifier.search_logs import EXPERIMENT_LOGS, log_file_for, log_files, read_records

LOGGED_ALGORITHMS = (
    "gf2-bp-cse-depth-stochastic-v1",
    "phase4-depth8-starting-point-v1",
    "phase4-balanced-depth-starting-point-v1",
    "phase4-depth8-refinement-v1",
    "phase4-min-depth-refinement-v1",
    "phase5-exact-single-cone-v1",
    "phase5-exact-exclusive-cone-v2",
    "kraft-bounded-bp-cse-depth7-v1",
    "kraft-bounded-bp-cse-depth6-v1",
    "dclo-kraft-depth7-v1",
    "ablation-rewrite-depth7-v1",
    "kraft-slack-tiebreak-depth6-v1",
    "kraft-adaptive-tiebreak-half-depth6-v1",
)


def _record(algorithm: str, seed: int) -> dict[str, object]:
    return {"attempt_id": f"{algorithm}-seed-{seed}", "algorithm": algorithm, "seed": seed}


class MappingTests(unittest.TestCase):
    def test_every_logged_algorithm_maps_to_exactly_one_file(self) -> None:
        for algorithm in LOGGED_ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                self.assertEqual(log_file_for(algorithm).parent, Path("results/search_logs"))

    def test_unregistered_algorithm_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not registered"):
            log_file_for("new-unregistered-search-v1")

    def test_no_prefix_shadows_another(self) -> None:
        prefixes = [prefix for prefix, _ in EXPERIMENT_LOGS]
        for prefix in prefixes:
            self.assertEqual([other for other in prefixes if prefix.startswith(other)], [prefix])


class ReadTests(unittest.TestCase):
    def test_directory_reads_every_file_in_name_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b.jsonl").write_text(json.dumps(_record("x", 2)) + "\n")
            (root / "a.jsonl").write_text(json.dumps(_record("x", 1)) + "\n")
            (root / "ignored.lock").write_text("")
            self.assertEqual([path.name for path in log_files(root)], ["a.jsonl", "b.jsonl"])
            self.assertEqual([record["seed"] for record in read_records(root)], [1, 2])
            self.assertEqual(read_records(root / "b.jsonl"), [_record("x", 2)])


class SplitTests(unittest.TestCase):
    def test_split_preserves_every_line_and_order_and_migrates_checkpoints(self) -> None:
        records = [
            _record("dclo-kraft-depth7-v1", 1),
            _record("gf2-bp-cse-depth-stochastic-v1", 0),
            _record("dclo-kraft-depth7-v1", 2),
            _record("phase4-depth8-refinement-v1", 5),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "search_log.jsonl"
            legacy.write_text("".join(json.dumps(record) + "\n" for record in records))
            logs = root / "search_logs"
            counts = split(legacy, logs)
            self.assertEqual(
                counts,
                {"candidate_a.jsonl": 1, "dclo.jsonl": 2, "phase4_refinement.jsonl": 1},
            )
            self.assertEqual(
                [record["seed"] for record in read_records(logs / "dclo.jsonl")], [1, 2]
            )
            with self.assertRaises(FileExistsError):
                split(legacy, logs)

            checkpoints = root / "checkpoints"
            (checkpoints / "nested").mkdir(parents=True)
            relative = checkpoints / "a.json"
            relative.write_text(
                '{\n  "algorithm": "gf2-bp-cse-depth-stochastic-v1",\n'
                '  "search_log_path": "../search_log.jsonl"\n}\n'
            )
            nested = checkpoints / "nested" / "b.json"
            nested.write_text(
                json.dumps(
                    {"algorithm": "dclo-kraft-depth7-v1", "search_log_path": str(legacy)},
                    indent=2,
                )
            )
            migrated = migrate_checkpoints(checkpoints, legacy, logs)
            self.assertEqual(len(migrated), 2)
            self.assertEqual(
                json.loads(relative.read_text())["search_log_path"],
                "../search_logs/candidate_a.jsonl",
            )
            self.assertEqual(
                json.loads(nested.read_text())["search_log_path"], str(logs / "dclo.jsonl")
            )


if __name__ == "__main__":
    unittest.main()

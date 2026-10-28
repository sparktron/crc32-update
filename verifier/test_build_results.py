"""Regression tests for final frontier and metrics regeneration."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from verifier.build_results import (
    PHASE5_ALGORITHM,
    BoundedBudget,
    Submission,
    check_bounded_search,
    check_class_objectives,
    check_phase5,
    dominates,
    nondominated,
    structural_fingerprint,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _point(count: int, depth: int, fanout: int, excess: int) -> dict[str, int]:
    return {
        "xor2_count": count,
        "maximum_depth": depth,
        "maximum_fanout": fanout,
        "total_excess_fanout_above_4": excess,
    }


class ParetoTests(unittest.TestCase):
    def test_dominance_needs_one_strict_improvement(self) -> None:
        self.assertTrue(dominates(_point(439, 8, 5, 5), _point(439, 9, 6, 5)))
        self.assertFalse(dominates(_point(439, 8, 5, 5), _point(439, 8, 5, 5)))
        self.assertFalse(dominates(_point(439, 8, 5, 5), _point(1390, 6, 20, 1038)))

    def test_frontier_keeps_tradeoffs_and_drops_dominated_points(self) -> None:
        points = {
            "area": _point(439, 8, 5, 5),
            "depth": _point(1390, 6, 20, 1038),
            "superseded": _point(439, 9, 6, 5),
            "middle": _point(1123, 7, 15, 536),
        }
        self.assertEqual(nondominated(points), ["area", "depth", "middle"])


class ClassObjectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metrics = {
            "A": _point(439, 8, 5, 5),
            "B": _point(439, 8, 5, 5),
            "B7": _point(441, 7, 5, 5),
            "C": _point(470, 6, 6, 20),
            "C0": _point(1390, 6, 20, 1038),
        }

    def test_each_class_wins_its_objective(self) -> None:
        check_class_objectives(self.metrics)

    def test_candidate_c_needs_the_gate_count_tie_break(self) -> None:
        self.metrics["C"], self.metrics["C0"] = self.metrics["C0"], self.metrics["C"]
        with self.assertRaisesRegex(ValueError, "Candidate C does not minimize depth"):
            check_class_objectives(self.metrics)

    def test_candidate_b_must_win_within_its_depth_bound(self) -> None:
        self.metrics["B"] = _point(441, 7, 5, 5)
        with self.assertRaisesRegex(ValueError, "Candidate B does not minimize"):
            check_class_objectives(self.metrics)

    def test_candidate_b_must_meet_its_depth_bound(self) -> None:
        self.metrics["B"] = _point(445, 9, 5, 5)
        with self.assertRaisesRegex(ValueError, "class constraint"):
            check_class_objectives(self.metrics)

    def test_missing_required_class_is_rejected(self) -> None:
        del self.metrics["C"]
        with self.assertRaisesRegex(ValueError, "missing: C"):
            check_class_objectives(self.metrics)


class FingerprintTests(unittest.TestCase):
    def test_renaming_module_and_wires_keeps_the_fingerprint(self) -> None:
        source = (FIXTURES / "duplicate_instances.v").read_text()
        renamed = re.sub(r"\bn(\d+)\b", r"w\1", source).replace(
            "module duplicate_instances", "module renamed_copy"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "renamed.v"
            path.write_text(renamed)
            self.assertEqual(
                structural_fingerprint(path),
                structural_fingerprint(FIXTURES / "duplicate_instances.v"),
            )

    def test_different_structures_have_different_fingerprints(self) -> None:
        self.assertNotEqual(
            structural_fingerprint(FIXTURES / "duplicate_instances.v"),
            structural_fingerprint(FIXTURES / "unreachable_node.v"),
        )


class Phase5RecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = Path("results/phase4/candidate_b_refined.v")
        self.outcomes = [
            {
                "root": "n1",
                "solver_status": "unsat",
                "replacement_gate_count": None,
                "witness": None,
            }
        ]
        self.study = {
            "status": "completed",
            "configuration": {"candidate": str(self.candidate), "roots": ["n1"]},
            "outcomes": self.outcomes,
        }
        self.checkpoint = {"completed_roots": ["n1"], "outcomes": self.outcomes}
        self.records = [
            {
                "algorithm": PHASE5_ALGORITHM,
                "accepted": False,
                "study_outcome": self.outcomes[0],
            }
        ]

    def test_unimproving_study_is_summarized(self) -> None:
        summary = check_phase5(self.study, self.checkpoint, self.records, self.candidate)
        self.assertEqual(summary["solver_status_counts"], {"unsat": 1})
        self.assertEqual(summary["accepted_replacements"], 0)

    def test_unintegrated_witness_is_rejected(self) -> None:
        self.outcomes[0]["witness"] = [["a", "b"]]
        self.outcomes[0]["replacement_gate_count"] = 1
        with self.assertRaisesRegex(ValueError, "replacement witness"):
            check_phase5(self.study, self.checkpoint, self.records, self.candidate)

    def test_study_on_another_candidate_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "submitted Candidate B"):
            check_phase5(
                self.study, self.checkpoint, self.records, Path("results/other.v")
            )


class BoundedBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.budget = BoundedBudget(7, root / "checkpoint.json", root / "incumbents")
        self.budget.incumbent_dir.mkdir()
        self.artifact = root / "candidate.v"
        self.submission = Submission("B7", self.artifact, bounded=self.budget)
        self.best = {**_point(448, 7, 5, 5), "output_depths": [7]}
        worse = {**_point(456, 7, 5, 5), "output_depths": [7]}
        incumbent = self.budget.incumbent_dir / "seed_11.v"
        incumbent.write_text("module best;\n")
        self.artifact.write_text("module best;\n")
        self.records = [
            self._record(10, worse, True, self.budget.incumbent_dir / "seed_10.v"),
            self._record(11, self.best, True, incumbent),
            self._record(12, worse, False, None),
        ]
        self.checkpoint = {
            "algorithm": self.budget.algorithm,
            "depth_cap": 7,
            "seed_start": 10,
            "seed_count": 3,
            "completed_seeds": 3,
            "random_tests": 100_000,
            "random_seed": 0xC32A5EED,
            "incumbent_seed": 11,
            "incumbent_metrics": self.best,
            "status": "completed",
        }

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _record(self, seed, metrics, accepted, artifact):
        return {
            "algorithm": self.budget.algorithm,
            "attempt_id": f"{self.budget.algorithm}-seed-{seed}",
            "seed": seed,
            "final_metrics": metrics,
            "verification_passed": True,
            "accepted": accepted,
            "artifact": None if artifact is None else str(artifact),
        }

    def _check(self):
        self.budget.checkpoint.write_text(json.dumps(self.checkpoint))
        return check_bounded_search(
            self.submission,
            {**self.best, "unreachable_nodes": []},
            self.records,
            100_000,
            0xC32A5EED,
            replay=False,
        )

    def test_completed_budget_identifies_its_best_trial(self) -> None:
        provenance = self._check()
        self.assertEqual(provenance["seed"], 11)
        self.assertEqual(provenance["accepted_incumbents"], 2)

    def test_incomplete_budget_is_rejected(self) -> None:
        self.checkpoint["status"] = "running"
        with self.assertRaisesRegex(ValueError, "not complete"):
            self._check()

    def test_missing_seed_is_rejected(self) -> None:
        del self.records[2]
        with self.assertRaisesRegex(ValueError, "complete ordered seed range"):
            self._check()

    def test_better_unaccepted_trial_is_rejected(self) -> None:
        self.records[2]["final_metrics"] = {**_point(440, 7, 5, 5), "output_depths": [7]}
        with self.assertRaisesRegex(ValueError, "not the last accepted"):
            self._check()

    def test_artifact_differing_from_incumbent_is_rejected(self) -> None:
        self.artifact.write_text("module edited;\n")
        with self.assertRaisesRegex(ValueError, "differs from its accepted incumbent"):
            self._check()


class SelectedTrialTests(unittest.TestCase):
    """A submission may be a logged trial other than the budget's incumbent."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.root = root
        # Seed 11 wins on maximum fanout. Seed 12 ties its XOR2 count and has
        # lower excess fanout, so it is nondominated.
        self.incumbent_metrics = {**_point(465, 6, 5, 21), "output_depths": [6]}
        self.selected_metrics = {**_point(465, 6, 6, 19), "output_depths": [6]}
        self.records = [
            self._record(10, {**_point(480, 6, 6, 30), "output_depths": [6]}, True),
            self._record(11, self.incumbent_metrics, True),
            self._record(12, self.selected_metrics, False),
            self._record(13, {**_point(466, 6, 6, 19), "output_depths": [6]}, False),
        ]
        self.checkpoint = {
            "algorithm": "test-algorithm-depth6-v1",
            "depth_cap": 6,
            "seed_start": 10,
            "seed_count": 4,
            "completed_seeds": 4,
            "random_tests": 100_000,
            "random_seed": 0xC32A5EED,
            "incumbent_seed": 11,
            "incumbent_metrics": self.incumbent_metrics,
            "status": "completed",
        }

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _record(self, seed, metrics, accepted):
        return {
            "algorithm": "test-algorithm-depth6-v1",
            "attempt_id": f"test-seed-{seed}",
            "seed": seed,
            "final_metrics": metrics,
            "verification_passed": True,
            "accepted": accepted,
            "artifact": str(self.root / f"seed_{seed}.v") if accepted else None,
        }

    def _check(self, selected_seed, measured, source="module selected;\n"):
        budget = BoundedBudget(
            6,
            self.root / "checkpoint.json",
            self.root,
            logged_algorithm="test-algorithm-depth6-v1",
            selected_seed=selected_seed,
        )
        budget.checkpoint.write_text(json.dumps(self.checkpoint))
        artifact = self.root / "candidate.v"
        artifact.write_text("module selected;\n")
        submission = Submission("C", artifact, bounded=budget)
        with mock.patch.object(BoundedBudget, "regenerate_source", return_value=source):
            return check_bounded_search(
                submission, {**measured, "unreachable_nodes": []}, self.records,
                100_000, 0xC32A5EED,
            )

    def test_nondominated_minimum_trial_is_accepted(self) -> None:
        provenance = self._check(12, self.selected_metrics)
        self.assertEqual(provenance["seed"], 12)
        self.assertEqual(provenance["winning_attempt_id"], "test-seed-11")
        self.assertEqual(provenance["selection"], "selected nondominated minimum-XOR2 trial")

    def test_trial_above_the_budget_minimum_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "minimum XOR2 count"):
            self._check(13, self.records[3]["final_metrics"])

    def test_dominated_trial_is_rejected(self) -> None:
        self.records[2]["final_metrics"] = {**_point(465, 6, 6, 22), "output_depths": [6]}
        with self.assertRaisesRegex(ValueError, "dominated within its budget"):
            self._check(12, self.records[2]["final_metrics"])

    def test_measurement_must_match_the_selected_record(self) -> None:
        with self.assertRaisesRegex(ValueError, "do not match measurement"):
            self._check(12, self.incumbent_metrics)

    def test_artifact_must_replay_from_the_selected_seed(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not replay"):
            self._check(12, self.selected_metrics, source="module other;\n")


if __name__ == "__main__":
    unittest.main()

"""Regression tests for final frontier and metrics regeneration."""

from __future__ import annotations

from pathlib import Path
import re
import tempfile
import unittest

from verifier.build_results import (
    PHASE5_ALGORITHM,
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


if __name__ == "__main__":
    unittest.main()

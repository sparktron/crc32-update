"""Regression tests for Phase 6 frontier validation."""

from __future__ import annotations

import unittest

from verifier.verify_final import validate_frontier_entries


def _entry(
    candidate_id: str,
    classes: list[str],
    fingerprint: str,
    objectives: tuple[int, int, int, int],
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_classes": classes,
        "structural_fingerprint": fingerprint,
        "metrics": {
            "xor2_count": objectives[0],
            "maximum_depth": objectives[1],
            "maximum_fanout": objectives[2],
            "total_excess_fanout_above_4": objectives[3],
        },
    }


class FinalFrontierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = [
            _entry("candidate_ab", ["A", "B"], "first", (439, 8, 5, 5)),
            _entry("tradeoff", [], "second", (1123, 7, 15, 536)),
            _entry("candidate_c", ["C"], "third", (1390, 6, 20, 1038)),
        ]

    def test_three_distinct_nondominated_entries_are_accepted(self) -> None:
        validate_frontier_entries(self.entries)

    def test_duplicate_circuit_is_rejected(self) -> None:
        self.entries[1]["structural_fingerprint"] = "first"

        with self.assertRaisesRegex(ValueError, "three distinct circuits"):
            validate_frontier_entries(self.entries)

    def test_missing_required_class_is_rejected(self) -> None:
        self.entries[0]["candidate_classes"] = ["A"]

        with self.assertRaisesRegex(ValueError, "candidate class\(es\): B"):
            validate_frontier_entries(self.entries)

    def test_dominated_entry_is_rejected(self) -> None:
        self.entries[1]["metrics"] = {
            "xor2_count": 1400,
            "maximum_depth": 9,
            "maximum_fanout": 21,
            "total_excess_fanout_above_4": 1040,
        }

        with self.assertRaisesRegex(ValueError, "tradeoff is dominated"):
            validate_frontier_entries(self.entries)


if __name__ == "__main__":
    unittest.main()

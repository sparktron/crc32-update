"""Regression tests for Candidate A result-record verification."""

from __future__ import annotations

import unittest

from verifier.verify_candidate import _validate_frontier_verification


class CandidateRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = {
            "exact_vectors_checked": 97,
            "random_vectors_checked": 100_000,
            "random_seed": 0xC32A5EED,
        }
        self.verification = {
            "structural": "passed",
            "exact_vectors": 97,
            "random_vectors": 100_000,
            "random_seed": 0xC32A5EED,
            "formal_equivalence": "passed",
        }

    def test_frontier_verification_matches_performed_checks(self) -> None:
        _validate_frontier_verification(
            {"verification": self.verification},
            self.report,
            100_000,
            0xC32A5EED,
        )

    def test_stale_frontier_verification_is_rejected(self) -> None:
        for field, stale_value in (
            ("structural", "failed"),
            ("exact_vectors", 96),
            ("random_vectors", 99_999),
            ("random_seed", 0),
            ("formal_equivalence", "failed"),
        ):
            with self.subTest(field=field):
                verification = dict(self.verification)
                verification[field] = stale_value
                with self.assertRaisesRegex(
                    ValueError, "verification record does not match"
                ):
                    _validate_frontier_verification(
                        {"verification": verification},
                        self.report,
                        100_000,
                        0xC32A5EED,
                    )


if __name__ == "__main__":
    unittest.main()

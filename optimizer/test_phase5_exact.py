"""Regression tests for bounded exact cone synthesis."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from optimizer.phase5_exact import (
    ALGORITHM,
    Cone,
    _completed_outcomes,
    _cone,
    _stored_outcomes,
    solve_strict_improvement,
)
from verifier.verify_network import NormalizedNetwork, XorNode


class Phase5ExactTests(unittest.TestCase):
    def test_solver_finds_the_exact_three_input_lower_bound(self) -> None:
        cone = Cone(
            root="root",
            nodes=("n0", "n1", "n2"),
            leaves=("a", "b", "c"),
            target_vector=0b111,
        )

        result = solve_strict_improvement(cone, timeout_ms=1_000)

        self.assertEqual(result.status, "sat")
        self.assertEqual(result.gate_count, 2)
        self.assertIsNotNone(result.witness)

    def test_cone_cuts_internally_shared_nodes(self) -> None:
        network = NormalizedNetwork(
            module_name="test",
            nodes=(
                XorNode("xor2", "n0", "a", "b", 0),
                XorNode("xor2", "root", "n0", "c", 1),
                XorNode("xor2", "other", "n0", "d", 2),
            ),
            canonical_inputs={
                "n0": ("a", "b"),
                "root": ("c", "n0"),
                "other": ("d", "n0"),
            },
            output_sources=("root",) * 32,
            direct_output_alias_count=32,
            unreachable_nodes=(),
        )

        cone = _cone(network, "root")

        self.assertEqual(cone.nodes, ("root",))
        self.assertEqual(cone.leaves, ("c", "n0"))

    def test_completed_outcomes_restore_after_interrupted_resume(self) -> None:
        configuration = {"algorithm": ALGORITHM, "roots": ["prior", "resumed"]}
        prior = {
            "root": "prior",
            "original_gate_count": 2,
            "cut_leaf_count": 3,
            "solver_status": "unsat",
            "replacement_gate_count": None,
            "witness": None,
        }
        resumed = {**prior, "root": "resumed", "solver_status": "sat"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_path = root / "study.json"
            log_path = root / "search.jsonl"
            output_path.write_text(json.dumps({"configuration": configuration, "outcomes": [prior]}))
            log_path.write_text(
                "\n".join(
                    (
                        json.dumps({"algorithm": ALGORITHM, "parameters": {"root": "prior"}}),
                        json.dumps(
                            {
                                "algorithm": ALGORITHM,
                                "parameters": {"root": "resumed"},
                                "study_outcome": resumed,
                            }
                        ),
                    )
                )
                + "\n"
            )

            stored = _stored_outcomes(output_path, configuration, {"prior", "resumed"})
            restored = _completed_outcomes(log_path, {"prior", "resumed"}, stored)

        self.assertEqual(restored, {"prior": prior, "resumed": resumed})


if __name__ == "__main__":
    unittest.main()

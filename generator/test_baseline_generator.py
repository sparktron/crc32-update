"""Tests for deterministic Phase 2 baseline generation."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from generator.baseline_generator import (
    render_balanced,
    render_greedy_cse,
    render_independent,
    render_yosys_abc,
)
from generator.build_matrix import build_transformation_matrix
from verifier.verify_network import parse_network, verify_exact_equivalence


class BaselineGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = build_transformation_matrix()

    def _metrics(self, source: str):
        network = parse_network(source).normalize()
        self.assertEqual(verify_exact_equivalence(network), 97)
        return network.metrics()

    def test_independent_expansion(self) -> None:
        metrics = self._metrics(render_independent(self.rows))
        self.assertEqual(metrics.xor2_count, 1390)
        self.assertEqual(metrics.maximum_depth, 51)

    def test_balanced_no_sharing(self) -> None:
        metrics = self._metrics(render_balanced(self.rows))
        self.assertEqual(metrics.xor2_count, 1390)
        self.assertEqual(metrics.maximum_depth, 6)

    def test_greedy_common_subexpression_elimination(self) -> None:
        metrics = self._metrics(render_greedy_cse(self.rows))
        self.assertEqual(metrics.xor2_count, 454)
        self.assertEqual(metrics.maximum_depth, 9)

    @unittest.skipUnless(
        shutil.which("yosys") and shutil.which("yosys-abc"),
        "Yosys and Berkeley ABC are not installed",
    )
    def test_yosys_abc_output_is_normalized_and_equivalent(self) -> None:
        metrics = self._metrics(render_yosys_abc(self.rows))
        self.assertGreater(metrics.xor2_count, 0)

    def test_deterministic_python_generators(self) -> None:
        generators = (render_independent, render_balanced, render_greedy_cse)
        with tempfile.TemporaryDirectory() as temporary_dir:
            marker = Path(temporary_dir) / "used"
            for generator in generators:
                first = generator(self.rows)
                marker.write_text(first)
                self.assertEqual(marker.read_text(), generator(self.rows))


if __name__ == "__main__":
    unittest.main()

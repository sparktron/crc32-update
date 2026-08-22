from __future__ import annotations

import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import unittest

from generator.build_matrix import (
    apply_transformation_matrix,
    basis_signal_names,
    build_transformation_matrix,
    matrix_document,
    render_structural_reference,
)
from reference.crc32_reference import crc32_update_reference
from verifier.verify_network import (
    EquivalenceError,
    ParseError,
    parse_network,
    parse_network_file,
    verify_exact_equivalence,
    verify_random_equivalence,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "verifier" / "fixtures"
VALID_NETWORK = FIXTURES / "valid_crc32_network.v"
INVALID_FIXTURES = FIXTURES / "invalid"
FORMAL_TOOLS_AVAILABLE = bool(
    shutil.which("yosys")
    and shutil.which("yosys-smtbmc")
    and shutil.which("z3")
    and shutil.which("yosys-abc")
)


class ReferenceModelTests(unittest.TestCase):
    def test_frozen_vectors(self) -> None:
        vectors = (
            (0x00000000, 0x0000000000000000, 0x00000000),
            (0xFFFFFFFF, 0x0000000000000000, 0x9ADD2096),
            (0x00000000, 0xFFFFFFFFFFFFFFFF, 0x44660075),
            (0x12345678, 0x0123456789ABCDEF, 0x9B62EADF),
            (0x00000001, 0x0000000000000000, 0xCCAA009E),
            (0x00000000, 0x0000000000000001, 0xCCAA009E),
        )
        for crc, data, expected in vectors:
            with self.subTest(crc=crc, data=data):
                self.assertEqual(crc32_update_reference(crc, data), expected)

    def test_inputs_are_masked_to_frozen_widths(self) -> None:
        expected = crc32_update_reference(0x12345678, 0x0123456789ABCDEF)
        self.assertEqual(
            crc32_update_reference(
                (1 << 80) | 0x12345678,
                (1 << 100) | 0x0123456789ABCDEF,
            ),
            expected,
        )


class MatrixGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = build_transformation_matrix()

    def test_matrix_shape_and_basis_order(self) -> None:
        self.assertEqual(len(self.rows), 32)
        self.assertEqual(len(basis_signal_names()), 96)
        self.assertEqual(basis_signal_names()[0], "crc[0]")
        self.assertEqual(basis_signal_names()[31], "crc[31]")
        self.assertEqual(basis_signal_names()[32], "data[0]")
        self.assertEqual(basis_signal_names()[95], "data[63]")
        self.assertTrue(all(0 <= row < (1 << 96) for row in self.rows))

    def test_matrix_reconstructs_reference(self) -> None:
        generator = random.Random(0x4D4154524958)
        for _ in range(1_000):
            crc = generator.getrandbits(32)
            data = generator.getrandbits(64)
            self.assertEqual(
                apply_transformation_matrix(self.rows, crc, data),
                crc32_update_reference(crc, data),
            )

    def test_matrix_json_round_trip(self) -> None:
        document = matrix_document(self.rows)
        encoded = json.dumps(document, sort_keys=True)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["schema_version"], 1)
        self.assertEqual(len(decoded["rows_hex"]), 32)
        self.assertEqual(len(decoded["basis_order"]), 96)

    def test_structural_fixture_is_reproducible(self) -> None:
        self.assertEqual(
            VALID_NETWORK.read_text(), render_structural_reference(self.rows)
        )


class StructuralParserTests(unittest.TestCase):
    def test_generated_reference_is_accepted(self) -> None:
        network = parse_network_file(VALID_NETWORK).normalize()
        metrics = network.metrics()
        self.assertEqual(metrics.xor2_count, 1_390)
        self.assertEqual(metrics.maximum_depth, 51)
        self.assertEqual(metrics.maximum_fanout, 20)
        self.assertEqual(metrics.total_fanout, 2_812)
        self.assertEqual(metrics.direct_output_alias_count, 32)
        self.assertEqual(metrics.unreachable_nodes, ())

    def test_explicit_xor2_instance_is_accepted(self) -> None:
        lines = [
            "module explicit_xor2(crc, data, next_crc);",
            "input [31:0] crc;",
            "input [63:0] data;",
            "output [31:0] next_crc;",
            "wire n0;",
            "xor2 g0 (.b(data[0]), .y(n0), .a(crc[0]));",
            "assign next_crc[0] = n0;",
        ]
        lines.extend(
            f"assign next_crc[{index}] = crc[{index}];"
            for index in range(1, 32)
        )
        lines.append("endmodule")
        metrics = parse_network("\n".join(lines)).normalize().metrics()
        self.assertEqual(metrics.xor2_count, 1)
        self.assertEqual(metrics.maximum_depth, 1)
        self.assertEqual(metrics.total_fanout, 34)

    def test_invalid_structures_are_rejected(self) -> None:
        expected_errors = {
            "chained_xor.v": "chained or multi-input XOR",
            "cycle.v": "combinational cycle",
            "forbidden_gate.v": "prohibited gate type",
            "forward_reference.v": "forward reference",
            "missing_output.v": "missing or undriven outputs",
            "multiply_defined.v": "multiply defined signal",
            "undefined_signal.v": "undefined signal",
        }
        for filename, expected_error in expected_errors.items():
            with self.subTest(filename=filename):
                with self.assertRaisesRegex(ParseError, expected_error):
                    parse_network_file(INVALID_FIXTURES / filename)

    def test_wrong_function_fails_exact_equivalence(self) -> None:
        network = parse_network_file(
            INVALID_FIXTURES / "wrong_function.v"
        ).normalize()
        with self.assertRaisesRegex(EquivalenceError, "exact vector"):
            verify_exact_equivalence(network)

    def test_unreachable_node_is_reported_and_removed(self) -> None:
        metrics = parse_network_file(
            FIXTURES / "unreachable_node.v"
        ).normalize().metrics()
        self.assertEqual(metrics.xor2_count, 0)
        self.assertEqual(metrics.intermediate_node_count, 0)
        self.assertEqual(metrics.unreachable_nodes, ("assign:dead",))
        self.assertEqual(metrics.total_fanout, 32)

    def test_identical_physical_instances_are_preserved(self) -> None:
        metrics = parse_network_file(
            FIXTURES / "duplicate_instances.v"
        ).normalize().metrics()
        self.assertEqual(metrics.xor2_count, 4)
        self.assertEqual(metrics.intermediate_node_count, 4)
        self.assertEqual(metrics.maximum_depth, 2)
        self.assertEqual(metrics.maximum_fanout, 2)
        self.assertEqual(metrics.total_fanout, 40)
        self.assertEqual(metrics.unreachable_nodes, ())

    def test_alias_propagation_and_excess_fanout(self) -> None:
        lines = [
            "module alias_fanout(crc, data, next_crc);",
            "input [31:0] crc;",
            "input [63:0] data;",
            "output [31:0] next_crc;",
            "wire n0;",
            "wire alias0;",
            "assign n0 = crc[0] ^ data[0];",
            "assign alias0 = n0;",
        ]
        lines.extend(
            f"assign next_crc[{index}] = alias0;" for index in range(10)
        )
        lines.extend(
            f"assign next_crc[{index}] = crc[{index}];"
            for index in range(10, 32)
        )
        lines.append("endmodule")
        metrics = parse_network("\n".join(lines)).normalize().metrics()
        self.assertEqual(metrics.xor2_count, 1)
        self.assertEqual(metrics.maximum_depth, 1)
        self.assertEqual(metrics.output_depths[:10], (1,) * 10)
        self.assertEqual(metrics.maximum_fanout, 10)
        self.assertEqual(metrics.total_fanout, 34)
        self.assertEqual(metrics.total_excess_fanout_above_4, 6)
        self.assertEqual(metrics.direct_output_alias_count, 32)

    def test_cli_exits_nonzero_for_every_invalid_network(self) -> None:
        for path in sorted(INVALID_FIXTURES.glob("*.v")):
            with self.subTest(filename=path.name):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "verifier.verify_network",
                        str(path),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("verification failed", result.stderr)


class EquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.network = parse_network_file(VALID_NETWORK).normalize()

    def test_all_zero_and_basis_vectors(self) -> None:
        self.assertEqual(verify_exact_equivalence(self.network), 97)

    def test_seeded_random_sanity_sample(self) -> None:
        self.assertEqual(
            verify_random_equivalence(
                self.network,
                count=2_000,
                seed=0x54455354,
            ),
            2_000,
        )


class FormalEquivalenceTests(unittest.TestCase):
    def test_rejects_requested_module_mismatch(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "verifier.run_formal",
                str(VALID_NETWORK),
                "--module",
                "not_the_submitted_module",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match submitted module", result.stderr)

    @unittest.skipUnless(
        FORMAL_TOOLS_AVAILABLE,
        "Yosys, Berkeley ABC, and Z3 are not installed",
    )
    def test_yosys_abc_equivalence(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "verifier.run_formal",
                str(VALID_NETWORK),
                "--module",
                "crc32_network",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(VALID_NETWORK.resolve()), result.stdout)

    @unittest.skipUnless(
        FORMAL_TOOLS_AVAILABLE,
        "Yosys, Berkeley ABC, and Z3 are not installed",
    )
    def test_yosys_rejects_wrong_submitted_function(self) -> None:
        wrong_network = INVALID_FIXTURES / "wrong_function.v"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "verifier.run_formal",
                str(wrong_network),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not prove equivalence", result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Generate deterministic Phase 2 CRC-32 XOR2 baseline circuits."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from itertools import combinations
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Sequence

from generator.build_matrix import (
    INPUT_COUNT,
    OUTPUT_COUNT,
    basis_signal_names,
    build_transformation_matrix,
)


@dataclass(frozen=True)
class Operation:
    output: str
    input_a: str
    input_b: str


def _row_terms(row: int) -> list[str]:
    names = basis_signal_names()
    return [names[index] for index in range(INPUT_COUNT) if row & (1 << index)]


def _render_network(
    module_name: str,
    operations: Sequence[Operation],
    output_sources: Sequence[str],
) -> str:
    if len(output_sources) != OUTPUT_COUNT:
        raise ValueError(f"expected {OUTPUT_COUNT} output sources")

    lines = [
        f"module {module_name}(crc, data, next_crc);",
        "input [31:0] crc;",
        "input [63:0] data;",
        "output [31:0] next_crc;",
    ]
    lines.extend(f"wire {operation.output};" for operation in operations)
    lines.append("")
    lines.extend(
        f"assign {operation.output} = {operation.input_a} ^ {operation.input_b};"
        for operation in operations
    )
    lines.append("")
    lines.extend(
        f"assign next_crc[{index}] = {source};"
        for index, source in enumerate(output_sources)
    )
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def _reduce_terms(
    terms: Sequence[str],
    operations: list[Operation],
    prefix: str,
    balanced: bool,
) -> str:
    if not terms:
        raise ValueError("the restricted network cannot directly represent zero")
    current = list(terms)
    sequence = 0
    if not balanced:
        result = current[0]
        for term in current[1:]:
            node = f"{prefix}_{sequence}"
            sequence += 1
            operations.append(Operation(node, result, term))
            result = node
        return result

    while len(current) > 1:
        next_level: list[str] = []
        for index in range(0, len(current) - 1, 2):
            node = f"{prefix}_{sequence}"
            sequence += 1
            operations.append(Operation(node, current[index], current[index + 1]))
            next_level.append(node)
        if len(current) & 1:
            next_level.append(current[-1])
        current = next_level
    return current[0]


def render_independent(rows: Sequence[int]) -> str:
    """Render serial, independently expanded XOR2 equations per output."""

    operations: list[Operation] = []
    outputs = [
        _reduce_terms(_row_terms(row), operations, f"o{index}_n", balanced=False)
        for index, row in enumerate(rows)
    ]
    return _render_network("baseline_independent", operations, outputs)


def render_balanced(rows: Sequence[int]) -> str:
    """Render balanced per-output XOR2 trees without cross-output sharing."""

    operations: list[Operation] = []
    outputs = [
        _reduce_terms(_row_terms(row), operations, f"o{index}_n", balanced=True)
        for index, row in enumerate(rows)
    ]
    return _render_network("baseline_balanced", operations, outputs)


def render_greedy_cse(rows: Sequence[int]) -> str:
    """Greedily extract the most frequent two-signal XOR subexpression."""

    expressions = [set(_row_terms(row)) for row in rows]
    operations: list[Operation] = []
    signal_order = {name: index for index, name in enumerate(basis_signal_names())}

    while True:
        frequencies: Counter[tuple[str, str]] = Counter()
        for expression in expressions:
            ordered = sorted(expression, key=signal_order.__getitem__)
            frequencies.update(combinations(ordered, 2))
        useful = [pair for pair, count in frequencies.items() if count > 1]
        if not useful:
            break
        pair = min(
            useful,
            key=lambda item: (
                -frequencies[item],
                signal_order[item[0]],
                signal_order[item[1]],
            ),
        )
        node = f"cse_{len(operations)}"
        operations.append(Operation(node, pair[0], pair[1]))
        signal_order[node] = len(signal_order)
        for expression in expressions:
            if pair[0] in expression and pair[1] in expression:
                expression.remove(pair[0])
                expression.remove(pair[1])
                expression.add(node)

    outputs = [
        _reduce_terms(
            sorted(expression, key=signal_order.__getitem__),
            operations,
            f"o{index}_n",
            balanced=True,
        )
        for index, expression in enumerate(expressions)
    ]
    return _render_network("baseline_greedy_cse", operations, outputs)


def _yosys_quote(path: Path) -> str:
    text = str(path)
    if "\n" in text or "\r" in text:
        raise ValueError("Yosys paths cannot contain newlines")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _normalize_yosys_json(document: dict[str, object]) -> str:
    modules = document.get("modules")
    if not isinstance(modules, dict) or len(modules) != 1:
        raise RuntimeError("Yosys JSON must contain exactly one module")
    module = next(iter(modules.values()))
    if not isinstance(module, dict):
        raise RuntimeError("malformed Yosys module")
    ports = module.get("ports")
    cells = module.get("cells")
    if not isinstance(ports, dict) or not isinstance(cells, dict):
        raise RuntimeError("malformed Yosys ports or cells")

    values: dict[int, tuple[str, int]] = {}
    for port_name, width in (("crc", 32), ("data", 64)):
        port = ports.get(port_name)
        if not isinstance(port, dict) or port.get("direction") != "input":
            raise RuntimeError(f"missing Yosys input port {port_name}")
        bits = port.get("bits")
        if not isinstance(bits, list) or len(bits) != width:
            raise RuntimeError(f"wrong width for Yosys input port {port_name}")
        for index, bit in enumerate(bits):
            if not isinstance(bit, int):
                raise RuntimeError("constant or malformed primary-input bit")
            values[bit] = (f"{port_name}[{index}]", 0)

    pending = dict(cells)
    operations: list[Operation] = []
    while pending:
        progressed = False
        for cell_name in sorted(tuple(pending)):
            cell = pending[cell_name]
            if not isinstance(cell, dict):
                raise RuntimeError("malformed Yosys cell")
            cell_type = cell.get("type")
            connections = cell.get("connections")
            if not isinstance(connections, dict):
                raise RuntimeError("malformed Yosys cell connections")
            if cell_type == "$_NOT_":
                input_ports = ("A",)
            elif cell_type == "$_XOR_":
                input_ports = ("A", "B")
            else:
                raise RuntimeError(
                    f"ABC emitted non-normalizable cell type {cell_type!r}"
                )
            try:
                input_bits = [connections[port][0] for port in input_ports]
                output_bit = connections["Y"][0]
            except (KeyError, IndexError, TypeError) as error:
                raise RuntimeError("malformed Yosys cell port") from error
            if not all(isinstance(bit, int) and bit in values for bit in input_bits):
                continue

            if cell_type == "$_NOT_":
                source, phase = values[input_bits[0]]
                values[output_bit] = (source, phase ^ 1)
            else:
                input_a, phase_a = values[input_bits[0]]
                input_b, phase_b = values[input_bits[1]]
                node = f"abc_n{len(operations)}"
                operations.append(Operation(node, input_a, input_b))
                values[output_bit] = (node, phase_a ^ phase_b)
            del pending[cell_name]
            progressed = True
        if not progressed:
            raise RuntimeError("Yosys/ABC cell graph is cyclic or has undefined inputs")

    output_port = ports.get("next_crc")
    if not isinstance(output_port, dict) or output_port.get("direction") != "output":
        raise RuntimeError("missing Yosys output port next_crc")
    output_bits = output_port.get("bits")
    if not isinstance(output_bits, list) or len(output_bits) != OUTPUT_COUNT:
        raise RuntimeError("wrong width for Yosys output port next_crc")
    outputs: list[str] = []
    for bit in output_bits:
        if not isinstance(bit, int) or bit not in values:
            raise RuntimeError("undriven or malformed Yosys output bit")
        source, phase = values[bit]
        if phase:
            raise RuntimeError("ABC output contains an unpaired affine inversion")
        outputs.append(source)
    return _render_network("baseline_yosys_abc", operations, outputs)


def render_yosys_abc(rows: Sequence[int], yosys: str = "yosys") -> str:
    """Synthesize with Yosys/ABC, then normalize XOR/NOT phases to XOR2."""

    executable = shutil.which(yosys)
    if executable is None:
        raise RuntimeError(f"required synthesis tool is not installed: {yosys}")
    with tempfile.TemporaryDirectory(prefix="crc32-baseline-") as temporary_dir:
        temporary = Path(temporary_dir)
        source_path = temporary / "input.v"
        json_path = temporary / "output.json"
        script_path = temporary / "synthesize.ys"
        source_path.write_text(render_independent(rows).replace(
            "baseline_independent", "baseline_yosys_input", 1
        ))
        script_path.write_text(
            "\n".join(
                [
                    f"read_verilog {_yosys_quote(source_path)}",
                    "hierarchy -check -top baseline_yosys_input",
                    "proc",
                    "flatten",
                    "opt",
                    "techmap",
                    "opt",
                    "abc -exe yosys-abc -g XOR,AND",
                    "opt_clean",
                    f"write_json {_yosys_quote(json_path)}",
                ]
            )
            + "\n"
        )
        result = subprocess.run(
            [executable, "-q", "-s", str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Yosys/ABC baseline synthesis failed:\n" + result.stderr)
        return _normalize_yosys_json(json.loads(json_path.read_text()))


def generate_baselines(output_dir: Path) -> dict[str, float]:
    rows = build_transformation_matrix()
    generators = (
        ("independent_per_output.v", render_independent),
        ("balanced_per_output.v", render_balanced),
        ("greedy_cse.v", render_greedy_cse),
        ("yosys_abc.v", render_yosys_abc),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    runtimes: dict[str, float] = {}
    for filename, generator in generators:
        started = time.perf_counter()
        content = generator(rows)
        runtimes[filename] = time.perf_counter() - started
        (output_dir / filename).write_text(content)
    return runtimes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/baselines"),
    )
    parser.add_argument(
        "--timings-output",
        type=Path,
        help="optionally record observed generation runtimes as JSON",
    )
    args = parser.parse_args()
    try:
        runtimes = generate_baselines(args.output_dir)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"baseline generation failed: {error}\n")
    if args.timings_output:
        args.timings_output.parent.mkdir(parents=True, exist_ok=True)
        args.timings_output.write_text(json.dumps(runtimes, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

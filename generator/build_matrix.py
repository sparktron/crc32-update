"""Build the 32-by-96 GF(2) matrix for the frozen CRC-32 update."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from reference.crc32_reference import (
    CRC_MASK,
    DATA_MASK,
    crc32_update_reference,
)

CRC_WIDTH = 32
DATA_WIDTH = 64
INPUT_COUNT = CRC_WIDTH + DATA_WIDTH
OUTPUT_COUNT = CRC_WIDTH


def basis_signal_names() -> tuple[str, ...]:
    """Return the frozen 96-element basis order from SPEC.md."""

    return tuple(
        [f"crc[{index}]" for index in range(CRC_WIDTH)]
        + [f"data[{index}]" for index in range(DATA_WIDTH)]
    )


def basis_input(index: int) -> tuple[int, int]:
    """Return `(crc, data)` for one basis vector in the frozen order."""

    if not 0 <= index < INPUT_COUNT:
        raise IndexError(f"basis index out of range: {index}")
    if index < CRC_WIDTH:
        return 1 << index, 0
    return 0, 1 << (index - CRC_WIDTH)


def build_transformation_matrix() -> tuple[int, ...]:
    """Return 32 row masks, each a 96-bit GF(2) input coefficient vector."""

    if crc32_update_reference(0, 0) != 0:
        raise ValueError("the frozen update is unexpectedly affine, not linear")

    rows = [0] * OUTPUT_COUNT
    for input_index in range(INPUT_COUNT):
        crc, data = basis_input(input_index)
        output = crc32_update_reference(crc, data)
        for output_index in range(OUTPUT_COUNT):
            if (output >> output_index) & 1:
                rows[output_index] |= 1 << input_index
    return tuple(rows)


def apply_transformation_matrix(rows: Sequence[int], crc: int, data: int) -> int:
    """Apply a generated row-mask matrix to one input pair."""

    if len(rows) != OUTPUT_COUNT:
        raise ValueError(f"expected {OUTPUT_COUNT} matrix rows, got {len(rows)}")

    input_vector = (crc & CRC_MASK) | ((data & DATA_MASK) << CRC_WIDTH)
    output = 0
    for output_index, row in enumerate(rows):
        output |= ((row & input_vector).bit_count() & 1) << output_index
    return output


def matrix_document(rows: Sequence[int]) -> dict[str, object]:
    """Return a deterministic JSON-serializable matrix document."""

    if len(rows) != OUTPUT_COUNT:
        raise ValueError(f"expected {OUTPUT_COUNT} matrix rows, got {len(rows)}")
    return {
        "schema_version": 1,
        "crc_semantics": "reflected IEEE CRC-32 raw-state update, data[0] first",
        "basis_order": list(basis_signal_names()),
        "output_order": [f"next_crc[{index}]" for index in range(OUTPUT_COUNT)],
        "rows_hex": [f"0x{row:024x}" for row in rows],
    }


def render_structural_reference(
    rows: Sequence[int], module_name: str = "crc32_network"
) -> str:
    """Render an unoptimized XOR-chain network for Phase 1 verification only."""

    if len(rows) != OUTPUT_COUNT:
        raise ValueError(f"expected {OUTPUT_COUNT} matrix rows, got {len(rows)}")

    basis_names = basis_signal_names()
    operations: list[tuple[str, str, str]] = []
    output_sources: list[str] = []

    for output_index, row in enumerate(rows):
        terms = [
            basis_names[input_index]
            for input_index in range(INPUT_COUNT)
            if (row >> input_index) & 1
        ]
        if not terms:
            raise ValueError(
                f"next_crc[{output_index}] is constant zero, which the structural "
                "format cannot represent"
            )
        if len(terms) == 1:
            output_sources.append(terms[0])
            continue

        left = terms[0]
        for right in terms[1:]:
            node = f"n{len(operations)}"
            operations.append((node, left, right))
            left = node
        output_sources.append(left)

    lines = [
        f"module {module_name}(crc, data, next_crc);",
        "input [31:0] crc;",
        "input [63:0] data;",
        "output [31:0] next_crc;",
    ]
    lines.extend(f"wire {node};" for node, _, _ in operations)
    lines.append("")
    lines.extend(
        f"assign {node} = {left} ^ {right};"
        for node, left, right in operations
    )
    lines.append("")
    lines.extend(
        f"assign next_crc[{index}] = {source};"
        for index, source in enumerate(output_sources)
    )
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix-output",
        type=Path,
        help="write the deterministic JSON matrix to this path",
    )
    parser.add_argument(
        "--network-output",
        type=Path,
        help="write the unoptimized Phase 1 structural reference to this path",
    )
    args = parser.parse_args()

    rows = build_transformation_matrix()
    document = json.dumps(matrix_document(rows), indent=2, sort_keys=True) + "\n"

    if args.matrix_output:
        _write_text(args.matrix_output, document)
    if args.network_output:
        _write_text(args.network_output, render_structural_reference(rows))
    if not args.matrix_output and not args.network_output:
        print(document, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

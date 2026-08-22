"""Verify and measure a restricted structural CRC-32 XOR network."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import random
import re
import sys
from typing import Iterable, Mapping, Sequence

from reference.crc32_reference import crc32_update_reference

CRC_WIDTH = 32
DATA_WIDTH = 64
INPUT_COUNT = CRC_WIDTH + DATA_WIDTH
DEFAULT_RANDOM_TESTS = 100_000
DEFAULT_RANDOM_SEED = 0xC32A5EED

IDENTIFIER_PATTERN = r"[A-Za-z_][A-Za-z0-9_$]*"
BIT_SIGNAL_PATTERN = re.compile(
    rf"^(crc|data|next_crc)\[(0|[1-9][0-9]*)\]$"
)
IDENTIFIER_RE = re.compile(rf"^{IDENTIFIER_PATTERN}$")


class VerificationError(ValueError):
    """Base class for structural or functional verification failures."""


class ParseError(VerificationError):
    """Raised when the submitted structural network is malformed."""


class EquivalenceError(VerificationError):
    """Raised when a structurally valid network computes the wrong function."""


@dataclass(frozen=True)
class XorNode:
    name: str
    output: str
    input_a: str
    input_b: str
    order: int

    @property
    def inputs(self) -> tuple[str, str]:
        return self.input_a, self.input_b


@dataclass(frozen=True)
class Alias:
    output: str
    source: str
    order: int

    @property
    def inputs(self) -> tuple[str, ...]:
        return (self.source,)


Driver = XorNode | Alias


@dataclass(frozen=True)
class Metrics:
    xor2_count: int
    maximum_depth: int
    output_depths: tuple[int, ...]
    maximum_fanout: int
    total_fanout: int
    total_excess_fanout_above_4: int
    intermediate_node_count: int
    direct_output_alias_count: int
    unreachable_nodes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["output_depths"] = list(self.output_depths)
        result["unreachable_nodes"] = list(self.unreachable_nodes)
        return result


def primary_inputs() -> tuple[str, ...]:
    return tuple(
        [f"crc[{index}]" for index in range(CRC_WIDTH)]
        + [f"data[{index}]" for index in range(DATA_WIDTH)]
    )


def primary_outputs() -> tuple[str, ...]:
    return tuple(f"next_crc[{index}]" for index in range(CRC_WIDTH))


PRIMARY_INPUTS = primary_inputs()
PRIMARY_INPUT_SET = frozenset(PRIMARY_INPUTS)
PRIMARY_OUTPUTS = primary_outputs()
PRIMARY_OUTPUT_SET = frozenset(PRIMARY_OUTPUTS)


def _parse_signal(text: str, context: str) -> str:
    signal = text.strip()
    bit_match = BIT_SIGNAL_PATTERN.fullmatch(signal)
    if bit_match:
        vector_name, index_text = bit_match.groups()
        index = int(index_text)
        width = DATA_WIDTH if vector_name == "data" else CRC_WIDTH
        if index >= width:
            raise ParseError(
                f"{context}: {vector_name}[{index}] is outside [0:{width - 1}]"
            )
        return signal
    if IDENTIFIER_RE.fullmatch(signal):
        return signal
    raise ParseError(f"{context}: malformed or prohibited expression: {text.strip()}")


def _strip_comments(source: str) -> str:
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", without_blocks)


def _split_statements(source: str) -> list[str]:
    clean = _strip_comments(source)
    clean = re.sub(r"\bendmodule\b\s*;?", "endmodule;", clean)
    pieces = [piece.strip() for piece in clean.split(";")]
    return [piece for piece in pieces if piece]


class StructuralNetwork:
    """Parsed restricted network before alias and reachability normalization."""

    def __init__(
        self,
        module_name: str,
        drivers: Mapping[str, Driver],
        xor_nodes: Sequence[XorNode],
        declared_wires: Iterable[str],
    ) -> None:
        self.module_name = module_name
        self.drivers = dict(drivers)
        self.xor_nodes = tuple(xor_nodes)
        self.declared_wires = frozenset(declared_wires)

    def normalize(self) -> "NormalizedNetwork":
        def resolve_alias(signal: str) -> str:
            current = signal
            driver = self.drivers.get(current)
            while isinstance(driver, Alias):
                current = driver.source
                driver = self.drivers.get(current)
            return current

        reachable_outputs: set[str] = set()

        def visit(signal: str) -> None:
            resolved = resolve_alias(signal)
            driver = self.drivers.get(resolved)
            if not isinstance(driver, XorNode) or resolved in reachable_outputs:
                return
            reachable_outputs.add(resolved)
            visit(driver.input_a)
            visit(driver.input_b)

        for output in PRIMARY_OUTPUTS:
            visit(output)

        reachable_nodes = tuple(
            node for node in self.xor_nodes if node.output in reachable_outputs
        )
        unreachable_nodes = tuple(
            node.name for node in self.xor_nodes if node.output not in reachable_outputs
        )
        canonical_inputs = {
            node.output: tuple(
                sorted((resolve_alias(node.input_a), resolve_alias(node.input_b)))
            )
            for node in reachable_nodes
        }
        output_sources = tuple(resolve_alias(output) for output in PRIMARY_OUTPUTS)
        direct_output_alias_count = sum(
            isinstance(self.drivers[output], Alias) for output in PRIMARY_OUTPUTS
        )
        return NormalizedNetwork(
            module_name=self.module_name,
            nodes=reachable_nodes,
            canonical_inputs=canonical_inputs,
            output_sources=output_sources,
            direct_output_alias_count=direct_output_alias_count,
            unreachable_nodes=unreachable_nodes,
        )


@dataclass(frozen=True)
class NormalizedNetwork:
    module_name: str
    nodes: tuple[XorNode, ...]
    canonical_inputs: Mapping[str, tuple[str, str]]
    output_sources: tuple[str, ...]
    direct_output_alias_count: int
    unreachable_nodes: tuple[str, ...]

    def _evaluate_planes(self, input_values: Mapping[str, int]) -> tuple[int, ...]:
        values = dict(input_values)
        for node in self.nodes:
            input_a, input_b = self.canonical_inputs[node.output]
            values[node.output] = values[input_a] ^ values[input_b]
        return tuple(values[source] for source in self.output_sources)

    def evaluate(self, crc: int, data: int) -> int:
        values = {
            **{
                f"crc[{index}]": (crc >> index) & 1
                for index in range(CRC_WIDTH)
            },
            **{
                f"data[{index}]": (data >> index) & 1
                for index in range(DATA_WIDTH)
            },
        }
        output_planes = self._evaluate_planes(values)
        return sum(bit << index for index, bit in enumerate(output_planes))

    def evaluate_batch(self, pairs: Sequence[tuple[int, int]]) -> tuple[int, ...]:
        values: dict[str, int] = {}
        for bit_index in range(CRC_WIDTH):
            plane = 0
            for lane, (crc, _) in enumerate(pairs):
                plane |= ((crc >> bit_index) & 1) << lane
            values[f"crc[{bit_index}]"] = plane
        for bit_index in range(DATA_WIDTH):
            plane = 0
            for lane, (_, data) in enumerate(pairs):
                plane |= ((data >> bit_index) & 1) << lane
            values[f"data[{bit_index}]"] = plane
        return self._evaluate_planes(values)

    def metrics(self) -> Metrics:
        depths = {signal: 0 for signal in PRIMARY_INPUTS}
        fanouts = {signal: 0 for signal in PRIMARY_INPUTS}
        fanouts.update({node.output: 0 for node in self.nodes})

        for node in self.nodes:
            input_a, input_b = self.canonical_inputs[node.output]
            depths[node.output] = 1 + max(depths[input_a], depths[input_b])
            fanouts[input_a] += 1
            fanouts[input_b] += 1

        for source in self.output_sources:
            fanouts[source] += 1

        output_depths = tuple(depths[source] for source in self.output_sources)
        maximum_fanout = max(fanouts.values(), default=0)
        gate_count = len(self.nodes)
        return Metrics(
            xor2_count=gate_count,
            maximum_depth=max(output_depths, default=0),
            output_depths=output_depths,
            maximum_fanout=maximum_fanout,
            total_fanout=sum(fanouts.values()),
            total_excess_fanout_above_4=sum(
                max(0, fanout - 4) for fanout in fanouts.values()
            ),
            intermediate_node_count=gate_count,
            direct_output_alias_count=self.direct_output_alias_count,
            unreachable_nodes=self.unreachable_nodes,
        )


def parse_network(source: str) -> StructuralNetwork:
    """Parse and validate the restricted structural Verilog subset."""

    statements = _split_statements(source)
    if not statements:
        raise ParseError("empty structural network")

    module_match = re.fullmatch(
        rf"module\s+({IDENTIFIER_PATTERN})\s*\((.*?)\)",
        statements[0],
        flags=re.DOTALL,
    )
    if not module_match:
        raise ParseError("first statement must be a non-ANSI module declaration")
    module_name, port_text = module_match.groups()
    ports = tuple(port.strip() for port in port_text.split(",") if port.strip())
    if ports != ("crc", "data", "next_crc"):
        raise ParseError("module ports must be exactly: crc, data, next_crc")

    drivers: dict[str, Driver] = {}
    xor_nodes: list[XorNode] = []
    declared_wires: set[str] = set()
    instance_names: set[str] = set()
    input_declarations: dict[str, tuple[int, int]] = {}
    output_declarations: dict[str, tuple[int, int]] = {}
    saw_endmodule = False
    operation_order = 0

    def add_driver(target: str, driver: Driver) -> None:
        if target in PRIMARY_INPUT_SET:
            raise ParseError(f"cannot drive primary input {target}")
        if target in drivers:
            raise ParseError(f"multiply defined signal: {target}")
        drivers[target] = driver
        if isinstance(driver, XorNode):
            xor_nodes.append(driver)

    for statement_index, statement in enumerate(statements[1:], 2):
        context = f"statement {statement_index}"
        if saw_endmodule:
            raise ParseError(f"{context}: content after endmodule")
        if statement == "endmodule":
            saw_endmodule = True
            continue

        declaration_match = re.fullmatch(
            rf"(input|output)(?:\s+wire)?\s*\[(\d+)\s*:\s*(\d+)\]\s*"
            rf"({IDENTIFIER_PATTERN})",
            statement,
        )
        if declaration_match:
            direction, msb_text, lsb_text, name = declaration_match.groups()
            declaration = (int(msb_text), int(lsb_text))
            target = input_declarations if direction == "input" else output_declarations
            if name in target:
                raise ParseError(f"{context}: duplicate {direction} declaration: {name}")
            target[name] = declaration
            continue

        wire_match = re.fullmatch(r"wire\s+(.+)", statement, flags=re.DOTALL)
        if wire_match:
            names = [name.strip() for name in wire_match.group(1).split(",")]
            if not names or any(not IDENTIFIER_RE.fullmatch(name) for name in names):
                raise ParseError(f"{context}: only scalar internal wires are permitted")
            for name in names:
                if name in declared_wires or name in {"crc", "data", "next_crc"}:
                    raise ParseError(f"{context}: duplicate or reserved wire: {name}")
                declared_wires.add(name)
            continue

        assign_match = re.fullmatch(r"assign\s+(.+?)\s*=\s*(.+)", statement, re.DOTALL)
        if assign_match:
            target = _parse_signal(assign_match.group(1), context)
            expression = assign_match.group(2).strip()
            xor_count = expression.count("^")
            if xor_count > 1:
                raise ParseError(
                    f"{context}: chained or multi-input XOR expression is prohibited"
                )
            if xor_count == 1:
                input_texts = expression.split("^")
                input_a = _parse_signal(input_texts[0], context)
                input_b = _parse_signal(input_texts[1], context)
                node = XorNode(
                    name=f"assign:{target}",
                    output=target,
                    input_a=input_a,
                    input_b=input_b,
                    order=operation_order,
                )
                add_driver(target, node)
            else:
                source_signal = _parse_signal(expression, context)
                add_driver(
                    target,
                    Alias(
                        output=target,
                        source=source_signal,
                        order=operation_order,
                    ),
                )
            operation_order += 1
            continue

        xor_match = re.fullmatch(
            rf"xor2\s+({IDENTIFIER_PATTERN})\s*\((.*)\)",
            statement,
            flags=re.DOTALL,
        )
        if xor_match:
            instance_name, connection_text = xor_match.groups()
            if instance_name in instance_names:
                raise ParseError(f"{context}: duplicate instance name: {instance_name}")
            connection_pattern = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)")
            connections: dict[str, str] = {}
            for connection_match in connection_pattern.finditer(connection_text):
                port, signal_text = connection_match.groups()
                if port in connections:
                    raise ParseError(f"{context}: duplicate xor2 port: {port}")
                connections[port] = _parse_signal(signal_text, context)
            residual = connection_pattern.sub("", connection_text)
            if residual.strip(" \t\r\n,") or set(connections) != {"a", "b", "y"}:
                raise ParseError(
                    f"{context}: xor2 requires exactly named ports .a, .b, and .y"
                )
            instance_names.add(instance_name)
            node = XorNode(
                name=instance_name,
                output=connections["y"],
                input_a=connections["a"],
                input_b=connections["b"],
                order=operation_order,
            )
            add_driver(node.output, node)
            operation_order += 1
            continue

        generic_instance = re.fullmatch(
            rf"({IDENTIFIER_PATTERN})\s+({IDENTIFIER_PATTERN})\s*\(.*\)",
            statement,
            flags=re.DOTALL,
        )
        if generic_instance:
            raise ParseError(
                f"{context}: prohibited gate type: {generic_instance.group(1)}"
            )
        raise ParseError(f"{context}: unsupported or prohibited statement")

    if not saw_endmodule:
        raise ParseError("missing endmodule")
    if input_declarations != {"crc": (31, 0), "data": (63, 0)}:
        raise ParseError("inputs must be declared as crc[31:0] and data[63:0]")
    if output_declarations != {"next_crc": (31, 0)}:
        raise ParseError("output must be declared as next_crc[31:0]")

    for target in drivers:
        if target not in PRIMARY_OUTPUT_SET and target not in declared_wires:
            raise ParseError(f"driver target is not a declared wire or output: {target}")

    for target, driver in drivers.items():
        for source in driver.inputs:
            if source not in PRIMARY_INPUT_SET and source not in drivers:
                raise ParseError(f"undefined signal {source} used by {target}")

    visit_state: dict[str, int] = {}
    visit_path: list[str] = []

    def visit_driver(signal: str) -> None:
        state = visit_state.get(signal, 0)
        if state == 2:
            return
        if state == 1:
            cycle_start = visit_path.index(signal)
            cycle = " -> ".join(visit_path[cycle_start:] + [signal])
            raise ParseError(f"combinational cycle detected: {cycle}")
        visit_state[signal] = 1
        visit_path.append(signal)
        for source in drivers[signal].inputs:
            if source in drivers:
                visit_driver(source)
        visit_path.pop()
        visit_state[signal] = 2

    for driven_signal in drivers:
        visit_driver(driven_signal)

    for target, driver in drivers.items():
        for source in driver.inputs:
            source_driver = drivers.get(source)
            if source_driver is not None and source_driver.order >= driver.order:
                raise ParseError(f"forward reference: {target} uses {source}")

    missing_outputs = [output for output in PRIMARY_OUTPUTS if output not in drivers]
    if missing_outputs:
        raise ParseError(
            "missing or undriven outputs: " + ", ".join(missing_outputs)
        )

    return StructuralNetwork(
        module_name=module_name,
        drivers=drivers,
        xor_nodes=xor_nodes,
        declared_wires=declared_wires,
    )


def parse_network_file(path: Path | str) -> StructuralNetwork:
    network_path = Path(path)
    return parse_network(network_path.read_text())


def verify_exact_equivalence(network: NormalizedNetwork) -> int:
    """Evaluate the all-zero vector and all 96 independent basis vectors."""

    cases: list[tuple[int, int, str]] = [(0, 0, "all-zero")]
    cases.extend(
        (1 << index, 0, f"crc[{index}]") for index in range(CRC_WIDTH)
    )
    cases.extend(
        (0, 1 << index, f"data[{index}]") for index in range(DATA_WIDTH)
    )

    for crc, data, label in cases:
        expected = crc32_update_reference(crc, data)
        actual = network.evaluate(crc, data)
        if actual != expected:
            raise EquivalenceError(
                f"exact vector {label} failed: expected 0x{expected:08x}, "
                f"got 0x{actual:08x}"
            )
    return len(cases)


def verify_random_equivalence(
    network: NormalizedNetwork,
    count: int = DEFAULT_RANDOM_TESTS,
    seed: int = DEFAULT_RANDOM_SEED,
    batch_size: int = 512,
) -> int:
    """Run reproducible bit-parallel randomized parser/evaluator sanity checks."""

    if count < 0:
        raise ValueError("random test count cannot be negative")
    if batch_size <= 0:
        raise ValueError("batch size must be positive")

    generator = random.Random(seed)
    completed = 0
    while completed < count:
        current_size = min(batch_size, count - completed)
        pairs = [
            (generator.getrandbits(CRC_WIDTH), generator.getrandbits(DATA_WIDTH))
            for _ in range(current_size)
        ]
        expected_values = [
            crc32_update_reference(crc, data) for crc, data in pairs
        ]
        actual_planes = network.evaluate_batch(pairs)
        for output_index, actual_plane in enumerate(actual_planes):
            expected_plane = 0
            for lane, expected in enumerate(expected_values):
                expected_plane |= ((expected >> output_index) & 1) << lane
            difference = actual_plane ^ expected_plane
            if difference:
                lane = (difference & -difference).bit_length() - 1
                crc, data = pairs[lane]
                actual = sum(
                    ((plane >> lane) & 1) << bit_index
                    for bit_index, plane in enumerate(actual_planes)
                )
                expected = expected_values[lane]
                raise EquivalenceError(
                    f"random vector {completed + lane} failed for "
                    f"crc=0x{crc:08x}, data=0x{data:016x}: expected "
                    f"0x{expected:08x}, got 0x{actual:08x}"
                )
        completed += current_size
    return completed


def verification_report(
    path: Path,
    random_tests: int = DEFAULT_RANDOM_TESTS,
    seed: int = DEFAULT_RANDOM_SEED,
) -> dict[str, object]:
    parsed = parse_network_file(path)
    normalized = parsed.normalize()
    exact_count = verify_exact_equivalence(normalized)
    random_count = verify_random_equivalence(normalized, random_tests, seed)
    return {
        "network": str(path),
        "module": normalized.module_name,
        "exact_vectors_checked": exact_count,
        "random_vectors_checked": random_count,
        "random_seed": seed,
        "verification_passed": True,
        "metrics": normalized.metrics().to_dict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("network", type=Path)
    parser.add_argument(
        "--random-tests",
        type=int,
        default=DEFAULT_RANDOM_TESTS,
        help=f"random vectors to check (minimum {DEFAULT_RANDOM_TESTS})",
    )
    parser.add_argument(
        "--seed",
        type=lambda value: int(value, 0),
        default=DEFAULT_RANDOM_SEED,
    )
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    args = parser.parse_args()

    if args.random_tests < DEFAULT_RANDOM_TESTS:
        parser.error(
            f"--random-tests must be at least {DEFAULT_RANDOM_TESTS} for acceptance"
        )

    try:
        report = verification_report(args.network, args.random_tests, args.seed)
    except (OSError, VerificationError, ValueError) as error:
        print(f"verification failed: {error}", file=sys.stderr)
        return 1

    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized)
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

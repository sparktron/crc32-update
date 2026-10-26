"""Verify crcZero's CRC-32/ISO-HDLC D=64 output against the frozen experiment.

Usage (from the repository root, with a crcZero checkout you obtained):

    python3 scripts/compare_crczero.py --crczero-src /path/to/crcZero \
        --output results/external/crczero_comparison.json

crcZero is third-party code. It runs only in an isolated child interpreter
(``python3 -I -B``) from an empty working directory, and the Verilog it emits is
then read here as data. The emitted ``assign`` equations are checked
bit-for-bit against ``generator.build_matrix``. They are then converted to the
restricted XOR2 subset twice: once with the operators chained left to right as
written (Verilog's ``^`` is left-associative), and once as balanced trees.
Both netlists go through the independent verifier and the formal-equivalence
flow. Nothing is downloaded.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generator.build_matrix import basis_signal_names, build_transformation_matrix  # noqa: E402
from verifier.build_results import structural_fingerprint  # noqa: E402
from verifier.run_formal import run as run_formal  # noqa: E402
from verifier.verify_network import (  # noqa: E402
    DEFAULT_RANDOM_SEED,
    DEFAULT_RANDOM_TESTS,
    verification_report,
)

ALGORITHM = "CRC-32/ISO-HDLC"
DATA_WIDTH = 64
BASELINES = {
    "chained": ROOT / "results/baselines/independent_per_output.v",
    "balanced": ROOT / "results/baselines/balanced_per_output.v",
}

# Executed by the isolated child interpreter; argv[1] is the crcZero source
# root and argv[2] the output file.
CHILD = f"""
import sys
sys.path.insert(0, sys.argv[1] + "/src")
from crczero import CrcGenerator, catalog
generator = CrcGenerator(catalog[{ALGORITHM!r}], data_width={DATA_WIDTH})
if not generator.self_test():
    raise SystemExit("crcZero self-test failed")
open(sys.argv[2], "w").write(generator.generate_verilog())
"""


def generate(crczero_src: Path, workdir: Path) -> str:
    output = workdir / "crczero.v"
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", CHILD, str(crczero_src.resolve()), str(output)],
        cwd=workdir,
        check=True,
    )
    return output.read_text()


def parse_equations(verilog: str) -> dict[int, list[str]]:
    outputs: dict[int, list[str]] = {}
    for match in re.finditer(r"assign\s+crc_out\[(\d+)\]\s*=\s*([^;]+);", verilog):
        terms = [
            term.strip().replace("crc_in", "crc").replace("data_in", "data")
            for term in match.group(2).split("^")
        ]
        if not all(re.fullmatch(r"(crc|data)\[\d+\]", term) for term in terms):
            raise ValueError(f"unexpected term in crc_out[{match.group(1)}]")
        outputs[int(match.group(1))] = terms
    if sorted(outputs) != list(range(32)):
        raise ValueError("crcZero output does not assign all 32 bits")
    return outputs


def matching_outputs(outputs: dict[int, list[str]]) -> list[int]:
    index = {name: position for position, name in enumerate(basis_signal_names())}
    rows = build_transformation_matrix()
    return [
        bit
        for bit in range(32)
        if len(set(outputs[bit])) == len(outputs[bit])
        and sum(1 << index[term] for term in outputs[bit]) == rows[bit]
    ]


def render(module: str, outputs: dict[int, list[str]], balanced: bool) -> str:
    gates: list[tuple[str, str, str]] = []

    def gate(left: str, right: str) -> str:
        name = f"n{len(gates)}"
        gates.append((name, left, right))
        return name

    def chain(terms: list[str]) -> str:
        signal = terms[0]
        for term in terms[1:]:
            signal = gate(signal, term)
        return signal

    def tree(terms: list[str]) -> str:
        level = list(terms)
        while len(level) > 1:
            level = [
                gate(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
                for i in range(0, len(level), 2)
            ]
        return level[0]

    sources = [(tree if balanced else chain)(outputs[bit]) for bit in range(32)]
    lines = [
        f"module {module}(crc, data, next_crc);",
        "input [31:0] crc;",
        "input [63:0] data;",
        "output [31:0] next_crc;",
        *(f"wire {name};" for name, _, _ in gates),
        *(f"assign {name} = {left} ^ {right};" for name, left, right in gates),
        *(f"assign next_crc[{bit}] = {source};" for bit, source in enumerate(sources)),
        "endmodule",
    ]
    return "\n".join(lines) + "\n"


def crczero_commit(crczero_src: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(crczero_src), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def compare(crczero_src: Path, random_tests: int, random_seed: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as directory:
        workdir = Path(directory)
        outputs = parse_equations(generate(crczero_src, workdir))
        matching = matching_outputs(outputs)
        realizations = {}
        for style, balanced in (("chained", False), ("balanced", True)):
            module = f"crczero_{style}"
            path = workdir / f"{module}.v"
            path.write_text(render(module, outputs, balanced))
            report = verification_report(path, random_tests, random_seed)
            run_formal(path)
            fingerprint = structural_fingerprint(path)
            metrics = {
                key: value
                for key, value in report["metrics"].items()
                if key not in ("output_depths", "unreachable_nodes")
            }
            realizations[style] = {
                "metrics": metrics,
                "verification": {
                    "structural": "passed",
                    "exact_vectors": report["exact_vectors_checked"],
                    "random_vectors": report["random_vectors_checked"],
                    "random_seed": report["random_seed"],
                    "formal_equivalence": "passed",
                },
                "circuit_id": fingerprint[:12],
                "structurally_identical_to": (
                    str(BASELINES[style].relative_to(ROOT))
                    if structural_fingerprint(BASELINES[style]) == fingerprint
                    else None
                ),
            }
    return {
        "schema_version": 1,
        "tool": "crcZero",
        "tool_commit": crczero_commit(crczero_src),
        "algorithm": ALGORITHM,
        "data_width": DATA_WIDTH,
        "xor_operators_emitted": sum(len(terms) - 1 for terms in outputs.values()),
        "outputs_matching_frozen_matrix": len(matching),
        "realizations": realizations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crczero-src", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--random-tests", type=int, default=DEFAULT_RANDOM_TESTS)
    parser.add_argument(
        "--seed", type=lambda value: int(value, 0), default=DEFAULT_RANDOM_SEED
    )
    args = parser.parse_args()
    summary = compare(args.crczero_src, args.random_tests, args.seed)
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")
    return 0 if summary["outputs_matching_frozen_matrix"] == 32 else 1


if __name__ == "__main__":
    raise SystemExit(main())

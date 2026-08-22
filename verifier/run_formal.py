"""Run the Yosys/ABC/Z3 Phase 1 formal-equivalence flow."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from verifier.verify_network import VerificationError, parse_network_file

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_TEMPLATE = ROOT / "verifier" / "formal_equivalence.ys"


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"required formal tool is not installed: {name}")
    return path


def _yosys_quote(value: Path) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise RuntimeError("formal paths cannot contain newlines")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render_script(candidate: Path, module_name: str, smt2_output: Path) -> str:
    template = SCRIPT_TEMPLATE.read_text()
    replacements = {
        "@CANDIDATE_FILE@": _yosys_quote(candidate),
        "@CANDIDATE_MODULE@": module_name,
        "@SMT2_OUTPUT@": _yosys_quote(smt2_output),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    if "@CANDIDATE_" in template or "@SMT2_OUTPUT@" in template:
        raise RuntimeError("formal script template contains unresolved placeholders")
    return template


def run(network_path: Path, requested_module: str | None = None) -> None:
    candidate = network_path.resolve()
    parsed = parse_network_file(candidate)
    module_name = parsed.module_name
    if requested_module is not None and requested_module != module_name:
        raise RuntimeError(
            f"requested module {requested_module!r} does not match submitted "
            f"module {module_name!r}"
        )
    if module_name == "crc32_reference":
        raise RuntimeError("submitted module name conflicts with crc32_reference")

    yosys = _tool("yosys")
    smtbmc = _tool("yosys-smtbmc")
    _tool("z3")
    _tool("yosys-abc")

    with tempfile.TemporaryDirectory(prefix="crc32-formal-") as temporary_dir:
        temporary_path = Path(temporary_dir)
        candidate_copy = temporary_path / "submitted_network.v"
        script_path = temporary_path / "formal_equivalence.ys"
        smt2_path = temporary_path / "equivalence_miter.smt2"
        shutil.copyfile(candidate, candidate_copy)
        script_path.write_text(
            _render_script(candidate_copy, module_name, smt2_path)
        )

        synthesis = subprocess.run(
            [yosys, "-q", "-s", str(script_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if synthesis.returncode != 0:
            raise RuntimeError(
                "Yosys miter generation failed:\n"
                + synthesis.stdout
                + synthesis.stderr
            )

        proof = subprocess.run(
            [smtbmc, "-s", "z3", "-t", "1", "--noprogress", str(smt2_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        output = proof.stdout + proof.stderr
        if proof.returncode != 0 or "Status: PASSED" not in output:
            raise RuntimeError("Yosys SMTBMC/Z3 did not prove equivalence:\n" + output)

    print(f"Formal target: {candidate} (module {module_name}).")
    print("Yosys generated a combined 96-input equivalence miter.")
    print("Berkeley ABC synthesis completed on the submitted network.")
    print("Yosys SMTBMC/Z3 proved all 32 output comparisons for every input.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("network", type=Path, help="submitted structural network")
    parser.add_argument(
        "--module",
        help="expected top module name; defaults to the parsed submitted module",
    )
    args = parser.parse_args()
    try:
        run(args.network, args.module)
    except (OSError, RuntimeError, VerificationError) as error:
        print(f"formal equivalence failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

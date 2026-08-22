"""Run the Yosys/ABC/Z3 Phase 1 formal-equivalence flow."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "verifier" / "formal_equivalence.ys"
MITER_SMT2 = Path("/tmp/crc32_equivalence_miter.smt2")


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"required formal tool is not installed: {name}")
    return path


def run() -> None:
    yosys = _tool("yosys")
    smtbmc = _tool("yosys-smtbmc")
    _tool("z3")
    _tool("yosys-abc")

    synthesis = subprocess.run(
        [yosys, "-q", "-s", str(SCRIPT)],
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
        [smtbmc, "-s", "z3", "-t", "1", "--noprogress", str(MITER_SMT2)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = proof.stdout + proof.stderr
    if proof.returncode != 0 or "Status: PASSED" not in output:
        raise RuntimeError("Yosys SMTBMC/Z3 did not prove equivalence:\n" + output)
    print("Yosys generated a combined 96-input equivalence miter.")
    print("Berkeley ABC synthesis completed on an independent miter copy.")
    print("Yosys SMTBMC/Z3 proved all 32 output comparisons for every input.")


def main() -> int:
    try:
        run()
    except (OSError, RuntimeError) as error:
        print(f"formal equivalence failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

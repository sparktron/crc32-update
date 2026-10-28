"""Run a frozen experiment's command in an isolated checkout of its code commit.

An experiment's run manifest freezes the hashes of every tracked Python source.
Any later commit (a new experiment module, a log registration) changes that
set, so the experiment's own provenance check rightly refuses to replay on a
newer revision. Audits instead copy the evidence into a detached worktree at
the manifest's ``code_commit``, run there, and copy back only declared outputs.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources_match(manifest: dict) -> bool:
    """True when this checkout has exactly the manifest's frozen sources and bytes."""
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    frozen = manifest["source_sha256"]
    python = {path for path in tracked if path.endswith(".py")}
    if python != {path for path in frozen if path.endswith(".py")}:
        return False
    return all(Path(path).exists() and _sha256(Path(path)) == digest
               for path, digest in frozen.items())


def _files(paths):
    for path in map(Path, paths):
        yield from (sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path])


def run_frozen(commit: str, evidence, command, outputs) -> None:
    """Run ``command`` at ``commit`` on a copy of ``evidence``; copy back ``outputs``.

    ``outputs`` are glob patterns relative to the repository root. Every other
    copied evidence file must be byte-identical after the command.
    """
    with tempfile.TemporaryDirectory(prefix="frozen-checkout-") as parent:
        checkout = Path(parent) / "checkout"
        subprocess.run(["git", "worktree", "add", "--detach", str(checkout), commit],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            copied = list(_files(evidence))
            for path in copied:
                (checkout / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, checkout / path)
            subprocess.run(command, cwd=checkout, check=True)
            produced = {path.relative_to(checkout) for pattern in outputs
                        for path in checkout.glob(pattern) if path.is_file()}
            for path in copied:
                if path not in produced and _sha256(checkout / path) != _sha256(path):
                    raise ValueError(f"frozen command changed evidence: {path}")
            for path in sorted(produced):
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(checkout / path, path)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(checkout)],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

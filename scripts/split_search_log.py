"""Split results/search_log.jsonl into one log per experiment (one-time migration).

Every line is moved byte for byte into the experiment file that
``verifier.search_logs.log_file_for`` assigns to its algorithm, keeping its
order within that file. Before anything is removed, the script checks that:
- each original line appears in exactly one file;
- each file is exactly its algorithms' lines, in original order;
- attempt IDs are unique.

Checkpoints whose ``search_log_path`` names the legacy file are rewritten to
name their experiment file. Only that one value changes, and checkpoint-
relative paths stay relative. The legacy file is deleted last.

The script refuses to run while any search holds the legacy log's lock.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path

from verifier.search_logs import LEGACY_SEARCH_LOG, SEARCH_LOG_DIR, log_file_for


def _assert_unlocked(legacy: Path) -> None:
    lock_path = legacy.with_suffix(legacy.suffix + ".lock")
    if not lock_path.exists():
        return
    with lock_path.open("a") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"a search still holds {lock_path}") from error
        fcntl.flock(lock_file, fcntl.LOCK_UN)


def split(legacy: Path, directory: Path) -> dict[str, int]:
    """Write the per-experiment files and return each file's line count."""
    data = legacy.read_bytes()
    if not data.endswith(b"\n"):
        raise ValueError(f"{legacy} does not end with a newline")
    if directory.exists() and any(directory.glob("*.jsonl")):
        raise FileExistsError(f"{directory} already holds search logs")
    lines = data.splitlines(keepends=True)
    groups: dict[Path, list[bytes]] = {}
    attempt_ids: set[str] = set()
    for line_number, line in enumerate(lines, 1):
        record = json.loads(line)
        attempt_id = record["attempt_id"]
        if attempt_id in attempt_ids:
            raise ValueError(f"{legacy}:{line_number}: duplicate attempt_id {attempt_id}")
        attempt_ids.add(attempt_id)
        groups.setdefault(log_file_for(record["algorithm"], directory), []).append(line)

    directory.mkdir(parents=True, exist_ok=True)
    for path, group in groups.items():
        path.write_bytes(b"".join(group))

    # Re-read everything and compare against the original before any removal.
    written = {path: path.read_bytes().splitlines(keepends=True) for path in groups}
    if sorted(line for group in written.values() for line in group) != sorted(lines):
        raise RuntimeError("split files do not hold exactly the original lines")
    for path, group in written.items():
        expected = [
            line for line in lines if log_file_for(json.loads(line)["algorithm"], directory) == path
        ]
        if group != expected:
            raise RuntimeError(f"{path} does not preserve the original order")
    return {path.name: len(group) for path, group in sorted(written.items())}


def migrate_checkpoints(root: Path, legacy: Path, directory: Path) -> list[str]:
    """Point every checkpoint that names the legacy log at its experiment log."""
    migrated = []
    for checkpoint_path in sorted(root.rglob("*.json")):
        text = checkpoint_path.read_text()
        checkpoint = json.loads(text)
        if not isinstance(checkpoint, dict) or "search_log_path" not in checkpoint:
            continue
        old = checkpoint["search_log_path"]
        target = log_file_for(checkpoint["algorithm"], directory)
        if Path(old).is_absolute():
            if Path(old).resolve() != legacy.resolve():
                continue
            new = str(target.resolve())
        elif (checkpoint_path.parent / old).resolve() == legacy.resolve():
            # Candidate A checkpoints record a checkpoint-relative path.
            new = os.path.relpath(target.resolve(), checkpoint_path.parent.resolve())
        elif Path(old).resolve() == legacy.resolve():
            # Bounded-search checkpoints record a repository-relative path.
            new = str(target)
        else:
            continue
        needle = f'"search_log_path": {json.dumps(old)}'
        if text.count(needle) != 1:
            raise ValueError(f"{checkpoint_path}: search_log_path is not uniquely formatted")
        updated = text.replace(needle, f'"search_log_path": {json.dumps(new)}')
        if json.loads(updated) != {**checkpoint, "search_log_path": new}:
            raise RuntimeError(f"{checkpoint_path}: migration changed more than the path")
        checkpoint_path.write_text(updated)
        migrated.append(f"{checkpoint_path}: {old} -> {new}")
    return migrated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", type=Path, default=LEGACY_SEARCH_LOG)
    parser.add_argument("--directory", type=Path, default=SEARCH_LOG_DIR)
    parser.add_argument(
        "--checkpoints",
        type=Path,
        default=Path("results/checkpoints"),
        help="checkpoint tree to migrate; pass an empty directory to skip",
    )
    parser.add_argument(
        "--keep-legacy", action="store_true", help="leave the legacy file in place"
    )
    args = parser.parse_args()
    _assert_unlocked(args.legacy)
    counts = split(args.legacy, args.directory)
    migrated = migrate_checkpoints(args.checkpoints, args.legacy, args.directory)
    if not args.keep_legacy:
        args.legacy.unlink()
    print(
        json.dumps(
            {"files": counts, "total_records": sum(counts.values()), "checkpoints": migrated},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

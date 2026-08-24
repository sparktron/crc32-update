"""Deduplicate interrupted concurrent optimization-search log records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


OUTCOME_FIELDS = (
    "algorithm",
    "parameters",
    "seed",
    "starting_metrics",
    "final_metrics",
    "verification_passed",
    "accepted",
    "rejection_reason",
    "artifact",
)


def _records(path: Path) -> Iterable[dict[str, object]]:
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            raise ValueError(f"{path}:{line_number}: blank record")
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{line_number}: record is not an object")
        attempt_id = record.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError(f"{path}:{line_number}: invalid attempt_id")
        yield record


def deduplicate(records: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Keep the earliest record for each ID after proving outcomes agree."""

    retained: dict[str, dict[str, object]] = {}
    ordered: list[dict[str, object]] = []
    for record in records:
        attempt_id = str(record["attempt_id"])
        first = retained.get(attempt_id)
        if first is None:
            retained[attempt_id] = record
            ordered.append(record)
            continue
        if any(first.get(field) != record.get(field) for field in OUTCOME_FIELDS):
            raise ValueError(f"conflicting duplicate search attempt: {attempt_id}")
    return ordered


def repair(path: Path, backup_path: Path) -> tuple[int, int]:
    source = list(_records(path))
    repaired = deduplicate(source)
    if len(repaired) == len(source):
        return len(source), 0
    if backup_path.exists():
        raise FileExistsError(f"refusing to overwrite backup: {backup_path}")
    backup_path.write_bytes(path.read_bytes())
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in repaired)
    )
    temporary.replace(path)
    return len(repaired), len(source) - len(repaired)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=Path("results/search_log.jsonl"))
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    try:
        retained, removed = repair(args.log, args.backup)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"search-log repair failed: {error}\n")
    print(f"Retained {retained} records; removed {removed} duplicate records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

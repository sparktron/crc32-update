"""Locate and read the per-experiment optimization search logs.

Search attempts are recorded as JSONL, one file per experiment, under
``results/search_logs/``. Until 2026-10-27 they were one file,
``results/search_log.jsonl``. ``scripts/split_search_log.py`` split it without
changing any record, because one growing file would pass GitHub's 100 MB
file limit. The record schema and the append-only rule are unchanged.

Each algorithm belongs to exactly one experiment file, chosen by algorithm-name
prefix. A new experiment must be registered in ``EXPERIMENT_LOGS`` before it
can log anything.
"""

from __future__ import annotations

import json
from pathlib import Path

SEARCH_LOG_DIR = Path("results/search_logs")
LEGACY_SEARCH_LOG = Path("results/search_log.jsonl")

# (algorithm-name prefix, file name). No prefix is a prefix of another, so the
# order does not matter, and each algorithm maps to exactly one file.
EXPERIMENT_LOGS: tuple[tuple[str, str], ...] = (
    ("elite-prefix-", "elite_prefix.jsonl"),
    ("sharing-lookahead-", "sharing_lookahead.jsonl"),
    ("gf2-bp-cse-depth-stochastic-", "candidate_a.jsonl"),
    ("phase4-", "phase4_refinement.jsonl"),
    ("phase5-", "phase5_exact.jsonl"),
    ("kraft-bounded-bp-cse-", "kraft_bounded.jsonl"),
    ("dclo-kraft-", "dclo.jsonl"),
    ("ablation-", "ablation_toward_dclo.jsonl"),
    ("kraft-slack-tiebreak-", "kraft_slack_tiebreak.jsonl"),
    ("kraft-adaptive-tiebreak-", "kraft_adaptive_tiebreak.jsonl"),
    ("kraft-phase-isolation-", "kraft_phase_isolation.jsonl"),
)


def log_file_for(algorithm: str, directory: Path = SEARCH_LOG_DIR) -> Path:
    """Return the experiment log that records ``algorithm``."""
    matches = [name for prefix, name in EXPERIMENT_LOGS if algorithm.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"algorithm {algorithm!r} is not registered to one search log")
    return directory / matches[0]


def log_files(path: Path = SEARCH_LOG_DIR) -> list[Path]:
    """Return the log files at ``path``: every ``*.jsonl`` in a directory, or one file."""
    if path.is_dir():
        return sorted(path.glob("*.jsonl"))
    return [path]


def read_records(path: Path = SEARCH_LOG_DIR) -> list[dict[str, object]]:
    """Return every record, file by file in name order, each file in append order."""
    records: list[dict[str, object]] = []
    for log_path in log_files(path):
        records.extend(
            json.loads(line) for line in log_path.read_text().splitlines() if line
        )
    return records

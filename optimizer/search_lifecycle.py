"""Durable, ordered search orchestration shared by the seeded runners.

The journal is authoritative. A started event is synced before dispatch; a
terminal event is synced before checkpointing. Only successful terminals count
towards the seed budget. On failure we cancel pending futures and let at most
``workers`` already dispatched trials finish, without accepting their results.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
from functools import partial
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import threading
import time


def timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_checkpoint(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as output:
        output.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def append_log(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as output:
        for record in records:
            output.write(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            )
        output.flush()
        os.fsync(output.fileno())


def inspect_log(path):
    """Read without mutation; only a malformed, unterminated final line is recoverable."""
    data = path.read_bytes() if path.exists() else b""
    lines = data.splitlines(keepends=True)
    records = []
    valid_size = 0
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except (ValueError, UnicodeDecodeError) as error:
            incomplete = (
                isinstance(error, json.JSONDecodeError)
                and (
                    error.msg.startswith("Unterminated string")
                    or error.pos >= len(line.rstrip())
                    or (
                        error.msg == "Expecting value"
                        # Literal errors point to the token's start, in characters.
                        and any(
                            error.doc[error.pos :] == literal[:length]
                            for literal in ("true", "false", "null")
                            for length in range(1, len(literal))
                        )
                    )
                )
            ) or (
                isinstance(error, UnicodeDecodeError)
                and error.reason == "unexpected end of data"
                and error.end == len(line)
            )
            if index == len(lines) - 1 and not line.endswith(b"\n") and incomplete:
                return records, data, valid_size
            raise ValueError(f"{path}:{index + 1}: corrupt journal record") from error
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{index + 1}: record is not an object")
        records.append(record)
        valid_size += len(line)
    return records, data, valid_size


def recover_tail(path, data, valid_size):
    if valid_size == len(data):
        # A complete JSON object without a newline also needs a separator.
        if data and not data.endswith(b"\n"):
            with path.open("ab") as output:
                output.write(b"\n")
                output.flush()
                os.fsync(output.fileno())
        return
    backup = path.with_name(path.name + ".damaged-" + hashlib.sha256(data).hexdigest())
    if backup.exists():
        if backup.read_bytes() != data:
            raise ValueError("damaged journal backup conflicts")
    else:
        with backup.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    temporary = path.with_suffix(path.suffix + ".recovering")
    with temporary.open("wb") as output:
        output.write(data[:valid_size])
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def budget_records(records, algorithm, seed_start, seed_count):
    """Validate retries/events and return successes, all terminals and open starts.

    Legacy rows are successful terminals unless explicitly marked unverified.
    Their identifiers and contents are never rewritten.
    """
    selected = [
        r
        for r in records
        if r.get("algorithm") == algorithm
        and isinstance(r.get("seed"), int)
        and seed_start <= r["seed"] < seed_start + seed_count
    ]
    seen = set()
    starts = {}
    terminals = []
    successes = []
    last_retry = {}
    for record in selected:
        identifier = record.get("attempt_id")
        if identifier is not None:
            if identifier in seen:
                raise ValueError("duplicate attempt ID in search log")
            seen.add(identifier)
        status = record.get(
            "status",
            "failed" if record.get("verification_passed") is False else "succeeded",
        )
        if status != "succeeded" and record.get("accepted"):
            raise ValueError("unsuccessful attempt cannot be accepted")
        if record.get("schema_version") == 2:
            seed = record["seed"]
            retry = record.get("attempt_number")
            if not isinstance(retry, int) or retry <= 0:
                raise ValueError("invalid retry number")
            if status == "started":
                if retry <= last_retry.get(seed, 0):
                    raise ValueError("retry numbers must increase")
                last_retry[seed] = retry
                trial_id = record.get("trial_id")
                if trial_id in starts or not trial_id:
                    raise ValueError("duplicate or missing trial ID")
                starts[trial_id] = record
                continue
            start = starts.pop(record.get("trial_id"), None)
            if (
                start is None
                or start["seed"] != seed
                or start["attempt_number"] != retry
            ):
                raise ValueError("terminal event has no matching start")
            if status not in ("succeeded", "failed", "cancelled", "interrupted"):
                raise ValueError("invalid attempt status")
            if status != "succeeded" and (
                record.get("verification_passed") is not False
                or record.get("accepted") is not False
                or not record.get("error_reason")
            ):
                raise ValueError("failure record has invalid acceptance status")
        terminals.append(record)
        if status == "succeeded":
            if record.get("verification_passed") is False:
                raise ValueError("successful seed is marked unverified")
            if not isinstance(record.get("final_metrics"), dict):
                raise ValueError("successful seed has no metrics")
            successes.append(record)
    if [r["seed"] for r in successes] != list(
        range(seed_start, seed_start + len(successes))
    ):
        raise ValueError("search log is not a contiguous unique seed prefix")
    return successes, terminals, starts


def tool_versions():
    versions = {"python": platform.python_version()}
    for name, command in (
        ("yosys", ["yosys", "-V"]),
        ("abc", ["yosys-abc", "-c", "version"]),
        ("z3", ["z3", "--version"]),
    ):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            versions[name] = {
                "returncode": result.returncode,
                "version": (result.stdout + result.stderr).strip()[:2000],
            }
        except (OSError, subprocess.TimeoutExpired) as error:
            versions[name] = {"unavailable": type(error).__name__}
    return versions


def experiment_manifest(configuration, identity_inputs=None):
    from generator.build_matrix import build_transformation_matrix

    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for directory in ("optimizer", "generator", "reference", "verifier"):
        for path in sorted((root / directory).glob("*")):
            if path.suffix not in (".py", ".v") or path.name.startswith("test_"):
                continue
            digest.update(
                str(path.relative_to(root)).encode() + b"\0" + path.read_bytes()
            )
    manifest = {
        "configuration": configuration,
        "inputs": identity_inputs or {},
        "source_sha256": digest.hexdigest(),
        "matrix_sha256": hashlib.sha256(
            json.dumps(build_transformation_matrix()).encode()
        ).hexdigest(),
        "tool_versions": tool_versions(),
    }
    manifest["identity"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode()
    ).hexdigest()
    return manifest


def callable_identity(function):
    """Include bound strategy parameters, rather than a partial's object address."""

    def encode_parameter(value):
        if is_dataclass(value) and not isinstance(value, type):
            return {
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "fields": asdict(value),
            }
        if isinstance(value, Path):
            return {"path": str(value)}
        raise TypeError(
            f"trial parameter cannot be recorded immutably: {type(value).__name__}"
        )

    if isinstance(function, partial):
        return json.loads(
            json.dumps(
                {
                    "function": callable_identity(function.func),
                    "args": list(function.args),
                    "keywords": function.keywords,
                },
                default=encode_parameter,
            )
        )
    return {"function": f"{function.__module__}.{function.__qualname__}"}


def recorded_log(checkpoint, checkpoint_path, requested):
    value = checkpoint.get("search_log_path")
    if value is None:
        # Old refinement and early bounded checkpoints did not record a path.
        return requested
    path = Path(value)
    if not path.is_absolute():
        if (
            checkpoint.get("search_log_path_base") == "checkpoint"
            or checkpoint.get("algorithm") == "gf2-bp-cse-depth-stochastic-v1"
        ):
            path = checkpoint_path.parent / path
    return path


def preflight(configuration, checkpoint_path, requested_log, identity_inputs=None):
    """Validate everything read-only, including relocation, before recovery/writes."""
    loaded = (
        json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else None
    )
    path = (
        requested_log
        if loaded is None
        else recorded_log(loaded, checkpoint_path, requested_log)
    )
    if path.resolve() == checkpoint_path.resolve():
        raise ValueError("checkpoint and journal must be different files")
    if loaded is not None:
        if {k: loaded.get(k) for k in configuration} != configuration:
            raise ValueError("checkpoint configuration does not match requested search")
        if not path.is_file():
            raise FileNotFoundError(f"checkpoint search log is missing: {path}")
        if path.resolve() != requested_log.resolve():
            if loaded.get("status") != "completed":
                raise ValueError("running checkpoint must resume with its recorded log")
            if (
                requested_log.exists()
                and requested_log.read_bytes() != path.read_bytes()
            ):
                raise ValueError(
                    "requested search log conflicts with checkpoint search log"
                )
    records, data, valid_size = inspect_log(path)
    successes, terminals, starts = budget_records(
        records,
        configuration["algorithm"],
        configuration["seed_start"],
        configuration["seed_count"],
    )
    if loaded is None and (successes or terminals or starts):
        if (
            len(successes) == configuration["seed_count"]
            and not starts
            and all(r.get("schema_version") != 2 for r in terminals)
        ):
            # Early bounded/DCLO runners supported log-only completed recovery.
            # Reconstruct a summary, without attributing current source to history.
            loaded = {
                **configuration,
                "status": "completed",
                "completed_seeds": len(successes),
                "_reconstructed_legacy": True,
            }
        else:
            raise ValueError("search log has attempts without a checkpoint")
    if loaded is not None:
        count = loaded.get("completed_seeds", 0)
        if not isinstance(count, int) or not 0 <= count <= configuration["seed_count"]:
            raise ValueError("checkpoint counter is outside the seed budget")
        if count > len(successes):
            raise ValueError("search log is behind checkpoint")
        if (
            loaded.get("status") == "completed"
            and len(successes) != configuration["seed_count"]
        ):
            raise ValueError("completed checkpoint has an incomplete log")
        size = loaded.get("log_size")
        if size is not None and (
            not isinstance(size, int)
            or not 0 <= size <= valid_size
            or hashlib.sha256(data[:size]).hexdigest() != loaded.get("log_sha256")
        ):
            raise ValueError("recorded journal contents conflict with checkpoint")
    manifest = loaded.get("manifest") if loaded else None
    remaining = len(successes) < configuration["seed_count"]
    if manifest is not None:
        if manifest != experiment_manifest(configuration, identity_inputs):
            raise ValueError(
                "experiment source/configuration/matrix/toolchain identity changed"
            )
        for record in records:
            if (
                record.get("schema_version") == 2
                and record.get("algorithm") == configuration["algorithm"]
                and configuration["seed_start"]
                <= record.get("seed", -1)
                < configuration["seed_start"] + configuration["seed_count"]
            ):
                if record.get("run_identity") != manifest["identity"]:
                    raise ValueError(
                        "journal belongs to a different experiment identity"
                    )
    elif loaded is not None and remaining:
        raise ValueError(
            "legacy checkpoint has no immutable manifest; restore/replay only, use a new budget for new work"
        )
    elif loaded is None:
        manifest = experiment_manifest(configuration, identity_inputs)
    return loaded, path, successes, terminals, starts, data, valid_size, manifest


@contextmanager
def cancellation_signals():
    """Turn SIGTERM into ordinary cancellation so the journal can be flushed."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        raise KeyboardInterrupt("SIGTERM")

    signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def run_budget(
    *,
    configuration,
    workers,
    checkpoint_path,
    log_path,
    worker,
    score,
    eligible,
    restore,
    accept,
    initial=None,
    append=append_log,
    save=write_checkpoint,
    identity_inputs=None,
):
    """Run a budget using strategy callbacks; return (seed, metrics, source)."""
    if workers <= 0 or configuration["seed_count"] <= 0:
        raise ValueError("seed_count and workers must be positive")
    loaded, recorded, successes, terminals, starts, data, valid_size, manifest = (
        preflight(configuration, checkpoint_path, log_path, identity_inputs)
    )
    best_seed, best_metrics, best_source = initial or (None, None, None)
    accepted = [r for r in successes if r.get("accepted")]
    if accepted:
        best_seed = accepted[-1]["seed"]
        best_metrics, best_source = restore(accepted[-1])
        if best_metrics != accepted[-1]["final_metrics"]:
            raise ValueError("incumbent artifact metrics differ from the search log")
        recorded_digest = accepted[-1].get("artifact_sha256")
        if (
            recorded_digest is not None
            and hashlib.sha256(best_source.encode()).hexdigest() != recorded_digest
        ):
            raise ValueError(
                "incumbent artifact contents differ from the accepted artifact"
            )
    elif loaded is not None and loaded.get("incumbent_seed") is not None:
        raise ValueError("checkpoint incumbent is absent from the search log")
    if (
        loaded is not None
        and loaded.get("status") == "completed"
        and best_metrics is None
    ):
        raise ValueError("completed checkpoint has no retained incumbent")
    if loaded is not None and loaded.get("completed_seeds") == len(successes):
        if "incumbent_seed" in loaded and loaded["incumbent_seed"] != best_seed:
            raise ValueError("checkpoint incumbent conflicts with its journal")
        if "incumbent_metrics" in loaded:
            previous = loaded["incumbent_metrics"]
            if isinstance(previous, dict):
                previous = {
                    k: v for k, v in previous.items() if k != "unreachable_nodes"
                }
            if previous != best_metrics:
                raise ValueError(
                    "checkpoint incumbent measurements conflict with its journal"
                )

    # Nothing persistent above this boundary has been modified.
    recover_tail(recorded, data, valid_size)
    if recorded.resolve() != log_path.resolve():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_bytes(recorded.read_bytes())
    if loaded is not None and loaded.get("status") == "completed":
        if loaded.pop("_reconstructed_legacy", False) or loaded.get(
            "completed_seeds"
        ) != len(successes):
            content = log_path.read_bytes()
            loaded.update(
                {
                    "search_log_path": os.path.relpath(
                        recorded.resolve(), checkpoint_path.parent.resolve()
                    ),
                    "search_log_path_base": "checkpoint",
                    "incumbent_seed": best_seed,
                    "incumbent_metrics": best_metrics,
                    "completed_seeds": len(successes),
                    "log_size": len(content),
                    "log_sha256": hashlib.sha256(content).hexdigest(),
                }
            )
            save(checkpoint_path, loaded)
        return best_seed, best_metrics, best_source
    append(log_path, [])  # An empty run still has a recorded, existing journal.
    log_content = log_path.read_bytes()
    log_digest = hashlib.sha256(log_content)
    log_size = len(log_content)
    journal_healthy = True

    def journal_append(records):
        nonlocal log_size, journal_healthy
        journal_healthy = False
        append(log_path, records)
        for record in records:
            encoded = (
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            log_digest.update(encoded)
            log_size += len(encoded)
        journal_healthy = True

    checkpoint = dict(loaded or configuration)
    checkpoint.update(
        {
            "search_log_path": os.path.relpath(
                log_path.resolve(), checkpoint_path.parent.resolve()
            ),
            "search_log_path_base": "checkpoint",
            "status": "running",
        }
    )
    if manifest is not None:
        checkpoint["manifest"] = manifest

    def persist(status="running"):
        checkpoint.update(
            {
                "completed_seeds": len(successes),
                "incumbent_seed": best_seed,
                "incumbent_metrics": best_metrics,
                "status": status,
                "log_size": log_size,
                "log_sha256": log_digest.hexdigest(),
            }
        )
        save(checkpoint_path, checkpoint)

    def finish(
        start,
        status,
        *,
        metrics=None,
        accepted=False,
        artifact=None,
        reason=None,
        runtime=None,
        source=None,
        failure_stage=None,
    ):
        record = {
            **start,
            "attempt_id": start["trial_id"],
            "status": status,
            "timestamp_utc": timestamp(),
            "runtime_seconds": round(runtime, 6) if runtime is not None else None,
            "final_metrics": metrics,
            "verification_passed": status == "succeeded",
            "verification_stage": (
                ("full" if accepted else "exact") if status == "succeeded" else "failed"
            ),
            "accepted": accepted,
            "artifact": str(artifact) if artifact else None,
            "artifact_sha256": (
                hashlib.sha256(source.encode()).hexdigest() if accepted else None
            ),
            "error_reason": reason if status != "succeeded" else None,
            "failure_stage": failure_stage,
            "rejection_reason": reason,
        }
        journal_append([record])
        return record

    for start in starts.values():
        terminal = finish(
            start,
            "interrupted",
            reason="parent terminated before a terminal record; detected on resume",
        )
        terminals.append(terminal)
    persist()
    retries = {}
    for record in terminals:
        retries[record["seed"]] = max(
            retries.get(record["seed"], 0), record.get("attempt_number", 1)
        )
    seeds = iter(
        range(
            configuration["seed_start"] + len(successes),
            configuration["seed_start"] + configuration["seed_count"],
        )
    )
    pending = deque()
    executor = None
    active = {}
    try:
        with cancellation_signals():
            executor = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None

            def submit_one():
                seed = next(seeds, None)
                if seed is None:
                    return False
                attempt_number = retries.get(seed, 0) + 1
                trial_id = (
                    f"{configuration['algorithm']}-seed-{seed}-attempt-{attempt_number}"
                )
                start = {
                    "schema_version": 2,
                    "attempt_id": trial_id + "-started",
                    "trial_id": trial_id,
                    "attempt_number": attempt_number,
                    "algorithm": configuration["algorithm"],
                    "seed": seed,
                    "run_identity": manifest["identity"],
                    "status": "started",
                    "timestamp_utc": timestamp(),
                    "runtime_seconds": None,
                    "verification_passed": False,
                    "accepted": False,
                    "rejection_reason": "attempt dispatched; verification pending",
                    "artifact": None,
                    "starting_metrics": initial[1] if initial else None,
                    "final_metrics": None,
                    "parameters": {
                        **configuration,
                        "seed_budget": configuration["seed_count"],
                    },
                }
                journal_append([start])
                active[trial_id] = start
                pending.append(
                    (start, executor.submit(worker, seed) if executor else None)
                )
                return True

            for _ in range(workers):
                if not submit_one():
                    break
            while pending:
                start, future = pending.popleft()
                metrics = None
                phase = "worker"
                began = time.perf_counter()
                try:
                    seed, metrics, source, runtime = (
                        future.result() if future else worker(start["seed"])
                    )
                    if seed != start["seed"]:
                        raise ValueError("worker returned the wrong seed")
                    phase = "objective_selection"
                    allowed = eligible(metrics)
                    improves = allowed and (
                        best_metrics is None
                        or score(metrics, seed)
                        < score(
                            best_metrics, best_seed if best_seed is not None else -1
                        )
                    )
                    phase = "parent_verification"
                    artifact = accept(seed, metrics, source) if improves else None
                    record = finish(
                        start,
                        "succeeded",
                        metrics=metrics,
                        accepted=improves,
                        artifact=artifact,
                        runtime=runtime,
                        source=source,
                        reason=(
                            None
                            if improves
                            else (
                                "does not improve incumbent"
                                if allowed
                                else "exceeds depth bound"
                            )
                        ),
                    )
                    del active[start["trial_id"]]
                    successes.append(record)
                    if improves:
                        best_seed, best_metrics, best_source = seed, metrics, source
                    persist()
                except BaseException as error:
                    # If appending itself failed, leave the start open for recovery.
                    if start["trial_id"] in active and journal_healthy:
                        finish(
                            start,
                            (
                                "cancelled"
                                if isinstance(error, KeyboardInterrupt)
                                else "failed"
                            ),
                            metrics=metrics,
                            reason=f"{type(error).__name__}: {error}",
                            runtime=time.perf_counter() - began,
                            failure_stage=phase,
                        )
                        del active[start["trial_id"]]
                    raise
                submit_one()  # Refill only after parent verification and persistence.
    except BaseException:
        for _, future in pending:
            if future is not None:
                future.cancel()
        if journal_healthy:
            for start in list(active.values()):
                finish(
                    start,
                    "cancelled",
                    reason="parent stopped accepting results; pending work cancelled, dispatched workers allowed to finish",
                )
            persist("interrupted")
        raise
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
    persist("completed")
    return best_seed, best_metrics, best_source

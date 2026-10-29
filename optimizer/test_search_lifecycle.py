"""Fault injection at journal, resume, worker and process-pool boundaries."""

from functools import partial
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from optimizer.search_lifecycle import (
    append_log,
    budget_records,
    callable_identity,
    inspect_log,
    run_budget,
    write_checkpoint,
)


def simple_worker(seed):
    return seed, {"value": seed}, str(seed), 0.01


def process_worker(seed, marker):
    with open(marker, "a") as output:
        output.write(str(seed) + "\n")
        output.flush()
        os.fsync(output.fileno())
    time.sleep(0.03 * (3 - seed % 3))
    return simple_worker(seed)


def run_until_killed(root):
    def blocking(seed):
        (root / "ready").touch()
        time.sleep(30)
        return simple_worker(seed)

    run_fixture(root, worker=blocking)


def configuration(count=3):
    return {"algorithm": "lifecycle-regression", "seed_start": 0, "seed_count": count}


def run_fixture(
    root, *, count=3, worker=simple_worker, accept=None, workers=1, log=None
):
    def save_artifact(seed, metrics, source):
        path = root / f"seed_{seed}.txt"
        path.write_text(source)
        return path

    def restore(record):
        return {"value": record["seed"]}, (
            root / f"seed_{record['seed']}.txt"
        ).read_text()

    return run_budget(
        configuration=configuration(count),
        workers=workers,
        checkpoint_path=root / "checkpoint.json",
        log_path=log or root / "log.jsonl",
        worker=worker,
        score=lambda metrics, seed: (metrics["value"], seed),
        eligible=lambda metrics: True,
        restore=restore,
        accept=accept or save_artifact,
    )


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def records(self):
        return inspect_log(self.root / "log.jsonl")[0]

    def checkpoint(self):
        return json.loads((self.root / "checkpoint.json").read_text())

    def fail(self, *args):
        raise RuntimeError("injected verification failure")

    def test_bound_trial_parameters_survive_manifest_serialization(self):
        identity = callable_identity(partial(simple_worker, 1))
        self.assertEqual(json.loads(json.dumps(identity)), identity)
        self.assertNotEqual(identity, callable_identity(partial(simple_worker, 2)))

    def test_historical_failed_rows_are_preserved_and_do_not_complete_a_seed(self):
        historical = {
            "algorithm": "lifecycle-regression",
            "seed": 0,
            "attempt_id": "historical-failure",
            "verification_passed": False,
            "accepted": False,
            "final_metrics": None,
            "rejection_reason": "old failure",
        }
        original = dict(historical)
        successes, terminals, starts = budget_records(
            [historical], "lifecycle-regression", 0, 3
        )
        self.assertEqual(successes, [])
        self.assertEqual(terminals, [historical])
        self.assertEqual(starts, {})
        self.assertEqual(historical, original)

    def test_complete_final_record_without_newline_gets_a_separator(self):
        run_fixture(self.root)
        log = self.root / "log.jsonl"
        valid = log.read_bytes()
        log.write_bytes(valid.rstrip(b"\n"))
        # Model a stale checkpoint whose durable prefix ends before the last row.
        document = self.checkpoint()
        document.pop("log_size")
        document.pop("log_sha256")
        write_checkpoint(self.root / "checkpoint.json", document)
        run_fixture(self.root, worker=self.fail)
        self.assertEqual(log.read_bytes(), valid)

    def test_new_events_preserve_the_ci_journal_contract(self):
        run_fixture(self.root)
        required = {
            "timestamp_utc",
            "attempt_id",
            "algorithm",
            "parameters",
            "seed",
            "runtime_seconds",
            "starting_metrics",
            "final_metrics",
            "verification_passed",
            "accepted",
            "rejection_reason",
            "artifact",
        }
        for record in self.records():
            self.assertTrue(required <= record.keys())
            self.assertIs(type(record["verification_passed"]), bool)
            self.assertIs(type(record["accepted"]), bool)
            if not record["accepted"]:
                self.assertTrue(record["rejection_reason"])

    def test_worker_failure_is_durable_and_retry_does_not_complete_seed(self):
        with self.assertRaisesRegex(RuntimeError, "verification failure"):
            run_fixture(self.root, worker=self.fail)
        failed = self.records()[-1]
        self.assertEqual(failed["status"], "failed")
        self.assertIsNone(failed["final_metrics"])
        self.assertFalse(failed["verification_passed"])
        self.assertFalse(failed["accepted"])
        self.assertIn("injected", failed["error_reason"])
        self.assertEqual(self.checkpoint()["completed_seeds"], 0)
        run_fixture(self.root)
        rows = self.records()
        self.assertEqual(len({r["attempt_id"] for r in rows}), len(rows))
        successes, _, _ = budget_records(rows, "lifecycle-regression", 0, 3)
        self.assertEqual([r["seed"] for r in successes], [0, 1, 2])
        self.assertEqual(successes[0]["attempt_number"], 2)

    def test_parent_verification_failures_preserve_measured_metrics(self):
        for error in (RuntimeError("exact mismatch"), OSError("formal tool missing")):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.assertRaises(type(error)):
                    run_fixture(root, accept=mock.Mock(side_effect=error))
                failed = inspect_log(root / "log.jsonl")[0][-1]
                self.assertEqual(failed["final_metrics"], {"value": 0})
                self.assertFalse(failed["accepted"])
                self.assertFalse(failed["verification_passed"])
                self.assertIn(str(error), failed["error_reason"])

    def test_cancellation_records_reason_and_retries(self):
        with self.assertRaises(KeyboardInterrupt):
            run_fixture(
                self.root,
                accept=mock.Mock(side_effect=KeyboardInterrupt("operator cancelled")),
            )
        self.assertEqual(self.records()[-1]["status"], "cancelled")
        self.assertIn("operator cancelled", self.records()[-1]["error_reason"])
        run_fixture(self.root)
        self.assertEqual(self.checkpoint()["completed_seeds"], 3)

    def test_real_pool_failure_does_not_drain_budget(self):
        marker = self.root / "workers.txt"
        with self.assertRaisesRegex(RuntimeError, "verification failure"):
            run_fixture(
                self.root,
                count=12,
                workers=2,
                worker=partial(process_worker, marker=str(marker)),
                accept=self.fail,
            )
        executed = [int(line) for line in marker.read_text().splitlines()]
        self.assertGreaterEqual(len(executed), 1)
        self.assertLessEqual(len(executed), 2)
        self.assertTrue(set(executed) <= {0, 1})
        self.assertEqual(self.checkpoint()["completed_seeds"], 0)
        self.assertTrue(all(not r["accepted"] for r in self.records()))

    def test_real_pool_keeps_seed_order_and_winner(self):
        result = run_fixture(
            self.root,
            count=6,
            workers=2,
            worker=partial(process_worker, marker=str(self.root / "workers.txt")),
        )
        self.assertEqual(result[0], 0)
        successes, _, _ = budget_records(self.records(), "lifecycle-regression", 0, 6)
        self.assertEqual([r["seed"] for r in successes], list(range(6)))

    def test_sigkill_is_detected_as_interrupted_on_resume(self):
        script = "from pathlib import Path; from optimizer.test_search_lifecycle import run_until_killed; run_until_killed(Path(__import__('sys').argv[1]))"
        process = subprocess.Popen([sys.executable, "-B", "-c", script, str(self.root)])
        try:
            deadline = time.monotonic() + 10
            while (
                not (self.root / "ready").exists()
                and process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            self.assertTrue((self.root / "ready").exists())
        finally:
            process.kill()
            process.wait(timeout=5)
        run_fixture(self.root)
        interrupted = [r for r in self.records() if r.get("status") == "interrupted"]
        self.assertEqual(len(interrupted), 1)
        self.assertIsNone(interrupted[0]["final_metrics"])
        self.assertFalse(interrupted[0]["accepted"])
        successes, _, _ = budget_records(self.records(), "lifecycle-regression", 0, 3)
        self.assertEqual(successes[0]["attempt_number"], 2)

    def test_invalid_resume_leaves_checkpoint_and_log_untouched(self):
        run_fixture(self.root)
        checkpoint = self.root / "checkpoint.json"
        log = self.root / "log.jsonl"
        saved_checkpoint, saved_log = checkpoint.read_bytes(), log.read_bytes()
        for status in ("running", "completed"):
            for problem in ("missing", "conflicting", "behind", "invalid_counter"):
                with self.subTest(status=status, problem=problem):
                    document = json.loads(saved_checkpoint)
                    document["status"] = status
                    if problem == "invalid_counter":
                        document["completed_seeds"] = 10
                    checkpoint.write_text(json.dumps(document))
                    log.write_bytes(saved_log)
                    requested = log
                    if problem == "missing":
                        log.unlink()
                    elif problem == "conflicting":
                        requested = self.root / "different.jsonl"
                        requested.write_text("{}\n")
                    elif problem == "behind":
                        log.write_text("")
                    original_checkpoint = checkpoint.read_bytes()
                    original_log = log.read_bytes() if log.exists() else None
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        run_fixture(self.root, log=requested)
                    self.assertEqual(checkpoint.read_bytes(), original_checkpoint)
                    self.assertEqual(
                        log.read_bytes() if log.exists() else None, original_log
                    )

    def test_completed_relocation_copies_validated_log_without_dispatch(self):
        result = run_fixture(self.root)
        before = (self.root / "checkpoint.json").read_bytes()
        destination = self.root / "relocated" / "log.jsonl"
        with mock.patch("optimizer.search_lifecycle.ProcessPoolExecutor") as executor:
            self.assertEqual(
                run_fixture(self.root, workers=2, worker=self.fail, log=destination),
                result,
            )
        executor.assert_not_called()
        self.assertEqual(
            destination.read_bytes(), (self.root / "log.jsonl").read_bytes()
        )
        self.assertEqual((self.root / "checkpoint.json").read_bytes(), before)

    def test_stale_counter_recovers_from_log_without_dispatch(self):
        result = run_fixture(self.root)
        document = self.checkpoint()
        document.update(
            status="running",
            completed_seeds=0,
            incumbent_seed=None,
            incumbent_metrics=None,
        )
        write_checkpoint(self.root / "checkpoint.json", document)
        self.assertEqual(run_fixture(self.root, worker=self.fail), result)
        self.assertEqual(self.checkpoint()["completed_seeds"], 3)

    def test_completed_stale_counter_is_reconciled_after_validation(self):
        result = run_fixture(self.root)
        document = self.checkpoint()
        document.update(completed_seeds=0, incumbent_seed=None, incumbent_metrics=None)
        write_checkpoint(self.root / "checkpoint.json", document)
        self.assertEqual(run_fixture(self.root, worker=self.fail), result)
        self.assertEqual(self.checkpoint()["completed_seeds"], 3)

    def test_checkpoint_incumbent_conflict_is_rejected_without_mutation(self):
        run_fixture(self.root)
        document = self.checkpoint()
        document["incumbent_metrics"] = {"value": 99}
        path = self.root / "checkpoint.json"
        write_checkpoint(path, document)
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "measurements conflict"):
            run_fixture(self.root)
        self.assertEqual(path.read_bytes(), before)

    def test_partial_tail_is_backed_up_and_recovered(self):
        run_fixture(self.root)
        log = self.root / "log.jsonl"
        valid = log.read_bytes()
        damaged = valid + b'{"algorithm":"unfinished'
        log.write_bytes(damaged)
        run_fixture(self.root, worker=self.fail)
        self.assertEqual(log.read_bytes(), valid)
        self.assertEqual(
            next(self.root.glob("log.jsonl.damaged-*")).read_bytes(), damaged
        )

    def test_truncated_literals_are_backed_up_and_recovered(self):
        result = run_fixture(self.root)
        records = self.records()
        log = self.root / "log.jsonl"
        checkpoint = self.root / "checkpoint.json"
        valid = log.read_bytes()
        saved_checkpoint = checkpoint.read_bytes()
        for literal in ("true", "false", "null"):
            field = "final_metrics" if literal == "null" else "accepted"
            for length in range(1, len(literal)):
                for prefix in (f'{{"{field}":', '{"label":"é","nested":[{"value":'):
                    tail = (prefix + literal[:length]).encode()
                    with self.subTest(tail=tail):
                        damaged = valid + tail
                        log.write_bytes(damaged)
                        self.assertEqual(
                            inspect_log(log), (records, damaged, len(valid))
                        )
                        self.assertEqual(log.read_bytes(), damaged)
                        self.assertEqual(
                            run_fixture(self.root, worker=self.fail), result
                        )
                        self.assertEqual(log.read_bytes(), valid)
                        self.assertEqual(checkpoint.read_bytes(), saved_checkpoint)
                        self.assertIn(
                            damaged,
                            [p.read_bytes() for p in self.root.glob("*.damaged-*")],
                        )

    def test_malformed_literals_and_nonfinal_prefixes_are_not_recovered(self):
        run_fixture(self.root)
        log = self.root / "log.jsonl"
        checkpoint = self.root / "checkpoint.json"
        valid = log.read_bytes()
        saved_checkpoint = checkpoint.read_bytes()
        tails = (
            b'{"accepted":falsx',
            b'{"accepted":False',
            b'{"accepted":fal ',
            b'{"accepted":fal}',
            b'{"accepted" fal',
            b'{"final_metrics":nux',
            b'{"accepted":fal\n',
            b'{"final_metrics":nu\n',
            b'{"accepted":tr\n{}\n',
        )
        for tail in tails:
            with self.subTest(tail=tail):
                damaged = valid + tail
                log.write_bytes(damaged)
                with self.assertRaisesRegex(ValueError, "corrupt journal"):
                    run_fixture(self.root, worker=self.fail)
                self.assertEqual(log.read_bytes(), damaged)
                self.assertEqual(checkpoint.read_bytes(), saved_checkpoint)
                self.assertEqual(list(self.root.glob("*.damaged-*")), [])

    def test_interior_corruption_is_never_recovered(self):
        run_fixture(self.root)
        log = self.root / "log.jsonl"
        damaged = b"{bad}\n" + log.read_bytes()
        log.write_bytes(damaged)
        before = (self.root / "checkpoint.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "corrupt journal"):
            run_fixture(self.root)
        self.assertEqual(log.read_bytes(), damaged)
        self.assertEqual((self.root / "checkpoint.json").read_bytes(), before)
        self.assertEqual(list(self.root.glob("*.damaged-*")), [])

    def test_complete_malformed_final_record_is_not_treated_as_torn_write(self):
        run_fixture(self.root)
        log = self.root / "log.jsonl"
        damaged = log.read_bytes() + b"{bad}"
        log.write_bytes(damaged)
        with self.assertRaisesRegex(ValueError, "corrupt journal"):
            run_fixture(self.root)
        self.assertEqual(log.read_bytes(), damaged)

    def test_open_start_with_changed_run_identity_is_rejected(self):
        with self.assertRaises(RuntimeError):
            run_fixture(self.root, worker=self.fail)
        log = self.root / "log.jsonl"
        rows = self.records()
        rows[0]["run_identity"] = "other-run"
        log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        document = self.checkpoint()
        document.pop("log_size")
        document.pop("log_sha256")
        write_checkpoint(self.root / "checkpoint.json", document)
        with self.assertRaisesRegex(ValueError, "different experiment identity"):
            run_fixture(self.root)

    def test_tool_versions_are_recorded_in_new_manifest(self):
        run_fixture(self.root)
        self.assertEqual(
            set(self.checkpoint()["manifest"]["tool_versions"]),
            {"python", "yosys", "abc", "z3"},
        )

    def test_replaced_log_at_same_path_is_rejected_by_digest(self):
        run_fixture(self.root)
        log = self.root / "log.jsonl"
        log.write_bytes(log.read_bytes().replace(b'"value":0', b'"value":9'))
        with self.assertRaisesRegex(ValueError, "contents conflict"):
            run_fixture(self.root)

    def test_source_matrix_toolchain_or_configuration_change_is_rejected(self):
        run_fixture(self.root)
        original = self.checkpoint()["manifest"]
        for key in ("source_sha256", "matrix_sha256", "tool_versions", "configuration"):
            changed = {**original, key: "changed"}
            before = (self.root / "checkpoint.json").read_bytes()
            with self.subTest(field=key), mock.patch(
                "optimizer.search_lifecycle.experiment_manifest", return_value=changed
            ):
                with self.assertRaisesRegex(ValueError, "identity changed"):
                    run_fixture(self.root)
            self.assertEqual((self.root / "checkpoint.json").read_bytes(), before)

    def test_legacy_incomplete_budget_cannot_mix_new_source(self):
        checkpoint = {**configuration(), "completed_seeds": 0, "status": "running"}
        write_checkpoint(self.root / "checkpoint.json", checkpoint)
        (self.root / "log.jsonl").touch()
        with self.assertRaisesRegex(ValueError, "legacy checkpoint"):
            run_fixture(self.root)

    def test_checkpoint_write_failure_recovers_the_durable_success(self):
        real_save = write_checkpoint

        def fail_after_acceptance(path, document):
            if document["completed_seeds"] == 1:
                raise OSError("injected checkpoint replace failure")
            real_save(path, document)

        with mock.patch(
            "optimizer.search_lifecycle.write_checkpoint",
            side_effect=fail_after_acceptance,
        ):
            # Pass the patched function explicitly: run_budget's default is bound.
            with self.assertRaisesRegex(OSError, "replace failure"):
                run_budget(
                    configuration=configuration(),
                    workers=1,
                    checkpoint_path=self.root / "checkpoint.json",
                    log_path=self.root / "log.jsonl",
                    worker=simple_worker,
                    score=lambda m, s: (m["value"], s),
                    eligible=lambda m: True,
                    restore=lambda r: ({"value": 0}, "0"),
                    accept=lambda s, m, source: (self.root / "seed_0.txt").write_text(
                        source
                    ),
                    save=fail_after_acceptance,
                )
        run_fixture(self.root)
        successes, _, _ = budget_records(self.records(), "lifecycle-regression", 0, 3)
        self.assertEqual(len(successes), 3)

    def test_partial_terminal_write_is_not_followed_by_another_append(self):
        log = self.root / "log.jsonl"
        calls = []

        def damaged_append(path, records):
            calls.append(records)
            if records and records[0].get("status") == "succeeded":
                with path.open("ab") as output:
                    output.write(b'{"schema_version":2,"status":"succ')
                raise OSError("injected journal write failure")
            append_log(path, records)

        with self.assertRaisesRegex(OSError, "journal write failure"):
            run_budget(
                configuration=configuration(),
                workers=1,
                checkpoint_path=self.root / "checkpoint.json",
                log_path=log,
                worker=simple_worker,
                score=lambda m, s: (m["value"], s),
                eligible=lambda m: True,
                restore=lambda r: ({"value": 0}, "0"),
                accept=lambda s, m, source: (self.root / "seed_0.txt").write_text(
                    source
                ),
                append=damaged_append,
            )
        damaged = log.read_bytes()
        self.assertTrue(damaged.endswith(b'"succ'))
        self.assertEqual(len(calls), 3)  # empty file, start, partial terminal
        run_fixture(self.root)
        self.assertEqual(next(self.root.glob("*.damaged-*")).read_bytes(), damaged)
        successes, _, _ = budget_records(self.records(), "lifecycle-regression", 0, 3)
        self.assertEqual(successes[0]["attempt_number"], 2)


if __name__ == "__main__":
    unittest.main()

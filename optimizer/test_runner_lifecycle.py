"""Exercise the shared lifecycle through all three public seeded runners."""

from contextlib import ExitStack
from functools import partial
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from optimizer.depth_bounded import run_bounded_search, search_seed_bounded
from optimizer.optimize import _saved_candidate, run_search
from optimizer.refine_candidates import run_refinement
from verifier.verify_network import parse_network
from verifier.build_results import check_candidate_a


class RunnerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (
            Path("results/phase6/candidate_depth6_bounded.v")
            .read_text()
            .replace("module candidate_depth6_bounded", "module candidate_a_min_area")
        )
        cls.metrics = parse_network(cls.source).normalize().metrics().to_dict()
        cls.metrics.pop("unreachable_nodes")

    def setup_runner(
        self,
        root,
        kind,
        stack,
        *,
        worker_error=None,
        verification_error=None,
        mismatch=False,
    ):
        output = root / "candidate.v"
        checkpoint = root / "checkpoint.json"
        log = root / "log.jsonl"
        worker_result = (0, self.metrics, self.source, 0.01)
        if kind == "a":
            module = "optimizer.optimize"
            candidate = _saved_candidate(0, self.source)
            stack.enter_context(
                mock.patch(f"{module}.search_seed", return_value=candidate)
            )
            report_metrics = {**self.metrics, "unreachable_nodes": []}
            if mismatch:
                report_metrics["xor2_count"] += 1
            verifier = stack.enter_context(
                mock.patch(
                    f"{module}._full_verify", return_value={"metrics": report_metrics}
                )
            )
            if verification_error:
                verifier.side_effect = verification_error

            def call():
                return run_search(
                    0,
                    1,
                    1,
                    checkpoint,
                    output,
                    root / "frontier.json",
                    root / "metrics.csv",
                    log,
                    100_000,
                    0xC32A5EED,
                )

        else:
            module = (
                "optimizer.depth_bounded"
                if kind == "bounded"
                else "optimizer.refine_candidates"
            )
            report_metrics = dict(self.metrics)
            if mismatch:
                report_metrics["xor2_count"] += 1

            def report(path, *args):
                if path.name == "candidate_c_min_depth.v":
                    return {
                        "metrics": parse_network(path.read_text())
                        .normalize()
                        .metrics()
                        .to_dict()
                    }
                return {"metrics": report_metrics}

            stack.enter_context(
                mock.patch(f"{module}.verification_report", side_effect=report)
            )
            formal = stack.enter_context(mock.patch(f"{module}.run_formal"))
            if verification_error:
                formal.side_effect = (
                    [None, verification_error]
                    if kind == "refine"
                    else verification_error
                )
            if kind == "bounded":

                def call():
                    return run_bounded_search(
                        7,
                        0,
                        1,
                        1,
                        checkpoint,
                        output,
                        root / "incumbents",
                        log,
                        100_000,
                        0xC32A5EED,
                        trial=partial(search_seed_bounded),
                    )

            else:
                initial = root / "candidate_c_min_depth.v"
                initial.write_text(
                    Path("results/phase4/candidate_c_min_depth.v").read_text()
                )
                output = root / "candidate_c_refined.v"

                def call():
                    return run_refinement(
                        "C", 0, 1, 1, checkpoint, root, log, 100_000, 0xC32A5EED
                    )

        worker = stack.enter_context(
            mock.patch(f"{module}._worker", return_value=worker_result)
        )
        if worker_error:
            worker.side_effect = worker_error
        return call, worker, output, checkpoint, log

    def test_worker_failure_is_recorded_by_each_runner(self):
        for kind in ("a", "bounded", "refine"):
            with self.subTest(
                runner=kind
            ), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                call, _, _, checkpoint, log = self.setup_runner(
                    Path(directory), kind, stack, worker_error=OSError("worker failed")
                )
                with self.assertRaisesRegex(OSError, "worker failed"):
                    call()
                failed = json.loads(log.read_text().splitlines()[-1])
                self.assertEqual(failed["status"], "failed")
                self.assertIsNone(failed["final_metrics"])
                self.assertFalse(failed["verification_passed"])
                self.assertFalse(failed["accepted"])
                self.assertEqual(
                    json.loads(checkpoint.read_text())["completed_seeds"], 0
                )

    def test_candidate_a_rejects_worker_source_different_from_the_proved_replay(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            call, worker, _, _, log = self.setup_runner(Path(directory), "a", stack)
            wrong_source = re.sub(
                r"assign next_crc\[0\] = [^;]+;",
                "assign next_crc[0] = crc[0];",
                self.source,
            )
            worker.return_value = (0, self.metrics, wrong_source, 0.01)
            with self.assertRaisesRegex(RuntimeError, "source differs"):
                call()
            self.assertFalse(json.loads(log.read_text().splitlines()[-1])["accepted"])

    def test_formal_failure_is_recorded_by_each_runner(self):
        for kind in ("a", "bounded", "refine"):
            with self.subTest(
                runner=kind
            ), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                call, _, _, _, log = self.setup_runner(
                    Path(directory),
                    kind,
                    stack,
                    verification_error=OSError("formal failed"),
                )
                with self.assertRaisesRegex(OSError, "formal failed"):
                    call()
                failed = json.loads(log.read_text().splitlines()[-1])
                self.assertEqual(failed["final_metrics"], self.metrics)
                self.assertFalse(failed["verification_passed"])
                self.assertFalse(failed["accepted"])
                self.assertIn("formal failed", failed["error_reason"])

    def test_inconsistent_verification_metrics_are_recorded_by_each_runner(self):
        for kind in ("a", "bounded", "refine"):
            with self.subTest(
                runner=kind
            ), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                call, _, _, _, log = self.setup_runner(
                    Path(directory), kind, stack, mismatch=True
                )
                with self.assertRaises(RuntimeError):
                    call()
                failed = json.loads(log.read_text().splitlines()[-1])
                self.assertEqual(failed["status"], "failed")
                self.assertFalse(failed["accepted"])

    def test_completed_runners_restore_outputs_without_seed_execution(self):
        for kind in ("a", "bounded", "refine"):
            with self.subTest(
                runner=kind
            ), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                root = Path(directory)
                call, worker, output, checkpoint, log = self.setup_runner(
                    root, kind, stack
                )
                call()
                saved_source = output.read_text()
                if kind == "a":
                    records = [
                        json.loads(line) for line in log.read_text().splitlines()
                    ]
                    measured = (
                        parse_network(saved_source).normalize().metrics().to_dict()
                    )
                    self.assertEqual(
                        check_candidate_a(measured, output, records, (checkpoint,))[
                            "seed"
                        ],
                        0,
                    )
                saved_checkpoint, saved_log = checkpoint.read_bytes(), log.read_bytes()
                output.unlink()
                worker.reset_mock()
                worker.side_effect = AssertionError("completed seed dispatched")
                if kind == "a":
                    stack.enter_context(
                        mock.patch(
                            "optimizer.optimize.search_seed",
                            side_effect=AssertionError("completed seed replayed"),
                        )
                    )
                call()
                worker.assert_not_called()
                self.assertEqual(output.read_text(), saved_source)
                self.assertEqual(checkpoint.read_bytes(), saved_checkpoint)
                self.assertEqual(log.read_bytes(), saved_log)


if __name__ == "__main__":
    unittest.main()

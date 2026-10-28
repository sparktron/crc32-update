"""Frozen-checkout audits run old code on copied evidence and copy back outputs only."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.frozen_checkout import run_frozen, sources_match

TOOL = 'from pathlib import Path\nPath("out.txt").write_text("{}:" + Path("evidence/in.txt").read_text())\n'


class FrozenCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous = os.getcwd()
        os.chdir(self.directory.name)
        git = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com"]
        subprocess.run(["git", "init", "-q"], check=True)
        Path("tool.py").write_text(TOOL.format("frozen"))
        subprocess.run([*git, "add", "tool.py"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "frozen"], check=True)
        self.commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        self.manifest = {"source_sha256": {
            "tool.py": hashlib.sha256(Path("tool.py").read_bytes()).hexdigest()}}
        Path("evidence").mkdir()
        Path("evidence/in.txt").write_text("data")

    def tearDown(self):
        os.chdir(self.previous)
        self.directory.cleanup()

    def test_runs_frozen_code_and_copies_back_declared_outputs(self):
        self.assertTrue(sources_match(self.manifest))
        Path("tool.py").write_text(TOOL.format("later"))
        Path("helper.py").write_text("")
        subprocess.run(["git", "add", "helper.py"], check=True)
        self.assertFalse(sources_match(self.manifest))
        run_frozen(self.commit, ["evidence"], ["python3", "-B", "tool.py"], ["out.txt"])
        self.assertEqual(Path("out.txt").read_text(), "frozen:data")
        self.assertEqual(Path("evidence/in.txt").read_text(), "data")
        self.assertNotIn("frozen-checkout-", subprocess.check_output(["git", "worktree", "list"], text=True))

    def test_rejects_changed_evidence(self):
        command = ["python3", "-B", "-c", "open('evidence/in.txt', 'w').write('changed')"]
        with self.assertRaisesRegex(ValueError, "changed evidence"):
            run_frozen(self.commit, ["evidence"], command, ["out.txt"])
        self.assertEqual(Path("evidence/in.txt").read_text(), "data")


if __name__ == "__main__":
    unittest.main()

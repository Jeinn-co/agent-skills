import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


class ClaudeSessionTests(unittest.TestCase):
    def read(self, folder):
        output = io.StringIO()
        with patch("pathlib.Path.home", return_value=Path(folder)), \
                patch("sys.argv", ["session_info.py", "claude"]), contextlib.redirect_stdout(output):
            runpy.run_path(str(Path(__file__).with_name("session_info.py")))
        return output.getvalue()

    def write(self, folder, name, record, stamp):
        path = Path(folder)/".claude/projects/project"/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        os.utime(path, (stamp, stamp))

    def test_usage_probe_files_cannot_hide_real_session_after_twentieth_file(self):
        with tempfile.TemporaryDirectory() as folder:
            self.write(folder, "real.jsonl", {"type": "assistant",
                       "message": {"model": "claude-opus-5-5"}, "perTurnEffort": "high"}, 1000000000)
            for i in range(24):
                self.write(folder, "probe-%d.jsonl" % i, {"type": "system", "local_command": "usage"}, 1000000001+i)
            text = self.read(folder)
            self.assertIn("claude-opus-5-5", text)
            self.assertIn("effort  high", text)
            self.assertNotIn("no local session", text)

    def test_synthetic_reply_does_not_replace_real_model(self):
        with tempfile.TemporaryDirectory() as folder:
            self.write(folder, "real.jsonl", {"type": "assistant", "message": {"model": "real-model"}}, 1000000000)
            self.write(folder, "synthetic.jsonl", {"type": "assistant", "message": {"model": "<synthetic>"}}, 1000000001)
            self.assertIn("real-model", self.read(folder))

    def test_only_empty_probes_means_no_local_session(self):
        with tempfile.TemporaryDirectory() as folder:
            self.write(folder, "probe.jsonl", {"type": "system", "local_command": "usage"}, 1000000000)
            self.assertEqual(self.read(folder).strip(), "no local session")


if __name__ == "__main__":
    unittest.main()

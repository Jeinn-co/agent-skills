import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


def _pb_bytes(field_number, payload):
    tag = (field_number << 3) | 2
    out = bytearray()
    for value in (tag, len(payload)):
        while value >= 0x80:
            out.append((value & 0x7F) | 0x80)
            value >>= 7
        out.append(value)
    return bytes(out) + payload


class AgySessionTests(unittest.TestCase):
    def read(self, folder):
        output = io.StringIO()
        with patch("pathlib.Path.home", return_value=Path(folder)), \
                patch("sys.argv", ["session_info.py", "agy"]), contextlib.redirect_stdout(output):
            runpy.run_path(str(Path(__file__).with_name("session_info.py")))
        return output.getvalue()

    def write_db(self, path, selected=None, base_model=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB)")
        blob = b""
        if base_model:
            blob += _pb_bytes(1, _pb_bytes(19, base_model.encode()))
        if selected:
            blob += _pb_bytes(3, _pb_bytes(28, selected.encode()))
        con.execute("INSERT INTO gen_metadata VALUES (1, ?)", (blob,))
        con.commit()
        con.close()

    def test_reads_model_and_effort_from_ide_conversation_db(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / ".gemini/antigravity/conversations/c1.db"
            self.write_db(db, selected="gemini-4-hydrogen-high", base_model="gemini-4-hydrogen")
            text = self.read(folder)
            self.assertIn("model   gemini-4-hydrogen", text)
            self.assertIn("effort  high", text)

    def test_orchestrator_uses_underlying_model_and_unknown_prints_question_mark(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / ".gemini/antigravity/conversations/c1.db"
            self.write_db(db, selected="gemini-pro-orchestrator-neon", base_model="gemini-4-neon")
            text = self.read(folder)
            self.assertIn("model   gemini-4-neon", text)
            self.assertIn("effort  ?", text)

        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / ".gemini/antigravity/conversations/empty.db"
            db.parent.mkdir(parents=True)
            db.write_bytes(b"")
            text = self.read(folder)
            self.assertIn("model   ?", text)
            self.assertIn("effort  ?", text)
            self.assertNotIn("gemini-3.8-flash", text)


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

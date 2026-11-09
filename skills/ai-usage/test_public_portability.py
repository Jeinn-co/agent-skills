"""Capability/OS branches: mocks are not native Windows or Linux integration tests."""
import contextlib
import datetime as dt
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import portable


class PublicPortabilityTests(unittest.TestCase):
    def test_default_timezone_is_host_local_not_taipei(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"XDG_CONFIG_HOME": folder}):
            self.assertIsNone(portable.report_timezone())

    def test_personal_offset_and_default_work_outside_current_machine(self):
        code = """import datetime as dt, time
import limit_resets, portable
if hasattr(time, 'tzset'): time.tzset()
stamp = dt.datetime(2026, 11, 30, 19, 22, tzinfo=dt.timezone.utc)
print(limit_resets.expiry(stamp.isoformat(), stamp-dt.timedelta(days=1)))
print(stamp.astimezone(portable.report_timezone()).strftime('%Y-%m-%d %H:%M'))
"""
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder)/"ai-usage/config.json"; config.parent.mkdir()
            for offset, expected in ((480, "2026-12-01 03:22"), (-300, "2026-11-30 14:22"), (None, None)):
                config.write_text(json.dumps({"timezone_offset_minutes": offset}))
                env = dict(os.environ, XDG_CONFIG_HOME=folder, TZ="UTC")
                result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parent,
                                        env=env, text=True, capture_output=True, check=True, timeout=5)
                lines = result.stdout.splitlines()
                self.assertIn(expected or lines[1], lines[0])

    def test_no_browser_and_no_cli_reports_missing_capability(self):
        text = io.StringIO()
        with patch("claude_browser.current_report", return_value=None), \
                patch("portable.argv", return_value=None), contextlib.redirect_stdout(text):
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(Path(__file__).with_name("claude_usage.py")))
        self.assertEqual(result.exception.code, 0)
        self.assertIn("not installed", text.getvalue())
        self.assertNotIn("0.0% used", text.getvalue())

    def test_provider_runs_in_clean_profile_without_cli_or_browser(self):
        driver = """from pathlib import Path
from unittest.mock import patch
import runpy, sys
with patch('pathlib.Path.home', return_value=Path(sys.argv[1])):
    runpy.run_path(sys.argv[2], run_name='__main__')
"""
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, XDG_CONFIG_HOME=folder, PATH="")
            result = subprocess.run([sys.executable, "-c", driver, folder,
                                     str(Path(__file__).with_name("claude_usage.py"))],
                                    env=env, text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertIn("claude CLI not installed", result.stdout)
            self.assertNotIn("0.0% used", result.stdout)

    def test_clear_command_removes_only_browser_observation(self):
        driver = """from pathlib import Path
from unittest.mock import patch
import runpy, sys
folder, source = Path(sys.argv[1]), sys.argv[2]
sys.argv = [source, '--clear']
with patch('pathlib.Path.home', return_value=folder):
    runpy.run_path(source, run_name='__main__')
"""
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)/".cache/ai-usage"; cache.mkdir(parents=True)
            snapshot = cache/"claude-browser.json"; snapshot.write_text("old observation")
            sibling = cache/"keep.json"; sibling.write_text("keep")
            result = subprocess.run([sys.executable, "-c", driver, folder,
                                     str(Path(__file__).with_name("claude_browser.py"))],
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertFalse(snapshot.exists())
            self.assertTrue(sibling.exists())

    def test_windows_cli_shim_dispatch(self):
        with patch("portable.os.name", "nt"), patch("portable.shutil.which", return_value=r"C:\tools\claude.cmd"):
            self.assertEqual(portable.argv("claude", "auth", "status"),
                             ["cmd", "/c", r"C:\tools\claude.cmd", "auth", "status"])


if __name__ == "__main__":
    unittest.main()

import datetime as dt
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
import contextlib

import claude_browser


class ClaudeBrowserTests(unittest.TestCase):
    def setUp(self):
        timezone = patch("portable.report_timezone", return_value=dt.timezone(dt.timedelta(hours=8)))
        timezone.start()
        self.addCleanup(timezone.stop)

    def data(self):
        return {"sourceUrl": "https://claude.ai/new#settings/usage", "browserName": "Chrome",
                "observedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "plan": "pro",
                "windows": {"5h": {"usedPercent": 0, "resetsAt": None},
                            "week": {"usedPercent": 78, "resetsAt": "2026-11-09T17:00:00+08:00"}},
                "resetCredits": {"availableCount": 0, "credits": []}}

    def test_browser_fable_reset_is_hidden_like_cli(self):
        data = self.data()
        data["resetCredits"] = {"availableCount": 2, "credits": [
            {"status": "available", "expiresAt": "2026-12-11T06:00:00+08:00", "label": "Full reset"},
            {"status": "available", "expiresAt": "2026-11-17T15:59:00+08:00", "label": "Fable reset"}]}
        text = "\n".join(claude_browser.report(data))
        self.assertIn("Limit resets: 1 available", text)
        self.assertIn("2026-12-11", text)
        self.assertNotIn("2026-11-17", text)
        self.assertNotIn("Reset 2", text)

    def test_browser_usage_keeps_explicit_source(self):
        text = "\n".join(claude_browser.report(self.data()))
        self.assertIn("plan: pro", text)
        self.assertIn("78.0% used", text)
        self.assertIn("nov 09 at 05:00pm", text)
        self.assertIn("Limit resets: 0 available", text)
        self.assertIn("Source: Chrome", text)

    def test_stale_future_and_invalid_data_are_rejected(self):
        for change in ({"observedAt": (dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=6)).isoformat()},
                       {"observedAt": (dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=6)).isoformat()},
                       {"sourceUrl": "https://other.example/"}, {"plan": "unknown"}):
            data = self.data() | change
            with self.assertRaises(ValueError):
                claude_browser.report(data)
        for value in (True, -1, 101, float("nan")):
            data = self.data(); data["windows"]["week"]["usedPercent"] = value
            with self.assertRaises(ValueError):
                claude_browser.report(data)

    def test_missing_browser_resets_are_unavailable_not_zero(self):
        data = self.data(); data["resetCredits"] = None
        self.assertIn("Limit resets: unavailable", "\n".join(claude_browser.report(data)))

    def test_saved_snapshot_discards_auth_fields(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(claude_browser, "SNAPSHOT", Path(folder)/"usage.json"):
            data = self.data(); data["cookie"] = "secret"; data["windows"]["week"]["token"] = "secret"
            claude_browser.save(data)
            saved = claude_browser.SNAPSHOT.read_text()
            self.assertNotIn("secret", saved)
            self.assertIn("resetCredits", saved)
            self.assertIsNotNone(claude_browser.current_report())
            if os.name != "nt":
                self.assertEqual(claude_browser.SNAPSHOT.stat().st_mode & 0o777, 0o600)

    def test_single_visible_window_does_not_invent_weekly_usage(self):
        data = self.data(); del data["windows"]["week"]; del data["browserName"]
        text = "\n".join(claude_browser.report(data))
        self.assertIn("Source: Browser", text)
        self.assertNotIn("week", text)

    def test_corrupt_oversized_and_stale_snapshot_fall_back(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(claude_browser, "SNAPSHOT", Path(folder)/"usage.json"):
            for text in ("not json", "x" * 65537, json.dumps(self.data() | {
                    "observedAt": (dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=6)).isoformat()})):
                claude_browser.SNAPSHOT.write_text(text)
                self.assertIsNone(claude_browser.current_report())

    def test_valid_browser_source_bypasses_cli_and_its_login(self):
        output = io.StringIO()
        with patch("claude_browser.current_report", return_value=claude_browser.report(self.data())), \
                patch("portable.argv") as argv, contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(Path(__file__).with_name("claude_usage.py")))
            self.assertEqual(result.exception.code, 0)
            argv.assert_not_called()
        self.assertIn("78.0% used", output.getvalue())

    def test_visible_browser_reset_expiry_and_validation(self):
        data = self.data()
        data["resetCredits"] = {"availableCount": 1, "credits": [
            {"status": "available", "expiresAt": "2026-12-01T03:22:00+08:00"}]}
        lines = claude_browser.report(data)
        self.assertIn("Limit resets: 1 available", lines)
        self.assertTrue(any("expires 2026-12-01 03:22" in line for line in lines))
        for invalid in ({"availableCount": True}, {"availableCount": 1, "credits": [{}]},
                        {"availableCount": 1, "credits": [{"status": "available", "expiresAt": "bad"}]}):
            data["resetCredits"] = invalid
            with self.assertRaises(ValueError):
                claude_browser.report(data)


if __name__ == "__main__":
    unittest.main()

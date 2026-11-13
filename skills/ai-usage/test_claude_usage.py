import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch

import limit_resets


class ClaudeAuthTests(unittest.TestCase):
    def probe(self, auth, recover=False, oauth_error=None, usage_text=None):
        def reply(args, **kwargs):
            if args[1:] == ["--version"]:
                text = "2.1.318 (Claude Code)"
            elif args[1:] == ["auth", "status"]:
                text = json.dumps(auth)
            else:
                usage = ("Current session: 0% used\nCurrent week (all models): 78% used"
                         if auth.get("loggedIn") or recover else "Total cost: $0.0000")
                text = json.dumps({"result": usage}) if usage_text is None else usage_text
            return subprocess.CompletedProcess(args, 0, stdout=text)
        output = io.StringIO()
        with patch("portable.argv", side_effect=lambda name, *args: [name, *args]), \
                patch("subprocess.run", side_effect=reply) as calls, \
                patch("claude_browser.current_report", return_value=None), \
                patch("limit_resets.fetch_claude",
                      side_effect=oauth_error or ValueError("no login")), \
                contextlib.redirect_stdout(output):
            code = 0
            try:
                runpy.run_path(str(Path(__file__).with_name("claude_usage.py")))
            except SystemExit as error:
                code = error.code
        return output.getvalue(), code, calls

    def test_signed_out_reports_failure_after_trying_original_usage_call(self):
        text, code, calls = self.probe({"loggedIn": False, "authMethod": "none"})
        self.assertEqual(code, 1)
        self.assertIn("not signed in", text)
        self.assertNotIn("could not parse", text)
        self.assertEqual(calls.call_count, 3)
        self.assertIn("/usage", calls.call_args_list[2].args[0])

    def test_status_false_does_not_block_cli_auth_recovery(self):
        text, code, calls = self.probe({"loggedIn": False, "authMethod": "none"}, recover=True)
        self.assertEqual(code, 0)
        self.assertIn("78.0% used", text)
        self.assertNotIn("not signed in", text)
        self.assertEqual(calls.call_count, 3)

    def test_signed_in_still_reads_live_usage(self):
        text, code, calls = self.probe({"loggedIn": True, "subscriptionType": "pro"})
        self.assertEqual(code, 0)
        self.assertIn("plan: pro", text)
        self.assertIn("78.0% used", text)
        self.assertIn("Limit resets: unavailable (CLI auth or read-only API failed)", text)
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(calls.call_args_list[1].args[0], ["claude", "auth", "status"])
        self.assertIn("/usage", calls.call_args_list[2].args[0])

    def test_reset_auth_failure_keeps_successful_usage(self):
        text, code, calls = self.probe({"loggedIn": True, "subscriptionType": "pro"},
                                      oauth_error=urllib.error.HTTPError("u", 401, "x", {}, None))
        self.assertEqual(code, 0)
        self.assertIn("78.0% used", text)
        self.assertIn("Limit resets: unavailable (HTTP 401)", text)
        self.assertNotIn("not signed in", text)
        self.assertEqual(calls.call_count, 3)

    def test_expired_token_retries_oauth_after_cli_renews_it(self):
        data = {"five_hour": {"utilization": 9, "resets_at": "2026-11-13T14:20:00+00:00"}}
        text, code, calls = self.probe({"loggedIn": True}, usage_text="", oauth_error=[
            limit_resets.TokenExpired(), ({"subscriptionType": "pro"}, data)])
        self.assertEqual(code, 0)
        self.assertIn("plan: pro", text)
        self.assertIn("9.0% used", text)
        self.assertIn("/usage", calls.call_args_list[2].args[0])

    def test_both_paths_failing_names_reason_and_next_step(self):
        text, code, _ = self.probe({"loggedIn": True}, usage_text="",
                                   oauth_error=urllib.error.HTTPError("u", 401, "x", {}, None))
        self.assertEqual(code, 1)
        self.assertIn("usage call failed (OAuth: HTTP 401; CLI /usage returned nothing in time)", text)
        self.assertIn("rerun the ai-usage skill", text)


class TokenExpiryTests(unittest.TestCase):
    def test_expired_stored_token_is_not_sent(self):
        with tempfile.TemporaryDirectory() as config:
            Path(config, ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
                "accessToken": "t", "expiresAt": (time.time() - 5) * 1000}}))
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_OAUTH_TOKEN"}
            with patch.dict(os.environ, {**env, "CLAUDE_CONFIG_DIR": config}, clear=True), \
                    patch("urllib.request.OpenerDirector.open") as opened:
                with self.assertRaises(limit_resets.TokenExpired):
                    limit_resets.fetch_claude("2.1.323")
                opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()

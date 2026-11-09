import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import unittest
from unittest.mock import patch


class ClaudeAuthTests(unittest.TestCase):
    def probe(self, auth, recover=False, reset_lines=None):
        def reply(args, **kwargs):
            if args[1:] == ["--version"]:
                text = "2.1.318 (Claude Code)"
            elif args[1:] == ["auth", "status"]:
                text = json.dumps(auth)
            else:
                usage = ("Current session: 0% used\nCurrent week (all models): 78% used"
                         if auth.get("loggedIn") or recover else "Total cost: $0.0000")
                text = json.dumps({"result": usage})
            return subprocess.CompletedProcess(args, 0, stdout=text)
        output = io.StringIO()
        with patch("portable.argv", side_effect=lambda name, *args: [name, *args]), \
                patch("subprocess.run", side_effect=reply) as calls, \
                patch("claude_browser.current_report", return_value=None), \
                patch("limit_resets.claude_report", return_value=reset_lines or ["Limit resets: 0 available"]), \
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
        self.assertEqual(calls.call_count, 2)
        self.assertIn("/usage", calls.call_args_list[1].args[0])

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
        self.assertIn("Limit resets: 0 available", text)
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(calls.call_args_list[0].args[0], ["claude", "auth", "status"])
        self.assertIn("/usage", calls.call_args_list[1].args[0])

    def test_reset_auth_failure_keeps_successful_usage(self):
        text, code, calls = self.probe({"loggedIn": True, "subscriptionType": "pro"},
                                      reset_lines=["Limit resets: unavailable (HTTP 401)"])
        self.assertEqual(code, 0)
        self.assertIn("78.0% used", text)
        self.assertIn("Limit resets: unavailable (HTTP 401)", text)
        self.assertNotIn("not signed in", text)
        self.assertEqual(calls.call_count, 3)


if __name__ == "__main__":
    unittest.main()

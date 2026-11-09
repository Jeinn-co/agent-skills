import contextlib
import io
from pathlib import Path
import runpy
import unittest
from unittest.mock import MagicMock, patch

import html_report


class CodexAuthTests(unittest.TestCase):
    def probe(self, reply, signed_in=True):
        process = MagicMock()
        process.stdin = io.StringIO()
        process.stdout = []
        process.poll.return_value = 0
        output = io.StringIO()
        with patch("portable.argv", return_value=["codex", "app-server"]), \
                patch("subprocess.Popen", return_value=process), \
                patch("portable.rpc_reply", side_effect=[{"result": {}}, reply]), \
                patch("provider_login.signed_in", return_value=signed_in) as status, \
                contextlib.redirect_stdout(output):
            code = 0
            try:
                runpy.run_path(str(Path(__file__).with_name("codex_usage.py")))
            except SystemExit as error:
                code = error.code
        return output.getvalue(), code, status

    def test_server_rejected_cached_auth_shows_login_button(self):
        text, code, status = self.probe({"error": {"code": 401, "message": "Unauthorized"}}, True)
        self.assertEqual(code, 1)
        self.assertIn("not signed in", text)
        self.assertIn('data-provider-login="CHATGPT"', html_report.render("### CHATGPT\n" + text))
        status.assert_not_called()

    def test_signed_out_status_shows_button_on_failure(self):
        text, code, status = self.probe({"error": {"code": -32000, "message": "request failed"}}, False)
        self.assertEqual(code, 1)
        self.assertIn("not signed in", text)
        status.assert_called_once_with("CHATGPT")

    def test_network_failure_with_valid_login_does_not_offer_reauthentication(self):
        text, code, status = self.probe({"error": {"message": "connection refused"}}, True)
        self.assertEqual(code, 1)
        self.assertNotIn("not signed in", text)
        self.assertNotIn("data-provider-login", html_report.render("### CHATGPT\n" + text))

    def test_successful_usage_does_not_query_login_status(self):
        reply = {"result": {"rateLimits": {"planType": "plus",
            "primary": {"usedPercent": 10, "windowDurationMins": 300, "resetsAt": 1794024000},
            "secondary": {"usedPercent": 70, "windowDurationMins": 10080, "resetsAt": 1794379712}},
            "rateLimitResetCredits": {"availableCount": 2, "credits": None}}}
        text, code, status = self.probe(reply)
        self.assertEqual(code, 0)
        self.assertIn("plan: plus", text)
        self.assertIn("2 available", text)
        status.assert_not_called()


if __name__ == "__main__":
    unittest.main()

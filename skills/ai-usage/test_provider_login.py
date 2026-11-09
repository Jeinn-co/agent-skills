import ast
import http.client
import http.server
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import unittest
from unittest.mock import patch

import provider_login
import html_report


class ProviderLoginTests(unittest.TestCase):
    def setUp(self):
        cli = patch("provider_login.portable.argv", side_effect=lambda name, *args: [name, *args])
        cli.start()
        self.addCleanup(cli.stop)

    def test_success_requires_cli_login_and_verified_auth(self):
        with patch("provider_login.portable.argv", return_value=["claude", "auth", "login", "--claudeai"]), \
                patch("provider_login.signed_in", return_value=True) as status, \
                patch("provider_login.portable.run_bounded", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(provider_login.sign_in("CLAUDE")["ok"])
        self.assertEqual(status.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["claude", "auth", "login", "--claudeai"])
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["timeout"], 300)

    def test_explicit_click_can_reauthorize_even_if_credentials_look_cached(self):
        with patch("provider_login.signed_in", return_value=True), \
                patch("provider_login.portable.run_bounded", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(provider_login.sign_in("CLAUDE")["ok"])
            run.assert_called_once()

    def test_missing_cli_and_concurrent_click_do_not_launch(self):
        with patch("provider_login.portable.argv", return_value=None):
            self.assertFalse(provider_login.sign_in("CLAUDE")["ok"])
        with provider_login._lock, patch("provider_login.portable.run_bounded") as run:
            self.assertIn("already in progress", provider_login.sign_in("CLAUDE")["message"])
            run.assert_not_called()

    def test_failed_login_does_not_claim_success(self):
        for code, statuses in ((1, []), (0, [False])):
            with patch("provider_login.signed_in", side_effect=statuses), \
                    patch("provider_login.portable.run_bounded", return_value=subprocess.CompletedProcess([], code)):
                self.assertFalse(provider_login.sign_in("CLAUDE")["ok"])

    def test_timeout_and_errors_release_lock_without_leaking_output(self):
        for error in (subprocess.TimeoutExpired("private-output", 300), RuntimeError("private-output")):
            with patch("provider_login.portable.run_bounded", side_effect=error):
                result = provider_login.sign_in("CLAUDE")
            self.assertFalse(result["ok"])
            self.assertNotIn("private-output", str(result))
            self.assertTrue(provider_login._lock.acquire(blocking=False))
            provider_login._lock.release()

    def test_login_buttons_only_for_signed_out_providers(self):
        page = html_report.render("### CLAUDE\nplan: unavailable\nClaude CLI is not signed in.\n")
        self.assertIn('data-provider-login="CLAUDE"', page)
        self.assertIn('role="status"', page)
        self.assertIn('>Sign in to Claude</button>', page)
        page = html_report.render("### CHATGPT\nplan: unavailable\nChatGPT CLI is not signed in.\n")
        self.assertIn('data-provider-login="CHATGPT"', page)
        self.assertIn('>Sign in to ChatGPT</button>', page)
        self.assertIn('aria-describedby="chatgpt-login-status"', page)
        for raw in ("### CLAUDE\nplan: pro\n", "### CHATGPT\nplan: plus\n"):
            self.assertNotIn("data-provider-login", html_report.render(raw))

    def test_codex_login_command_and_post_login_check(self):
        with patch("provider_login.signed_in", return_value=True) as status, \
                patch("provider_login.portable.run_bounded", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(provider_login.sign_in("CHATGPT")["ok"])
        self.assertEqual(run.call_args.args[0], ["codex", "login"])
        status.assert_called_once_with("CHATGPT")

    def test_codex_auth_status_accepts_chatgpt_not_api_key(self):
        for code, stdout, stderr, expected in (
                (0, "", "Logged in using ChatGPT", True),
                (0, "Logged in using ChatGPT", "", True),
                (1, "", "Not logged in", False),
                (0, "Logged in using an API key", "", False)):
            with patch("provider_login.portable.run_bounded", return_value=
                       subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)):
                self.assertEqual(provider_login.signed_in("CHATGPT"), expected)

    def test_auth_errors_are_distinct_from_network_errors(self):
        for error in ({"code": 401}, {"code": -32000, "message": "Refresh token expired"},
                      {"message": "Unauthorized"}):
            self.assertTrue(provider_login.requires_auth(error))
        for error in (None, {"message": "connection refused"}, {"message": "rate limit exceeded"},
                      {"code": 407, "message": "proxy authentication required"}):
            self.assertFalse(provider_login.requires_auth(error))

    def test_unknown_provider_cannot_launch_a_command(self):
        with patch("provider_login.portable.run_bounded") as run:
            self.assertFalse(provider_login.sign_in("untrusted command")["ok"])
            run.assert_not_called()

    def test_http_login_requires_explicit_same_origin_post(self):
        # Compile the real request handler without running the launcher/server main.
        tree = ast.parse(Path(__file__).with_name("run.py").read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Handler")
        namespace = {"BaseHTTPRequestHandler": http.server.BaseHTTPRequestHandler, "json": json,
                     "SERVE_PORT": 0}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "run.py", "exec"), namespace)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), namespace["Handler"])
        port = server.server_address[1]; namespace["SERVE_PORT"] = port
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def request(method, headers, provider="CLAUDE"):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request(method, "/login", json.dumps({"id": provider}), headers)
            response = conn.getresponse(); body = response.read(); status = response.status
            conn.close(); return status, body
        try:
            with patch("provider_login.sign_in", return_value={"ok": True, "message": "test only"}) as login:
                self.assertEqual(request("GET", {})[0], 404)
                self.assertEqual(request("POST", {})[0], 404)
                self.assertEqual(request("POST", {"X-AI-Usage": "1", "Origin": "https://other.example"})[0], 403)
                login.assert_not_called()
                status, body = request("POST", {"X-AI-Usage": "1", "Origin": "http://127.0.0.1:%d" % port})
                self.assertEqual(status, 200)
                self.assertTrue(json.loads(body)["ok"])
                login.assert_called_once_with("CLAUDE")
                status, body = request("POST", {"X-AI-Usage": "1"}, "CHATGPT")
                self.assertEqual(status, 200)
                login.assert_called_with("CHATGPT")
                status, body = request("POST", {"X-AI-Usage": "1"}, "untrusted command")
                self.assertEqual(status, 403)
                self.assertEqual(login.call_count, 2)
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=2)

    @unittest.skipUnless(shutil.which("node"), "Node required for browser-handler self-check")
    def test_browser_binding_does_not_login_until_clicked_and_refreshes_after_success(self):
        tree = ast.parse(Path(__file__).with_name("run.py").read_text())
        shell = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "SHELL" for t in n.targets))
        source = re.search(r"function bindProviderLogin\(doc\) \{.*?\n\}", shell, re.S).group()
        driver = """const vm = require('node:vm'), fs = require('node:fs');
const signIn = {hidden: true, dataset: {providerLogin: 'CLAUDE', providerName: 'Claude'}}, status = {}, calls = [];
let refresh = 0, finish;
const doc = {querySelectorAll: () => [signIn], getElementById: () => status};
const context = {post: (path, body) => {calls.push({path, body}); return new Promise(r => finish=r);},
  button: {click: () => refresh++}};
vm.runInNewContext(fs.readFileSync(0, 'utf8'), context);
context.bindProviderLogin(doc);
if (calls.length || signIn.hidden) throw Error('binding started login or left button hidden');
(async () => {
  const task = signIn.onclick();
  if (!signIn.disabled || calls.length !== 1) throw Error('click did not start exactly one login');
  finish({ok: true, message: 'done'}); await task;
  if (refresh !== 1 || signIn.disabled || status.textContent !== 'done') throw Error('success did not refresh');
  const failed = signIn.onclick(); finish({ok: false, message: 'cancelled'}); await failed;
  if (refresh !== 1 || status.textContent !== 'cancelled') throw Error('failure claimed success');
  console.log(JSON.stringify(calls));
})().catch(e => {console.error(e); process.exitCode=1;});
"""
        result = subprocess.run([shutil.which("node"), "-e", driver], input=source,
                                text=True, capture_output=True, check=True, timeout=5)
        self.assertEqual(json.loads(result.stdout)[0], {"path": "/login", "body": {"id": "CLAUDE"}})


if __name__ == "__main__":
    unittest.main()

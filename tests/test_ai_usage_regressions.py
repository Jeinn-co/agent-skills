import contextlib
import io
import json
import os
import runpy
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "ai-usage"


class ClaudeQuotaTests(unittest.TestCase):
    """OAuth usage endpoint first; any failure falls back to `claude -p /usage` text."""
    LOGIN = json.dumps({"claudeAiOauth": {
        "accessToken": "test-token-never-log", "subscriptionType": "pro"}})
    FALLBACK = json.dumps({"result": "Current session: 25% used\nCurrent week (all models): 3% used"})

    def run_claude(self, usage, *, error=None, credentials=None):
        sys.path.insert(0, str(SKILL))
        import claude_browser
        import portable

        def reply(args, **kwargs):
            if args[1:] == ["--version"]:
                text = "2.1.319 (Claude Code)"
            elif args[1:] == ["auth", "status"]:
                text = json.dumps({"loggedIn": True, "subscriptionType": "max"})
            else:
                text = self.FALLBACK
            return subprocess.CompletedProcess(args, 0, stdout=text)

        opener = mock.MagicMock()
        opener.open.return_value.__enter__.return_value = io.StringIO(json.dumps(usage))
        if error is not None:
            opener.open.side_effect = error
        output = io.StringIO()
        with mock.patch.object(portable, "argv", side_effect=lambda name, *a: [name, *a]), \
                mock.patch.object(portable, "stdout_utf8"), \
                mock.patch.object(claude_browser, "current_report", return_value=None), \
                mock.patch.object(Path, "is_file", return_value=True), \
                mock.patch.object(Path, "read_text", autospec=True,
                                  return_value=credentials or self.LOGIN), \
                mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "test-claude-config",
                                             "CLAUDE_CODE_OAUTH_TOKEN": ""}), \
                mock.patch("urllib.request.build_opener", return_value=opener), \
                mock.patch("subprocess.run", side_effect=reply) as cli, \
                contextlib.redirect_stdout(output):
            code = 0
            try:
                runpy.run_path(str(SKILL / "claude_usage.py"), run_name="__main__")
            except SystemExit as error_exit:
                code = error_exit.code
        self.assertNotIn("test-token-never-log", output.getvalue())
        self.assertEqual(output.getvalue().count("plan:"), 1, output.getvalue())
        used_fallback = any("/usage" in c.args[0] for c in cli.call_args_list)
        return code, output.getvalue(), opener, used_fallback

    def test_reads_quota_and_banked_resets_in_one_request(self):
        code, output, opener, fallback = self.run_claude({
            "five_hour": {"utilization": 25, "resets_at": "2099-09-12T07:40:00Z"},
            "seven_day": {"utilization": 41, "resets_at": "2099-09-14T09:00:00Z"},
            "extra_usage": {"is_enabled": True},
            "cedar_ember": {"eligible": False, "ineligible_reason": "no_grant", "grants": []},
        })
        self.assertEqual(code, 0, output)
        self.assertFalse(fallback)
        self.assertIn("plan: pro", output)
        self.assertIn("25.0% used  resets Sep", output)
        self.assertIn("41.0% used", output)
        self.assertIn("bar █████░░░░░░░░░░░░░░░", output)
        self.assertIn("Limit resets: 0 available", output)
        self.assertNotIn("extra usage", output.lower())
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://api.anthropic.com/api/oauth/usage?"))
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token-never-log")
        self.assertEqual(request.get_header("Anthropic-beta"), "oauth-2025-04-20")

    def test_zero_usage_without_reset_is_preserved(self):
        code, output, _, fallback = self.run_claude({
            "five_hour": {"utilization": 0, "resets_at": None},
            "seven_day": {"utilization": 59, "resets_at": None},
        })
        self.assertEqual(code, 0, output)
        self.assertFalse(fallback)
        self.assertIn("0.0% used", output)
        self.assertIn("59.0% used", output)
        self.assertNotIn("used  resets", output)

    def test_invalid_credentials_skip_network_and_fall_back(self):
        code, output, opener, fallback = self.run_claude({}, credentials="invalid json")
        self.assertEqual(code, 0, output)
        opener.open.assert_not_called()
        self.assertTrue(fallback)
        self.assertIn("plan: max", output)
        self.assertIn("25.0% used", output)
        self.assertIn("Limit resets: unavailable (CLI auth or read-only API failed)", output)

    def test_auth_and_rate_limit_errors_fall_back_with_reason(self):
        for status in (401, 429):
            with self.subTest(status=status):
                error = urllib.error.HTTPError(
                    "https://api.anthropic.com/api/oauth/usage", status, "failed", {}, None)
                code, output, _, fallback = self.run_claude({}, error=error)
                self.assertEqual(code, 0, output)
                self.assertTrue(fallback)
                self.assertIn("25.0% used", output)
                self.assertIn("Limit resets: unavailable (HTTP %s)" % status, output)

    def test_invalid_quota_response_never_defaults_to_zero(self):
        responses = [{}, [], {"five_hour": {}},
                     {"five_hour": {"utilization": 25, "resets_at": "invalid"}}]
        for value in (True, "25", -1, 101, float("nan"), float("inf")):
            responses.append({"five_hour": {"utilization": value}})
        for usage in responses:
            with self.subTest(usage=usage):
                code, output, _, fallback = self.run_claude(usage)
                self.assertTrue(fallback, output)
                self.assertNotIn("0.0% used", output)
                self.assertIn("25.0% used", output)


@unittest.skipIf(os.name == "nt", "POSIX fake executables are used for probe tests")
class ProviderRegressionTests(unittest.TestCase):
    def run_probe(self, probe, cli_name, source):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / cli_name
            executable.write_text(
                "#!%s\n%s" % (sys.executable, textwrap.dedent(source)),
                encoding="utf-8",
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
            env = os.environ.copy()
            env["PATH"] = directory + os.pathsep + env.get("PATH", "")
            return subprocess.run(
                [sys.executable, str(SKILL / probe)],
                cwd=SKILL,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )

    def test_codex_rejects_incomplete_rate_limit_data(self):
        result = self.run_probe(
            "codex_usage.py",
            "codex",
            r'''
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    if request["id"] == 1:
        response = {"jsonrpc": "2.0", "id": 1, "result": {}}
    else:
        response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "rateLimits": {
                    "planType": "plus",
                    "primary": {
                        "usedPercent": 12,
                        "windowDurationMins": 300,
                        "resetsAt": 1893456000,
                    }
                }
            },
        }
    print(json.dumps(response), flush=True)
''',
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("rateLimits call failed (invalid response:", result.stdout)
        self.assertNotIn("1970", result.stdout)
        self.assertNotIn("0.0% used", result.stdout)

    def test_codex_omits_unread_usage_limit_resets_row(self):
        result = self.run_probe(
            "codex_usage.py",
            "codex",
            r'''
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    if request["id"] == 1:
        response = {"jsonrpc": "2.0", "id": 1, "result": {}}
    else:
        response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "rateLimits": {
                    "planType": "plus",
                    "primary": {
                        "usedPercent": 12,
                        "windowDurationMins": 300,
                        "resetsAt": 1893456000,
                    },
                    "secondary": {
                        "usedPercent": 8,
                        "windowDurationMins": 10080,
                        "resetsAt": 1893456000,
                    },
                    "credits": {"balance": "0"},
                }
            },
        }
    print(json.dumps(response), flush=True)
''',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("plan: plus", result.stdout)
        self.assertIn("12.0% used", result.stdout)
        self.assertNotIn("resets available", result.stdout.lower())
        self.assertNotIn("unknown (web only)", result.stdout.lower())

    def test_grok_rejects_incomplete_billing_data(self):
        result = self.run_probe(
            "grok_usage.py",
            "grok",
            r'''
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    response = {
        "jsonrpc": "2.0",
        "id": request["id"],
        "result": {} if request["id"] == 1 else {
            "subscription_tier": "SuperGrok",
            "config": {},
        },
    }
    print(json.dumps(response), flush=True)
''',
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("billing call failed (invalid response:", result.stdout)
        self.assertNotIn("0.0% used", result.stdout)
        self.assertNotIn("<1% used", result.stdout)

    def test_grok_absent_percent_reads_as_under_one(self):
        result = self.run_probe(
            "grok_usage.py",
            "grok",
            r'''
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    if request["id"] == 1:
        response = {"jsonrpc": "2.0", "id": 1, "result": {}}
    else:
        response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "subscription_tier": "SuperGrok",
                "config": {
                    "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY"},
                    "billingPeriodEnd": "2099-01-01T00:00:00Z",
                    "prepaidBalance": {"val": 0},
                    "onDemandUsed": {"val": 0},
                    "onDemandCap": {"val": 0},
                },
            },
        }
    print(json.dumps(response), flush=True)
''',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("plan: SuperGrok", result.stdout)
        self.assertIn("<1% used", result.stdout)
        self.assertNotIn("0.0% used", result.stdout)
        week_line = [
            line for line in result.stdout.splitlines() if line.startswith("week")
        ][0]
        self.assertIn("resets", week_line)

    def test_grok_rejects_non_numeric_percent(self):
        result = self.run_probe(
            "grok_usage.py",
            "grok",
            r'''
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    if request["id"] == 1:
        response = {"jsonrpc": "2.0", "id": 1, "result": {}}
    else:
        response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "subscription_tier": "SuperGrok",
                "config": {
                    "creditUsagePercent": "27",
                    "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY"},
                    "billingPeriodEnd": "2099-01-01T00:00:00Z",
                },
            },
        }
    print(json.dumps(response), flush=True)
''',
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("billing call failed (invalid response:", result.stdout)
        self.assertNotIn("0.0% used", result.stdout)
        self.assertNotIn("<1% used", result.stdout)

    def _grok_billing_cli(self, prepaid, on_demand_used, on_demand_cap):
        return r'''
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    if request["id"] == 1:
        response = {"jsonrpc": "2.0", "id": 1, "result": {}}
    else:
        response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "subscription_tier": "SuperGrok",
                "config": {
                    "creditUsagePercent": 27,
                    "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY"},
                    "billingPeriodEnd": "2099-01-01T00:00:00Z",
                    "prepaidBalance": {"val": %s},
                    "onDemandUsed": {"val": %s},
                    "onDemandCap": {"val": %s},
                },
            },
        }
    print(json.dumps(response), flush=True)
''' % (prepaid, on_demand_used, on_demand_cap)

    def test_grok_omits_zero_prepaid_and_on_demand(self):
        result = self.run_probe(
            "grok_usage.py",
            "grok",
            self._grok_billing_cli(0, 0, 0),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("plan: SuperGrok", result.stdout)
        self.assertIn("27.0% used", result.stdout)
        self.assertNotIn("prepaid", result.stdout.lower())
        self.assertNotIn("on-demand", result.stdout.lower())

    def test_grok_prints_non_zero_prepaid(self):
        result = self.run_probe(
            "grok_usage.py",
            "grok",
            self._grok_billing_cli(12, 0, 0),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("prepaid balance 12 | on-demand 0/0", result.stdout)

    def _muse_serve_cli(self, usage):
        return r'''
import json
import sys

USAGE = %s

def send(message):
    print(json.dumps(message), flush=True)

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if "id" not in request:
        continue
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {}})
    elif method == "session/start":
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"session": {"sessionId": "s1"}}})
    elif method == "turn/start":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {}})
        if USAGE:
            send({"jsonrpc": "2.0", "method": "usage/changed", "params": USAGE})
        send({"jsonrpc": "2.0", "method": "turn/completed", "params": {}})
    elif method == "usage/read":
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"usage": USAGE} if USAGE else {}})
''' % repr(usage)

    def test_muse_prints_window_and_week(self):
        result = self.run_probe(
            "muse_usage.py",
            "muse",
            self._muse_serve_cli({
                "observedAtMs": 1,
                "tier": "27681527378179523",
                "window": {"usedPercent": 5, "resetsAtMs": 4070908800000,
                           "windowDurationMins": 300},
                "weekly": {"usedPercent": 1, "resetsAtMs": 4070908800000},
            }),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("plan: High Usage", result.stdout)
        self.assertNotIn("27681527378179523", result.stdout)
        lines = result.stdout.splitlines()
        self.assertTrue(any(l.startswith("5h") and "5.0% used" in l for l in lines))
        self.assertTrue(any(l.startswith("week") and "1.0% used" in l for l in lines))

    def test_muse_fails_when_no_usage_observed(self):
        result = self.run_probe("muse_usage.py", "muse", self._muse_serve_cli(None))

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("usage call failed (no usage observed", result.stdout)
        self.assertNotIn("0.0% used", result.stdout)


@unittest.skipIf(os.name == "nt", "POSIX fake executables are used for probe tests")
class GeminiAgyTests(unittest.TestCase):
    """agy_usage.py runs ~/.gemini/bin/agy, never an `agy` on PATH (the IDE launcher)."""

    def run_agy(self, source, on_path=None, signed_in=True, auth_logs=None):
        with tempfile.TemporaryDirectory() as home:
            env = os.environ.copy()
            env["HOME"] = home
            if auth_logs is None:
                auth_logs = {"antigravity-cli": (
                    "URL: https://example/v1internal:loadCodeAssist\n" if signed_in
                    else "Authentication required. Please visit the URL to log in\n")}
            for index, (folder, text) in enumerate(auth_logs.items()):
                logs = Path(home) / ".gemini" / folder / "log"
                logs.mkdir(parents=True)
                log = logs / "cli-20260101_000000.log"
                log.write_text(text, encoding="utf-8")
                os.utime(log, (1_000_000_000 + index, 1_000_000_000 + index))
            if source is not None:
                cli = Path(home) / ".gemini" / "bin" / "agy"
                cli.parent.mkdir(parents=True, exist_ok=True)
                cli.write_text("#!%s\n%s" % (sys.executable, textwrap.dedent(source)),
                               encoding="utf-8")
                cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
            if on_path is not None:
                bin_dir = Path(home) / "ide-bin"
                bin_dir.mkdir()
                launcher = bin_dir / "agy"
                launcher.write_text("#!%s\n%s" % (sys.executable, textwrap.dedent(on_path)),
                                    encoding="utf-8")
                launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
                env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            return subprocess.run([sys.executable, str(SKILL / "agy_usage.py")], cwd=SKILL,
                                  env=env, capture_output=True, text=True, timeout=15)

    USAGE = r'''
import os, sys
assert sys.argv[1:3] == ["-p", "/usage"], sys.argv
assert os.environ.get("AGY_CLI_DISABLE_AUTO_UPDATE") == "1"
print("Gemini Models\tWeekly Limit Remaining\t88%\t2099-10-08T20:09:18Z")
print("Claude and GPT models\tWeekly Limit Remaining\t100%\t2099-10-08T20:09:18Z")
'''

    def test_prints_used_from_remaining_per_pool(self):
        result = self.run_agy(self.USAGE)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("plan: ?", result.stdout)
        lines = result.stdout.splitlines()
        self.assertTrue(any(l.startswith("gemini") and "12.0% used" in l and "window weekly" in l
                            for l in lines), result.stdout)
        self.assertTrue(any(l.startswith("cl+gpt") and "0.0% used" in l for l in lines), result.stdout)
        self.assertNotIn("5h", result.stdout)

    def test_fails_visibly_when_usage_is_not_parsed(self):
        result = self.run_agy('print("error: not signed in")\n')

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("usage call failed", result.stdout)
        self.assertNotIn("% used", result.stdout)

    def test_current_layout_login_is_found_despite_newer_unrelated_legacy_log(self):
        result = self.run_agy(self.USAGE, auth_logs={
            "antigravity": "URL: https://example/v1internal:loadCodeAssist\n",
            "antigravity-cli": "Starting CLI\n",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("12.0% used", result.stdout)

    def test_newer_signed_out_log_overrides_authenticated_other_layout(self):
        result = self.run_agy('raise AssertionError("must not start")\n', auth_logs={
            "antigravity-cli": "URL: https://example/v1internal:loadCodeAssist\n",
            "antigravity": "Authentication required\n",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not signed in", result.stdout)
        self.assertNotIn("usage call failed", result.stdout)

    def test_never_runs_the_ide_launcher_on_path(self):
        result = self.run_agy(None, on_path=self.USAGE)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "agy CLI not installed")

    def test_signed_out_agy_is_never_started(self):
        # a signed-out agy opens the Google sign-in page in a browser; the probe must not run it
        result = self.run_agy('import sys; open(sys.argv[0] + ".ran", "w").close(); print("x")\n',
                              signed_in=False)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not signed in", result.stdout)
        self.assertNotIn("% used", result.stdout)
        self.assertNotIn("usage call failed", result.stdout)

    def test_session_reads_model_from_the_run_log(self):
        import datetime
        for storage in ("antigravity-cli", "antigravity"):
            with self.subTest(storage=storage), tempfile.TemporaryDirectory() as home:
                base = Path(home) / ".gemini" / storage
                (base / "conversations").mkdir(parents=True)
                (base / "log").mkdir()
                started = datetime.datetime.now() - datetime.timedelta(minutes=2)
                log = base / "log" / ("cli-%s.log" % started.strftime("%Y%m%d_%H%M%S"))
                log.write_text('x selected model override to backend: label="Gemini 3.8 Flash (High)"\n',
                               encoding="utf-8")
                # a later run (e.g. the /usage probe) writes a log but no conversation
                later = base / "log" / ("cli-%s.log" % (datetime.datetime.now()
                                                         + datetime.timedelta(minutes=5)).strftime("%Y%m%d_%H%M%S"))
                later.write_text('x selected model override to backend: label="Gemini 3.1 Pro (Low)"\n',
                                 encoding="utf-8")
                (base / "conversations" / "c1.db").write_bytes(b"")
                env = os.environ.copy()
                env["HOME"] = home
                result = subprocess.run([sys.executable, str(SKILL / "session_info.py"), "agy"],
                                        cwd=SKILL, env=env, capture_output=True, text=True, timeout=15)
                self.assertIn("model   gemini-3.8-flash", result.stdout)
                self.assertIn("effort  high", result.stdout)


class ArtificialAnalysisTests(unittest.TestCase):
    def aa_rows(self, model, rows):
        sys.path.insert(0, str(SKILL))
        import cursorbench
        from unittest import mock
        with mock.patch.object(cursorbench, "published", return_value=rows):
            return cursorbench.aa_rows(model)

    def test_variant_without_cost_is_left_out_not_borrowed(self):
        rows = self.aa_rows("Gemini 3.8 Flash", [
            {"model": "Gemini 3.8 Flash", "effort": "High", "score": 40.9, "cost": 1.24},
            {"model": "Gemini 3.8 Flash", "effort": "Low", "score": 33.5, "cost": None},
            {"model": "Opus 5.5", "effort": "Low", "score": 57.6, "cost": 5.98},
        ])
        self.assertEqual(set(rows), {"high"})
        self.assertEqual(rows["high"][:2], (40.9, 1.24))
        self.assertEqual(rows["high"][3:], (0.0, 0.0, 0.0))

    def test_aa_rows_reads_speed_verbosity_latency(self):
        sys.path.insert(0, str(SKILL))
        import cursorbench
        rows = self.aa_rows("GPT-6.1 Sol", [
            {"model": "GPT-6.1 Sol", "effort": "Extra High", "score": 51.0, "cost": 0.39},
            {"model": "GPT-6.1 Sol", "effort": "High", "score": 50.237, "cost": 0.319,
             "speed": 50.854, "verbosity": 25376903, "latency": 46.5526},
        ])
        self.assertEqual(set(rows), {"high", "xhigh"})
        self.assertEqual(rows["high"][:2], (50.237, 0.319))
        self.assertEqual(rows["high"][3:], (50.854, 25376903.0, 46.5526))
        self.assertEqual(cursorbench._aa_speed(50.854), "50.9/s")
        self.assertEqual(cursorbench._aa_verbosity(25376903), "25M")
        self.assertEqual(cursorbench._aa_latency(46.5526), "46.6s")


class AAQualifiedMainTests(unittest.TestCase):
    def run_main(self, rows, argv, aa=None):
        sys.path.insert(0, str(SKILL))
        import cursorbench
        from unittest import mock
        import io, contextlib
        patches = [mock.patch.object(cursorbench, "published", side_effect=rows if isinstance(rows, Exception) else None,
                                     return_value=None if isinstance(rows, Exception) else rows),
                   mock.patch.object(sys, "argv", ["cursorbench.py", *argv])]
        if aa is not None:
            patches.append(mock.patch.object(cursorbench, "aa_rows", return_value=aa))
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            with contextlib.redirect_stdout(out):
                code = cursorbench.main()
        return code, out.getvalue()

    def test_aa_down_prints_bench_failed(self):
        code, out = self.run_main(RuntimeError("AA down"), ["agy=gemini-3.8-flash:high"])
        self.assertEqual(code, 1)
        self.assertIn("bench failed (AA down)", out)

    def test_aa_bench_line_prints_speed_verbosity_latency(self):
        rows = [{"model": "GPT-6.1 Sol", "effort": "High", "score": 50.237, "cost": 0.319}]
        aa = {"high": (50.237, 0.319, 0.0, 50.854, 25376903.0, 46.5526)}
        code, out = self.run_main(rows, ["codex=gpt-6.1-sol:high"], aa)
        self.assertEqual(code, 0)
        line = [ln for ln in out.splitlines() if ln.startswith("bench")][0]
        self.assertIn("GPT-6.1 Sol High  aa 50.2", line)
        self.assertIn("cost $0.32", line)
        self.assertIn("speed 50.9/s", line)
        self.assertIn("verbosity 25M", line)
        self.assertIn("latency 46.6s", line)
        self.assertIn("(AA)", line)
        self.assertIn("pick    codex  GPT-6.1 Sol High  aa 50.2", out)

    def test_unlisted_current_model_still_gets_a_pick(self):
        rows = [{"model": "Gemini 4 Argon", "effort": "High", "score": 50.4, "cost": 9.95}]
        code, out = self.run_main(rows, ["agy=gemini-3.8-flash:high"], {})
        self.assertIn("bench   agy  Gemini 3.8 Flash  high  not listed", out)
        self.assertIn("pick    agy  Gemini 4 Argon High  aa 50.4", out)


class CursorBenchNameTests(unittest.TestCase):
    def test_maps_cli_model_ids_to_leaderboard_names(self):
        sys.path.insert(0, str(SKILL))
        import cursorbench

        cases = {
            ("claude", "claude-opus-5-5"): "Opus 5.5",
            ("claude", "claude-fable-5-1"): "Fable 5.1",
            ("claude", "claude-sonnet-5"): "Sonnet 5",
            ("claude", "opus"): None,
            ("codex", "gpt-6-sol"): "GPT-6 Sol",
            ("codex", "gpt-6.1-sol"): "GPT-6.1 Sol",
            ("codex", "gpt-5.6-terra"): "GPT-5.6 Terra",
            ("grok", "grok-4.7"): "Grok 4.7",
            ("grok", "grok-4.7-build-fast"): None,
            ("muse", "muse-spark-1.3-contributor"): "Muse Spark 1.3",
            ("muse", "muse-spark-1.3"): "Muse Spark 1.3",
            ("agy", "gemini-3.8-flash"): "Gemini 3.8 Flash",
            ("agy", "gemini-3.1-pro"): "Gemini 3.1 Pro",
            ("agy", "claude-opus-4.6"): "Opus 4.6",
            ("agy", "gpt-oss-120b"): None,
        }
        for (cli, model), expected in cases.items():
            self.assertEqual(cursorbench.name(cli, model) or None, expected, (cli, model))

    def test_pick_searches_the_provider_for_45_on_aa(self):
        sys.path.insert(0, str(SKILL))
        import cursorbench

        def row(model, effort, score, cost):
            return {"model": model, "effort": effort, "score": score, "cost": cost}
        rows = [
            row("Opus 5.5", "High", 51.8, 3.46), row("Opus 5.5", "Medium", 48.2, 2.45),
            row("Sonnet 5.5", "High", 41.5, 1.64), row("Fable 5.2", "Low", 53.9, 3.10),
            row("Grok 4.7", "Extra High", 35.5, 7.77), row("Grok 4.7", "Low", 20.0, 0.50),
            row("Gemini 4 Carbon", "Medium", 58.3, 6.59), row("Gemini 4 Argon", "High", 50.4, 9.95),
            row("Gemini 3.8 Flash", "Medium", 30.1, 6.26), row("Opus 5.5", "None", 60.0, 0.10),
        ]
        # Claude reaches 45: best cp among >= 45 rows; Sonnet High is cheaper but below 45,
        # and an effort AA labels "None" is not a CLI effort
        self.assertEqual(cursorbench.pick(rows, "claude"), ("Opus 5.5 Medium", 48.2, 2.45, "cp"))
        # nothing from Grok reaches 45: its highest score, not its best cp
        self.assertEqual(cursorbench.pick(rows, "grok"), ("Grok 4.7 Extra High", 35.5, 7.77, "closest"))
        # an unavailable model is never picked, even with the best cp
        self.assertEqual(cursorbench.pick(rows, "agy")[0], "Gemini 4 Argon High")
        self.assertIsNone(cursorbench.pick(rows, "muse"))


class UsageBarTests(unittest.TestCase):
    def bar(self, percent):
        sys.path.insert(0, str(SKILL))
        import portable
        return portable.usage_bar(percent)

    def test_length_and_ends(self):
        self.assertEqual(self.bar(0), "░" * 20)
        self.assertEqual(self.bar(100), "█" * 20)
        self.assertEqual(len(self.bar(28.4)), 20)

    def test_eighths_split_percents_the_10_cell_bar_merged(self):
        # 10 cells rounded both of these to three full blocks.
        self.assertEqual(self.bar(28), "█████▋░░░░░░░░░░░░░░")
        self.assertEqual(self.bar(30), "██████░░░░░░░░░░░░░░")
        self.assertNotEqual(self.bar(28), self.bar(30))

    def test_small_percents_stay_visible(self):
        self.assertEqual(self.bar(1), "▎░░░░░░░░░░░░░░░░░░░")
        self.assertEqual(self.bar(2), "▍░░░░░░░░░░░░░░░░░░░")
        self.assertNotEqual(self.bar(1), self.bar(0))
        self.assertEqual(self.bar(0.1), "▏░░░░░░░░░░░░░░░░░░░")


class AdviceTests(unittest.TestCase):
    def advice(self, raw):
        import datetime
        import importlib.util
        spec = importlib.util.spec_from_file_location("ai_usage_html", SKILL / "html_report.py")
        html_report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(html_report)
        return html_report.advice(textwrap.dedent(raw), datetime.datetime(2026, 10, 23, 10, 0))

    def test_tightest_window_and_week_warning(self):
        lines = self.advice("""\
            ### CLAUDE
            plan: pro
            5h      16.0% used  resets Oct 23 at 1:49pm  bar x
            week    85.0% used  resets Oct 26 at 4:59pm  bar x
            ### GROK
            plan: SuperGrok
            week       <1% used  window weekly  resets 10-30 01:11 (6d14h)  bar x
            ### GEMINI
            plan: ?
            gemini  30.0% used  window weekly  pool gemini  resets 10-30 (6d14h)  bar x
            cl+gpt  20.0% used  window weekly  pool x  resets 10-30 (6d14h)  bar x
            """)
        self.assertEqual(lines, [
            "> **Warning:** Claude week is 85% used; resets in 3d6h.",
            "> **→ Use Grok right now:** 100% left in its tightest window."])

    def test_near_tie_goes_to_higher_aa_score(self):
        raw = """            ### CLAUDE
            plan: pro
            week    10.0% used  resets Oct 26 at 4:59pm  bar x
            ### CHATGPT
            plan: plus
            outer    5.0% used  window 168h  resets 10-30 01:11 (6d14h)  bar x
            ### CURSORBENCH
            bench   claude  Opus 5.5 High  aa 51.8  cost $3.46  cp 15.0  (AA)
            bench   codex  GPT-6.1 Sol High  {}
            """
        self.assertIn("Use Claude", self.advice(raw.format("aa 40.0  cost $1.00  cp 40.0  (AA)"))[-1])
        self.assertIn("Use ChatGPT", self.advice(raw.format("aa 55.0  cost $0.32  cp 171.9  (AA)"))[-1])

    def test_free_plan_is_never_picked(self):
        lines = self.advice("""\
            ### CHATGPT
            plan: plus
            outer   40.0% used  window 168h  resets 10-30 01:11 (6d14h)  bar x
            ### GROK
            plan: Free
            week       <1% used  window weekly  resets 10-30 01:11 (6d14h)  bar x
            ### GEMINI
            plan: ?
            gemini   0.0% used  window weekly  pool g  resets 10-30 (6d14h)  bar x
            """)
        self.assertEqual(lines, ["> **→ Use ChatGPT right now:** 60% left in its tightest window."])

    def test_no_usage_block_no_advice(self):
        self.assertEqual(self.advice("### CLAUDE\nnot installed\n"), [])

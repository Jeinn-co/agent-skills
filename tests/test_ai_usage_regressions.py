import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "ai-usage"


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

    def test_claude_does_not_report_fast_mode_as_extra_usage(self):
        result = self.run_probe(
            "claude_usage.py",
            "claude",
            r'''
import json
import sys

if sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({"subscriptionType": "pro"}))
else:
    print(json.dumps({
        "result": (
            "Current session: 25% used · resets Sep 12 at 3:40am\n"
            "Current week (all models): 41% used · resets Sep 14 at 5pm"
        ),
        "fast_mode_disabled_reason": "sdk_opt_in_required",
    }))
''',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("extra usage", result.stdout.lower())
        self.assertIn("25.0% used", result.stdout)
        self.assertIn("bar █████░░░░░░░░░░░░░░░", result.stdout)

    def test_claude_prints_session_when_reset_clause_is_omitted(self):
        result = self.run_probe(
            "claude_usage.py",
            "claude",
            r'''
import json
import sys

if sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({"subscriptionType": "pro"}))
else:
    print(json.dumps({
        "result": (
            "Current session: 0% used\n"
            "Current week (all models): 59% used · resets Sep 21 at 4:59pm"
        ),
    }))
''',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        session_line = [
            line for line in result.stdout.splitlines() if line.startswith("5h")
        ][0]
        week_line = [
            line for line in result.stdout.splitlines() if line.startswith("week")
        ][0]
        self.assertIn("0.0% used", session_line)
        self.assertNotIn("resets", session_line)
        self.assertIn("59.0% used", week_line)
        self.assertIn("resets Sep 21 at 4:59pm", week_line)

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

    def run_agy(self, source, on_path=None, signed_in=True):
        with tempfile.TemporaryDirectory() as home:
            env = os.environ.copy()
            env["HOME"] = home
            logs = Path(home) / ".gemini" / "antigravity-cli" / "log"
            logs.mkdir(parents=True)
            (logs / "cli-20260101_000000.log").write_text(
                "URL: https://example/v1internal:loadCodeAssist\n" if signed_in
                else "Authentication required. Please visit the URL to log in\n",
                encoding="utf-8")
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
        with tempfile.TemporaryDirectory() as home:
            base = Path(home) / ".gemini" / "antigravity-cli"
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
    def test_variant_without_cost_is_left_out_not_borrowed(self):
        sys.path.insert(0, str(SKILL))
        import cursorbench
        from unittest import mock

        def variant(slug, release, level, score, cost):
            data = {"id": "0f0f0f0f-0000-0000-0000-000000000000", "slug": slug,
                    "release": {"slug": release}, "effort": {"level": level},
                    "intelligenceIndex": score}
            if cost is not None:
                data["intelligenceIndexCostPerTask"] = {"cost": {"total": cost}}
            return json.dumps(data, separators=(",", ":"))

        page = "<script>" + ",".join([
            variant("gemini-3-8-flash", "gemini-3-8-flash", 40, 40.9, 1.24),
            variant("gemini-3-8-flash-low", "gemini-3-8-flash", 20, 33.5, None),
            variant("claude-opus-5-5", "claude-opus-5-5", 60, 57.6, 5.98),
        ]) + "</script>"

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return page.encode("utf-8")

        with mock.patch.object(cursorbench.urllib.request, "urlopen", return_value=Response()):
            rows = cursorbench.aa_rows("gemini-3.8-flash")
        self.assertEqual(set(rows), {"high"})
        self.assertEqual(rows["high"][:2], (40.9, 1.24))
        self.assertEqual(rows["high"][3:], (0.0, 0.0, 0.0))

    def test_aa_rows_reads_speed_verbosity_latency(self):
        sys.path.insert(0, str(SKILL))
        import cursorbench
        from unittest import mock

        data = {
            "id": "0f0f0f0f-0000-0000-0000-000000000000",
            "slug": "gpt-6-1-sol-high",
            "release": {"slug": "gpt-6-1-sol"},
            "effort": {"level": 40},
            "intelligenceIndex": 50.237,
            "intelligenceIndexCostPerTask": {"cost": {"total": 0.319}},
            "intelligenceIndexOutputTokensPerTask": {"output": 13191.8},
            "medianOutputSpeed": 50.854,
            "canonicalIntelligenceIndexTokenCount": {"output": 25376903},
            "timeToFirstAnswerToken": {"total": 46.5526},
        }
        page = "<script>" + json.dumps(data, separators=(",", ":")) + "</script>"

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return page.encode("utf-8")

        with mock.patch.object(cursorbench.urllib.request, "urlopen", return_value=Response()):
            rows = cursorbench.aa_rows("gpt-6.1-sol")
        self.assertEqual(rows["high"][:2], (50.237, 0.319))
        self.assertEqual(rows["high"][3:], (50.854, 25376903.0, 46.5526))
        self.assertEqual(cursorbench._aa_speed(50.854), "50.9/s")
        self.assertEqual(cursorbench._aa_verbosity(25376903), "25M")
        self.assertEqual(cursorbench._aa_latency(46.5526), "46.6s")


class AAExtraPickTests(unittest.TestCase):
    def test_extra_qualifies_only_when_it_reaches_target(self):
        sys.path.insert(0, str(SKILL))
        import cursorbench
        from unittest import mock

        boards = {"gemini-4-argon": {"high": (52.6, 1.99, 0.0)},
                  "gpt-6.1-sol": {"high": (50.237, 0.319, 0.0)}}
        with mock.patch.object(cursorbench, "aa_rows", side_effect=lambda slug: boards.get(slug, {})):
            hit = cursorbench.extra_pick("agy")
            self.assertEqual(hit[:4], ("Gemini 4 Argon High", 52.6, 1.99, "cp"))
            hit = cursorbench.extra_pick("codex")
            self.assertEqual(hit[:4], ("GPT-6.1 Sol High", 50.237, 0.319, "cp"))
            self.assertIsNone(cursorbench.extra_pick("grok"))
        boards = {"gemini-4-argon": {"high": (45.0, 1.99, 0.0)},
                  "gpt-6.1-sol": {"high": (45.0, 0.32, 0.0)}}
        with mock.patch.object(cursorbench, "aa_rows", side_effect=lambda slug: boards.get(slug, {})):
            self.assertIsNone(cursorbench.extra_pick("agy"))
            self.assertIsNone(cursorbench.extra_pick("codex"))


class AAExtraFailureTests(unittest.TestCase):
    def test_pick_table_survives_a_failing_extra(self):
        sys.path.insert(0, str(SKILL))
        import cursorbench
        from unittest import mock

        board = {"Gemini 3.8 Flash High": ["39.6%", "$4.70", "162,565", "324"]}
        with mock.patch.object(cursorbench, "rows", return_value=board), \
                mock.patch.object(cursorbench, "aa_rows", side_effect=RuntimeError("AA down")), \
                mock.patch.object(sys, "argv", ["cursorbench.py", "agy=gemini-3.8-flash:high"]):
            import io, contextlib
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cursorbench.main()
        self.assertEqual(code, 0)
        self.assertIn("pick    agy  Gemini 3.8 Flash High  score 39.6%", out.getvalue())

    def test_aa_bench_line_prints_speed_verbosity_latency(self):
        sys.path.insert(0, str(SKILL))
        import cursorbench
        from unittest import mock
        import io, contextlib

        board = {}
        aa = {"high": (50.237, 0.319, 13191.8, 50.854, 25376903.0, 46.5526)}
        with mock.patch.object(cursorbench, "rows", return_value=board), \
                mock.patch.object(cursorbench, "aa_rows", return_value=aa), \
                mock.patch.object(sys, "argv", ["cursorbench.py", "codex=gpt-6.1-sol:high"]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cursorbench.main()
        self.assertEqual(code, 0)
        line = [ln for ln in out.getvalue().splitlines() if ln.startswith("bench")][0]
        self.assertIn("aa 50", line)
        self.assertIn("cost $0.32", line)
        self.assertIn("speed 50.9/s", line)
        self.assertIn("verbosity 25M", line)
        self.assertIn("latency 46.6s", line)
        self.assertIn("(AA)", line)
        self.assertNotIn("output tokens", line)


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

    def test_pick_searches_the_provider_for_50_percent(self):
        sys.path.insert(0, str(SKILL))
        import cursorbench

        board = {
            "Opus 5.5 Max": ["57.8%", "$13.43"],
            "Opus 5.5 High": ["56.0%", "$3.97"],
            "Opus 5.5 Low": ["43.7%", "$1.17"],
            "Fable 5.1 Max": ["51.8%", "$17.28"],
            "Grok 4.7 Extra High": ["46.3%", "$6.01"],
            "Grok 4.7 Medium": ["41.6%", "$3.49"],
            "Grok 4.6 High": ["40.4%", "$5.20"],
            "Muse Spark 1.3 Max": ["41.6%", "$2.64"],
            "Muse Spark 1.3 Minimal": ["24.3%", "$0.56"],
            "GPT-5.6 Sol Max": ["41.7%", "$8.23"],
        }
        # Claude reaches 50%: best cp among >= 50% rows of any Claude model; Low is out
        self.assertEqual(cursorbench.pick(board, "claude", "Opus 5.5")[0], "Opus 5.5 High")
        self.assertEqual(cursorbench.pick(board, "claude", "Opus 5.5")[3], "cp")
        # nothing from Grok reaches 50%: its highest score, not its best cp, and no floor
        self.assertEqual(cursorbench.pick(board, "grok", "Grok 4.7")[:2], ("Grok 4.7 Extra High", 46.3))
        self.assertEqual(cursorbench.pick(board, "grok", "Grok 4.7")[3], "closest")
        self.assertEqual(cursorbench.pick(board, "muse", "Muse Spark 1.3")[0], "Muse Spark 1.3 Max")
        # an unlisted current model gets no pick, even though older GPT rows exist
        self.assertIs(cursorbench.pick(board, "codex", "GPT-6 Sol"), False)


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

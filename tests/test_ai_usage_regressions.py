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
        self.assertNotIn("percent omitted", result.stdout)

    def test_grok_omits_percent_when_field_absent(self):
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
        self.assertIn("percent omitted", result.stdout)
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
        self.assertNotIn("percent omitted", result.stdout)

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
        self.assertIn("plan: ?", result.stdout)
        self.assertNotIn("27681527378179523", result.stdout)
        lines = result.stdout.splitlines()
        self.assertTrue(any(l.startswith("5h") and "5.0% used" in l for l in lines))
        self.assertTrue(any(l.startswith("week") and "1.0% used" in l for l in lines))

    def test_muse_fails_when_no_usage_observed(self):
        result = self.run_probe("muse_usage.py", "muse", self._muse_serve_cli(None))

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("usage call failed (no usage observed", result.stdout)
        self.assertNotIn("0.0% used", result.stdout)


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
            ("codex", "gpt-5.6-terra"): "GPT-5.6 Terra",
            ("grok", "grok-4.7"): "Grok 4.7",
            ("grok", "grok-4.7-build-fast"): None,
            ("muse", "muse-spark-1.3-contributor"): "Muse Spark 1.3",
            ("muse", "muse-spark-1.3"): "Muse Spark 1.3",
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

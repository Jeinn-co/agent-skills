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

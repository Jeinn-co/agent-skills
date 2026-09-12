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


if __name__ == "__main__":
    unittest.main()

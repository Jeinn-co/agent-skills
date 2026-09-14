#!/usr/bin/env python3
"""Claude usage via `claude -p --output-format json "/usage"`.

Print mode routes the built-in /usage slash command, so this needs no credentials and
makes no model call. `--output-format json` puts the answer in a stable `result` field
instead of raw stdout, which keeps stray warnings out of the parse.

There is no structured local source. Checked 2026-09-12: `claude mcp serve` exposes
tools only; the binary's `account/*` strings are web API paths. The only deeper source
is `/api/oauth/usage` with the OAuth token from ~/.claude/.credentials.json, which the
sandbox blocks as credential access -- and `-p` is already live, so it buys nothing.

The two usage lines are free text, so they are regex-parsed. If Anthropic rewords them
this is the one thing in /uu that breaks; the raw line is printed as a fallback.
"""
import subprocess, json, re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

if portable.argv("claude") is None:
    print("claude CLI not installed")
    sys.exit(0)

def run(*args):
    args = portable.argv("claude", *args)
    try:
        return subprocess.run(args, capture_output=True, timeout=90,
                              stdin=subprocess.DEVNULL, **portable.text_kwargs()).stdout
    except Exception:
        return ""

# plan name comes from a properly structured command
plan = None
try:
    plan = (json.loads(run("auth", "status") or "{}")
            .get("subscriptionType"))
except Exception:
    pass
print("plan: %s" % (plan or "unknown"))

raw = run("-p", "--output-format", "json", "/usage")
env = {}
try:
    env = json.loads(raw)
    text = env.get("result", "")
except Exception:
    text = raw
if not text:
    print("usage call failed")
    sys.exit(1)

# "Current session: 25% used · resets Sep 12 at 3:40am (Asia/Taipei)"
pat = re.compile(r"Current (session|week[^:]*):\s*(\d+)%\s*used\s*·\s*resets\s+([^(\n]+)")
found = False
for m in pat.finditer(text):
    label = "5h" if m.group(1) == "session" else "week"
    print("%-6s %5.1f%% used  resets %s" % (label, float(m.group(2)), m.group(3).strip()))
    found = True
if not found:
    for line in text.splitlines():
        if "%" in line and "reset" in line.lower():
            print(line.strip())
            found = True
if not found:
    print("could not parse; raw first line: %s" % text.splitlines()[0][:120])

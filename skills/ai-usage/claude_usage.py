#!/usr/bin/env python3
"""Claude usage via `claude -p --output-format json "/usage"`.

Print mode routes the built-in /usage slash command using CLI-managed auth and
makes no model call. `--output-format json` puts the answer in a stable `result` field
instead of raw stdout, which keeps stray warnings out of the parse.

Banked resets are read separately through the read-only OAuth usage endpoint.
A reset lookup failure never replaces valid quota windows or refreshes credentials.

The two usage lines are free text, so they are regex-parsed. If Anthropic rewords them
this is the one thing in /uu that breaks; the raw line is printed as a fallback.
"""
import subprocess, json, re, time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable
from claude_browser import current_report
from limit_resets import claude_report

portable.stdout_utf8()
deadline = time.monotonic() + portable.CALL_TIMEOUT

browser = current_report()
if browser is not None:
    print("\n".join(browser))
    sys.exit(0)

if portable.argv("claude") is None:
    print("claude CLI not installed")
    sys.exit(0)

def run(*args, deadline=deadline):
    args = portable.argv("claude", *args)
    try:
        return subprocess.run(args, capture_output=True, timeout=portable.timeout_left(deadline, portable.CALL_TIMEOUT),
                              stdin=subprocess.DEVNULL, **portable.text_kwargs()).stdout
    except Exception:
        return ""

# plan name comes from a properly structured command
plan = None
auth = {}
try:
    auth = json.loads(run("auth", "status") or "{}")
    plan = auth.get("subscriptionType")
except Exception:
    auth = {}
# --strict-mcp-config: /usage needs no MCP server, and starting them took ~2.5s of ~4.4s.
raw = run("-p", "--output-format", "json", "--strict-mcp-config", "/usage")
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
# Claude omits the reset clause when a window is 0% used:
# "Current session: 0% used"
pat = re.compile(
    r"Current (session|week[^:]*):\s*(\d+)%\s*used(?:\s*·\s*resets\s+([^(\n]+))?"
)
# Preserve the original /usage call so the CLI can refresh auth before we reject it.
if auth.get("loggedIn") is False and not pat.search(text):
    print("plan: unavailable")
    print("Claude CLI is not signed in; /usage could not obtain subscription usage.")
    print("Use Sign in to Claude in the report, or run claude auth login in a terminal.")
    sys.exit(1)
print("plan: %s" % (plan or "unknown"))
found = False
for m in pat.finditer(text):
    label = "5h" if m.group(1) == "session" else "week"
    used = float(m.group(2))
    reset = (m.group(3) or "").strip()
    bar = portable.format_bar(used)
    if reset:
        print("%-6s %5.1f%% used  resets %s  %s" % (label, used, reset, bar))
    else:
        print("%-6s %5.1f%% used  %s" % (label, used, bar))
    found = True
if not found:
    for line in text.splitlines():
        if "%" in line and "reset" in line.lower():
            print(line.strip())
            found = True
if not found:
    print("could not parse; raw first line: %s" % text.splitlines()[0][:120])

if found:
    # Reserve exit time only from optional details, never from the quota call.
    reset_deadline = deadline - min(.25, portable.CALL_TIMEOUT * .05)
    if time.monotonic() >= reset_deadline:
        print("Limit resets: unavailable (timed out)")
    else:
        version = run("--version", deadline=reset_deadline).strip().split()
        for line in claude_report(version[0] if version else None, deadline=reset_deadline):
            print(line)

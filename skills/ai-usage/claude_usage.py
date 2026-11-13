#!/usr/bin/env python3
"""Claude usage: OAuth usage endpoint first, `claude -p "/usage"` text as fallback.

One read-only GET with the CLI's existing login (credentials file, macOS keychain or
CLAUDE_CODE_OAUTH_TOKEN) returns both quota windows and banked resets. It never
refreshes or prints tokens. Claude Code 2.1.319 on Windows prints a cost summary for
`/usage`, so its free text is only the fallback: no login, expired token (only the CLI
refreshes it), HTTP or invalid data. The fallback lines are regex-parsed; if Anthropic
rewords them the raw line is printed.
"""
import subprocess, json, re, time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable
from claude_browser import current_report
import limit_resets

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

version = run("--version").strip().split()
version = version[0] if version else None
def oauth_report():
    """Print the OAuth report and exit 0; raises when the read fails."""
    oauth, data = limit_resets.fetch_claude(version, deadline=deadline)
    rows = limit_resets.quota_rows(data)
    print("plan: %s" % (oauth.get("subscriptionType") or "unknown"))
    print("\n".join(rows))
    print("\n".join(limit_resets.claude_lines(data.get("cedar_ember"))))
    sys.exit(0)

try:
    oauth_report()
except Exception as error:
    oauth_error = error

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
# Running the CLI renews an expired token, so the full OAuth report may work now.
if limit_resets.auth_expired(oauth_error):
    try:
        oauth_report()
    except Exception as error:
        oauth_error = error
reset_failure = limit_resets.failure(oauth_error)
env = {}
try:
    env = json.loads(raw)
    text = env.get("result", "")
except Exception:
    text = raw
if not text:
    print("usage call failed (OAuth: %s; CLI /usage returned nothing in time)" % limit_resets.reason(oauth_error))
    print("Press Refresh or rerun the ai-usage skill. If it repeats, run claude once in a terminal so it renews its login.")
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
    print(reset_failure)

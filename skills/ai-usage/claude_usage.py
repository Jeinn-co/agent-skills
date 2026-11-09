#!/usr/bin/env python3
"""Read live Claude quota using the CLI's existing local OAuth login.

shortcut: requires file-based Claude credentials, add keychain support when needed.
The token stays in memory and is sent only to Anthropic's usage endpoint.
"""
import datetime
import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

if portable.argv("claude") is None:
    print("claude CLI not installed")
    sys.exit(0)

config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
try:
    credentials = json.loads((config_dir / ".credentials.json").read_text(encoding="utf-8"))
    oauth = credentials["claudeAiOauth"]
    token = oauth["accessToken"]
    if not isinstance(token, str) or not token:
        raise ValueError("missing access token")
except (OSError, ValueError, KeyError, TypeError):
    print("usage unavailable: Claude OAuth login not found or invalid")
    sys.exit(1)

print("plan: %s" % (oauth.get("subscriptionType") or "unknown"))
request = urllib.request.Request(
    "https://api.anthropic.com/api/oauth/usage",
    headers={"Authorization": "Bearer " + token,
             "anthropic-beta": "oauth-2025-04-20",
             "User-Agent": "ai-usage/" + portable.VERSION},
)
try:
    with urllib.request.urlopen(request, timeout=portable.CALL_TIMEOUT) as response:
        usage = json.load(response)
except urllib.error.HTTPError as error:
    print("usage request failed: HTTP %s" % error.code)
    sys.exit(1)
except (OSError, ValueError):
    print("usage request failed: network error or invalid response")
    sys.exit(1)

rows = []
try:
    for key, label in (("five_hour", "5h"), ("seven_day", "week")):
        window = usage.get(key)
        if window is None:
            continue
        percent = window["utilization"]
        if isinstance(percent, bool) or not isinstance(percent, (int, float)):
            raise ValueError("invalid percentage")
        if not math.isfinite(percent) or not 0 <= percent <= 100:
            raise ValueError("invalid percentage")
        reset = window.get("resets_at")
        reset_text = ""
        if reset:
            when = datetime.datetime.fromisoformat(reset.replace("Z", "+00:00"))
            if when.tzinfo is None:
                raise ValueError("reset timezone missing")
            reset_text = "  resets " + when.astimezone().strftime("%b %d at %I:%M%p")
        rows.append("%-6s %5.1f%% used%s  %s" % (
            label, percent, reset_text, portable.format_bar(percent)))
    if not rows:
        raise ValueError("no quota windows")
except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
    print("usage request failed: invalid quota response")
    sys.exit(1)

print("\n".join(rows))

"""Read-only banked resets, separate from quota windows and paid credits."""
import datetime as dt
import json
import math
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import portable


def expiry_time(value):
    if isinstance(value, bool):
        raise ValueError("invalid expiry")
    when = (dt.datetime.fromtimestamp(value, dt.timezone.utc)
            if isinstance(value, (int, float)) else
            dt.datetime.fromisoformat(value.replace("Z", "+00:00")))
    if when.tzinfo is None:
        raise ValueError("expiry needs a timezone")
    return when


def expiry(value, now):
    if value is None:
        return "expiry not provided"
    try:
        when = expiry_time(value)
        seconds = (when - now).total_seconds()
        minutes = max(0, int(seconds // 60))
        parts = [(minutes // 1440, "day"), (minutes % 1440 // 60, "hour"),
                 (minutes % 60, "minute")]
        # Long waits need days and hours; minutes matter for the final day.
        duration = " ".join("%d %s%s" % (n, unit, "s" if n != 1 else "")
                            for n, unit in (parts[:2] if minutes >= 1440 else parts) if n)
        left = "expired" if seconds <= 0 else (duration or "less than a minute") + " left"
        local = when.astimezone(portable.report_timezone())
        return "expires %s · %s" % (local.strftime("%Y-%m-%d %H:%M"), left)
    except (ValueError, TypeError, AttributeError, OverflowError, OSError):
        return "expiry unavailable (invalid timestamp)"


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def reset_note(prefix, value, now):
    note = prefix + expiry(value, now)
    lines = [note]
    if os.environ.get("AI_USAGE_METADATA") == "1" and value is not None:
        try:
            # Keep the exact instant separate from the deliberately compact display text.
            stamp = int(expiry_time(value).timestamp() * 1000)
            lines.append("reset-expiry " + json.dumps({"note": note, "expiresAt": stamp}))
        except (ValueError, TypeError, AttributeError, OverflowError, OSError):
            pass
    return lines


def codex_lines(data, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(data, dict) or not integer(data.get("availableCount")):
        return ["Usage limit resets: unavailable (CLI returned no valid count)"]
    count = data["availableCount"]
    lines = ["Usage limit resets: %d available" % count]
    rows = data.get("credits")
    if not isinstance(rows, list):
        if count:
            lines.append("Reset details: unavailable (count only)")
        return lines
    available = [r for r in rows if isinstance(r, dict) and r.get("status") == "available"]
    for i, row in enumerate(available, 1):
        lines.extend(reset_note("Reset %d: " % i, row.get("expiresAt"), now))
    if len(available) < count:
        lines.append("Reset details: %d of %d returned" % (len(available), count))
    return lines


def claude_lines(data, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if (not isinstance(data, dict) or not isinstance(data.get("eligible"), bool)
            or not isinstance(data.get("grants"), list)):
        return ["Limit resets: unavailable (no valid grants returned)"]
    reason = data.get("ineligible_reason")
    if reason not in (None, "no_grant"):
        return ["Limit resets: unavailable (API eligibility: %s)" % reason]
    rows = data["grants"]
    if any(not isinstance(r, dict) or not integer(r.get("resets_left")) for r in rows):
        return ["Limit resets: unavailable (invalid grant count)"]
    active = []
    for row in rows:
        try:
            bounds = [dt.datetime.fromisoformat(row[key].replace("Z", "+00:00"))
                      if row.get(key) is not None else None for key in ("starts_at", "ends_at")]
            if any(bound is not None and bound.tzinfo is None for bound in bounds):
                raise ValueError()
            if (bounds[0] is None or bounds[0] <= now) and (bounds[1] is None or bounds[1] > now):
                active.append(row)
        except (ValueError, TypeError, AttributeError):
            return ["Limit resets: unavailable (invalid grant dates)"]
    rows = active
    lines = ["Limit resets: %d available" % sum(r["resets_left"] for r in rows)]
    for row in rows:
        if row["resets_left"]:
            label, clears = row.get("label"), row.get("clears")
            fable_only = (isinstance(label, str) and re.search(r"\bfable\b", label, re.I)
                          and isinstance(clears, list) and "seven_day_overage_included" in clears
                          and "seven_day" not in clears)
            lines.extend(reset_note("Reset (%d left%s%s): " %
                         (row["resets_left"], "; Fable only" if fable_only else "",
                          "; paused" if row.get("paused") else ""),
                         row.get("ends_at"), now))
    return lines


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the CLI bearer to a redirect destination.


def fetch_claude(version, deadline=None):
    """One GET with existing CLI auth: quota windows plus banked resets.

    Never refreshes, persists or prints tokens. Returns (oauth login, usage JSON).
    """
    deadline = deadline if deadline is not None else time.monotonic() + 8
    portable.timeout_left(deadline, 8)
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("CLI version unavailable")
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    oauth = {"accessToken": token}
    if not token:
        config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
        path = config / ".credentials.json"
        if sys.platform == "darwin" and "CLAUDE_CONFIG_DIR" not in os.environ:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                capture_output=True, text=True, timeout=portable.timeout_left(deadline, 3))
            if result.returncode:
                raise ValueError("existing CLI credentials unavailable")
            credentials = json.loads(result.stdout)
        elif path.is_file():
            credentials = json.loads(path.read_text(encoding="utf-8"))
        else:
            raise ValueError("existing CLI credentials unavailable")
        oauth = credentials.get("claudeAiOauth", {})
        token = oauth.get("accessToken")
    if not isinstance(token, str) or not token:
        raise ValueError("existing CLI OAuth token unavailable")
    request = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage?cedar_ember=1&skip_spend=1",
        headers={"Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20",
                 "User-Agent": "claude-cli/%s (external, cli)" % version,
                 "x-app": "cli"}, method="GET")
    with urllib.request.build_opener(NoRedirect).open(request, timeout=portable.timeout_left(deadline, 5)) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise ValueError("invalid usage response")
    return oauth, data


# Hidden for now: the user does not track per-model caps; True brings back the row and its reset box.
SHOW_MODEL_CAPS = False


def quota_rows(data):
    """`five_hour` / `seven_day` / per-model weekly caps as probe lines; raises ValueError rather than guess 0%."""
    rows = []
    try:
        windows = [(label, data.get(key), "") for key, label in (("five_hour", "5h"), ("seven_day", "week"))]
        # Per-model weekly caps (e.g. Fable) only exist in `limits`; absent on plans without one.
        for limit in data.get("limits") or [] if SHOW_MODEL_CAPS else []:
            if limit.get("kind") == "weekly_scoped":
                name = ((limit.get("scope") or {}).get("model") or {}).get("display_name")
                if name:
                    windows.append(("".join(name.split()).lower(),
                                    {"utilization": limit["percent"], "resets_at": limit.get("resets_at")},
                                    "  window weekly"))
        for label, window, period in windows:
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
                when = dt.datetime.fromisoformat(reset.replace("Z", "+00:00"))
                if when.tzinfo is None:
                    raise ValueError("reset timezone missing")
                local = when.astimezone(portable.report_timezone())
                reset_text = "  resets " + local.strftime("%b %d at %I:%M%p")
            rows.append("%-6s %5.1f%% used%s%s  %s" % (
                label, percent, period, reset_text, portable.format_bar(percent)))
    except (AttributeError, KeyError, TypeError, OverflowError) as error:
        raise ValueError("invalid quota response") from error
    if not rows:
        raise ValueError("no quota windows")
    return rows


def failure(error):
    """A non-sensitive reason line; exception text can contain auth data."""
    if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
        return "Limit resets: unavailable (timed out)"
    if isinstance(error, urllib.error.HTTPError):
        return "Limit resets: unavailable (HTTP %d)" % error.code
    return "Limit resets: unavailable (CLI auth or read-only API failed)"


def read_claude(version, deadline=None):
    return claude_lines(fetch_claude(version, deadline)[1].get("cedar_ember"))


def claude_report(version, deadline=None):
    try:
        return read_claude(version, deadline=deadline)
    except Exception as error:
        return [failure(error)]

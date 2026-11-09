"""Read-only banked resets, separate from quota windows and paid credits."""
import datetime as dt
import json
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
            lines.extend(reset_note("Reset (%d left%s): " %
                         (row["resets_left"], "; paused" if row.get("paused") else ""),
                         row.get("ends_at"), now))
    return lines


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the CLI bearer to a redirect destination.


def read_claude(version, deadline=None):
    """Use existing CLI auth, without refreshing, persisting or printing tokens."""
    deadline = deadline if deadline is not None else time.monotonic() + 8
    portable.timeout_left(deadline, 8)
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("CLI version unavailable")
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
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
        token = credentials.get("claudeAiOauth", {}).get("accessToken")
    if not isinstance(token, str) or not token:
        raise ValueError("existing CLI OAuth token unavailable")
    request = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage?cedar_ember=1&skip_spend=1",
        headers={"Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20",
                 "User-Agent": "claude-cli/%s (external, cli)" % version,
                 "x-app": "cli"}, method="GET")
    with urllib.request.build_opener(NoRedirect).open(request, timeout=portable.timeout_left(deadline, 5)) as response:
        return claude_lines(json.load(response).get("cedar_ember"))


def claude_report(version, deadline=None):
    try:
        return read_claude(version, deadline=deadline)
    except (TimeoutError, subprocess.TimeoutExpired):
        return ["Limit resets: unavailable (timed out)"]
    except urllib.error.HTTPError as error:
        return ["Limit resets: unavailable (HTTP %d)" % error.code]
    except Exception:
        # Exception text can contain auth data; report only a non-sensitive status.
        return ["Limit resets: unavailable (CLI auth or read-only API failed)"]

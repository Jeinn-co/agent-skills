"""Optional Claude web observations imported by an agent's connected browser."""
import datetime as dt
import json
import os
import re
from pathlib import Path
import sys
import tempfile

import portable
import limit_resets
from limit_resets import codex_lines, integer

SNAPSHOT = Path.home() / ".cache/ai-usage/claude-browser.json"
MAX_AGE = 300
URLS = {"https://claude.ai/new#settings/usage", "https://claude.ai/settings/usage"}


def timestamp(value):
    when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return when


def report(data, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(data, dict) or data.get("sourceUrl") not in URLS:
        raise ValueError("Claude Usage page required")
    observed = timestamp(data["observedAt"])
    age = (now - observed).total_seconds()
    if age < -30 or age > MAX_AGE:
        raise ValueError("browser observation must be fresh")
    plan = data.get("plan")
    if plan not in ("free", "pro", "max", "team", "enterprise"):
        raise ValueError("visible plan required")
    windows = data.get("windows")
    if not isinstance(windows, dict) or not windows or not set(windows) <= {"5h", "week"}:
        raise ValueError("visible usage windows required")
    lines = ["plan: " + plan]
    for label in ("5h", "week"):
        if label not in windows:
            continue
        window = windows[label]
        used = window["usedPercent"]
        if isinstance(used, bool) or not isinstance(used, (float, int)) or not 0 <= used <= 100:
            raise ValueError("invalid usage percent")
        reset = ""
        if window.get("resetsAt") is not None:
            when = timestamp(window["resetsAt"]).astimezone(portable.report_timezone())
            reset = "  resets %s" % when.strftime("%b %d at %I:%M%p").lower()
        elif used:
            raise ValueError("reset time required for used window")
        lines.append("%-6s %5.1f%% used%s  %s" % (label, used, reset, portable.format_bar(used)))
    resets = data.get("resetCredits")
    if resets is None:
        lines.append("Limit resets: unavailable (not shown in browser)")
    else:
        if not isinstance(resets, dict) or not integer(resets.get("availableCount")):
            raise ValueError("invalid browser reset count")
        details = resets.get("credits")
        if details is not None and not isinstance(details, list):
            raise ValueError("browser reset details must be an array")
        for row in details or []:
            if not isinstance(row, dict) or row.get("status") != "available":
                raise ValueError("invalid browser reset details")
            value = row.get("expiresAt")
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (str, float, int)):
                    raise ValueError("invalid browser reset expiry")
                timestamp(value) if isinstance(value, str) else dt.datetime.fromtimestamp(value, dt.timezone.utc)
            if row.get("label") is not None and not isinstance(row["label"], str):
                raise ValueError("invalid browser reset label")
        fable = [r for r in details or [] if re.search(r"\bfable\b", r.get("label") or "", re.I)]
        if fable and not limit_resets.SHOW_MODEL_CAPS:
            # Same as the CLI path: a Fable-only reset belongs to the hidden per-model cap.
            resets = {"availableCount": max(0, resets["availableCount"] - len(fable)),
                      "credits": [r for r in details if r not in fable]}
        lines.extend(line.replace("Usage limit resets:", "Limit resets:")
                     for line in codex_lines(resets, now))
    name = data.get("browserName", "Browser")
    if name not in ("Browser", "Chrome", "Chromium", "Edge", "Firefox", "Safari"):
        name = "Browser"
    lines.append("Source: %s · checked %s · rerun the ai-usage skill to update" %
                 (name, observed.astimezone(portable.report_timezone()).strftime("%Y-%m-%d %H:%M")))
    return lines


def current_report():
    try:
        if SNAPSHOT.stat().st_size > 65536:
            return None
        return report(json.loads(SNAPSHOT.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        return None


def save(data):
    report(data)
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=SNAPSHOT.parent,
                                     prefix="claude-browser-", suffix=".tmp", delete=False) as stream:
        temp = Path(stream.name)
        # Persist usage fields only; discard any unexpected input, including auth data.
        cleaned = {key: data[key] for key in ("sourceUrl", "observedAt", "plan")}
        if data.get("browserName") in ("Browser", "Chrome", "Chromium", "Edge", "Firefox", "Safari"):
            cleaned["browserName"] = data["browserName"]
        cleaned["windows"] = {label: {"usedPercent": w["usedPercent"], "resetsAt": w.get("resetsAt")}
                              for label, w in data["windows"].items()}
        resets = data.get("resetCredits")
        cleaned["resetCredits"] = None if resets is None else {
            "availableCount": resets["availableCount"],
            "credits": None if resets.get("credits") is None else [
                {"status": row.get("status"), "expiresAt": row.get("expiresAt"),
                 "label": row["label"][:60] if isinstance(row.get("label"), str) else None}
                for row in resets["credits"]]}
        json.dump(cleaned, stream)
    try:
        os.replace(temp, SNAPSHOT)
    finally:
        temp.unlink(missing_ok=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--clear"]:
        SNAPSHOT.unlink(missing_ok=True)
        sys.exit(0)
    if sys.argv[1:] != ["--save"]:
        sys.exit("usage: claude_browser.py --clear | --save < usage.json")
    try:
        save(json.load(sys.stdin))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        sys.exit("Invalid or stale Claude browser observation; no snapshot saved.")
    print("Claude browser observation saved (valid for 5 minutes).")

#!/usr/bin/env python3
"""Gemini usage via the Antigravity CLI: `agy -p "/usage"`.

Found 2026-10-02 with agy 1.2.14. Print mode routes the built-in /usage slash command
(alias /quota), so it makes no model call, spends no quota and leaves no conversation.
It prints one tab-separated line per quota pool:

    Gemini Models<TAB>Weekly Limit Remaining<TAB>100%<TAB>2026-10-08T20:09:18Z
    Claude and GPT models<TAB>Weekly Limit Remaining<TAB>100%<TAB>2026-10-08T20:09:18Z

The percent is what is LEFT; this prints it as used (100 - left) like the other probes.

The CLI is ~/.gemini/bin/agy, not the `agy` on PATH: the Antigravity IDE installs a
launcher of the same name (`agy --help` prints the editor's options), so PATH is never
used to find it. It runs from the temp directory so no project folder is touched.
"""
import datetime, os, re, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

CLI = Path.home() / ".gemini" / "bin" / ("agy.exe" if os.name == "nt" else "agy")

if not CLI.is_file():
    print("agy CLI not installed")
    sys.exit(0)

FAIL = "usage call failed"

try:
    proc = subprocess.run([str(CLI), "-p", "/usage", "--print-timeout", "60s"],
                          capture_output=True, timeout=90, stdin=subprocess.DEVNULL,
                          cwd=tempfile.gettempdir(), **portable.text_kwargs())
    text = proc.stdout
except Exception as e:
    print("%s (%s)" % (FAIL, e))
    sys.exit(1)

# The pool names are Google's and printed as-is; short labels keep the rows aligned.
POOL = {"gemini models": "gemini", "claude and gpt models": "cl+gpt"}


def reset_clock(value):
    """'2026-10-08T20:09:18Z' -> local '10-09 04:09 (6d23h)', or the raw text."""
    try:
        at = datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return value
    left = int((at - datetime.datetime.now().astimezone()).total_seconds())
    rel = "%dd%dh" % (left // 86400, left % 86400 // 3600) if left > 0 else "now"
    return "%s (%s)" % (at.strftime("%m-%d %H:%M"), rel)


# /usage names no plan, and /credits only reports paid G1 credits.
print("plan: ?")
found = False
for line in text.splitlines():
    cells = [c.strip() for c in line.split("\t")]
    if len(cells) < 4 or "remaining" not in cells[1].lower():
        continue
    m = re.match(r"(\d+(?:\.\d+)?)%", cells[2])
    if not m:
        continue
    used = 100.0 - float(m.group(1))
    window = "weekly" if "week" in cells[1].lower() else cells[1]
    label = POOL.get(cells[0].lower(), cells[0])
    print("%-6s %5.1f%% used  window %s  pool %s  resets %s  %s"
          % (label, used, window, cells[0], reset_clock(cells[3]), portable.format_bar(used)))
    found = True

if not found:
    first = (text.strip().splitlines() or [proc.stderr.strip() or "no output"])[0]
    print("%s (%s; signed in? try `%s`)" % (FAIL, first[:120], CLI))
    sys.exit(1)

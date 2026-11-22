#!/usr/bin/env python3
"""Gemini usage via the Antigravity CLI: `agy -p "/usage"`.

Found 2026-10-02 with agy 1.2.14. Print mode routes the built-in /usage slash command
(alias /quota), so it makes no model call, spends no quota and leaves no conversation.
It prints one tab-separated line per quota pool:

    Gemini Models<TAB>Weekly Limit Remaining<TAB>100%<TAB>2026-10-08T20:09:18Z
    Claude and GPT models<TAB>Weekly Limit Remaining<TAB>100%<TAB>2026-10-08T20:09:18Z

The percent is what is LEFT; this prints it as used (100 - left) like the other probes,
with each pool's 5h window ordered before its weekly window. When a 5h limit is present
(Pro/Ultra only), `agy models` distinguishes `ultra` (lists `gemini-4-carbon`) from
`pro` without altering quota usage.

The CLI is ~/.gemini/bin/agy, not the `agy` on PATH: the Antigravity IDE installs a
launcher of the same name (`agy --help` prints the editor's options), so PATH is never
used to find it. It runs from the temp directory so no project folder is touched.

A signed-out agy does not fail quietly: print mode answers "Authentication required"
and opens the Google sign-in page in a browser (checked 2026-10-02 with an empty HOME).
The skill promises never to open a browser, so agy is only launched when its own log
shows it has signed in here: every signed-in run logs an authenticated
`v1internal:loadCodeAssist` call in ~/.gemini/antigravity/log/cli-*.log or the older
~/.gemini/antigravity-cli/log/cli-*.log. No log with
that call means `not signed in`, without starting agy. No credential file is read.
BROWSER is also pointed at a no-op on POSIX, in case agy honours it.

AGY_CLI_DISABLE_AUTO_UPDATE=1 keeps the CLI from updating itself during the probe.
"""
import datetime, os, re, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

HOME = Path.home()
CLI = HOME / ".gemini" / "bin" / ("agy.exe" if os.name == "nt" else "agy")
LOG_DIRS = [HOME / ".gemini" / folder / "log" for folder in ("antigravity", "antigravity-cli")]
SIGNED_IN_MARK = "v1internal:loadCodeAssist"

if not CLI.is_file():
    print("agy CLI not installed")
    sys.exit(0)


def signed_in():
    """True when the newest agy log that made any backend call made an authenticated one."""
    try:
        logs = [path for folder in LOG_DIRS
                for path in sorted(folder.glob("cli-*.log"),
                                   key=lambda p: p.stat().st_mtime, reverse=True)[:10]]
        logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return False
    for path in logs:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if SIGNED_IN_MARK in text:
            return True
        if "authentication required" in text.lower():
            return False
    return False


if not signed_in():
    print("agy not signed in here (run `%s` once and sign in); skipped so no browser opens" % CLI)
    sys.exit(0)

FAIL = "usage call failed"
env = dict(os.environ, AGY_CLI_DISABLE_AUTO_UPDATE="1")
if os.name != "nt":
    env["BROWSER"] = "true"
deadline = time.monotonic() + portable.CALL_TIMEOUT

try:
    timeout = portable.timeout_left(deadline, portable.CALL_TIMEOUT)
    proc = subprocess.run([str(CLI), "-p", "/usage", "--print-timeout", "%gs" % timeout],
                          capture_output=True, timeout=timeout,
                          stdin=subprocess.DEVNULL,
                          cwd=tempfile.gettempdir(), env=env, **portable.text_kwargs())
    text = proc.stdout
except Exception as e:
    print("%s (%s)" % (FAIL, e))
    sys.exit(1)

# The pool names are Google's and printed as-is; short labels keep the rows aligned.
POOL = {
    "gemini models": "gemini",
    "claude and gpt models": "cl+gpt",
    "gemini 4 argon": "argon",
}


def reset_clock(value):
    """Keep the year and UTC offset so the renderer can calculate the exact reset."""
    try:
        at = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if at.tzinfo is None:
            return value
        at = at.astimezone()
    except ValueError:
        return value
    left = int((at - datetime.datetime.now().astimezone()).total_seconds())
    rel = "%dd%dh" % (left // 86400, left % 86400 // 3600) if left > 0 else "now"
    return "%s (%s)" % (at.isoformat(timespec="seconds"), rel)


def detect_plan(has_5h):
    """Pro/Ultra carry a 5h window; `agy models` distinguishes Ultra (Carbon) from Pro."""
    if not has_5h:
        return "?"
    try:
        timeout = portable.timeout_left(deadline, portable.CALL_TIMEOUT)
        out = subprocess.run([str(CLI), "models"],
                             capture_output=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             cwd=tempfile.gettempdir(), env=env, **portable.text_kwargs()).stdout
    except Exception:
        return "?"
    if re.search(r"(?m)^gemini-4-carbon\b", out):
        return "ultra"
    if re.search(r"(?m)^gemini-4-(?:neon|argon|hydrogen)\b", out):
        return "pro"
    return "?"


pools = {}
for line in text.splitlines():
    cells = [c.strip() for c in line.split("\t")]
    if len(cells) < 4:
        continue
    period = cells[1].lower()
    if "remaining" not in period and "limit" not in period:
        continue
    m = re.match(r"(\d+(?:\.\d+)?)%", cells[2])
    if not m:
        continue
    used = max(0.0, min(100.0, 100.0 - float(m.group(1))))
    # antigravity.google/docs/cli/commands/usage: each pool has a weekly and a five-hour
    # limit; docs/plans: the five-hour one is Pro/Ultra only. Checked 2026-11-09.
    if "five hour" in period or "5h" in period:
        window = "5h"
    elif "weekly" in period:
        window = "weekly"
    else:
        window = cells[1]
    label = POOL.get(cells[0].lower(), re.sub(r"\s+", "-", cells[0].lower()))
    row = ("%-6s %5.1f%% used  window %s  pool %s  resets %s  %s"
           % (label, used, window, cells[0], reset_clock(cells[3]), portable.format_bar(used)))
    pools.setdefault(label, []).append((0 if window == "5h" else 1, row))

if not pools:
    first = (text.strip().splitlines() or [(proc.stderr or "").strip() or "no output"])[0]
    print("%s (%s)" % (FAIL, first[:120]))
    sys.exit(1)

has_5h = any(order == 0 for rows in pools.values() for order, _ in rows)
print("plan: %s" % detect_plan(has_5h))
for rows in pools.values():
    for _, row in sorted(rows, key=lambda item: item[0]):
        print(row)

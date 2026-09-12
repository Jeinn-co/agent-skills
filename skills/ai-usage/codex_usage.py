#!/usr/bin/env python3
"""ChatGPT usage via the codex app-server method `account/rateLimits/read`.

Found 2026-09-12. `codex app-server` speaks JSON-RPC 2.0 over stdio. This is live --
it replaces the earlier approach of scraping ~/.codex/sessions/**/rollout-*.jsonl,
which only ever showed numbers as of the last codex run.

Discovery trick: calling a bogus method returns -32600 whose message enumerates every
valid method name. That is how `account/rateLimits/read` was found; the string in the
binary is the shorter `account/usage`, which is not a real wire name.
"""
import subprocess, json, threading, time, datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

cmd = portable.argv("codex", "app-server")
if cmd is None:
    print("codex CLI not installed")
    sys.exit(0)

FAIL = "rateLimits call failed"

def die(why):
    print("%s (%s)" % (FAIL, why))
    try:
        p.kill()
    except Exception:
        pass
    sys.exit(1)

try:
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, bufsize=1)
except OSError as e:
    print("%s (could not start codex: %s)" % (FAIL, e))
    sys.exit(1)
out = []
threading.Thread(target=lambda: [out.append(l) for l in p.stdout], daemon=True).start()

def send(i, m, params=None):
    """False when the CLI has already exited, so its stdin is gone."""
    try:
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": m,
                                  "params": params or {}}) + "\n")
        p.stdin.flush()
        return True
    except (BrokenPipeError, OSError, ValueError):
        return False

if not send(1, "initialize", {"clientInfo": {"name": "uu", "title": "uu",
                                            "version": "1"}}):
    die("codex exited before answering; signed in? try `codex login`")
time.sleep(1.5)
if not send(2, "account/rateLimits/read"):
    die("codex exited before answering; signed in? try `codex login`")

res = None
for _ in range(40):
    time.sleep(0.25)
    for l in out:
        try:
            d = json.loads(l)
        except Exception:
            continue
        if d.get("id") == 2 and "result" in d:
            res = d["result"]
            break
    if res:
        break
p.kill()

if not res:
    die("no answer in 10s; exit code %s" % p.poll())

def require_mapping(value, path):
    if not isinstance(value, dict):
        raise ValueError("%s must be an object" % path)
    return value

def require_number(mapping, key, path):
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s.%s must be a number" % (path, key))
    return value

try:
    payload = require_mapping(res, "result")
    r = require_mapping(payload.get("rateLimits"), "rateLimits")
    windows = []
    for key, label in (("primary", "short"), ("secondary", "outer")):
        path = "rateLimits.%s" % key
        w = require_mapping(r.get(key), path)
        used = require_number(w, "usedPercent", path)
        duration = require_number(w, "windowDurationMins", path)
        ts = require_number(w, "resetsAt", path)
        if not 0 <= used <= 100:
            raise ValueError("%s.usedPercent must be between 0 and 100" % path)
        if duration <= 0:
            raise ValueError("%s.windowDurationMins must be positive" % path)
        if ts <= 0:
            raise ValueError("%s.resetsAt must be positive" % path)
        windows.append((label, used, duration, datetime.datetime.fromtimestamp(ts)))
except (ValueError, TypeError, OverflowError, OSError) as e:
    die("invalid response: %s" % e)

print("plan: %s" % (r.get("planType") or "unknown"))
for label, used, duration, dt in windows:
    left = dt - datetime.datetime.now()
    rel = "(%dd%dh)" % (left.days, left.seconds // 3600) if left.total_seconds() > 0 else "(expired)"
    print("%-6s %5.1f%% used  window %dh  resets %s %s"
          % (label, used, duration // 60, dt.strftime("%m-%d %H:%M"), rel))
# NOT the "Usage limit resets" count. `credits` is the paid top-up balance; the reset
# tokens shown under Settings > Usage limit resets are a separate pool and the
# app-server exposes no way to read them -- only `account/rateLimitResetCredit/consume`,
# which spends one. Checked all 163 methods 2026-09-12; `account/usage/read` carries
# lifetime token stats only. Do not print a redeem number here: it would contradict
# what the web UI shows.
c = r.get("credits") or {}
if c.get("unlimited"):
    print("credits: unlimited")
elif c.get("hasCredits"):
    print("credits: balance=%s" % c.get("balance"))
print("resets available: unknown (web only - chatgpt.com settings)")

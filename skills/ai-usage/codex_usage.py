#!/usr/bin/env python3
"""ChatGPT usage via the codex app-server method `account/rateLimits/read`.

Found 2026-09-12. `codex app-server` speaks JSON-RPC 2.0 over stdio. This is live --
it replaces the earlier approach of scraping ~/.codex/sessions/**/rollout-*.jsonl,
which only ever showed numbers as of the last codex run.

Discovery trick: calling a bogus method returns -32600 whose message enumerates every
valid method name. That is how `account/rateLimits/read` was found; the string in the
binary is the shorter `account/usage`, which is not a real wire name.
"""
import subprocess, json, threading, time, shutil, sys, datetime

if not shutil.which("codex"):
    print("codex CLI not installed")
    sys.exit(0)

p = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                     text=True, bufsize=1)
out = []
threading.Thread(target=lambda: [out.append(l) for l in p.stdout], daemon=True).start()

def send(i, m, params=None):
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": m,
                              "params": params or {}}) + "\n")
    p.stdin.flush()

send(1, "initialize", {"clientInfo": {"name": "uu", "title": "uu", "version": "1"}})
time.sleep(1.5)
send(2, "account/rateLimits/read")

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
    print("rateLimits call failed")
    sys.exit(1)

r = res.get("rateLimits", {})
print("plan: %s" % r.get("planType"))
now = datetime.datetime.now().timestamp()
for key, label in (("primary", "short"), ("secondary", "outer")):
    w = r.get(key) or {}
    ts = w.get("resetsAt", 0)
    dt = datetime.datetime.fromtimestamp(ts)
    left = dt - datetime.datetime.now()
    rel = "(%dd%dh)" % (left.days, left.seconds // 3600) if left.total_seconds() > 0 else "(expired)"
    print("%-6s %5.1f%% used  window %dh  resets %s %s"
          % (label, w.get("usedPercent", 0), (w.get("windowDurationMins") or 0) // 60,
             dt.strftime("%m-%d %H:%M"), rel))
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

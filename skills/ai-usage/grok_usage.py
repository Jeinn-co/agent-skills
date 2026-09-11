#!/usr/bin/env python3
"""Grok usage via the ACP extension method `_x.ai/billing`.

Found 2026-09-12. `grok agent stdio` speaks ACP over stdio. The method name in the
binary is `x.ai/billing`, but the wire name carries a leading underscore -- calling
`x.ai/billing` returns -32601 Method not found. No session/new needed; params {}.
"""
import subprocess, json, threading, time, shutil, sys, datetime

if not shutil.which("grok"):
    print("grok CLI not installed")
    sys.exit(0)

p = subprocess.Popen(["grok", "agent", "stdio"], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                     text=True, bufsize=1)
out = []
threading.Thread(target=lambda: [out.append(l) for l in p.stdout], daemon=True).start()

def send(i, m, params=None):
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": m,
                              "params": params or {}}) + "\n")
    p.stdin.flush()

send(1, "initialize", {"protocolVersion": 1,
                       "clientCapabilities": {"fs": {"readTextFile": False,
                                                     "writeTextFile": False}}})
time.sleep(2.5)
send(2, "_x.ai/billing")

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
    print("billing call failed")
    sys.exit(1)

c = res.get("config", {})
end = c.get("billingPeriodEnd", "")
try:
    dt = datetime.datetime.fromisoformat(end).astimezone()
    left = dt - datetime.datetime.now(dt.tzinfo)
    when = "%s (%dd%dh)" % (dt.strftime("%m-%d %H:%M"),
                           left.days, left.seconds // 3600)
except Exception:
    when = end

print("plan: %s" % res.get("subscription_tier"))
print("%-6s %5.1f%% used  window %s  resets %s"
      % ("week", c.get("creditUsagePercent", 0),
         (c.get("currentPeriod") or {}).get("type", "").replace("USAGE_PERIOD_TYPE_", "").lower(),
         when))
print("prepaid balance %s | on-demand %s/%s"
      % ((c.get("prepaidBalance") or {}).get("val"),
         (c.get("onDemandUsed") or {}).get("val"),
         (c.get("onDemandCap") or {}).get("val")))

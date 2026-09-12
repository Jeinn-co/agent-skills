#!/usr/bin/env python3
"""Grok usage via the ACP extension method `_x.ai/billing`.

Found 2026-09-12. `grok agent stdio` speaks ACP over stdio. The method name in the
binary is `x.ai/billing`, but the wire name carries a leading underscore -- calling
`x.ai/billing` returns -32601 Method not found. No session/new needed; params {}.
"""
import subprocess, json, threading, time, datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

cmd = portable.argv("grok", "agent", "stdio")
if cmd is None:
    print("grok CLI not installed")
    sys.exit(0)

FAIL = "billing call failed"

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
    print("%s (could not start grok: %s)" % (FAIL, e))
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

if not send(1, "initialize", {"protocolVersion": 1,
                              "clientCapabilities": {"fs": {"readTextFile": False,
                                                            "writeTextFile": False}}}):
    die("grok exited before answering; signed in? try `grok`")
time.sleep(2.5)
if not send(2, "_x.ai/billing"):
    die("grok exited before answering; signed in? try `grok`")

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
    c = require_mapping(payload.get("config"), "config")
    used = require_number(c, "creditUsagePercent", "config")
    if not 0 <= used <= 100:
        raise ValueError("config.creditUsagePercent must be between 0 and 100")
    period = require_mapping(c.get("currentPeriod"), "config.currentPeriod")
    period_type = period.get("type")
    if not isinstance(period_type, str) or not period_type:
        raise ValueError("config.currentPeriod.type must be a non-empty string")
    end = c.get("billingPeriodEnd")
    if not isinstance(end, str) or not end:
        raise ValueError("config.billingPeriodEnd must be a non-empty string")
    iso_end = end[:-1] + "+00:00" if end.endswith("Z") else end
    dt = datetime.datetime.fromisoformat(iso_end).astimezone()
    left = dt - datetime.datetime.now(dt.tzinfo)
    when = "%s (%dd%dh)" % (dt.strftime("%m-%d %H:%M"),
                           left.days, left.seconds // 3600)
except (ValueError, TypeError, OverflowError) as e:
    die("invalid response: %s" % e)

print("plan: %s" % (res.get("subscription_tier") or "unknown"))
print("%-6s %5.1f%% used  window %s  resets %s"
      % ("week", used,
         period_type.replace("USAGE_PERIOD_TYPE_", "").lower(),
         when))
balances = [c.get(key) for key in ("prepaidBalance", "onDemandUsed", "onDemandCap")]
if all(isinstance(item, dict) and item.get("val") is not None for item in balances):
    print("prepaid balance %s | on-demand %s/%s"
          % (balances[0]["val"], balances[1]["val"], balances[2]["val"]))

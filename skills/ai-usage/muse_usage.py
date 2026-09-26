#!/usr/bin/env python3
"""Muse Code usage via MSP (`muse serve`) -> JSON-RPC `usage/read`.

Found 2026-09-24. `usage/read` returns the host's *last-observed* subscription usage
(5h-class window + weekly block, tier). A fresh host has observed nothing and answers
`{}`: Muse keeps no usage on disk, `session/start` alone does not fetch it, and the
binary has no usage endpoint. The numbers arrive only with a model response. So this
probe starts one session in a dedicated empty workspace and sends one tiny turn at
`minimal` effort. That spends a sliver of quota and leaves one session in Muse's
history; session_info.py skips sessions rooted in PROBE_DIR.

The turn uses the non-contributor twin of the default model when the local catalog
lists one, so the probe prompt is not offered for product improvement.
"""
import datetime, json, os, secrets, subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

# session_info.py imports this to hide the probe's own sessions.
PROBE_DIR = os.path.join(tempfile.gettempdir(), "ai-usage-muse-probe")
# Muse `tier` id -> plan name as Muse's plan page shows it. 27681527378179523 was the
# account's id on 2026-09-24 while that page listed "High Usage" as the current plan.
TIER_NAMES = {"27681527378179523": "High Usage"}
CATALOG_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "muse", "model-catalog")
PROMPT = "Reply with the single word: ok"
TIMEOUT = 90


def uuid7():
    """MSP command ids must be UUIDv7; Python < 3.14 has no uuid.uuid7()."""
    ms = int(time.time() * 1000)
    rand = int.from_bytes(secrets.token_bytes(10), "big")
    value = (ms << 80) | (0x7 << 76) | (((rand >> 62) & 0xFFF) << 64) | (0b10 << 62) | (rand & ((1 << 62) - 1))
    return str(uuid.UUID(int=value))


def probe_model():
    """Non-contributor twin of the catalog default, or None to let Muse pick."""
    try:
        names = sorted(os.listdir(CATALOG_DIR))
    except OSError:
        return None
    for name in names:
        try:
            with open(os.path.join(CATALOG_DIR, name), encoding="utf-8") as handle:
                rows = json.load(handle).get("rows") or []
        except (OSError, ValueError):
            continue
        ids = {row.get("model_id") for row in rows}
        for row in rows:
            if row.get("is_default"):
                model = row.get("model_id") or ""
                plain = model[: -len("-contributor")] if model.endswith("-contributor") else model
                return plain if plain in ids else None
    return None


def main():
    cmd = portable.argv("muse", "serve")
    if cmd is None:
        print("muse CLI not installed")
        return 0
    os.makedirs(PROBE_DIR, exist_ok=True)
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, bufsize=1, cwd=PROBE_DIR,
                                # the launcher self-updates in the background otherwise
                                env={**os.environ, "MUSE_NO_AUTO_UPDATE": "1"},
                                **portable.text_kwargs())
    except OSError as exc:
        print("usage call failed (could not start muse: %s)" % exc)
        return 1

    # Set on the first usage/changed, or when the turn ends without one.
    replies, settled, lock = {}, threading.Event(), threading.Lock()

    def reader():
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                with lock:
                    replies[msg["id"]] = msg
            elif msg.get("method") in ("usage/changed", "turn/completed"):
                settled.set()

    threading.Thread(target=reader, daemon=True).start()

    def send(body):
        try:
            proc.stdin.write(json.dumps(body) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            raise RuntimeError("muse exited before answering; signed in? try `muse`")

    def call(i, method, params=None, wait=30):
        body = {"jsonrpc": "2.0", "id": i, "method": method}
        if params is not None:
            body["params"] = params
        send(body)
        end = time.time() + wait
        while time.time() < end:
            with lock:
                if i in replies:
                    msg = replies[i]
                    if "error" in msg:
                        raise RuntimeError("%s: %s" % (method, msg["error"].get("message")))
                    return msg["result"]
            if proc.poll() is not None:
                raise RuntimeError("muse exited (code %s); signed in? try `muse`" % proc.returncode)
            time.sleep(0.1)
        raise RuntimeError("%s: no answer in %ds" % (method, wait))

    try:
        call(1, "initialize", {"clientInfo": {"name": "ai_usage", "version": portable.VERSION}})
        send({"jsonrpc": "2.0", "method": "initialized"})
        start = {"commandId": uuid7(), "workspaceRoot": PROBE_DIR}
        model = probe_model()
        if model:
            start["modelId"] = model
        session = call(2, "session/start", start)["session"]["sessionId"]
        call(3, "turn/start", {"commandId": uuid7(), "sessionId": session,
                               "input": [{"type": "text", "text": PROMPT}],
                               "reasoningEffort": "minimal"})
        settled.wait(TIMEOUT)
        usage = call(4, "usage/read").get("usage")
    except RuntimeError as exc:
        print("usage call failed (%s)" % exc)
        return 1
    finally:
        try:
            proc.kill()
        except Exception:
            pass

    if not usage:
        print("usage call failed (no usage observed within %ds)" % TIMEOUT)
        return 1
    try:
        # `tier` is a numeric product id, not a plan name: map the ids a user has
        # matched against Muse's plan page (TIER_NAMES); any other id prints `?`.
        tier = str(usage.get("tier") or "")
        name = TIER_NAMES.get(tier) or (tier if tier and not tier.isdigit() else "?")
        print("plan: %s" % name)
        window, weekly = usage["window"], usage["weekly"]
        mins = window["windowDurationMins"]
        span = "%dh" % (mins // 60) if mins % 60 == 0 else "%dm" % mins
        now = datetime.datetime.now().astimezone()
        for label, block in ((span, window), ("week", weekly)):
            at = datetime.datetime.fromtimestamp(block["resetsAtMs"] / 1000).astimezone()
            left = at - now
            print("%-6s %5.1f%% used  resets %s (%dd%dh)"
                  % (label, block["usedPercent"], at.strftime("%m-%d %H:%M"), left.days, left.seconds // 3600))
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        print("usage call failed (invalid response: %s)" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

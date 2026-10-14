#!/usr/bin/env python3
"""/ai-usage entry point. Reads AI subscription usage. No browser, no stored credentials.

Each probe runs as a separate process with *this* interpreter (`sys.executable`), so
there is no dependency on a `python3` on PATH -- on Windows that name is often absent,
or worse, a Microsoft Store stub that opens the store instead of running anything.

Verified 2026-09-12 on macOS, 2026-09-14 on Windows 11. See README for platform notes.
"""
import subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

if "--version" in sys.argv:
    print("ai-usage %s" % portable.VERSION)
    sys.exit(0)

HERE = Path(__file__).resolve().parent

# claude -p --output-format json "/usage"          -- live, see claude_usage.py
# codex app-server  -> JSON-RPC account/rateLimits/read  -- live, see codex_usage.py
# grok agent stdio  -> ACP extension _x.ai/billing       -- live, see grok_usage.py
# muse serve        -> MSP usage/read after one tiny turn -- live, see muse_usage.py
# agy -p "/usage"   -> Antigravity CLI quota pools (Gemini) -- live, see agy_usage.py
# session_info.py <cli>  -> newest local session file     -- model/effort/permission
# cursorbench.py cli=model:effort ...  -> cursor.com/cursorbench rows for those models
PROBES = (("CLAUDE", "claude_usage.py", "claude"),
          ("CHATGPT", "codex_usage.py", "codex"),
          ("GROK", "grok_usage.py", "grok"),
          ("MUSE", "muse_usage.py", "muse"),
          ("GEMINI", "agy_usage.py", "agy"))


def usage(script):
    try:
        result = portable.run_bounded(
            [sys.executable, "-u", str(HERE / script)],
            timeout=portable.CALL_TIMEOUT, stdout=subprocess.PIPE,
            **portable.text_kwargs())
        return result.stdout
    except subprocess.TimeoutExpired:
        return "usage call timed out after %gs; skipped\n" % portable.CALL_TIMEOUT


def session(cli):
    try:
        return portable.run_bounded(
            [sys.executable, str(HERE / "session_info.py"), cli],
            timeout=portable.CALL_TIMEOUT, stdout=subprocess.PIPE,
            **portable.text_kwargs()).stdout
    except subprocess.TimeoutExpired:
        return "session lookup timed out after %gs; skipped\n" % portable.CALL_TIMEOUT


def benchmark(now):
    try:
        # Buffer the table: a timed-out lookup must not leave half a set of picks.
        return portable.run_bounded(
            [sys.executable, str(HERE / "cursorbench.py"), *now],
            timeout=portable.CALL_TIMEOUT, stdout=subprocess.PIPE,
            **portable.text_kwargs()).stdout
    except subprocess.TimeoutExpired:
        return "bench failed (lookup timed out after %gs; skipped)\n" % portable.CALL_TIMEOUT

try:
    print("### ai-usage %s" % portable.VERSION)
    print()
    sys.stdout.flush()
    with ThreadPoolExecutor(max_workers=2 * len(PROBES)) as pool:
        # Start every CLI and local session read before waiting for any result.
        calls = [pool.submit(usage, script) for _, script, _ in PROBES]
        sessions = [pool.submit(session, cli) for _, _, cli in PROBES]
        infos = [future.result() for future in sessions]
        now = []  # Every provider; an empty model means no local session.
        for (_, _, cli), info in zip(PROBES, infos):
            fields = dict(line.split(None, 1) for line in info.splitlines()
                          if line.startswith(("model ", "effort ")))
            if "model" in fields:
                now.append("%s=%s:%s" % (cli, fields["model"].strip(),
                                         (fields.get("effort") or "?").split()[0]))
            else:
                now.append("%s=:" % cli)
        # Benchmark needs model/effort, not usage: overlap its network calls too.
        bench = pool.submit(benchmark, now)
        for i, ((header, _, _), call, info) in enumerate(zip(PROBES, calls, infos)):
            if i:
                print()
            print("### %s" % header)
            print(call.result(), end="")
            print(info, end="")
            sys.stdout.flush()
        print()
        print("### CURSORBENCH")
        print(bench.result(), end="")
except BrokenPipeError:
    # someone piped us into `head` and walked away. Point the fd at devnull so the
    # interpreter's shutdown flush does not print a second traceback on top.
    import os
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    sys.exit(0)

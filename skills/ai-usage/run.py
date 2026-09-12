#!/usr/bin/env python3
"""/ai-usage entry point. Reads AI subscription usage. No browser, no stored credentials.

Each probe runs as a separate process with *this* interpreter (`sys.executable`), so
there is no dependency on a `python3` on PATH -- on Windows that name is often absent,
or worse, a Microsoft Store stub that opens the store instead of running anything.

Verified 2026-09-12 on macOS. See README for platform notes.
"""
import subprocess, sys
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
PROBES = (("CLAUDE", "claude_usage.py"),
          ("CHATGPT", "codex_usage.py"),
          ("GROK", "grok_usage.py"))

try:
    print("### ai-usage %s" % portable.VERSION)
    print()
    for i, (header, script) in enumerate(PROBES):
        if i:
            print()
        print("### %s" % header)
        sys.stdout.flush()
        subprocess.run([sys.executable, str(HERE / script)])
except BrokenPipeError:
    # someone piped us into `head` and walked away. Point the fd at devnull so the
    # interpreter's shutdown flush does not print a second traceback on top.
    import os
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    sys.exit(0)

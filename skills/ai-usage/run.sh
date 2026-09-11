#!/bin/bash
# /uu — read AI subscription usage. No browser, no stored credentials.
# Verified 2026-09-12 on macOS.

echo "### CLAUDE"
# claude -p --output-format json "/usage". Live. See claude_usage.py.
python3 "$(dirname "$0")/claude_usage.py"

echo
echo "### CHATGPT"
# codex app-server JSON-RPC method `account/rateLimits/read`. Live. See codex_usage.py.
python3 "$(dirname "$0")/codex_usage.py"
echo
echo "### GROK"
# ACP extension method `_x.ai/billing` over `grok agent stdio`. See grok_usage.py.
python3 "$(dirname "$0")/grok_usage.py"

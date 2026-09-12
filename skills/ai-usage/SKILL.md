---
name: ai-usage
description: Check AI subscription usage limits across Claude, ChatGPT and Grok in one unified report — percent used, how much is left, and when each window resets. Use when the user runs /ai-usage or /uu, or asks 額度, 用量, usage, limit, 還剩多少, 什麼時候 reset, 被限流了嗎, rate limit, quota, "am I out of Claude", "how much ChatGPT left".
metadata:
  author: Jeinn
  version: "1.1.0"
---

# /ai-usage — unified AI usage report

Run `python run.py` from this skill's directory (`./run.sh` is a POSIX shim for the
same thing). Reformat its output into the table below. Nothing else. No browser, no
stored credentials, no network calls of your own.

`/ai-usage fresh` — same thing; the script always reads live. The flag only means "do not
reuse an answer from earlier in this conversation".

The first output line is `### ai-usage <version>`. Do not put it in the report. Quote it
only when the user asks which version they are on, or when they are reporting a bug —
there is no other way for them to find out, since installing a skill copies the files
and leaves no record of where they came from. `python run.py --version` prints it alone.

## What must already be in place

Do not install anything and do not ask the user to log in. Just run the script and
report what comes back.

- **Python 3.9+** on PATH. `run.py` re-launches each probe with its own interpreter,
  so the caller's `python` / `python3` / `py` name does not matter.
- **At least one** of `claude`, `codex`, `grok`, already signed in. Zero of them is
  still a valid run: every row prints `not installed`.

If a provider prints `not installed`, that is the whole answer for that row — say so
and move on. Do not suggest installing it unless the user asks. If a provider is
installed but its call fails, report the failure for that row and still print the
others; never substitute a number from memory or from an earlier run.

## Where each number comes from

All three are live. No browser, no stored credentials, no cookie access.
Verified 2026-09-12 on macOS; Windows support is written for but not verified on
real hardware.

| Provider | Method |
|---|---|
| Claude | `claude -p "/usage" < /dev/null` — print mode routes the built-in slash command |
| ChatGPT | `codex app-server` → JSON-RPC `account/rateLimits/read` — see `codex_usage.py` |
| Grok | `grok agent stdio` → JSON-RPC `_x.ai/billing` — see `grok_usage.py` |

Two of the three are the CLI's own local agent server answering over stdio, so the
numbers are the same ones the TUI shows. Nothing is cached and nothing is scraped.

## Reading the output

**Claude** — current session (5h) and current week.

**ChatGPT** — `short` (5h) and `outer` (7d), plus `plan`.

The number of **"Usage limit resets"** (Settings > Usage limit resets, "Available N")
is **not readable locally**. The app-server has `account/rateLimitResetCredit/consume`,
which spends one, but no read counterpart -- verified against all 163 methods.
`credits.balance` is a *different* pool (paid top-ups) and must never be presented as
the reset count: an account can show `balance 0` while holding 2 available resets.
Print `resets available: unknown (web only)` and leave it at that.

**Grok** — weekly `creditUsagePercent` and the billing period end, plus
`prepaidBalance` and `onDemandCap`/`onDemandUsed`. Grok has only one window, not two —
do not invent a short row for it.

Do not label any of these "redeem" unless the provider itself uses that concept. Only
Claude's extra usage is confirmed to map onto it.

## Output

```
USAGE — 09-12 01:08

  Claude    pro
    5h    ███░░░░░░░  29%   resets 03:40 (2h32m)
    week  ████░░░░░░  41%   resets Mon 17:00 (2d16h)
    extra usage  disabled (Max only)

  ChatGPT   plus
    5h    ░░░░░░░░░░   0%   resets 05:55 (4h47m)
    week  ░░░░░░░░░░   0%   resets 09-18 17:07 (6d15h)
    resets available  unknown (web only)

  Grok      SuperGrok
    week  ███░░░░░░░  27%   resets 09-15 09:38 (3d8h)
    prepaid 0 / on-demand 0

  → Use ChatGPT right now. Both windows are fresh.
```

Rules:
- Bars 10 chars, `█` used / `░` free. Percentages are whole numbers.
- Relative time next to every reset clock.
- Last line names which tool to use right now, and why in a few words.
- If any week row is over 80%, put a `⚠` line above the arrow saying how long until it
  resets.
- A provider whose CLI is not installed prints `not installed` and is shown as one
  greyed row. Never drop it silently.
- No preamble, no recap, no closing offer.
- Match the user's language for the labels; the sample above is English.

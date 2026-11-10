# Why each provider works the way it does

All five services compute usage server-side. Each probe reads the result through
its provider's CLI or usage endpoint.

## Claude — optional browser source, OAuth usage endpoint, CLI fallback

See [claude-browser.md](claude-browser.md) to read the already signed-in browser Usage
page. Fresh browser observations bypass CLI auth and contain no cookies or tokens.
The source and check time are visible; snapshots expire after 5 minutes.

Without a browser observation, one read-only GET to
`https://api.anthropic.com/api/oauth/usage?cedar_ember=1&skip_spend=1` returns both the
quota windows (`five_hour`, `seven_day`) and the banked reset grants (`cedar_ember`).
The token comes from `CLAUDE_CODE_OAUTH_TOKEN`, the macOS keychain item
`Claude Code-credentials`, or `$CLAUDE_CONFIG_DIR/.credentials.json` (default
`~/.claude/.credentials.json`); it is never refreshed, saved or printed.

Fallback: on Windows with Claude Code 2.1.319, `claude -p --output-format json "/usage"`
returned a cost summary instead of the session and weekly quota windows, so the old
regex parser printed `could not parse; raw first line: Total cost: ...`. The first
version with this behavior has not been established; 2.1.318 on macOS still prints the
windows. The probe uses this text only when the OAuth request fails (no login, expired
token, HTTP error, invalid data), and the reset row then shows that request's failure.

The request sends Bearer auth and `anthropic-beta: oauth-2025-04-20`, and never follows
redirects. The plan comes from `claudeAiOauth.subscriptionType`. Only `five_hour` and
`seven_day` are reported, from `utilization` and `resets_at`; reset times are converted
to local time. Out-of-range, non-numeric or missing percentages are rejected (never 0%).

Claude Code does **not** persist rate-limit state anywhere on disk — checked:
- session jsonl `usage` field carries `input_tokens` / `cache_read_input_tokens` /
  `output_tokens` only, no percentage
- `~/.claude/stats-cache.json` is message and tool-call counts

The endpoint and credential file are internal interfaces and may change. This
method was verified live on Windows 11 (credentials file) and macOS (keychain) on 2026-11-09.

## ChatGPT — works, live

`codex app-server` speaks JSON-RPC 2.0 over stdio. Send `initialize`, then
`account/rateLimits/read`:

```json
{"rateLimits":{"primary":{"usedPercent":0,"windowDurationMins":300,"resetsAt":...},
 "secondary":{"usedPercent":0,"windowDurationMins":10080,"resetsAt":...},
 "credits":{"balance":"0"},"planType":"plus"}}
```

**Discovery trick worth reusing:** call a bogus method. The `-32600` error message
enumerates every valid method name. The string in the binary is `account/usage`, which
is *not* a real wire name — the list gave the true `account/rateLimits/read`.

`codex exec "/status"` does NOT work: exec mode does not route slash commands, it sends
"/status" to the model, which interprets it as a request to run `git status`. Cost 8k
tokens to learn.

Superseded approach, kept as context: `~/.codex/sessions/**/rollout-*.jsonl` carries the
same `rate_limits` object written from response headers, but only as of the last codex
run. The app-server method is live; prefer it.

## Grok — works, live

`grok agent stdio` speaks ACP (JSON-RPC 2.0, newline-delimited) over stdio.
Send `initialize`, then call `_x.ai/billing` with empty params:

```json
{"subscription_tier":"SuperGrok",
 "config":{"creditUsagePercent":27.0,
           "currentPeriod":{"type":"USAGE_PERIOD_TYPE_WEEKLY","start":"...","end":"..."},
           "billingPeriodEnd":"...",
           "onDemandCap":{"val":0},"onDemandUsed":{"val":0},"prepaidBalance":{"val":0}}}
```

`creditUsagePercent` is a whole number and is omitted while it is 0. Every reading
logged 2026-09-14..10-06 was integral (1.0 .. 66.0). On 2026-10-06 (grok 1.0.46) it
was omitted ~2h after the weekly reset; minutes later the same call returned 1.0
and grok.com Settings -> Usage showed "1% used". The probe prints `<1% used`.

Two traps that cost time:
- The method name in the binary is `x.ai/billing`, but the **wire name has a leading
  underscore**. `x.ai/billing` returns `-32601 Method not found`; `_x.ai/billing` works.
  Same for `_x.ai/auth/check_subscription`.
- No `session/new` needed. Params `{}`.

Dead ends, do not retry:
1. **Local cache** — `~/.grok` holds `totalTokens` and `costUsdTicks` only; `monthlyLimit`
   and `billingCycle` never touch disk. ccusage and TokenTracker have the same gap.
2. **`grok -p "/usage"`** — not routed as a slash command; goes to the model as a prompt.
   (It read `~/.claude/skills` and executed this very skill.)
3. **PTY** — `expect` driving the TUI returned nothing parseable.
4. **Browser** — grok.com returns **403 Cloudflare** to Playwright-driven Chrome even
   with real cookies copied from the user's profile. It fingerprints automation, not
   login state. The Playwright MCP extension route was never needed.

## Muse — works, live, costs one model call

`muse serve` speaks MSP (Muse Session Protocol, JSON-RPC 2.0) over stdio. `muse schema
generate-json-schema --out DIR` writes the full wire schema; the method is `usage/read`,
answering `{usage: {tier, window: {usedPercent, resetsAtMs, windowDurationMins},
weekly: {usedPercent, resetsAtMs}, observedAtMs}}`.

The catch: it returns the host's **last-observed** usage, and a fresh host has observed
nothing, so it answers `{}`. The numbers ride on model responses. The probe therefore
sends `initialize`, `initialized`, `session/start` (in a dedicated empty workspace), one
`turn/start` at `minimal` effort, waits for `usage/changed` or `turn/completed`, then
calls `usage/read`. Command ids must be UUIDv7. `tier` is a numeric product id, not a
plan name.

Dead ends, do not retry (checked 2026-09-24, Muse Code 1.3.0-R3401.1):
1. **Local files** — session logs, the session index and the model catalog carry no
   usage percentages.
2. **`session/start` without a turn** — still `{}`.
3. **`muse exec "/usage"`** — not routed as a slash command; goes to the model as a
   prompt (and ran this very skill). `/usage` in the TUI shows session tokens, not quota.
4. **A usage endpoint** — the binary's only `api.meta.ai/v1` paths besides the model API
   are metrics, logs and ASR.

## Gemini (Antigravity CLI) — works, live

`~/.gemini/bin/agy -p "/usage"` prints one tab-separated line per quota pool (found
2026-10-02, agy 1.2.14):

    Gemini Models<TAB>Weekly Limit Remaining<TAB>100%<TAB>2026-10-08T20:09:18Z
    Claude and GPT models<TAB>Weekly Limit Remaining<TAB>100%<TAB>2026-10-08T20:09:18Z

Print mode routes the slash command (`/usage`, alias `/quota`) without a model call.
`agy -p "/help"` lists the commands.

**Two binaries are named `agy`.** The Antigravity IDE puts an editor launcher on PATH
(`~/.antigravity/antigravity/bin/agy`, prints the VS Code style `--diff`/`--goto`
options); the CLI agent is `~/.gemini/bin/agy`. The probe only ever runs the latter.

Session model: conversations are `~/.gemini/antigravity/conversations/<id>.db` (older versions use `antigravity-cli`)
(SQLite; the model is not stored readably). Each CLI run writes
the matching `log/cli-YYYYMMDD_HHMMSS.log` under that same directory, which logs
`selected model override to backend: label="Gemini 3.8 Flash (High)"`. Slash-command
runs write a log too, so the log is matched to the newest conversation by start time.

**Signed out, agy opens a browser.** With an empty HOME, `agy -p "/usage"` printed
`Authentication required. Please visit the URL to log in` and opened the Google sign-in
page. The probe therefore launches agy only when the newest CLI logs contain an
authenticated `v1internal:loadCodeAssist` call, which every signed-in run makes.
`AGY_CLI_DISABLE_AUTO_UPDATE=1` (named in the binary: "Auto-update disabled via
environment variable") stops the self-update on start.

Dead ends (checked 2026-10-02):
1. **`agy models`** — lists model ids and labels, no quota.
2. **`/credits`** — paid G1 credits only; on a free account it errors `no credits info found`.
3. **`--output-format json`** on a real turn — carries token counts, not the model id.
4. **IDE conversation files** under `~/.gemini/antigravity/conversations/*.pb` — encrypted.

## Requirements (moved from SKILL.md)

Do not install anything and do not ask the user to log in. Just run the script and
report what comes back.

- **Python 3.9+**. The POSIX shim selects `python3` before `python`; Windows uses the
  `py -3` launcher when available. `run.py` then re-launches every probe with that exact
  interpreter.
- **At least one** of `claude`, `codex`, `grok`, `muse`, or the Antigravity CLI
  (`~/.gemini/bin/agy`), already signed in. Zero of them is
  still a valid run: every row prints `not installed`.
- **Subprocess and network access.** The host must allow local process launches, and
  each installed provider CLI must be able to reach its own service. Direct
  public HTTP requests the Python code makes are one GET of AI Model Compare's
  `data/aa.json` (`cursorbench.py`), and, for step 0 only,
  one GET of this skill's published `SKILL.md` on `raw.githubusercontent.com`; no
  credential is sent to these public sources. Claude quota and reset grants use
  one authenticated GET to api.anthropic.com; credentials are sent only to that vendor.

If a provider prints `not installed`, show that status in its usage block and Now
cell, but still show its Qualified model, cost and CP from the public benchmarks.
Do not suggest installing it unless the user asks. If a provider is
installed but its call fails, report the failure for that row and still print the
others; never substitute a number from memory or from an earlier run.

## Where each number comes from

All five are live. Claude can use the connected browser Usage page without cookie access.
Otherwise Claude quota windows and reset grants come from one read-only request with
existing CLI OAuth credentials, which is never refreshed or persisted; if it fails, the
windows come from the CLI's `/usage` text. Fresh browser observations can supply resets instead.
Verified 2026-09-12 on macOS, and 2026-09-14 on a zh-TW Windows 11 machine (PowerShell,
Python 3.12) — that run surfaced and fixed a UnicodeDecodeError in the Claude probe
(see Limitations in README).

| Provider | Method |
|---|---|
| Claude | OAuth GET `/api/oauth/usage` using the existing CLI login — see `claude_usage.py` |
| ChatGPT | `codex app-server` → JSON-RPC `account/rateLimits/read` — see `codex_usage.py` |
| Grok | `grok agent stdio` → JSON-RPC `_x.ai/billing` — see `grok_usage.py` |
| Muse | `muse serve` → one tiny turn, then MSP `usage/read` — see `muse_usage.py` |
| Gemini | `~/.gemini/bin/agy -p "/usage"` — the Antigravity CLI's built-in slash command, see `agy_usage.py` |

ChatGPT, Grok and Muse use their CLI's local agent server over stdio. Gemini uses
its CLI's `/usage` command in print mode, and Claude reads Anthropic's OAuth usage
endpoint. Quota windows are fetched live for each report.

**Gemini runs the Antigravity CLI at `~/.gemini/bin/agy`, never the `agy` on PATH.**
The Antigravity IDE installs a launcher with the same name; running it opens the
editor. `/usage` makes no model call and leaves no conversation. A signed-out agy opens
the Google sign-in page in a browser, so the probe only starts agy when the CLI's own log
shows a signed-in run under either `~/.gemini/antigravity/log/` or the older `~/.gemini/antigravity-cli/log/`; otherwise it prints `agy not signed in here … skipped so no
browser opens`. Report that row as not signed in; do not suggest a fix unless asked. The
probe sets `AGY_CLI_DISABLE_AUTO_UPDATE=1` so the CLI does not update itself.

**Muse costs one model call per run.** Muse keeps no usage on disk and reports it only
with a model response, so `muse_usage.py` sends `Reply with the single word: ok` at
`minimal` effort, using the non-contributor twin of the default model when the catalog
lists one. That spends a sliver of Muse quota and leaves one session in Muse's history,
rooted in `<temp>/ai-usage-muse-probe`; `session_info.py muse` skips those sessions.
It is skipped if the model response does not arrive within the launcher's 20-second
budget. It runs with `MUSE_NO_AUTO_UPDATE=1` so the launcher does not
self-update.

After each usage block, `session_info.py <cli>` prints three lines read from that CLI's
newest local session file (no network, nothing launched): `session` (last write time),
`model`, `effort`. These are what the CLI recorded for its last turn, not config
defaults. See the docstring in `session_info.py` for the files
and fields. A `?` means the file did not carry that field — print `?`, never a guess.
One exception: Muse records no effort for TUI turns unless `/effort` was used, and then
runs at its documented default (`muse --help`: "default: high"); the probe prints
`effort  high (default)`. Print it as `effort high (default)`; the AA lookup uses
High.
`no local session` means that CLI has never run here; print it as one row.


## Banked resets (2026-11-07)

`limit_resets.py` formats counts and expiry dates separately from paid credits and
quota-window reset clocks. Dates use `YYYY-MM-DD` and a 24-hour clock,
for example `Reset 1: expires 2026-12-01 03:22 · 23 days 20 hours left`.
Reset expiry dates use the host local timezone by default; a fixed offset can be
set per user in `config.json` (`timezone_offset_minutes`, e.g. 480 for Taipei).
The timezone label and reset titles are omitted. HTML notes are 13px, regular text.
A local timer updates remaining time and reminder colors every minute: normal
beyond 5 hours, orange fading to red within 5 hours, red at 1 hour or less.
The entire expiry row becomes bold with a red border at 30 minutes or less.
The year is always included. Long waits show
days and hours; waits under a day show hours and minutes. ChatGPT uses the documented `rateLimitResetCredits`
field in `account/rateLimits/read` ([schema](https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt));
`availableCount` is authoritative even when details are absent or capped.

Claude uses the undocumented read-only endpoint
`GET https://api.anthropic.com/api/oauth/usage?cedar_ember=1&skip_spend=1`.
The `cedar_ember` grants contain `resets_left`, `starts_at`, `ends_at` and `paused`.
Only currently active grants count; missing or malformed data is unavailable.
Existing CLI auth comes from `CLAUDE_CODE_OAUTH_TOKEN`, the default macOS Keychain
entry, or `.credentials.json` under `CLAUDE_CONFIG_DIR` / the default CLI directory.
The request is vendor-only, blocks redirects, and never refreshes, writes or prints
credentials. A failure affects reset details only, not valid quota windows.
Fresh browser observations may provide visible counts and expiry dates without CLI auth.
Normal probes keep their existing 20-second overall budget. Claude uses one monotonic
deadline for auth status, quota, version and reset lookup. Optional reset stages use
only the remaining time; the outer launcher preserves complete validated quota
windows if a child times out after producing them. Never redeem a reset.

The launcher sets `AI_USAGE_METADATA=1` for probes. Each valid reset expiry adds an
internal `reset-expiry {"note": "Reset ...", "expiresAt": <epoch milliseconds>}`
record immediately after its readable note. The renderer attaches it to that note
position, not its text: two grants can display the same minute but expire at different
seconds. The terminal tee hides these records while saving
them in raw report data; card responses and /finish merges preserve them. HTML uses
the epoch directly, retaining seconds and DST folds. Browser observations use the
same records through the shared formatter. Probes run standalone without this flag
print human-readable notes only. A legacy raw report without metadata is displayed
statically; its timezone-free date string is never used to reconstruct an instant.

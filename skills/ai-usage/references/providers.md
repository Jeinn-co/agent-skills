# Why each provider works the way it does

All five services compute usage server-side and return it in API response headers.
The difference is entirely what each CLI does with that after receiving it.

## Claude — works, live

`claude -p "/usage" < /dev/null` prints the live numbers. Print mode routes built-in
slash commands, so this needs no credentials and no browser.

`< /dev/null` is required, otherwise the CLI waits 3s for stdin and prints a warning.

Claude Code does **not** persist rate-limit state anywhere on disk — checked:
- session jsonl `usage` field carries `input_tokens` / `cache_read_input_tokens` /
  `output_tokens` only, no percentage
- `~/.claude/stats-cache.json` is message and tool-call counts

The binary does contain the full `anthropic-ratelimit-unified-*` header set and the
endpoint `/api/oauth/usage`, which is what `/usage` calls each time.

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

Print mode routes the slash command (`/usage`, alias `/quota`), like Claude's: no model
call, no quota spent, no conversation written. `agy -p "/help"` lists the commands.

**Two binaries are named `agy`.** The Antigravity IDE puts an editor launcher on PATH
(`~/.antigravity/antigravity/bin/agy`, prints the VS Code style `--diff`/`--goto`
options); the CLI agent is `~/.gemini/bin/agy`. The probe only ever runs the latter.

Session model: conversations are `~/.gemini/antigravity-cli/conversations/<id>.db`
(SQLite; the model is not stored readably). Each CLI run writes
`~/.gemini/antigravity-cli/log/cli-YYYYMMDD_HHMMSS.log`, which logs
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
  each installed provider CLI must be able to reach its own service. The only direct
  HTTP requests the Python code makes are one GET of the public page
  `https://cursor.com/cursorbench` (`cursorbench.py`), for a current model
  CursorBench does not list, one GET of its public Artificial Analysis release page
  (`https://artificialanalysis.ai/models/releases/<model id>`), and, for step 0 only,
  one GET of this skill's published `SKILL.md` on `raw.githubusercontent.com`; no
  credential is sent.

If a provider prints `not installed`, show that status in its usage block and Now
cell, but still show its Qualified model, cost and CP from the public benchmarks.
Do not suggest installing it unless the user asks. If a provider is
installed but its call fails, report the failure for that row and still print the
others; never substitute a number from memory or from an earlier run.

## Where each number comes from

All five are live. No browser, no stored credentials, no cookie access.
Verified 2026-09-12 on macOS, and 2026-09-14 on a zh-TW Windows 11 machine (PowerShell,
Python 3.12) — that run surfaced and fixed a UnicodeDecodeError in the Claude probe
(see Limitations in README).

| Provider | Method |
|---|---|
| Claude | `claude -p "/usage" < /dev/null` — print mode routes the built-in slash command |
| ChatGPT | `codex app-server` → JSON-RPC `account/rateLimits/read` — see `codex_usage.py` |
| Grok | `grok agent stdio` → JSON-RPC `_x.ai/billing` — see `grok_usage.py` |
| Muse | `muse serve` → one tiny turn, then MSP `usage/read` — see `muse_usage.py` |
| Gemini | `~/.gemini/bin/agy -p "/usage"` — the Antigravity CLI's built-in slash command, see `agy_usage.py` |

Three of the five are the CLI's own local agent server answering over stdio, and the
other two (Claude, Gemini) route the CLI's own `/usage` command in print mode, so the
numbers are the same ones the TUI shows. Nothing is cached and nothing is scraped.

**Gemini runs the Antigravity CLI at `~/.gemini/bin/agy`, never the `agy` on PATH.**
The Antigravity IDE installs a launcher with the same name; running it opens the
editor. `/usage` makes no model call and leaves no conversation. A signed-out agy opens
the Google sign-in page in a browser, so the probe only starts agy when the CLI's own log
shows a signed-in run; otherwise it prints `agy not signed in here … skipped so no
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
`effort  high (default)`. Print it as `effort high (default)`; CursorBench looks it up
as High.
`no local session` means that CLI has never run here; print it as one row.


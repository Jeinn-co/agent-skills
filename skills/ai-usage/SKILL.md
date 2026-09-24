---
name: ai-usage
description: Check AI subscription usage limits across Claude, ChatGPT, Grok and Muse in one unified report — percent used, how much is left, when each window resets, the model / effort of each CLI's newest session, and that model's CursorBench score, cost and CP. Use when the user runs /ai-usage or /uu, or asks 額度, 用量, usage, limit, 還剩多少, 什麼時候 reset, 被限流了嗎, rate limit, quota, "am I out of Claude", "how much ChatGPT left", Muse 額度.
compatibility: Requires Python 3.9+ and permission to launch subprocesses. Each provider shown needs its authenticated CLI and internet access; providers without a CLI are reported as unavailable.
metadata:
  author: Jeinn
  version: "1.4.0"
---

# /ai-usage — unified AI usage report

Run the platform launcher from this skill's directory: `./run.sh` on macOS or Linux;
`py -3 run.py` on Windows, falling back to `python run.py` if `py` is unavailable.
Reformat its output into the table below. Nothing else. No browser, no stored
credentials, and no direct HTTP calls of your own.

`/ai-usage fresh` — same thing; the script always reads live. The flag only means "do not
reuse an answer from earlier in this conversation".

The first output line is `### ai-usage <version>`. Put that version at the end of the
report's title line (`USAGE — <time> · ai-usage <version>`), so every report shows
which release produced it. This remains useful
for manually copied installations even though `npx skills` records source information
for installations it manages. Adding `--version` to the platform command prints the
version alone.

## What must already be in place

Do not install anything and do not ask the user to log in. Just run the script and
report what comes back.

- **Python 3.9+**. The POSIX shim selects `python3` before `python`; Windows uses the
  `py -3` launcher when available. `run.py` then re-launches every probe with that exact
  interpreter.
- **At least one** of `claude`, `codex`, `grok`, `muse`, already signed in. Zero of them is
  still a valid run: every row prints `not installed`.
- **Subprocess and network access.** The host must allow local process launches, and
  each installed provider CLI must be able to reach its own service. The only direct
  HTTP request the Python code makes is one GET of the public page
  `https://cursor.com/cursorbench` (`cursorbench.py`); no credential is sent.

If a provider prints `not installed`, that is the whole answer for that row — say so
and move on. Do not suggest installing it unless the user asks. If a provider is
installed but its call fails, report the failure for that row and still print the
others; never substitute a number from memory or from an earlier run.

## Where each number comes from

All four are live. No browser, no stored credentials, no cookie access.
Verified 2026-09-12 on macOS, and 2026-09-14 on a zh-TW Windows 11 machine (PowerShell,
Python 3.12) — that run surfaced and fixed a UnicodeDecodeError in the Claude probe
(see Limitations in README).

| Provider | Method |
|---|---|
| Claude | `claude -p "/usage" < /dev/null` — print mode routes the built-in slash command |
| ChatGPT | `codex app-server` → JSON-RPC `account/rateLimits/read` — see `codex_usage.py` |
| Grok | `grok agent stdio` → JSON-RPC `_x.ai/billing` — see `grok_usage.py` |
| Muse | `muse serve` → one tiny turn, then MSP `usage/read` — see `muse_usage.py` |

Three of the four are the CLI's own local agent server answering over stdio, so the
numbers are the same ones the TUI shows. Nothing is cached and nothing is scraped.

**Muse costs one model call per run.** Muse keeps no usage on disk and reports it only
with a model response, so `muse_usage.py` sends `Reply with the single word: ok` at
`minimal` effort, using the non-contributor twin of the default model when the catalog
lists one. That spends a sliver of Muse quota and leaves one session in Muse's history,
rooted in `<temp>/ai-usage-muse-probe`; `session_info.py muse` skips those sessions.
It takes about 15 s. It runs with `MUSE_NO_AUTO_UPDATE=1` so the launcher does not
self-update.

After each usage block, `session_info.py <cli>` prints three lines read from that CLI's
newest local session file (no network, nothing launched): `session` (last write time),
`model`, `effort`. These are what the CLI recorded for its last turn, not config
defaults. See the docstring in `session_info.py` for the files
and fields. A `?` means the file did not carry that field — print `?`, never a guess.
`no local session` means that CLI has never run here; print it as one row.

## Reading the output

**Claude** — current session (5h) and current week. Claude omits the reset clock
when a window is 0% used; still print that row, without inventing a reset time.

**ChatGPT** — `short` (5h) and `outer` (7d), plus `plan`. Do **not** print a
"Usage limit resets" / "resets available" row. That count is not readable locally
(the app-server can spend one via `account/rateLimitResetCredit/consume` but has
no read counterpart). Do not print `unknown (web only)` either. `credits.balance`
is a different pool (paid top-ups) and is never that reset count.

**Grok** — weekly `creditUsagePercent` and the billing period end when the
percent is present. `_x.ai/billing` sometimes omits `creditUsagePercent`; the
probe then prints `percent omitted`. Print that week row without a bar or
percent, still print the reset clock, and do not invent 0%. Print prepaid /
on-demand only when any of those values is non-zero. Do not print
`prepaid 0 / on-demand 0`. Grok has only one window, not two — do not invent a
5h row for it. Do not pick Grok as the tool to use just because the percent is
missing.

**Muse** — `plan: ?` (Muse reports a numeric tier id, not a plan name), a 5h window and a
week, both with reset clocks. Show the plan as `?`; do not map the id to a plan name.

**CursorBench** — after the four providers, `### CURSORBENCH` holds one `bench` line per
CLI with a local session (the CursorBench row for that CLI's current model + effort, or
`not listed`), then one `pick` line per CLI: the effort of that same model with the best
`cp` that scores at least 50%, searched across every model and effort CursorBench lists
for that provider; when none reaches 50%, the provider's highest score. `rule cp` /
`rule closest` says which applied. A CLI whose current model is unlisted gets `pick …
not listed`. `cp` is score ÷ cost per task: points per US dollar at Cursor's API
prices, not the subscription price. `(mapped from …-contributor)` means the CLI runs
Muse's contributor variant and the row is plain Muse Spark. `bench failed (...)` means
the page could not be fetched or parsed: print that one line and keep the rest.

Do not label any of these "redeem" unless the provider itself uses that concept.
Claude's current CLI response does not expose a reliable extra-usage field.
`fast_mode_disabled_reason` describes fast mode and must never be presented as extra
usage.

## Output

```
USAGE — 09-12 01:08 · ai-usage 1.4.0

  Claude    pro
    5h    ███░░░░░░░  29%   resets 03:40 (2h32m)
    week  ████░░░░░░  41%   resets Mon 17:00 (2d16h)
    now   claude-opus-5 · effort high   (0m ago)

  ChatGPT   plus
    5h    ░░░░░░░░░░   0%   resets 05:55 (4h47m)
    week  ░░░░░░░░░░   0%   resets 09-18 17:07 (6d15h)
    now   gpt-5.6-sol · effort high   (3m ago)

  Grok      SuperGrok
    week  ███░░░░░░░  27%   resets 09-15 09:38 (3d8h)
    now   grok-4.7 · effort high   (6m ago)

  Muse      ?
    5h    █░░░░░░░░░   5%   resets 16:24 (2h20m)
    week  ░░░░░░░░░░   1%   resets 09-28 08:00 (3d17h)
    now   muse-spark-1.3 · effort high   (2m ago)

  Qualified (CursorBench)
    Standard: any of the provider's models ≥ 50% → highest CP among those · none reach 50% → its highest score
    Provider  Now                          Now CP  Qualified                       Qualified CP
    Claude    Opus 5.5 High · 56.0%        14.1    Opus 5.5 Medium · 52.5%         18.0
    ChatGPT   GPT-6 Sol High · not listed  —       —                               —
    Grok      Grok 4.7 High · 43.9%         9.4    Grok 4.7 Extra High · 46.3% *    7.7
    Muse      Muse Spark 1.3 Max · 41.6%   15.8    Muse Spark 1.3 Max · 41.6% *    15.8

  CP = score ÷ cost per task at Cursor's API prices; higher is better. * nothing from this provider reaches 50%: its highest.
  Muse is scored as plain Muse Spark 1.3.

  ⚠ ChatGPT week is 92% used; resets in 2h23m.
  → Use Claude right now: the highest score, and its 5h window is 21% used.
```

Rules:
- Bars 10 chars, `█` used / `░` free. Percentages are whole numbers.
- Relative time next to every reset clock. If the probe omitted the reset (Claude
  5h at 0% used), omit the reset clause — do not invent a time. If the probe
  omitted the percent (Grok `percent omitted`), omit the bar and percent — do
  not invent 0%. Still print the reset clock.
- Never print ChatGPT "resets available" / "Usage limit resets", including
  `unknown (web only)`.
- Never invent a 5h row for Grok.
- Muse's plan is always `?`; never print its numeric tier id.
- Never print Grok prepaid / on-demand when every value is 0.
- One `now` row per provider from the session lines: model · effort, then the
  session age in parentheses. Never print the project folder. Omit the `now` row only when the probe printed
  `no local session`; then print `now   no local session`.
- Qualified table: exactly one row per provider, in provider order, merged from that
  provider's `bench` line (Now: model effort · score, then its CP) and `pick` line
  (Qualified: model effort · score, then its CP), all exactly as printed. Each side has
  its own score and its own CP column, so no number reads as the other side's. No cost
  column. The `Standard` line
  always prints, unshortened, directly under the header (Chinese: 「合格標準：同一家任一模型 ≥ 50% 者取 CP 最高 ·
  整家都達不到 50% 則取該家最高分」). Mark a Qualified cell whose `pick` line says
  `rule closest` with `*` and keep the `*` footnote (「* 這家沒有任何模型／強度到 50%，
  取最高的一檔」). The Qualified model can differ from the Now model (e.g. Fable 5.1). Chinese labels: 「服務」, 「目前」,
  「目前 CP」, 「合格」, 「合格 CP」, header 「合格（CursorBench）」 — never 「推薦」.
  A `bench … not listed` shows `not listed` in Now; a `pick … not listed` shows `—` in every Qualified column. Never borrow another model's
  or effort's numbers. Keep the filter to the one header line and the formula to the
  one footnote line, as in the sample; the footnote says higher is better, because a
  bare "CP" reads as a cost.
  In Chinese never write the unit as a bare 「分」 (it also means a cent): write
  「CursorBench 分數 ÷ 美元」 or 「每 1 美元換到的分數」. A `(mapped from …)` row gets the
  short clause at the end of that footnote, not a line of its own.
  Omit the table only for `bench failed`, and say it failed.
- The pick rule lives in `cursorbench.py` (across the provider's listed models: ≥ 50% →
  highest CP; otherwise the highest score). Do not re-pick
  by hand or re-rank by today's usage.
- The `→` line is the last line: which tool to use right now, and why in a few words.
- If any week row is over 80%, put a `⚠` line above the arrow saying how long until it
  resets.
- A provider whose CLI is not installed prints `not installed` and is shown as one
  greyed row. Never drop it silently.
- No preamble, no recap, no closing offer.
- Write the whole report in the language the user wrote their request in: labels,
  the Qualified header and footnote, the `⚠` and `→` lines. The sample above is English only as a template. Translate the
  English text that comes from the probes; never translate model
  ids, numbers, dates or times. With no user text to go by (a bare `/ai-usage`), use
  the language of the conversation so far, else English.

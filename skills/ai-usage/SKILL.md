---
name: ai-usage
description: Check AI subscription usage limits across Claude, ChatGPT and Grok in one unified report — percent used, how much is left, when each window resets, the model / effort of each CLI's newest session, and a cost-effectiveness recommendation. Use when the user runs /ai-usage or /uu, or asks 額度, 用量, usage, limit, 還剩多少, 什麼時候 reset, 被限流了嗎, rate limit, quota, "am I out of Claude", "how much ChatGPT left".
compatibility: Requires Python 3.9+ and permission to launch subprocesses. Each provider shown needs its authenticated CLI and internet access; providers without a CLI are reported as unavailable.
metadata:
  author: Jeinn
  version: "1.2.0"
---

# /ai-usage — unified AI usage report

Run the platform launcher from this skill's directory: `./run.sh` on macOS or Linux;
`py -3 run.py` on Windows, falling back to `python run.py` if `py` is unavailable.
Reformat its output into the table below. Nothing else. No browser, no stored
credentials, and no direct HTTP calls of your own.

`/ai-usage fresh` — same thing; the script always reads live. The flag only means "do not
reuse an answer from earlier in this conversation".

The first output line is `### ai-usage <version>`. Do not put it in the report. Quote it
only when the user asks which version they are on or reports a bug. This remains useful
for manually copied installations even though `npx skills` records source information
for installations it manages. Adding `--version` to the platform command prints the
version alone.

## What must already be in place

Do not install anything and do not ask the user to log in. Just run the script and
report what comes back.

- **Python 3.9+**. The POSIX shim selects `python3` before `python`; Windows uses the
  `py -3` launcher when available. `run.py` then re-launches every probe with that exact
  interpreter.
- **At least one** of `claude`, `codex`, `grok`, already signed in. Zero of them is
  still a valid run: every row prints `not installed`.
- **Subprocess and network access.** The host must allow local process launches, and
  each installed provider CLI must be able to reach its own service. The Python code
  does not make direct HTTP requests.

If a provider prints `not installed`, that is the whole answer for that row — say so
and move on. Do not suggest installing it unless the user asks. If a provider is
installed but its call fails, report the failure for that row and still print the
others; never substitute a number from memory or from an earlier run.

## Where each number comes from

All three are live. No browser, no stored credentials, no cookie access.
Verified 2026-09-12 on macOS, and 2026-09-14 on a zh-TW Windows 11 machine (PowerShell,
Python 3.12) — that run surfaced and fixed a UnicodeDecodeError in the Claude probe
(see Limitations in README).

| Provider | Method |
|---|---|
| Claude | `claude -p "/usage" < /dev/null` — print mode routes the built-in slash command |
| ChatGPT | `codex app-server` → JSON-RPC `account/rateLimits/read` — see `codex_usage.py` |
| Grok | `grok agent stdio` → JSON-RPC `_x.ai/billing` — see `grok_usage.py` |

Two of the three are the CLI's own local agent server answering over stdio, so the
numbers are the same ones the TUI shows. Nothing is cached and nothing is scraped.

After each usage block, `session_info.py <cli>` prints four lines read from that CLI's
newest local session file (no network, nothing launched): `session` (last write time),
`model`, `effort`, then one `option` line per model that CLI offers (from its own
model cache: id, effort levels, default, vendor description), then one `value` line: the
shared model + effort pick from `value.json`, or `value   stale` when a model was added
or dropped since that pick was made. A `profile` line follows a valid pick: what the shared set is
tuned for. These are what the CLI recorded for its
last turn, not config defaults. See the docstring in `session_info.py` for the files
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

Do not label any of these "redeem" unless the provider itself uses that concept.
Claude's current CLI response does not expose a reliable extra-usage field.
`fast_mode_disabled_reason` describes fast mode and must never be presented as extra
usage.

## Output

```
USAGE — 09-12 01:08

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

  Value (evaluated 2026-09-22) — quality-leaning: Plan, Coding, Review, Bug Fix, Testing
    Claude   Opus 5 High
    ChatGPT  GPT-5.6 Sol High
    Grok     Grok 4.7 High

  → Use ChatGPT right now. Both windows are fresh.
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
- Never print Grok prepaid / on-demand when every value is 0.
- One `now` row per provider from the session lines: model · effort, then the
  session age in parentheses. Never print the project folder. Omit the `now` row only when the probe printed
  `no local session`; then print `now   no local session`.
- `Value` block: one line per provider — its `value` pick as `<Model> <Effort>`, nothing
  else. This pick is shared and fixed: do not re-rank it by today's usage, and do not
  print `why` unless asked. The header carries the `evaluated` date and the `profile`
  text (once, not per provider).
- A `value   stale` line means a model shipped or was withdrawn. Only then re-evaluate,
  and always delegate it to Codex; do not judge it yourself:
  1. Save the full probe output to a scratch file, then run from this skill's directory
     `codex exec --ephemeral --skip-git-repo-check -s read-only -o <scratch>/value.new.json -`
     with stdin = this prompt, the current `value.json`, and the probe output:
     "Update this value.json for every provider marked `value stale`. For each: set
     `models` to every current `option` id, and pick the best cost-effectiveness
     default (`pick`, `effort`) that stays quality-leaning (fit for Plan,
     Coding, Review, Bug Fix, Testing), choosing only from the
     `option` lines and their effort levels. Keep providers that are not stale
     unchanged. Set `evaluated` to today. Reply with the JSON only."
  2. Check the reply parses as JSON and every `pick` is one of that provider's
     `option` ids. If not, keep the old `value.json` and say Codex's answer was
     rejected and why.
  3. Otherwise write it over `value.json` in this skill's directory, show the user the
     old → new pick in one line per provider, and say `value.json` changed and should
     be committed to the skill's source repo so every user gets it.
  If `codex` is not installed, print the stored pick with `(stale)` and do not guess.
  Never cite prices or per-token costs; they are not in the probe output.
- Last line names which tool to use right now, and why in a few words.
- If any week row is over 80%, put a `⚠` line above the arrow saying how long until it
  resets.
- A provider whose CLI is not installed prints `not installed` and is shown as one
  greyed row. Never drop it silently.
- No preamble, no recap, no closing offer.
- Write the whole report in the language the user wrote their request in: labels,
  the `Value` header and `profile` text, the `⚠` and `→` lines, and any stale or
  rejection note. The sample above is English only as a template. Translate the
  English text that comes from the probes and `value.json`; never translate model
  ids, numbers, dates or times. With no user text to go by (a bare `/ai-usage`), use
  the language of the conversation so far, else English.

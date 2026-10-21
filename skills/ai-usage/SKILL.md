---
name: ai-usage
description: Check AI subscription usage limits across Claude, ChatGPT, Grok, Muse and Gemini (Antigravity CLI) in one unified report — percent used, how much is left, when each window resets, the model / effort of each CLI's newest session, and that model's CursorBench score, cost and CP. `setup` chooses which providers to report. It first checks GitHub for a newer version of itself and asks y/n before updating. Use when the user runs /ai-usage or /uu (with or without `setup`), or asks about usage, limits, remaining quota, reset times, rate limits, "am I out of Claude", "how much ChatGPT left", Muse usage, Gemini usage or Antigravity quota, including equivalent requests in any language.
compatibility: Requires Python 3.9+ and permission to launch subprocesses. Each provider shown needs its authenticated CLI and internet access; providers without a CLI are reported as unavailable. The update check reads raw.githubusercontent.com.
metadata:
  author: Jeinn
  version: "1.12.0"
---

# /ai-usage — unified AI usage report

Run the platform launcher from this skill's directory: `./run.sh` on macOS or Linux;
`py -3 run.py` on Windows, falling back to `python run.py` if `py` is unavailable.
Reformat its output into the table below. Nothing else. No browser, no stored
credentials, and no direct HTTP calls of your own.

The launcher starts all five providers and their local session reads concurrently.
Benchmark requests start as soon as model/effort is known, overlapping the usage
lookups. Results are printed in provider order without mixing output.
Each provider lookup gets at most **20 seconds total**, including
CLI startup and every request in that probe. On timeout it stops the probe and its
CLI children, prints a timeout for that provider, and continues without retrying.
The benchmark lookup has the same 20-second budget; if it times out, report its
failure and keep the usage blocks. Never extend a timeout for a missing subscription.

`/ai-usage fresh` — same thing; the script always reads live. The flag only means "do not
reuse an answer from earlier in this conversation".

The first output line is `### ai-usage <version>`. Put that version at the end of the
report's heading (`### Usage — <time> · ai-usage <version>`), so every report shows
which release produced it. This remains useful
for manually copied installations even though `npx skills` records source information
for installations it manages. Adding `--version` to the platform command prints the
version alone.

## Step 0 — check this skill for an update first

Before anything else (the report, or `setup`), run the platform launcher with
`--check-skill`. It makes one GET of this skill's `SKILL.md` on GitHub `main`
(`raw.githubusercontent.com`) and prints one line:
`skill installed=… latest=… status=… update_cmd=…`, or `skill check failed (...)`.

- `status=up to date` or `check failed`: say nothing about it and continue.
- `status=update available`: print only

  ```
  ai-usage skill {installed} → {latest} is available.
  Update the skill now?
  [y] Update    [n] Skip
  ```

  and stop. Run nothing else this turn.
  - Exact `y` / `Y`: run `update_cmd`, report success or failure in one line, then read
    this skill's `SKILL.md` again from disk (it is now the new version) and continue
    with what the user asked for, following the new instructions.
  - `n` / `N`: say the skill was not updated and continue with what the user
    asked for.
  - Any other reply: repeat the two choices without updating.

The report itself never includes this line.

## What must already be in place

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

## Reading the output

**Bar** — every `% used` line ends with `bar` and 20 cells from `portable.usage_bar`.
Copy that glyph string. Do not redraw it from the whole-number percent.

**Claude** — current session (5h) and current week. Claude omits the reset clock
when a window is 0% used; still print that row, without inventing a reset time.

**ChatGPT** — `short` (5h) and `outer` (7d), plus `plan`. Do **not** print a
"Usage limit resets" / "resets available" row. That count is not readable locally
(the app-server can spend one via `account/rateLimitResetCredit/consume` but has
no read counterpart). Do not print `unknown (web only)` either. `credits.balance`
is a different pool (paid top-ups) and is never that reset count.

**Grok** — weekly `creditUsagePercent` and the billing period end when the
percent is present. `_x.ai/billing` reports whole percents and omits
`creditUsagePercent` while it is 0 (e.g. right after the weekly reset); the
probe then prints `<1% used` with an empty bar. Show it as `<1%`, never `0%`
and never "no percent". Print prepaid /
on-demand only when any of those values is non-zero. Do not print
`prepaid 0 / on-demand 0`. Grok has only one window, not two — do not invent a
5h row for it.

**Gemini** — two weekly pools from the Antigravity CLI: `gemini` (Gemini models) and
`cl+gpt` (the Claude and GPT models Antigravity also offers), each with a reset clock.
The CLI reports what is left; the probe prints it as used. `plan: ?` always — `/usage`
names no plan. There is no 5h row; never invent one.

**Muse** — `plan:` is the plan name when `muse_usage.py` knows the numeric tier id
(`TIER_NAMES`, e.g. `High Usage`), else `?`; a 5h window and a week, both with reset
clocks. Print the plan exactly as the probe does; never map an id by hand.

**CursorBench** — after the five providers, `### CURSORBENCH` holds one `bench` line per
CLI with a local session (the CursorBench row for that CLI's current model + effort, or
`not listed`), or `bench <cli> no local session` when there is none, then one `pick`
line per provider, including providers without an installed CLI or a local session.
Their Qualified model is selected from that provider's public benchmark rows using
the same rule and AA extras; never invent a current model or quota for them.
The `pick` line selects the best `cp` among rows scoring at least 50%, searched
across every model and effort CursorBench lists for that provider; when none
reaches 50%, it selects the provider's highest score. `rule cp` /
`rule closest` says which applied. A CLI whose current model is unlisted gets `pick …
not listed` — unless Artificial Analysis has a page for it: then its `bench` and `pick`
lines end in `(AA)` and carry `aa <index>` (the AA Intelligence Index, a different test
set) instead of a CursorBench percent, with AA's cost, speed (median output tok/s),
verbosity (index output tokens, e.g. `25M`) and latency (time to first answer token),
and the same pick
rule applied to that model's own efforts. When a provider's own pick is only `rule
closest`, a model listed in `AA_EXTRA` (`cursorbench.py`; Gemini 4 Argon for Gemini, GPT-6.1 Sol for ChatGPT) whose
own AA pick reaches 50 takes the `pick` line, marked `(AA)` and `rule cp`, even though the
Now side is a CursorBench row — the user asked for it. Only when AA has no page either does a `ref`
line follow, naming the newest listed same-provider row at the same effort —
orientation only, never compared. `cp` is score ÷ cost per task: points per US dollar at Cursor's API
prices, not the subscription price. `(mapped from …-contributor)` means the CLI runs
Muse's contributor variant and the row is plain Muse Spark; it applies even when the
effort is `?` (`bench muse  Muse Spark 1.3  ?  not listed  (mapped from …)`), so the Now
cell shows the mapped name — `Muse Spark 1.3 ? · not listed` — never the raw
`-contributor` id. `bench failed (...)` means
the page could not be fetched or parsed: print that one line and keep the rest.

Do not label any of these "redeem" unless the provider itself uses that concept.
Claude's current CLI response does not expose a reliable extra-usage field.
`fast_mode_disabled_reason` describes fast mode and must never be presented as extra
usage.

## Output format — HTML (default) or Markdown

Setup saves the format; `html` is the default when nothing is saved. There is no
command argument for it — only `setup` changes it. `--show-providers` prints `output=html`
or `output=md`.

- **html**: the launcher prints its usual raw lines, then writes a Morandi-palette page (cards with colour bars, a thin time bar under each one showing the time left in that window — full length 5 hours or 7 days, filled from the right — the Qualified table, links) to
  `<temp>/ai-usage/report.html`, opens it in the default browser, and ends with
  `### HTML <path>` (plus `(could not open a browser)` when that failed). The page is
  drawn by Python with no scripts and no external requests, so it costs no model
  tokens. In chat, print only:
  1. the `→` line as a blockquote (and the warning line above it, if any week row is over 80%),
  2. `**Report:** [Open the HTML report](file:///<path with forward slashes>)`, and a short
     note when the browser could not be opened.
  Do not print the Markdown report as well.
- **md**: no file is written; render the Markdown report below in chat.

## Output (Markdown)

<!-- Keep every dollar amount in this file from starting with a dollar sign then the digit zero: Claude Code replaces that token with the first skill argument (for example /ai-usage setup). -->

Render the report as **Markdown**, not inside a code block: a heading, a usage table, a
`Now` list, the Qualified table, footnotes, the `→` line and the links. Bars stay in
inline code so every font draws them at the same width. Sample:

### Usage — 09-12 01:08 · ai-usage 1.12.0

| Provider | Window | Used | Bar | Resets |
|---|---|--:|---|---|
| **Claude** · pro | 5h | 29% | `█████▊░░░░░░░░░░░░░░` | 03:40 (2h32m) |
| | week | 41% | `████████▎░░░░░░░░░░░` | Mon 17:00 (2d16h) |
| **ChatGPT** · plus | 5h | 0% | `░░░░░░░░░░░░░░░░░░░░` | 05:55 (4h47m) |
| | week | 0% | `░░░░░░░░░░░░░░░░░░░░` | 09-18 17:07 (6d15h) |
| **Grok** · SuperGrok | week | 27% | `█████▍░░░░░░░░░░░░░░` | 09-15 09:38 (3d8h) |
| **Muse** · ? | 5h | 5% | `█░░░░░░░░░░░░░░░░░░░` | 16:24 (2h20m) |
| | week | 1% | `▎░░░░░░░░░░░░░░░░░░░` | 09-28 08:00 (3d17h) |
| **Gemini** · ? | gemini | 12% | `██▌░░░░░░░░░░░░░░░░░` | 09-19 04:09 (6d23h) |
| | cl+gpt | 0% | `░░░░░░░░░░░░░░░░░░░░` | 09-19 04:09 (6d23h) |

**Now**
- Claude — `claude-opus-5` · effort high · 0m ago
- ChatGPT — `gpt-6.1-sol` · effort high · 3m ago
- Grok — `grok-4.7` · effort high · 6m ago
- Muse — `muse-spark-1.3` · effort high · 2m ago
- Gemini — `gemini-3.8-flash` · effort high · 5m ago

#### Qualified (CursorBench)

_Standard: any of the provider's models ≥ 50% → highest CP among those · none reach 50% → its highest score_

| Provider | Now | Now $ | Now CP | Qualified | Qualified $ | Qualified CP |
|---|---|--:|--:|---|--:|--:|
| Claude | Opus 5.5 High · 56.0% | $3.97 | 14.1 | Opus 5.5 Medium · 52.5% | $2.91 | 18.0 |
| ChatGPT | GPT-6.1 Sol High · AA 50 · 50.9/s · 25M · 46.6s | $1.32 | 37.9 | GPT-6.1 Sol High · AA 50 | $1.32 | 37.9 |
| Grok | Grok 4.7 High · 43.9% | $4.69 | 9.4 | Grok 4.7 Extra High · 46.3% \* | $6.01 | 7.7 |
| Muse | Muse Spark 1.3 Max · 41.6% | $2.64 | 15.8 | Muse Spark 1.3 Max · 41.6% \* | $2.64 | 15.8 |
| Gemini | Gemini 3.8 Flash High · 39.6% | $4.70 | 8.4 | Gemini 4 Argon High · AA 53 | $1.99 | 26.4 |

_$ = cost per task at API prices (AA rows: AA's cost per index task), not subscription quota. CP = score ÷ $; higher is better. \* nothing from this provider reaches 50%: its highest._
_Muse is scored as plain Muse Spark 1.3. AA = Artificial Analysis Intelligence Index (another test set): its score and CP are not comparable with CursorBench's._

> **→ Use Claude right now:** the highest CursorBench score, and its 5h window is 29% used.

**Usage pages:** [Claude](https://claude.ai/new#settings/usage) · [ChatGPT](https://chatgpt.com/settings/usage?tab=overview) · [Grok](https://grok.com/?_s=home)
**Compare models:** [AI Model Compare](https://jeinn-co.github.io/ai-model-compare/)

Rules:
- **Markdown layout.** Never wrap the report in a code block. One usage-table row per
  window; the provider name (bold) and plan go only on its first row, later rows leave
  that cell empty. A provider with no window to show (`not installed`, a failed or
  timed-out call, not signed in) gets one row: Window and Used `—`, Bar empty, and the
  status or failure reason in Resets. Escape a literal `*` or `|` inside a table cell
  with a backslash.
- Copy each window's `bar` exactly, inside inline code. It is 20 cells: each cell is 5 points, and the partial cell is one eighth (`▏▎▍▌▋▊▉`), so 28% and 30% no longer draw the same bar. Full cell `█`, empty track `░`. Do not redraw it and do not shorten it to 10 cells. The displayed percent stays a whole number.
- Keep icons to a minimum: no emoji or status lights anywhere in the report. Used is a plain percent; bold it when it is 80% or more.
- Relative time next to every reset clock. If the probe omitted the reset (Claude
  5h at 0% used), omit the reset clause — do not invent a time. Grok `<1% used`
  prints as `<1%` with the probe's empty bar.
- Never print ChatGPT "resets available" / "Usage limit resets", including
  `unknown (web only)`.
- Never invent a 5h row for Grok or Gemini. Gemini's two rows are its two weekly pools, labelled `gemini` and `cl+gpt` in the Window column.
- Muse's plan is what the probe prints (a known plan name or `?`); never print its numeric tier id.
- Never print Grok prepaid / on-demand when every value is 0.
- The `Now` list has one item per reported provider from its session lines:
  ``<Provider> — `<model>` · effort <effort> · <age> ago``. Never print the project
  folder. When the probe printed `no local session`, the item reads
  `<Provider> — no local session`; when the CLI is not installed, `<Provider> — not installed`.
- Qualified table: exactly one row per provider, in provider order, merged from that
  provider's `bench` line (Now: model effort · score, then its CP) and `pick` line
  (Qualified: model effort · score, then its CP), all exactly as printed. Each side has
  its own score, its own `$` column (the line's `cost`, two decimals, as printed) and its
  own CP column, so no number reads as the other side's. No tokens column. The `Standard` line
  always prints, unshortened and in italics, directly under the `Qualified (CursorBench)`
  heading. Mark a Qualified cell whose
  `pick` line says `rule closest` with `*` and keep the `*` footnote explaining that
  this provider has no model or effort at 50%, so its highest score is shown.
  The Qualified model can differ from the Now model (e.g. Fable 5.1). Use the labels
  Provider, Now, Now $, Now CP, Qualified, Qualified $, Qualified CP and the header
  Qualified (CursorBench). When localizing, preserve the meaning of Qualified;
  do not relabel it as Recommended.
  An `(AA)` line fills its Now cell as `<model effort> · AA <index> · <speed> · <verbosity> · <latency>`
  (the five AA model-page figures: index, cost in the `$` column, speed, verbosity, latency)
  and its Qualified cell as `<model effort> · AA <index>`, no percent sign, and adds the AA
  clause to the footnote explaining that AA is the Artificial Analysis Intelligence
  Index, a different test set whose scores and CP cannot be compared with CursorBench.
  Copy `speed` / `verbosity` / `latency`
  from the `bench` line onto Now only; a missing one is `?`. An `(AA)` row never decides the `→` line
  on score or CP against CursorBench rows.
  A `bench … not listed` shows `not listed` in Now; a `pick … not listed` shows `—` in every Qualified column. When a `ref` line exists for that provider, add one table row directly under its row with Provider `↳ ref` and the Now cell `<model effort> · <score> · CP <cp>`, other cells empty. Never borrow another model's
  or effort's numbers. Keep the filter to the one header line and the formula to the
  one footnote line, as in the sample; the footnote says higher is better, because a
  bare "CP" reads as a cost.
  The `$` footnote states cost per task at API prices (AA rows: AA's cost per index
  task), not subscription quota. When localizing CP's unit, spell out score points
  per US dollar so it cannot be mistaken for cents. A `(mapped from …)` row gets the
  short clause at the end of that footnote, not a line of its own.
  Omit the table only for `bench failed`, and say it failed.
- The pick rule lives in `cursorbench.py` (across the provider's listed models: ≥ 50% →
  highest CP; otherwise the highest score). Do not re-pick
  by hand or re-rank by today's usage.
- The `→` line is a blockquote, `> **→ Use <tool> right now:** <why in a few words>`.
- **Links** follow it as Markdown links, so they are clickable. First the
  `**Usage pages:**` line: one link per provider shown in this report (never a provider
  skipped by setup) that has a URL below, in provider order, joined with ` · `. Omit a
  provider with no URL; omit the whole line when none is left.

  | Provider | URL |
  |---|---|
  | Claude | `https://claude.ai/new#settings/usage` |
  | ChatGPT | `https://chatgpt.com/settings/usage?tab=overview` |
  | Grok | `https://grok.com/?_s=home` (opens Settings; the usage section appears on paid plans) |
  | Muse | none yet |
  | Gemini | none yet |

- Then, always, the last line: `**Compare models:** [AI Model Compare](https://jeinn-co.github.io/ai-model-compare/)`.
  Keep every URL exactly as written.
- If any week row is over 80%, put a `> **Warning:** …` blockquote line above the `→` line saying how
  long until it resets.
- A provider whose CLI is not installed prints `not installed` in its usage row
  and Now cell, with `—` for Now $ and Now CP. Keep its Qualified model, Qualified $
  and Qualified CP populated from its `pick` line. A provider with no local session
  uses `no local session` in Now unless its usage block says `not installed`.
  Never drop it silently or select an unavailable CLI for the final `→` action.
- **Skipped providers.** When setup has narrowed the list, the launcher prints
  `### skipped <ids>` after the version line and no usage block, `bench` or `pick` line
  for them. Show no usage row, Now item or table row for them; add one italic line
  directly above the `→` line: `_Not checked (setup): Muse, Gemini_`. The `→` line picks only among the
  reported providers.
- No preamble, no recap, no closing offer.
- Use the report language resolved below for every label, the Qualified header and
  footnotes, the warning and `→` lines, and readable status or error explanations.

## Setup — choose which providers to report

`/ai-usage setup` (alias `/uu setup`) changes which providers the report covers and the output format. It does
not run the report. Provider ids: `claude` (Claude), `codex` (ChatGPT), `grok` (Grok),
`muse` (Muse), `agy` (Gemini).

1. Run the platform launcher with `--show-providers`; it prints `providers=<ids>`, the
   current selection (every provider when nothing is saved), and `installed=<ids>`, the
   providers whose CLI is present. Offer only installed providers; one that is not
   installed is never saved.
2. Ask about the providers — **keep first**, one question per page, never split across
   several questions or tabs. A choice tool cannot pre-tick boxes, so never show an empty
   checkbox list for a selection the user already made.
   - With a choice tool (Claude Code: `AskUserQuestion`), first ask one single-select
     question, header `Report`: `Report — now: <current names>. Keep or change?` with
     options `Keep` (description: the current names) and `Change…` (description: the
     installed providers to pick from). `Keep` saves nothing for this step.
   - Only after `Change…`: ask one `multiSelect: true` question, header `Report`, one
     option per installed provider (at most 4 options; with 5 installed, use numbers
     instead), describing each as currently on or off.
   - Without a choice tool, show the current selection and ask for `keep`, numbers
     (`1,2`) or `all`.
3. Save with `--set-providers <ids>` (e.g. `--set-providers claude,codex`), or
   `--set-providers all` when every provider is chosen and every CLI is installed. It
   prints the saved `providers=<ids>`. Nothing chosen, a dismissed picker, or an invalid
   reply saves nothing: say the selection is unchanged.
4. Then ask the output format the same way — one single-select question, header
   `Output`: `Output — now: <HTML|Markdown>. Keep or change?` with options `Keep`
   (description: the current format) and the other format (`HTML` — a page opened in the
   browser, or `Markdown` — shown in chat). Without a choice tool, ask `keep`, `html` or
   `md`. Save only a change, with `--set-output html` or `--set-output md`; `Keep` or a
   dismissed question keeps the format.
5. Report one line: `Reporting: <names> · Not reported: <names> · Output: <HTML|Markdown>`,
   or `Reporting all providers · Output: <HTML|Markdown>`.

The selection is saved in `~/.config/ai-usage/config.json` (`$XDG_CONFIG_HOME` when set),
outside the skill folder, so reinstalling or updating the skill keeps it. Skipped
providers launch no CLI, so Muse spends no probe call while it is skipped.

## Language

The canonical documentation, examples and scripts' own data and status messages are
English. Resolve the agent-rendered report language in this order:

1. A language explicitly requested by the user for this report.
2. The computer's OS display or preferred language, only when the host provides it.
3. English when neither is available.

Do not infer a language from the current or earlier conversation, the timezone,
country, an encoding such as cp950, or a regional date/number format. A bare
`/ai-usage` follows the same order. The scripts do not detect the OS display language
or localize raw output. Translate readable prose only; keep model IDs, numbers,
dates, times, commands and error codes unchanged. Preserve provider diagnostics
verbatim when needed to explain a failure, even if a provider supplied localized text.

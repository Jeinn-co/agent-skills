# Markdown report (`output=md`)

Read this only when setup saved `output=md`. The launcher's `### ADVICE` lines are the warning and `→` lines: copy them, never re-pick.

## Reading the raw output

**Bar** — every `% used` line ends with `bar` and 20 cells from `portable.usage_bar`.
Copy that glyph string. Do not redraw it from the whole-number percent.
Internal `reset-expiry` JSON records, if reading a saved raw report directly, are
HTML timer metadata: omit them from Markdown. The normal launcher already hides them.

**Claude** — current session (5h) and current week. Claude omits the reset clock
when a window is 0% used; still print that row, without inventing a reset time.

**ChatGPT** — `short` (5h) and `outer` (7d), plus `plan`. Below the usage table,
copy the probe's `Usage limit resets` count and each reset's expiry (including
time left). `availableCount` is authoritative; details may be partial or absent.
`credits.balance` is paid top-ups, never the reset count. For Claude, also copy
the probe's `Limit resets` count and each grant's expiry below the usage table.
Missing auth, unsupported APIs or absent fields mean unavailable,
never zero. Never call a consume/reset method.

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

**Qualified (Artificial Analysis)** — after the five providers, `### CURSORBENCH` (the
section keeps its old name) holds one `bench` line per CLI with a local session (the
Artificial Analysis row for that CLI's current model + effort, or `not listed`), or
`bench <cli> no local session` when there is none, then one `pick` line per provider,
including providers without an installed CLI or a local session. Never invent a current
model or quota for them. Every line ends in `(AA)` and carries `aa <index>` (the AA
Intelligence Index) with AA's cost per index task; a `bench` line adds speed (median
output tok/s), verbosity (index output tokens, e.g. `25M`) and latency (time to first
answer token). The `pick` line selects the best `cp` among rows scoring at least 45,
searched across every model and effort AA lists for that provider; when none reaches 45,
it selects the provider's highest score. `rule cp` / `rule closest` says which applied.
Models in `UNAVAILABLE` (`cursorbench.py`; Gemini 4 Carbon) are never picked. `cp` is
index points / cost per task: points per US dollar at API prices, not the subscription
price. `(mapped from …-contributor)` means the CLI runs
Muse's contributor variant and the row is plain Muse Spark; it applies even when the
effort is `?` (`bench muse  Muse Spark 1.3  ?  not listed  (mapped from …)`), so the Now
cell shows the mapped name — `Muse Spark 1.3 ? · not listed` — never the raw
`-contributor` id. `bench failed (...)` means
the page could not be fetched or parsed: print that one line and keep the rest.

Do not label any of these "redeem" unless the provider itself uses that concept.
Claude's current CLI response does not expose a reliable extra-usage field.
`fast_mode_disabled_reason` describes fast mode and must never be presented as extra
usage.

## Output (Markdown)

<!-- Keep every dollar amount in this file from starting with a dollar sign then the digit zero: Claude Code replaces that token with the first skill argument (for example /ai-usage setup). -->

Render the report as **Markdown**, not inside a code block: a heading, a usage table, a
`Now` list, the Qualified table, footnotes, the `→` line and the links. Bars stay in
inline code so every font draws them at the same width. Sample:

### Usage — 09-12 01:08 · ai-usage 1.16.1

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

#### My usage

Before the Qualified table, render both personal-usage tables from `html_report.py` in the report language: daily defaults with effort-first escalation, and the six s-agent role assignments. Preserve full model versions, effort values, the snapshot date and Notion source link. State how the defaults were chosen (Artificial Analysis, dominated options skipped, daily default the cheapest remaining option scoring at least 45, cross-checked with ARC-AGI-2 and Terminal-Bench) and keep the note on Gemini 4 Carbon's limited access and the footnote on Gemini availability, that the effort-first escalation order itself is a workflow choice, that model availability depends on the account, and the role table is a static snapshot rather than a live Notion read or a change to CLI settings. Do not include the former general Model and effort guide.

#### Qualified (Artificial Analysis)

_Standard: any of the provider's models scoring ≥ 45 on the Artificial Analysis Intelligence Index → highest CP among those · none reach 45 → its highest score._

| Provider | Now | Now $ | Now CP | Qualified | Qualified $ | Qualified CP |
|---|---|--:|--:|---|--:|--:|
| Claude | Opus 5.5 High · 51.8 · ? · 56M · ? | $3.46 | 15.0 | Opus 5.5 Medium · 48.2 | $2.45 | 19.7 |
| ChatGPT | GPT-6.1 Sol High · 50.3 · ? · 25M · ? | $0.59 | 85.2 | GPT-6.1 Sol Medium · 46.3 | $0.36 | 129.0 |
| Grok | no local session | | | Grok 4.7 Extra High · 35.5 \* | $7.77 | 4.6 |
| Muse | Muse Spark 1.3 Max · 36.6 · ? · 123M · ? | $2.39 | 15.3 | Muse Wonder Max · 43.6 \* | $6.95 | 6.3 |
| Gemini | Gemini 3.8 Flash High · 30.8 · ? · 126M · ? | $7.77 | 4.0 | Gemini 4 Argon High · 50.4 | $9.95 | 5.1 |

_$ = Artificial Analysis's cost per index task at API prices, not subscription quota. CP = index points ÷ $; higher is better. \* nothing from this provider reaches 45: its highest._
_Muse is scored as plain Muse Spark 1.3._

> **→ Use ChatGPT right now:** the most usage left — 100% in its tightest window.

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
- Include reset counts and expiry details exactly as printed; never infer a count from paid credits.
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
  always prints, unshortened and in italics, directly under the `Qualified (Artificial Analysis)`
  heading. Mark a Qualified cell whose
  `pick` line says `rule closest` with `*` and keep the `*` footnote explaining that
  this provider has no model or effort at 45, so its highest score is shown.
  The Qualified model can differ from the Now model (e.g. Fable 5.1). Use the labels
  Provider, Now, Now $, Now CP, Qualified, Qualified $, Qualified CP and the header
  Qualified (Artificial Analysis). When localizing, preserve the meaning of Qualified;
  do not relabel it as Recommended.
  The Now cell is `<model effort> · <index> · <speed> · <verbosity> · <latency>`
  (the five AA model-page figures: index, cost in the `$` column, speed, verbosity, latency)
  and the Qualified cell `<model effort> · <index>`, no percent sign and no `AA` label. Copy `speed` /
  `verbosity` / `latency` from the `bench` line onto Now only; a missing one is `?`.
  A `bench … not listed` shows `not listed` in Now; a `pick … not listed` shows `—` in every Qualified column. Never borrow another model's
  or effort's numbers. Keep the filter to the one header line and the formula to the
  one footnote line, as in the sample; the footnote says higher is better, because a
  bare "CP" reads as a cost.
  The `$` footnote states Artificial Analysis's cost per index task at API prices, not subscription
  quota. When localizing CP's unit, spell out index points
  per US dollar so it cannot be mistaken for cents. A `(mapped from …)` row gets the
  short clause at the end of that footnote, not a line of its own.
  Omit the table only for `bench failed`, and say it failed.
- The pick rule lives in `cursorbench.py` (across the provider's AA models: ≥ 45 →
  highest CP; otherwise the highest score; `UNAVAILABLE` models skipped). Do not re-pick
  by hand or re-rank by today's usage. That applies to the Qualified table only; the
  `→` line below is chosen by usage left.
- The warning and `→` lines are the launcher's `### ADVICE` lines (headroom = 100 −
  tightest window; near ties go to the higher AA score, see `advice()` in
  `html_report.py`). Copy them; never re-pick.
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


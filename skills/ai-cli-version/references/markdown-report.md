# Markdown report (`output=md`)

Read this only when setup saved `output=md`.

No file is written in this mode; render the Markdown report below in chat. The HTML
report is described in `SKILL.md`.

## Report (Markdown)

Render the report as **Markdown**, not inside a code block, so tables align and links are
clickable. Sample:

### CLI versions — 09-17

| Tool | Installed | Latest | Status |
|---|---|---|---|
| Claude Code | 2.1.274 · 09/17 11:20 | 2.1.274 · released 09/17 06:36 | up to date · channel latest |
| Codex | 0.153.4 · 09/07 11:03 | 0.154.0 · released 09/10 06:40 | **update** → `codex update` |
| Grok Build | 1.0.34 · 09/17 09:28 | 1.0.34 · released ≤ 09/17 03:32\* | up to date · channel stable |
| Muse Code | 1.3.0-R3401.1 · 09/24 11:08 | 1.3.0-R3401.1 · released ? | up to date · channel muse-stable |
| Antigravity | 1.2.14 · 09/30 10:57 | 1.2.14 · released ? | up to date · channel stable |

_\* Grok release time is approximate (third-party mirror); official: x.ai/build/changelog_

> **→ 1 update available:** Codex.

**Compare models:** [AI Model Compare](https://jeinn-co.github.io/ai-model-compare/)

**Update the 1 outdated CLI now?**
`[y]` Update all · `[Esc]` Skip

**When no row has `status=update available`, print the short form instead of the table**
and no prompt — one row per tool with its installed version. The heading says
`all up to date` only when every selected check succeeded; when any row is
`check failed (...)`, it says `check incomplete` instead:

### CLI versions — 10-20 · all up to date

| Tool | Version |
|---|---|
| Claude Code | 2.1.304 |
| Codex | 0.163.0 |
| Grok Build | 1.0.62 |
| Muse Code | 1.4.11-R6667.1 |
| Antigravity | not installed |

**Compare models:** [AI Model Compare](https://jeinn-co.github.io/ai-model-compare/)

`not installed` and `check failed (...)` rows still appear in the short form, with their
reason in the Version cell, and the `### SUMMARY` line names the failed tools. As soon as one tool is outdated, print the full table above.

**Skipped tools.** When setup has narrowed the list, the launcher prints
`### skipped <ids>` after the version line and no row for those tools. Do not show a
row for them; add one italic line directly under the `→` line (or under the short-form
table), before the Compare models link: `_Not checked (setup): Grok Build, Muse Code, Antigravity_`.

### CLI versions — 10-20

| Tool | Installed | Latest | Status |
|---|---|---|---|
| Claude Code | 2.1.303 · 10/19 16:13 | 2.1.304 · released 10/20 03:47 | **update** → `claude update` |
| Codex | 0.163.0 · 10/19 16:14 | 0.163.0 · released 10/16 05:37 | up to date · channel latest |

> **→ 1 update available:** Claude Code.

_Not checked (setup): Grok Build, Muse Code, Antigravity_

**Compare models:** [AI Model Compare](https://jeinn-co.github.io/ai-model-compare/)

**Update the 1 outdated CLI now?**
`[y]` Update all · `[Esc]` Skip

Rules:
- Never wrap the report in a code block. Escape a literal `*` or `|` inside a table cell
  with a backslash.
- Show every tool the launcher printed. `not installed` and `check failed (...)` get their own row with the
  reason in the Installed cell and `—` in the others; never drop a row, and never fill in a version or time from memory.
- Show `?` for an unknown time; do not guess.
- Grok's release time always gets `≤` and the footnote.
- Muse's and Antigravity's release times are always `?`; do not fill them in from anywhere else.
- Label the `agy` row `Antigravity` (it is the Gemini CLI) and print its update command
  exactly as `update_cmd` gives it — a full path, never a bare `agy update`.
- Keep icons to a minimum: no emoji or status marks. Status reads `up to date · channel <channel>`, ``**update** → `<update_cmd>` ``, `check failed (...)` or `not installed`. Update rows end with the update command in inline code.
- `ahead of channel` means the installed build is newer than the channel tag — show it
  as-is, not as an error.
- Summary, `Not checked (setup)` line and update prompt: copy the launcher's `### SUMMARY`
  lines (the short form puts `all up to date` or `check incomplete` in its heading instead of the summary line; a `Check failed` summary line is still printed).
- `**Compare models:** [AI Model Compare](https://jeinn-co.github.io/ai-model-compare/)` always follows the report (after the summary and any `Not checked (setup)`
  line), before any update prompt. Keep the URL exactly as written.
- Use the report language resolved below for labels, readable status and error
  explanations, and update results.


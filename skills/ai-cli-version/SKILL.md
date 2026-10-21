---
name: ai-cli-version
description: Check whether the Claude Code, Codex, Grok Build, Muse Code and Antigravity (Gemini) CLIs are up to date, then optionally update outdated CLIs after a y/Esc choice. `setup` chooses which CLIs to check. It first checks GitHub for a newer version of itself and asks y/n before updating. Use when the user runs /ai-cli-version or /check-uu (with or without `setup`), or asks to check for updates, whether a CLI has a newer version, when a version was released or installed, "is my CLI up to date", or "when was this released", including equivalent requests in any language.
compatibility: Requires Python 3.9+, permission to launch subprocesses, and internet access to registry.npmjs.org, api.github.com, raw.githubusercontent.com, api.meta.ai and the Antigravity CLI auto-updater (run.app). Each tool shown needs its CLI installed; missing tools are reported as not installed. npm and Node.js are not required. Tested on Windows and macOS; Linux is not yet tested.
metadata:
  author: Jeinn
  version: "1.9.1"
---

# /ai-cli-version — CLI version and update check

Run the platform launcher from this skill's directory: `./run.sh` on macOS or Linux
(`sh run.sh` if it is not executable);
`py -3 run.py` on Windows, falling back to `python run.py` if `py` is unavailable.
Reformat its output into the report below, then follow the optional update flow.

All five checks start concurrently. Each tool has a **10-second total budget** for
CLI startup and every network request; a timeout stops that check and its CLI
children without retrying or delaying the other tools. Output stays in tool order.

The launcher is check-only and must never install anything. During the check phase, do
not run `claude update`, `codex update`, or `grok update` without `--check`, and do not
run Muse with `MUSE_SYNC_UPDATE=1`.

The first output line is `### ai-cli-version <version>`. Leave it out of the report; quote
it only when the user asks which version they are on or reports a bug. Adding `--version`
to the platform command prints the version alone.

## Step 0 — check this skill for an update first

Before anything else (the report, or `setup`), run the platform launcher with
`--check-skill`. It makes one GET of this skill's `SKILL.md` on GitHub `main`
(`raw.githubusercontent.com`) and prints one line:
`skill installed=… latest=… status=… update_cmd=…`, or `skill check failed (...)`.

- `status=up to date` or `check failed`: say nothing about it and continue.
- `status=update available`: print only

  ```
  ai-cli-version skill {installed} → {latest} is available.
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

The CLI check itself (step 1 onward) never includes this line.

## What is checked

Only the **latest** version and the **currently installed** version — no history.

| Tool | Installed version | Installed at | Latest version | Released |
|---|---|---|---|---|
| Claude Code | `claude --version` | `~/.local/share/claude/versions/<installed>` | npm `@anthropic-ai/claude-code`, dist-tag = `autoUpdatesChannel` in `settings.json` under `$CLAUDE_CONFIG_DIR` or `~/.claude` (default `latest`) | npm publish time |
| Codex | `codex --version` | `$CODEX_HOME` (default `~/.codex`) `/packages/standalone/releases/<installed>-*` | npm `@openai/codex`, dist-tag `latest` | npm publish time |
| Grok Build | `grok update --check --json` | `~/.grok/downloads/grok-<installed>-*` | same call | **approximate** — see below |
| Antigravity CLI | `~/.gemini/bin/agy --version` | the `agy` binary itself | the CLI's auto-updater: `Stable Version` on `https://antigravity-cli-auto-updater-974169037036.us-central1.run.app` | **not available** — see below |
| Muse Code | `muse --version` with `MUSE_NO_AUTO_UPDATE=1` | `muse-bin-<installed>*` next to the `muse` launcher | `https://api.meta.ai/muse-code/channels/<channel>`, channel = `$MUSE_CHANNEL`, else `.muse-channel` next to the launcher (default `muse-stable`) | **not available** — see below |

- `claude update` and `codex update` install immediately and have no check-only flag, so
  their latest version comes from the npm registry (queried over HTTP; npm is not needed).
  Grok Build has `--check`.
- **Installed at** is the folder's creation time (Windows, macOS) or modified time (Linux).
  If that path is missing — an npm or Homebrew install, or the macOS/Linux Grok
  installer, which stores builds without a version in the name — the real executable
  behind the command is used instead, then its folder.
- **Tested on Windows and macOS.** On Linux, if the script fails or a value looks wrong,
  report it as-is and mention that this platform has not been tested yet.
- A `check failed (... CERTIFICATE_VERIFY_FAILED ...)` on macOS means a python.org Python
  whose `Install Certificates.command` was never run. Say so; do not work around it. Timestamps before 2015 are discarded (npm extracts files
  with a fixed 1985 date).
- **Grok release time is approximate.** The official changelog (`x.ai/build/changelog`)
  blocks scripted requests, so the time comes from the GitHub release of the third-party
  NixOS package `timoteuszelle/x.ai-grok`, which auto-detects new versions. The official
  release is no later than that time.
- **Muse Code has no release time.** Its channel manifest — the same unauthenticated
  file the launcher reads — carries a version and nothing else dated, so `released=?`
  always. Versions look like `1.3.0-R3401.1`; the `R` build orders releases that share a
  semver. Muse's launcher self-updates in the background whenever it runs; the check
  sets `MUSE_NO_AUTO_UPDATE=1` so it stays check-only. There is no `muse update`: the
  update command forces the launcher's own synchronous update (`MUSE_SYNC_UPDATE=1`)
  and prints the new version.

- **Antigravity CLI is `~/.gemini/bin/agy`, never the `agy` on PATH.** The Antigravity IDE
  installs an editor launcher with the same name; running it opens a window. The update
  command is the full path, `~/.gemini/bin/agy update`. Its auto-updater lists versions
  without dates, so `released=?` always; the note says how far the rollout has gone.
  The CLI also updates itself when it starts, so the check runs `agy --version` with
  `AGY_CLI_DISABLE_AUTO_UPDATE=1` to stay read-only.

Each tool line is tab-separated:
`name installed=… installed_at=… latest=… released=… released_note=… channel=… status=… update_cmd=…`,
or `name<TAB>not installed`, or `name<TAB>check failed (<reason>)`. Times are local
`MM/DD HH:MM`; `?` means unknown.

## Output format — HTML (default) or Markdown

Setup saves the format; `html` is the default when nothing is saved. There is no
command argument for it — only `setup` changes it. `--show-tools` prints `output=html`
or `output=md`.

- **html**: the launcher prints its usual raw lines, then writes a Morandi-palette page (the version table with status badges) to
  `<temp>/ai-cli-version/report.html`, opens it in the default browser, and ends with
  `### HTML <path>` (plus `(could not open a browser)` when that failed). The page is
  drawn by Python with no scripts and no external requests, so it costs no model
  tokens. In chat, print only:
  1. the summary as a blockquote (`> **→ N update(s) available:** <tools>.` or
     `> **All up to date.**`),
  2. `**Report:** [Open the HTML report](file:///<path with forward slashes>)`, and a short
     note when the browser could not be opened,
  3. the update prompt below when anything is outdated.
  Do not print the Markdown report as well.
- **md**: no file is written; render the Markdown report below in chat.

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
and no prompt — the heading says everything is current, then one row per tool with its
installed version:

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
reason in the Version cell. As soon as one tool is outdated, print the full table above.

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
- Summary: a blockquote `> **→ N update(s) available:** <tools>.` in the full form; the
  short form says `all up to date` in its heading instead.
- `**Compare models:** [AI Model Compare](https://jeinn-co.github.io/ai-model-compare/)` always follows the report (after the summary and any `Not checked (setup)`
  line), before any update prompt. Keep the URL exactly as written.
- Use the report language resolved below for labels, readable status and error
  explanations, and update results.

## Language

The canonical documentation, examples and scripts' own data and status messages are
English. Resolve the agent-rendered report language in this order:

1. A language explicitly requested by the user for this report.
2. The computer's OS display or preferred language, only when the host provides it.
3. English when neither is available.

Do not infer a language from the current or earlier conversation, the timezone,
country, an encoding such as cp950, or a regional date/number format. A bare
`/ai-cli-version` follows the same order. The script does not detect the OS display
language or localize raw output. Translate readable prose only; keep tool names,
versions, dates, commands and error codes unchanged. Preserve provider diagnostics
verbatim when needed to explain a failure, even if a provider supplied localized text.
Use the same resolved language for the report, update prompt and update results.

## Setup — choose which tools to check

`/ai-cli-version setup` (alias `/check-uu setup`) changes which tools the check runs and the output format. It
does not run the check or any updater. Tool ids: `claude`, `codex`, `grok`, `muse`, `agy`.

1. Run the platform launcher with `--show-tools`; it prints `tools=<ids>`, the current
   selection (every tool when nothing is saved), and `installed=<ids>`, the tools whose
   CLI is present. Offer only installed tools; a tool that is not installed is never
   saved, so it drops out of later checks.
2. Ask which tools to check — **one question on one page**, never split across several
   questions or tabs.
   - With a multi-select choice tool and no more than 4 installed tools (Claude Code:
     `AskUserQuestion` allows at most 4 options), ask one `multiSelect: true` question,
     header `Check`, one option per installed tool. Boxes cannot start ticked, so put
     the current selection in the question text (`Now checking: Claude Code, Codex. Tick
     every CLI to check.`) and give each option a plain description such as `checked now`
     or `skipped now`.
   - Otherwise (no such tool, or 5 installed tools) list the installed tools numbered
     and ask for numbers (`1,2,3`) or `all`.
3. Save with `--set-tools <ids>` (comma-separated, e.g. `--set-tools claude,codex,grok`),
   or `--set-tools all` when every tool is chosen and every tool is installed. It prints the saved `tools=<ids>`.
   Nothing chosen, a dismissed picker, or an invalid reply saves nothing: say the
   selection is unchanged.
4. Then ask the output format — again one question on one page (`AskUserQuestion`, single
   select, header `Output`), marking the current one: `HTML` (default — a page opened in
   the browser) or `Markdown` (in chat). Without a choice tool, ask `html` or `md`. Save
   with `--set-output html` or `--set-output md`; a dismissed question keeps the format.
5. Report one line: `Checking: <names> · Not checked: <names> · Output: <HTML|Markdown>`,
   or `Checking all tools · Output: <HTML|Markdown>`.

The selection is saved in `~/.config/ai-cli-version/config.json` (`$XDG_CONFIG_HOME`
when set), outside the skill folder, so reinstalling or updating the skill keeps it.

## Optional update

Only when one or more rows have `status=update available`, append a two-choice prompt in
the report's resolved language and stop. Keep the keys exactly `y` and `Esc`:

**Update the N outdated CLIs now?**
`[y]` Update all · `[Esc]` Skip

- `/ai-cli-version` authorizes the check, not an update. Do not run any updater in the
  same turn as the initial report.
- A subsequent exact `y` or `Y` authorizes every `update_cmd` from the immediately
  preceding report whose status was `update available`. Run those commands separately,
  so one failure does not prevent the remaining updates.
- `Esc` or `Escape` skips all updates. Confirm that no updates were run.
- Any other reply is not authorization. Repeat the two valid choices without updating.
- After `y`, show success or failure for every selected tool, then run the check-only
  launcher again and show the refreshed report. Do not show another prompt for a tool
  whose updater failed during that same update attempt.
- If all tools are current, or the user explicitly asked for check-only behavior, do not
  show the prompt.
- No preamble, recap, or closing offer outside the report, prompt, and update results.

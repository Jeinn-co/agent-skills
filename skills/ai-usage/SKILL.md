---
name: ai-usage
description: Check AI subscription usage limits across Claude, ChatGPT, Grok, Muse and Gemini (Antigravity CLI) in one unified report — percent used, how much is left, when each window resets, banked reset counts and expiry dates for Claude and ChatGPT, the model / effort of each CLI's newest session, and that model's Artificial Analysis score, cost and CP. `setup` chooses which providers to report. It first checks GitHub for a newer version of itself and asks y/n before updating. Use when the user runs /ai-usage or /uu (with or without `setup`), or asks about usage, limits, remaining quota, reset times, rate limits, "am I out of Claude", "how much ChatGPT left", Muse usage, Gemini usage or Antigravity quota, including equivalent requests in any language.
metadata:
  author: Jeinn
  version: "1.23.5"
---


# /ai-usage — unified AI usage report

Requirements: Requires Python 3.9+ and permission to launch subprocesses. Each provider shown needs its authenticated CLI and internet access; providers without a CLI are reported as unavailable. The update check reads raw.githubusercontent.com.

Launcher, from this skill's directory: `./run.sh` on macOS or Linux; `py -3 run.py` on
Windows (`python run.py` if `py` is missing). Never install anything or start a login
flow automatically. When browser tools are available, read Claude's already signed-in
browser as described below; do not extract cookies or make HTTP calls of your own. Report only what the
launcher prints; never fill a number from memory or an earlier run.

## Step 0 — update check

Run the launcher with `--check-skill`. It prints one line,
`skill installed=… latest=… status=… update_cmd=…` or `skill check failed (...)`.

- `up to date` or `check failed`: say nothing and continue.
- `update available`: print only

  ```
  ai-usage skill {installed} → {latest} is available.
  Update the skill now?
  [y] Update    [n] Skip
  ```

  and stop. On exact `y`/`Y` run `update_cmd`, report it in one line, re-read this
  `SKILL.md` from disk and continue with the user's request. On `n`/`N` say it was not
  updated and continue. Any other reply: repeat the two choices.

`setup` (`/ai-usage setup`, `/uu setup`): read `references/setup.md` and follow it; do
not run the report.

## Report

Read the selection with `--show-providers`. When Claude is selected, follow
[references/claude-browser.md](references/claude-browser.md)
to read its Usage page using an available connected-browser tool. Respect the user's
browser choice; no particular connector or browser is assumed to exist. A fresh browser observation
takes priority over CLI auth. Refresh this observation on every `/uu` invocation;
clear the previous observation before attempting a new capture, as documented there.
never reuse an earlier report as a new observation. When no browser tool exists, skip
this optional adapter without asking the user to install one. If browser access is unavailable,
the launcher still tries the CLI. Only when both sources fail should the report
point the user to the Usage page to sign in; never demand CLI login while the web login works.

Run the launcher (no arguments; `fresh` only means do not reuse an earlier answer).
Each provider has a 20-second budget; never extend it. Claude quota and reset
lookups share one deadline; reset details only use the remaining time. If optional
details time out, retain complete validated quota windows and report resets unavailable.

When Claude or ChatGPT CLI auth has expired, the served HTML report offers
**Sign in to Claude** or **Sign in to ChatGPT**. Only the user's click starts the
provider's official browser flow (`claude auth login --claudeai` or `codex login`);
never click it or start that flow automatically. After the CLI confirms sign-in, the
page refreshes usage. Static HTML files use the terminal-command fallback instead.

- **Output**: the last line is `### HTML <target>`, an
  `http://127.0.0.1:…/` URL (the local page with a Refresh button) or a file path. Print
  only, with no preamble or recap:
  1. the `### ADVICE` lines as they are (a `> **Warning:**` line when a week window is
     over 80%, then the `> **→ Use … right now:**` line); nothing when the block is empty;
  2. `_Not checked (setup): <names>_` when a `### skipped <ids>` line exists
     (ids: claude Claude, codex ChatGPT, grok Grok, muse Muse, agy Gemini);
  3. `**Report:** [Open the HTML report](<target>)`: the URL as printed, or
     `file:///<path with forward slashes>` for a path. Add a short note for each
     parenthesised note on that line (`Refresh unavailable: …`, `could not open a browser`).

Do not suggest installing a missing CLI unless asked. `references/providers.md`
explains where each number comes from. Banked resets are read-only: never redeem a
reset. Claude prefers a fresh browser observation; otherwise one OAuth usage
request reads both quota windows and reset grants using existing CLI credentials.
This read never refreshes or writes credentials. If the request fails, the probe
falls back to CLI `/usage`. ChatGPT uses `account/rateLimits/read`, including reset details.
Original expiry epochs are carried in internal `reset-expiry` JSON records for HTML;
these records are hidden from normal terminal output. Legacy text-only
reports display static expiry text without guessing an instant from a local date.

The Claude probe reads the CLI's existing OAuth login (environment, Keychain or
credentials file) and sends its access token only to Anthropic's usage endpoint; it
falls back to `claude -p /usage` when that request fails.
Let the probe handle credentials and report its errors without printing tokens.

## Language

Use a language the user explicitly asked for, else the OS display language when the
host provides it, else English. Never infer it from the conversation, timezone or
encoding. Translate readable prose only; keep model IDs, numbers, times, commands and
provider diagnostics unchanged.

---
name: ai-cli-version
description: Check whether the Claude Code, Codex, Grok Build and Muse Code CLIs are up to date, then optionally update outdated CLIs after a y/Esc choice. Use when the user runs /ai-cli-version or /check-uu, or asks 檢查更新, CLI 有沒有新版, claude/codex/grok/muse 要不要更新, 什麼時候發佈, 我什麼時候更新的, "is my CLI up to date", "when was this released".
compatibility: Requires Python 3.9+, permission to launch subprocesses, and internet access to registry.npmjs.org, api.github.com and api.meta.ai. Each tool shown needs its CLI installed; missing tools are reported as not installed. npm and Node.js are not required. Tested on Windows and macOS; Linux is not yet tested.
metadata:
  author: Jeinn
  version: "1.2.0"
---

# /ai-cli-version — CLI version and update check

Run the platform launcher from this skill's directory: `./run.sh` on macOS or Linux
(`sh run.sh` if it is not executable);
`py -3 run.py` on Windows, falling back to `python run.py` if `py` is unavailable.
Reformat its output into the report below, then follow the optional update flow.

The launcher is check-only and must never install anything. During the check phase, do
not run `claude update`, `codex update`, or `grok update` without `--check`, and do not
run Muse with `MUSE_SYNC_UPDATE=1`.

The first output line is `### ai-cli-version <version>`. Leave it out of the report; quote
it only when the user asks which version they are on or reports a bug. Adding `--version`
to the platform command prints the version alone.

## What is checked

Only the **latest** version and the **currently installed** version — no history.

| Tool | Installed version | Installed at | Latest version | Released |
|---|---|---|---|---|
| Claude Code | `claude --version` | `~/.local/share/claude/versions/<installed>` | npm `@anthropic-ai/claude-code`, dist-tag = `autoUpdatesChannel` in `settings.json` under `$CLAUDE_CONFIG_DIR` or `~/.claude` (default `latest`) | npm publish time |
| Codex | `codex --version` | `$CODEX_HOME` (default `~/.codex`) `/packages/standalone/releases/<installed>-*` | npm `@openai/codex`, dist-tag `latest` | npm publish time |
| Grok Build | `grok update --check --json` | `~/.grok/downloads/grok-<installed>-*` | same call | **approximate** — see below |
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

Each tool line is tab-separated:
`name installed=… installed_at=… latest=… released=… released_note=… channel=… status=… update_cmd=…`,
or `name<TAB>not installed`, or `name<TAB>check failed (<reason>)`. Times are local
`MM/DD HH:MM`; `?` means unknown.

## Report

```
CLI VERSIONS — 09-17

  Tool          Installed               Latest                             Status
  Claude Code   2.1.274 (09/17 11:20)   2.1.274 (released 09/17 06:36)     ✓ up to date      channel: latest
  Codex         0.153.4 (09/07 11:03)   0.154.0 (released 09/10 06:40)     ↑ update → codex update
  Grok Build    1.0.34  (09/17 09:28)   1.0.34  (released ≤ 09/17 03:32*)  ✓ up to date      channel: stable
  Muse Code     1.3.0-R3401.1 (09/24 11:08)   1.3.0-R3401.1 (released ?)   ✓ up to date   channel: muse-stable

  * Grok release time is approximate (third-party mirror); official: x.ai/build/changelog
  → 1 update available: Codex.

  Update the 1 outdated CLI now?
  [y] Update all    [Esc] Skip
```

Rules:
- Show every tool. `not installed` and `check failed (...)` get their own row with the
  reason; never drop a row, and never fill in a version or time from memory.
- Show `?` for an unknown time; do not guess.
- Grok's release time always gets `≤` and the footnote.
- Muse's release time is always `?`; do not fill it in from anywhere else.
- `↑ update` rows end with the update command.
- `ahead of channel` means the installed build is newer than the channel tag — show it
  as-is, not as an error.
- Last report line: how many updates are available and for which tools, or `All up to date.`
- Match the user's language for labels.

## Optional update

Only when one or more rows have `status=update available`, append a two-choice prompt in
the user's language and stop. Keep the keys exactly `y` and `Esc`:

```
Update the N outdated CLIs now?
[y] Update all    [Esc] Skip
```

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

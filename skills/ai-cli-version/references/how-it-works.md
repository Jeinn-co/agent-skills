# How each version is checked

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


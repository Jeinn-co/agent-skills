# ai-cli-version

One report for whether your Claude Code, Codex and Grok Build CLIs are up to date — the
version you have and when you installed it, the latest version and when it was released.

The version check is always read-only. When an update is available, the agent offers two
choices: `y` updates every outdated CLI, while `Esc` skips all updates.

Works in Claude Code, Codex CLI, Grok Build, and anything else that reads the `SKILL.md`
convention. Nothing here depends on a particular host.

> **Tested on Windows and macOS. Linux has not been tested yet.** The code has a Linux
> path and the install locations were checked against the vendors' install scripts, but
> it has never been run there. If it fails, please open an issue with the output of
> `./run.sh`.

繁體中文說明：[README.zh-TW.md](README.zh-TW.md)

## Before you install

### 1. Python 3.9 or newer

Standard library only, no `pip install`, no virtualenv.

```bash
python --version     # or: python3 --version   /   py --version  (Windows)
```

On Windows, avoid the `python3` alias: it is often a Microsoft Store stub that opens the
store instead of running anything.

On macOS, `/usr/bin/python3` (3.9) comes with the Xcode Command Line Tools; if they are
missing, the first run pops up an installer instead. Homebrew's `python3` also works. If
you installed Python from python.org, run its `Install Certificates.command` once —
without it every HTTPS request fails with `CERTIFICATE_VERIFY_FAILED` and each tool shows
`check failed`.

### 2. The CLIs you want checked

| Tool | CLI |
|---|---|
| Claude Code | `claude` |
| Codex | `codex` |
| Grok Build | `grok` |

**You do not need all three.** A tool that is not installed prints `not installed`; the
others still run. Signing in is not required to read versions.

### 3. Network and subprocess access

The skill launches the CLIs above and makes HTTPS requests to `registry.npmjs.org` and
`api.github.com`. **npm and Node.js are not required** — the registry is queried directly.

## Install

Global install, for all three CLIs at once:

```bash
npx skills add Jeinn-co/agent-skills@ai-cli-version -g -a claude-code codex grok -y
```

Drop `-a ...` to pick agents interactively, or name just the ones you use. `-g` installs
into your home directory, so every project sees it:

| Agent (`-a`) | Global skills folder |
|---|---|
| `claude-code` | `~/.claude/skills/` (or `$CLAUDE_CONFIG_DIR/skills/`) |
| `codex` | `~/.codex/skills/` (or `$CODEX_HOME/skills/`) |
| `grok` | `~/.grok/skills/` (or `$GROK_HOME/skills/`) |

Without `-g` it installs into the current project instead.

Or copy the `skills/ai-cli-version/` directory into those folders yourself. On Windows,
copy rather than symlink. On macOS or Linux, check that `run.sh` is still executable
after copying (`chmod +x run.sh`).

If `/ai-cli-version` is not visible immediately, start a new conversation or restart the
agent so it reloads its skill list.

## Update

```bash
npx skills update ai-cli-version -g -y    # global install
npx skills update ai-cli-version -p -y    # project install
```

A manually copied skill is not tracked; copy the directory again to update it.

## Usage

Type the skill name as a slash command:

    /ai-cli-version

Or just ask — "is my CLI up to date?", "檢查更新", "when was this Codex released?". It reads
live every time; there is no cache or flag. If one or more versions are outdated, it
shows the report and waits for an explicit `y` before running their update commands.
Choose `Esc` to leave every CLI unchanged.

To run it outside an agent, change into the installed `ai-cli-version` directory — for
example `~/.claude/skills/ai-cli-version` — then use the launcher for your platform:

```bash
./run.sh          # macOS or Linux (or `sh run.sh` if it lost its executable bit)
py -3 run.py      # Windows; use `python run.py` if `py` is unavailable
```

Add `--version` to print the skill version and exit. Outside an agent you get the raw
tab-separated lines, not the formatted report.

## What it prints

`/ai-cli-version` in Claude Code, including the optional `y` update:

![ai-cli-version running in Claude Code](images/demo-claude-code.png)

As plain text:

```
CLI VERSIONS — 09-17

  Tool          Installed               Latest                             Status
  Claude Code   2.1.274 (09/17 11:20)   2.1.274 (released 09/17 06:36)     ✓ up to date      channel: latest
  Codex         0.153.4 (09/07 11:03)   0.154.0 (released 09/10 06:40)     ↑ update → codex update
  Grok Build    1.0.34  (09/17 09:28)   1.0.34  (released ≤ 09/17 03:32*)  ✓ up to date      channel: stable

  * Grok release time is approximate (third-party mirror); official: x.ai/build/changelog
  → 1 update available: Codex.

  Update the 1 outdated CLI now?
  [y] Update all    [Esc] Skip
```

The prompt appears only inside an agent. The standalone `run.py` / `run.sh` launcher is
always check-only and continues to print raw report data without accepting input.

## Where each value comes from

| Tool | Installed version | Installed at | Latest version | Released |
|---|---|---|---|---|
| Claude Code | `claude --version` | `~/.local/share/claude/versions/<installed>` | npm registry, dist-tag = `autoUpdatesChannel` in `settings.json` (default `latest`) | npm publish time |
| Codex | `codex --version` | `$CODEX_HOME/packages/standalone/releases/<installed>-*` | npm registry, `@openai/codex` `latest` | npm publish time |
| Grok Build | `grok update --check --json` | `~/.grok/downloads/grok-<installed>-*` | same call | GitHub release of `timoteuszelle/x.ai-grok` (approximate) |

`settings.json` is read from `$CLAUDE_CONFIG_DIR`, else `~/.claude`. `$CODEX_HOME`
defaults to `~/.codex`. If the installed-at path does not exist — npm or Homebrew
installs, or the macOS/Linux Grok installer, which saves builds as
`~/.grok/downloads/grok-<platform>` without a version — the real executable behind the
command is used instead.

Why not the CLIs' own updaters: `claude update` and `codex update` install immediately
and have no check-only option. `grok update --check` does, so Grok uses it.

## Limitations and known issues

**Grok release time is approximate.** The official changelog, `x.ai/build/changelog`,
returns 403 to scripted requests, and `grok update --check --json` carries no date. The
time shown comes from a third-party NixOS package that publishes a GitHub release when it
detects a new Grok Build version, so the official release happened *no later than* that.
If the mirror stops publishing, the Grok release time shows `?`.

**Native builds are assumed to track npm.** The native installers of Claude Code and Codex
are not published through npm. This skill assumes they ship the same version numbers as
the npm packages. The version numbers matched when this was verified, but no vendor
document states it.

**Install time depends on the filesystem.** Windows and macOS record folder creation
time. Linux does not expose it through Python, so the folder's modified time is used,
which can be later than the install. Timestamps before 2015 are discarded.

**Installed-at paths are the vendors' current native layouts.** If a vendor moves them, the
skill falls back to the real executable, which can be less precise.

**Update commands were checked with native installs only.** The command shown is the
CLI's own updater. If you installed a CLI with Homebrew or npm, updating through that
package manager (`brew upgrade`, `npm install -g`) is the safe choice.

**Payload size.** The npm registry document for `@openai/codex` is about 14 MB, because it
lists every version; expect a second or two per run.

**Verified** 2026-09-17 on Windows 11 (zh-TW, Python 3.12) against `claude` 2.1.274,
`codex` 0.154.0 and `grok` 1.0.34. On the same date the Codex and Grok paths were checked
against their install scripts (`chatgpt.com/codex/install.sh`, `x.ai/cli/install.sh`).

**Verified** 2026-09-18 on macOS 26.6.2 (arm64, Python 3.10.8) against `claude` 2.1.273,
`codex` 0.154.0 and `grok` 1.0.34. The check-only launcher, version and timestamp lookup,
and global installation for Claude Code, Codex and Grok Build all completed successfully.
Linux has not been tested yet.

## License

MIT

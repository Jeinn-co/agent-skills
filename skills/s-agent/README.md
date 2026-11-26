# S-Agent

Align subagent dispatch and clean external AI CLI execution with `/uu` (`ai-usage`) across **Codex, Claude Code and Antigravity (Gemini)** on **macOS, Linux and Windows**. Notion supplies the `reviewer` and `security` model/effort pairs; routine coding, planning, devops, and UI/UX stay in the main loop with skills; unrelated or general external AI CLI prompts run isolated in a repo-free temporary directory (`/tmp` on macOS/Linux; `$env:TEMP` / `%TEMP%` on Windows) so heavy repo prefixes do not burn tokens.

```text
/s-agent -h
/s-agent Ask Codex from a clean temp dir how to structure this retry queue.
/s-agent Have an independent reviewer check this diff.
```

In Codex, use `$s-agent` with the same arguments.

## Install

Requires Node.js 22.20+ and npm for the installer; running the skill and its self-updater needs only Python. Install for all three hosts in one command:

```bash
npx skills add Jeinn-co/agent-skills -g --skill s-agent -a codex claude-code antigravity-cli -y
```

Select only your supported hosts with `-a`. Omit `-g` for a project installation. The default shared mode keeps one installed copy in `~/.agents/skills/` and connects the selected hosts. Codex reads it directly; Claude Code uses `~/.claude/skills/` (or `$CLAUDE_CONFIG_DIR/skills/`), and Antigravity CLI uses `~/.gemini/config/skills/`. Use `--copy` when shared links are unavailable; each copy is self-contained.

Without Node/npm, copy this entire skill folder into your host's skill directory, including all scripts, assets, locales, data and references. Never commit machine symlinks to this repository. Use your own installed tools/accounts. Start a new session/restart the host if the installed skill does not appear.

Requirements: Codex, Claude Code or Antigravity with delegation or CLI access, a connected Notion read tool or public-page web access, and **Python 3.11+** for schema validation/sync. Companion skills (`ai-usage`, UI skills) and browser tools (`playwright-cli`) are optional and used only when installed. No API key or user-specific path is bundled.

Platforms tested:

| OS | Status |
|---|---|
| Windows 11 | Profile writes exercised with Python 3.12 (`py -3.11`); temp-dir uses `$env:TEMP` / `%TEMP%`. |
| macOS | Profile writes and clean CLI workflow exercised. |
| Linux | Not tested. |

## Automatic skill updates

Every `/s-agent` invocation, including `-h`, first resolves the installed skill directory and runs from the task workspace, outside that installed directory:

```bash
python3.11 "<skill-dir>/scripts/check_update.py" --apply
```

On Windows, invoke `py -3.11` instead of `python3.11`. A newer published version is downloaded and installed automatically, without a y/n prompt. The agent re-reads the updated `SKILL.md` and continues the original request. Development checkouts are not overwritten. A failed check/update reports its reason and local version, then immediately continues the original request when that local copy is usable. Omit `--apply` for a read-only check.

## Notion is configuration

[Open the shared Notion configuration](https://honorable-ground-e97.notion.site/s-agent-config-effort-4118e936085b810891bdc1a77dd59b63).
Its JSON block under **S-Agent configuration** supplies `reviewer` and `security` (`model` and `effort`), while **My usage configuration** supplies `daily` choices used by `/uu` and main-loop tasks. Change a `model` or `effort`; the next S-Agent invocation automatically synchronizes changed settings. You can supply a different HTTPS Notion URL with the same schema.

Every invocation, including `-h`, tries Notion first. When validated settings match local profiles, it uses local profiles without writes or backups. If Notion is unreachable, existing valid local profiles remain usable and are labeled `Local fallback; Notion unavailable`. Invalid or truncated remote configs stop settings-dependent dispatch without touching local files.

Automatic sync updates Codex (`~/.codex/agents/`), Claude (`~/.claude/agents/`), shared role sources (`~/.agents/roles/`), and Antigravity (`~/.gemini/config/agents/` with `model: inherit`) for `reviewer` and `security` while preserving existing prompts, tools and permissions. Backups live in `~/.agents/s-agent-backups/`, and the source URL is recorded in `~/.agents/s-agent-source.json`. Failed writes roll back atomically.

## `/uu`-aligned modes and clean temp-dir CLI isolation

| Mode / Role | Scope | How it runs |
|---|---|---|
| Main loop + Skills | Planning, coding, devops, UI/UX design | Stay in main loop at `daily` model/effort; load installed skills on demand (e.g. `frontend-design` / `impeccable` / `ui-ux-pro-max` + `web-design-guidelines`). |
| `reviewer` | Independent review & QA | Isolated subagent (fresh context, never forked) at Notion `reviewer` model/effort. |
| `security` | Read-only security scan | Isolated read-only subagent (fresh context, never forked) at Notion `security` model/effort. |
| Clean temp-dir CLI | General Q&A, second opinions, unrelated external CLI calls | Run from `/tmp` (macOS/Linux) or `$env:TEMP` / `%TEMP%` (Windows, e.g. `codex exec -C ...`); for Claude `claude -p`, use `--strict-mcp-config --setting-sources user` (plus `--no-session-persistence --tools ""` for pure Q&A; never default `--bare`, which skips OAuth/keychain login). |

For Antigravity `reviewer` / `security`, S-Agent prefers `invoke_subagent` (`model: inherit`); only when exact `[gemini]` model/effort locking (such as `gemini-4-neon` / `xhigh` for high-risk `security`) is required or explicitly requested does it launch `agy --agent <role> --model <model> --effort <effort> -p <handoff>` inside the target repository with `--mode plan` for read-only work. Always disclose who is dispatched and how before running.

## Helper and validation

The host reads Notion and supplies strict JSON and a current capability catalog to [`scripts/sync_roles.py`](scripts/sync_roles.py). The helper uses only Python's standard library; optional legacy role keys (`planner`, `designer`, `executor`, `devops`) in a policy remain validated without writing local files. See [SKILL.md](SKILL.md) for the exact workflow.

```bash
python3.11 scripts/sync_roles.py POLICY.json --catalog CATALOG.json  # preview
python3.11 scripts/sync_roles.py POLICY.json --catalog CATALOG.json --apply
```

Isolated sync tests cover strict validation, preservation, bootstrap, legacy-role transition compatibility, future model identifiers, idempotence, rollback and closing temporary files before replacement.

[Traditional Chinese](README.zh-TW.md) ·
[Claude subagents](https://code.claude.com/docs/en/sub-agents) ·
[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) ·
[Antigravity subagents](https://antigravity.google/docs/subagents)

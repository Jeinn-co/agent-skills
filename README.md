# Jeinn Agent Skills

Agent skills for Claude Code, Codex CLI, Grok Build, and anything else that reads the
`SKILL.md` convention.

## Install

```bash
npx skills add Jeinn-co/agent-skills              # all skills
npx skills add Jeinn-co/agent-skills --skill ai-usage
```

Or copy a skill directory into `~/.claude/skills/`.

## Skills

### `ai-usage`

One report for how much of your Claude, ChatGPT and Grok subscription you have left —
percent used, when each window resets, and what top-up you have.

```
USAGE — 09-12 01:08

  Claude    pro
    5h    ███░░░░░░░  29%   resets 03:40 (2h32m)
    week  ████░░░░░░  41%   resets Mon 17:00 (2d16h)

  ChatGPT   plus
    5h    ░░░░░░░░░░   0%   resets 05:55 (4h47m)
    week  ░░░░░░░░░░   0%   resets 09-18 17:07 (6d15h)

  Grok      SuperGrok
    week  ███░░░░░░░  27%   resets 09-15 09:38 (3d8h)

  → Use ChatGPT right now. Both windows are fresh.
```

**All three numbers are live.** Nothing is scraped from a web page, no browser is
driven, and no stored credential is ever read. Each provider's own CLI is asked
directly:

| Provider | How |
|---|---|
| Claude | `claude -p "/usage"` — print mode routes the built-in slash command |
| ChatGPT | `codex app-server` → JSON-RPC `account/rateLimits/read` |
| Grok | `grok agent stdio` → ACP extension method `_x.ai/billing` |

Providers whose CLI is not installed are reported as `not installed`; the rest still
run. Requires Python 3.9+. No dependencies.

Two things that are deliberately *not* reported, because they cannot be read locally
and a wrong number is worse than none:

- **ChatGPT "Usage limit resets"** — the app-server can spend one
  (`account/rateLimitResetCredit/consume`) but exposes no way to count them. Checked
  against all 163 methods. `credits.balance` is a different pool and is not a
  substitute.
- **Claude extra usage** — reported only as enabled/disabled, which is all the CLI
  exposes.

See [`skills/ai-usage/references/providers.md`](skills/ai-usage/references/providers.md)
for how each method was found, including the dead ends, so nobody has to re-walk them.

## License

MIT

# Jeinn Agent Skills

Agent skills for Claude Code, Codex CLI, Grok Build, and anything else that reads the
`SKILL.md` convention. Nothing here depends on a particular host.

## Install

```bash
npx skills add Jeinn-co/agent-skills@ai-usage     # just this skill
npx skills add Jeinn-co/agent-skills              # everything in the repo
```

Or copy a skill directory into your agent's skills folder — `~/.claude/skills/`,
`~/.codex/skills/`, `~/.grok/skills/`.

## Usage

Type the skill name as a slash command:

    /ai-usage

That is the whole interface. It reads live every time, so there is no cache to clear
and no refresh flag to remember. You can also run it outside any agent:

    ./skills/ai-usage/run.sh

## Requirements

- **Python 3.9+**, standard library only.
- The CLI of each provider you want reported, already signed in: `claude`, `codex`,
  `grok`.

You do not need all three. Install one and you get one row; the others print
`not installed` and nothing breaks. The skill never prompts for a login.

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

It asks each provider's CLI rather than its own host, so the report is the same
wherever you install it — run it inside Codex and you still get your Claude and Grok
numbers.

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

## Limitations and known issues

**Platform.** Developed and verified on macOS. The code is plain Python with no
platform-specific calls, so Linux should work, but it is untested. Windows is untested.

**Version-pinned.** Verified 2026-09-12 against `claude` 2.1.268, `codex` 0.154.0,
`grok` 1.0.25.

| Risk | Where | What happens if it breaks |
|---|---|---|
| Claude's two usage lines are free text and are regex-parsed | `claude_usage.py` | Falls back to printing the raw line; never prints a wrong number |
| Codex's app-server protocol is private to OpenAI and carries no compatibility promise | `codex_usage.py` | Method rename would return `-32600`; the ChatGPT row fails, others still run |
| Grok's `_x.ai/billing` is a vendor ACP extension, not part of the ACP spec | `grok_usage.py` | Same |

**Deliberately not reported.** A wrong number here is worse than no number:

- **ChatGPT "Usage limit resets"** (Settings shows `Available N`) cannot be read. The
  app-server can *spend* one via `account/rateLimitResetCredit/consume` but exposes no
  count — checked against all 163 methods. `credits.balance` is a different pool: an
  account can show `balance 0` while holding 2 available resets, so it is never
  substituted.
- **Claude extra usage** is reported only as enabled/disabled, which is all the CLI
  exposes.
- **Grok has one window, not two.** No 5-hour row is invented for it.

**Numbers are per-account, not per-machine.** Claude's `/usage` notes its breakdown is
approximate and covers local sessions on this machine only; the headline percentages
are account-wide.

## License

MIT

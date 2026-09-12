# Jeinn Agent Skills

Agent skills for Claude Code, Codex CLI, Grok Build, and anything else that reads the
`SKILL.md` convention. Nothing here depends on a particular host.

繁體中文：[README.zh-TW.md](README.zh-TW.md)

## Skills

| Skill | What it does | Docs |
|---|---|---|
| [`ai-usage`](skills/ai-usage/) | One report for how much of your Claude, ChatGPT and Grok subscription is left — percent used, when each window resets, what top-up you have. | [README](skills/ai-usage/README.md) · [中文](skills/ai-usage/README.zh-TW.md) |

## Install

```bash
npx skills add Jeinn-co/agent-skills@ai-usage     # just this skill
npx skills add Jeinn-co/agent-skills              # everything in the repo
```

Or copy a skill directory into your agent's skills folder — `~/.claude/skills/`,
`~/.codex/skills/`, `~/.grok/skills/`.

**Read the skill's own README before installing** — each one lists what must already be
on your machine. Installing copies only that skill's directory, so its README travels
with it and this page does not.

## Conventions

- **English is canonical.** A `.zh-TW.md` beside a doc is a mirror; when one changes,
  the other changes in the same commit.
- **Docs live with the skill.** Anything a user needs after installing goes inside
  `skills/<name>/`, not here. This page is an index.
- **Versions are by hand.** `SKILL.md` frontmatter carries `metadata.version`; the skill
  also prints its version so an installed copy can identify itself. Nothing in the
  tooling reads or enforces either — installing a skill copies files and leaves no
  record of where they came from.

## License

MIT

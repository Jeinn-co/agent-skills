# S-Agent

Choose subagents for the current task in **Codex and Claude Code**. Notion supplies
the model and effort for each role; the main agent coordinates and verifies work.

```text
/s-agent -h
/s-agent Fix this bug and have another agent review it.
```

In Codex, use `$s-agent` with the same arguments.

## Install

```bash
npx skills add Jeinn-co/agent-skills@s-agent
```

Or copy this whole directory into `~/.codex/skills/s-agent/` or
`~/.claude/skills/s-agent/`. Start a new session if the skill does not appear.
The installer requires a compatible Node.js/npm; manual copying does not.

Requirements: Codex or Claude Code with delegation tools, a connected Notion read
tool or public-page web access, and **Python 3.11+** for schema validation/sync.
No API key or user-specific path is bundled. Windows/Linux have not been tested.

## Notion is configuration

[Open the shared Notion configuration](https://honorable-ground-e97.notion.site/s-agent-config-effort-4118e936085b810891bdc1a77dd59b63).
Its single JSON block under **S-Agent configuration** is authoritative.
Change a role's `model` or `effort`; the next S-Agent invocation automatically
synchronizes changed settings. No separate sync command or skill release is needed
for a new supported model. Supply your own Notion configuration URL in a request
to select a different page with the same schema.

Every invocation, including `-h`, tries Notion first. If its validated settings
match local profiles, it uses those profiles directly without writes or backups.
If settings changed or profiles are missing, it automatically validates current
host-supported model/effort pairs, previews changes, backs up and applies them.
No user-entered `sync` command is required. `-h` shows role values and source/read
time; it may sync settings but never launches subagents or performs the task.

When Notion or its read tool is unavailable, existing valid local profiles remain
usable. Output clearly labels `Local fallback; Notion unavailable`; cached/local
values are never called a fresh Notion read. Without usable local profiles, it
reports the missing configuration. A reachable but invalid/truncated configuration
or unsupported update stops dispatch and preserves local files.

Automatic sync updates native Codex/Claude profiles and existing shared role
sources while preserving prompts, tools and permissions. Missing profiles receive
minimal role prompts. Complex layouts and symlinks are rejected before writes.
Failed writes roll back; unchanged settings are not rewritten. Backups are stored
under `~/.agents/s-agent-backups/`; the selected source URL is stored in
`~/.agents/s-agent-source.json`. Legacy `/s-agent sync [Notion URL]` remains
compatible as a refresh-only invocation, but is optional.

A current capability catalog is required for apply; it is discovered by the host,
not copied from the desired policy. Documented model support does not prove account
access. Unknown support blocks apply. Existing running agents keep their models;
reload/restart the host to load changed profiles. Dispatch reports settings
mismatches instead of silently using an older model.

## Roles and coordination

| Role | Responsibility |
|---|---|
| `pm` / PO | Needs, scope, priorities and acceptance criteria |
| `designer` | UI/UX, flows and accessibility |
| `developer` | Investigation, implementation and fixes |
| `qa` | Reproduction, regression tests and acceptance |
| `reviewer` | Independent correctness/security review |
| `devops` | CI/CD, environments, logs and reliability |

Start with one subagent; use up to three only for independent work and within the
host limit. Keep ownership clear, sequence dependent work and reuse agents for
related follow-up. Small chores can stay with the main agent. No task is invented
from an editor tab. No tool access means no claimed delegation.

The current task and necessary follow-up define scope. Existing approval gates,
browser preferences and test environments remain in force. A plan stays a plan;
a role does not authorize deployment, publication or external writes. Delegation
does not guarantee lower total token usage.

## Helper and validation

The host reads Notion and supplies strict JSON and a current capability catalog to
[`scripts/sync_roles.py`](scripts/sync_roles.py). The helper uses only Python's
standard library; it has no network or token handling. See [SKILL.md](SKILL.md) for
the exact workflow. Its CLI `--help` describes helper flags; `/s-agent -h` is the
agent-facing help that reads Notion.

```bash
python3.11 scripts/sync_roles.py POLICY.json --catalog CATALOG.json  # preview
python3.11 scripts/sync_roles.py POLICY.json --catalog CATALOG.json --apply
```

Version 1.0.1: isolated sync unit tests cover strict validation, preservation,
bootstrap, future model identifiers, idempotence and rollback. A Codex forward-test
actually delegated a Python fixture fix and independently passed five regressions.
That does not establish live Claude dispatch, every account's model access or
cross-platform compatibility. Native configuration validation is not a live model
request.

[Traditional Chinese](README.zh-TW.md) ·
[Claude subagents](https://code.claude.com/docs/en/sub-agents) ·
[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)

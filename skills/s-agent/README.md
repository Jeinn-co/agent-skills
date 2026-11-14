# S-Agent

Choose subagents for the current task in **Codex, Claude Code and Antigravity (Gemini)**. Notion supplies
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

Requirements: Codex, Claude Code or Antigravity with delegation tools, a connected Notion read
tool or public-page web access, and **Python 3.11+** for schema validation/sync.
No API key or user-specific path is bundled.

Platforms tested:

| OS | Status |
|---|---|
| Windows 11 | Profile writes have been exercised with Python 3.12. Live agent dispatch is not covered. |
| macOS | Not recorded. |
| Linux | Not tested. |

## Automatic skill updates

Every `/s-agent` invocation, including `-h`, first runs:

```bash
python3.11 scripts/check_update.py --apply
```

A newer published version is downloaded and installed automatically, without a y/n
prompt. The agent re-reads the updated `SKILL.md` and continues the original request.
The shared Python updater replaces only this installed skill; installer-managed and
manually copied folders work without Node/npm, install records or a sibling checkout.
The bundle is validated before replacement; failed replacement restores the old copy.
User settings outside the skill folder remain in place. Development checkouts are not
replaced. A failed check/update reports its reason and local version, then immediately continues
the original request without a prompt when that local copy is usable. Only a missing or
unusable local copy stops the request.

Omit `--apply` for a read-only check. No credentials are read. Skill self-updates
are separate from Notion model/effort synchronization and do not launch subagents.

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
sources while preserving prompts, tools and permissions. Model versions belong
in the existing `model` ID. Help shows the full configured ID; an alias remains
labeled as an alias until the host supplies its resolved version. Configuration
is not proof of live model execution. Role defaults are policy choices, not a
universal industry standard. Missing profiles receive
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


## Gemini role settings

Add `gemini` with `model` and `effort` to all six roles in the Notion JSON.
Existing policies with only `codex` and `claude` remain supported. The capability
catalog includes `gemini` when the policy does. Exact Gemini settings are stored
in `~/.agents/roles/<role>.toml`; native role prompts are discovered from
`~/.gemini/config/agents/<role>.md` with `model: inherit`.

S-Agent launches the exact pair through `agy --agent <role> --model <model>
--effort <effort> -p <handoff>`. Native subagent tiers do not prove an exact model
or effort. Account access requires a signed-in CLI and the appropriate plan.
By default, use the current host platform: Gemini/Antigravity selects the Notion
`gemini` settings; another provider requires an explicit user choice. Analysis-only
CLI handoffs explicitly use `--mode plan` and carry no-edit and project test rules.
Separate CLI sessions do not automatically inherit parent permissions or sandbox;
enforce equivalent scopes before launch, or keep work in the authorized host.
The coordinator verifies the returned work.

For Hydrogen roles configured with `"effort": "high"`, high remains the default.
To select xhigh for one handoff, say `/s-agent Use Gemini reviewer at xhigh to
review this change.` S-Agent verifies support, reports the effective effort and
passes `--effort xhigh`. It does not change Notion or saved role defaults; later
handoffs use their configured effort. `-h` shows the default and optional xhigh,
with support labeled unverified until checked. There is no automatic escalation.

Known Gemini thinking levels are read from the bundled `data/gemini-models.json`,
distributed from the repository's shared model catalog also used by ai-usage.
Current host/account support is still checked separately; model facts never
override Notion defaults or establish account access.

## Roles and coordination

| Role | Responsibility |
|---|---|
| `planner` | Executable plan: scope, acceptance criteria, steps and checks |
| `designer` | UI/UX, flows and accessibility |
| `executor` | Implements an approved plan step by step |
| `reviewer` | Independent review and testing |
| `devops` | CI/CD, environments, logs and reliability |
| `security` | Security scans of code, dependencies and configuration |

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

Isolated sync tests cover strict validation, preservation, bootstrap, future model
identifiers, idempotence, rollback and closing temporary files before replacement.
Configuration checks do not establish live model access or agent dispatch.

[Traditional Chinese](README.zh-TW.md) ·
[Claude subagents](https://code.claude.com/docs/en/sub-agents) ·
[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)

[Antigravity subagents](https://antigravity.google/docs/subagents) · [Antigravity CLI](https://antigravity.google/docs/cli/reference/)

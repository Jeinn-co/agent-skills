# ai-usage

One report for how much of your Claude, ChatGPT, Grok and Muse subscription you have left —
percent used, when each window resets, and what top-up you have — plus which model
and effort each CLI is running now, and a shared model + effort pick per provider.

Works in Claude Code, Codex CLI, Grok Build, and anything else that reads the `SKILL.md`
convention. Nothing here depends on a particular host.

繁體中文說明：[README.zh-TW.md](README.zh-TW.md)

## Before you install

Read this first — the skill reports on tools it does **not** install for you.

### 1. Python 3.9 or newer

Standard library only, no `pip install`, no virtualenv.

```bash
python --version     # or: python3 --version   /   py --version  (Windows)
```

`run.py` launches each probe with the *same* interpreter you started it with
(`sys.executable`), so whichever of those names works for you is the right one. On
Windows, avoid the `python3` alias specifically: it is often a Microsoft Store stub
that opens the store instead of running anything.

### 2. At least one provider CLI, already signed in

| Provider | CLI | Sign in with |
|---|---|---|
| Claude | `claude` | `claude` once, then `/login` |
| ChatGPT | `codex` | `codex login` |
| Grok | `grok` | `grok` once, then follow the auth prompt |
| Muse | `muse` | `muse login` |

**You do not need all four.** Install one and you get one row; the others print
`not installed` and nothing else breaks. The skill never prompts for a login, never
opens a browser, and never reads a stored credential — it asks each CLI's own local
agent server, which means a CLI that is installed but signed out reports a failed
call, not a login screen.

### 3. Network and subprocess access

The agent host must allow this skill to launch local subprocesses. Each provider CLI
must also be able to reach its own service over the internet. The Python code makes no
direct HTTP requests; authentication and network access stay inside the provider CLIs.

### 4. Platform

macOS, Linux and Windows — but see [Limitations](#limitations-and-known-issues). The
launcher and `portable.py` handle Store-stub `python3`, npm `.cmd` shims that
`CreateProcess` refuses, and cp950/cp1252 stdout; verified 2026-09-14 on a zh-TW
Windows 11 machine.

### 5. Not required

No API key. No account beyond the subscriptions you already pay for. No Python package
installation: the skill uses only the standard library.

## Install

The `npx` method requires Node.js and npm. At the time of this release, `skills` CLI
1.5.26 declares Node.js 22.20 or newer:

```bash
node --version
npx --version
```

If that environment is not available, use the manual-copy method below; Node.js is not
needed when the skill runs.

```bash
npx skills add Jeinn-co/agent-skills@ai-usage     # just this skill
npx skills add Jeinn-co/agent-skills              # everything in the repo
```

Or copy a skill directory into your agent's skills folder — `~/.claude/skills/`,
`~/.codex/skills/`, `~/.grok/skills/`.

On Windows, copy the directory rather than linking it; if you do want a link, use a
junction (`mklink /J`), which needs no elevation. Never commit a symlink into this
repo — Git for Windows checks it out as a text file containing the target path and the
skill silently stops working.

If `/ai-usage` is not visible immediately after installation, start a new conversation
or restart the agent so it reloads its skill list.

## Update

Updates are not automatic. Installs made with `npx skills add` record their GitHub
source, so users can update them in place after a release:

```bash
npx skills update ai-usage -g -y    # global install
npx skills update ai-usage -p -y    # project install
```

Open a new conversation or restart the agent after updating so it reloads the skill.
A manually copied skill is not tracked; copy the directory again to update it.

## Usage

Type the skill name as a slash command:

    /ai-usage

That is the whole interface. It reads live every time, so there is no cache to clear
and no refresh flag to remember. To run it outside an agent, first change into the
installed `ai-usage` directory, then use the launcher for your platform:

```bash
./run.sh          # macOS or Linux
py -3 run.py      # Windows; use `python run.py` if `py` is unavailable
```

The report's title line ends with the skill version that produced it. Add `--version`
to the platform command to print the version alone and exit.

## What it prints

![ai-usage report](images/demo.png)

It asks each provider's CLI rather than its own host, so it reads the same provider
accounts wherever you install it — run it inside Codex and you still get your Claude
and Grok numbers.

**Usage numbers are live.** Nothing is scraped from a web page, no browser is driven,
and no stored credential is ever read. Each provider's own CLI is asked directly:

| Provider | How |
|---|---|
| Claude | `claude -p "/usage"` — print mode routes the built-in slash command |
| ChatGPT | `codex app-server` → JSON-RPC `account/rateLimits/read` |
| Grok | `grok agent stdio` → ACP extension method `_x.ai/billing` |
| Muse | `muse serve` → one tiny turn, then MSP `usage/read` |

**Muse costs one model call per run.** Muse keeps no usage on disk, and `session/start`
alone does not fetch it: the numbers arrive only with a model response. So the probe
sends `Reply with the single word: ok` at `minimal` effort, on the non-contributor twin
of the default model when the local catalog lists one. Each run spends a sliver of Muse
quota, takes about 15 s, and leaves one session in Muse's history under
`<temp>/ai-usage-muse-probe`, which the `now` row skips.

Providers whose CLI is not installed are reported as `not installed`; the rest still
run. What is deliberately left out is listed under
[Limitations](#limitations-and-known-issues).

**Current model and effort.** Under each provider, `now` shows the model and effort
of that CLI's newest local session, read from the session files the CLI already
writes (`session_info.py`; no network, nothing launched). It reflects the last turn
that was sent, so a model switched since then appears after the next message.

**CursorBench.** Below the providers, one table row per CLI you use: the
[CursorBench](https://cursor.com/cursorbench) score, cost / task, tokens / task and
steps / task of the exact model + effort that CLI ran last, plus CP (score ÷ cost per
task, points per dollar at Cursor's API prices — higher is better), and one qualified row per
provider: across every model and effort CursorBench lists for that provider, the best CP at a
score of 50% or more; when nothing from that provider reaches 50%, its highest score. A model CursorBench does not list shows `not listed`, never a
neighbouring row. `cursorbench.py` fetches the public page once per run; that is the
only HTTP request the skill's own code makes, and it sends no credential.

**Language.** The report is written in the language you asked in — English, 中文 or
anything else. Model names, numbers and times are never translated.

See [`references/providers.md`](references/providers.md) for how each usage method
was found, including the dead ends, so nobody has to re-walk them.

## Limitations and known issues

**Platform.** Developed and verified on macOS. Linux is untested but uses the same
code path. **Windows was verified 2026-09-14** on a zh-TW Windows 11 machine
(PowerShell, Python 3.12) — the launcher and `portable.py` handle Store-stub
`python3`, `.cmd` shims that `CreateProcess` refuses, and cp950/cp1252 *our own*
stdout. That first real run also caught a bug this paragraph used to gloss over:
`subprocess`'s `text=True` decodes a *launched CLI's* output with the OS locale
encoding, not UTF-8, so Claude's usage line raised `UnicodeDecodeError` under cp950.
Fixed by pinning `encoding="utf-8"` in `portable.text_kwargs()` (used by all three
probes). Only tested on one Windows machine and one non-English locale so far — other
locales or Windows builds may still surface something new. Bug reports from Windows
are welcome and will be believed over this paragraph.

**Version-pinned.** Verified 2026-09-12 against `claude` 2.1.268, `codex` 0.154.0,
`grok` 1.0.25. Grok's omitted `creditUsagePercent` re-checked 2026-09-22 on
`grok` 1.0.40. The session and model-cache fields read by `session_info.py` were
verified 2026-09-22 against `claude` 2.1.278, Codex sessions written by the VS Code
extension (0.154.0-alpha), and `grok` 1.0.40. Muse (probe and session fields) verified
2026-09-24 against Muse Code 1.3.0-R3401.1 on Windows 11.

| Risk | Where | What happens if it breaks |
|---|---|---|
| Claude's two usage lines are free text and are regex-parsed | `claude_usage.py` | Falls back to printing the raw line; never prints a wrong number |
| Codex's app-server protocol is private to OpenAI and carries no compatibility promise | `codex_usage.py` | A method rename or missing required field makes the ChatGPT row fail visibly; it never defaults to 0% |
| Grok's `_x.ai/billing` is a vendor ACP extension, not part of the ACP spec | `grok_usage.py` | A method rename or missing required field (period, `billingPeriodEnd`) makes the Grok row fail visibly. An omitted `creditUsagePercent` prints `percent omitted`; it never defaults to 0% |
| Muse's `usage/read` returns only what the host has observed | `muse_usage.py` | If the turn ends with no usage, the Muse row fails visibly (`no usage observed`); it never defaults to 0% |
| Session files and model caches are internal to each CLI and undocumented | `session_info.py` | A renamed field prints `?` for that value; a moved file prints `no local session`. The usage rows are unaffected |
| CursorBench is a web page parsed by its HTML table, and model ids are mapped to its names by rule | `cursorbench.py` | A layout change prints `bench failed (...)` and the usage rows are unaffected. A model the rules cannot map, or a name CursorBench spells differently, shows `not listed` |

**Deliberately not reported.** A wrong number here is worse than no number:

- **ChatGPT "Usage limit resets"** (Settings shows `Available N`) cannot be read. The
  app-server can *spend* one via `account/rateLimitResetCredit/consume` but exposes no
  count — checked against all 163 methods. The report omits the row; it does not print
  `unknown`. `credits.balance` is a different pool: an account can show `balance 0`
  while holding 2 available resets, so it is never substituted.
- **Claude extra usage** is not reported. The current CLI response exposes no reliable
  field for it; `fast_mode_disabled_reason` is specifically about fast mode.
- **Grok has one window, not two.** No 5-hour row is invented for it.
- **Grok `creditUsagePercent` omitted** is not treated as 0%. The probe prints
  `percent omitted` and still reports the reset clock.
- **Grok prepaid / on-demand at 0** is omitted. The values are readable; printing
  `prepaid 0 / on-demand 0` is noise. The line appears only when any value is
  non-zero.
- **Muse plan name** is not reported. `usage/read` gives a numeric tier id
  (`27681527378179523`), not a name, so the plan shows `?`.

**Numbers are per-account, not per-machine.** Claude's `/usage` notes its breakdown is
approximate and covers local sessions on this machine only; the headline percentages
are account-wide.

## License

MIT

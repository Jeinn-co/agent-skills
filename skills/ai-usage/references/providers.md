# Why each provider works the way it does

All three services compute usage server-side and return it in API response headers.
The difference is entirely what each CLI does with that after receiving it.

## Claude — works, live

`claude -p "/usage" < /dev/null` prints the live numbers. Print mode routes built-in
slash commands, so this needs no credentials and no browser.

`< /dev/null` is required, otherwise the CLI waits 3s for stdin and prints a warning.

Claude Code does **not** persist rate-limit state anywhere on disk — checked:
- session jsonl `usage` field carries `input_tokens` / `cache_read_input_tokens` /
  `output_tokens` only, no percentage
- `~/.claude/stats-cache.json` is message and tool-call counts

The binary does contain the full `anthropic-ratelimit-unified-*` header set and the
endpoint `/api/oauth/usage`, which is what `/usage` calls each time.

## ChatGPT — works, live

`codex app-server` speaks JSON-RPC 2.0 over stdio. Send `initialize`, then
`account/rateLimits/read`:

```json
{"rateLimits":{"primary":{"usedPercent":0,"windowDurationMins":300,"resetsAt":...},
 "secondary":{"usedPercent":0,"windowDurationMins":10080,"resetsAt":...},
 "credits":{"balance":"0"},"planType":"plus"}}
```

**Discovery trick worth reusing:** call a bogus method. The `-32600` error message
enumerates every valid method name. The string in the binary is `account/usage`, which
is *not* a real wire name — the list gave the true `account/rateLimits/read`.

`codex exec "/status"` does NOT work: exec mode does not route slash commands, it sends
"/status" to the model, which interprets it as a request to run `git status`. Cost 8k
tokens to learn.

Superseded approach, kept as context: `~/.codex/sessions/**/rollout-*.jsonl` carries the
same `rate_limits` object written from response headers, but only as of the last codex
run. The app-server method is live; prefer it.

## Grok — works, live

`grok agent stdio` speaks ACP (JSON-RPC 2.0, newline-delimited) over stdio.
Send `initialize`, then call `_x.ai/billing` with empty params:

```json
{"subscription_tier":"SuperGrok",
 "config":{"creditUsagePercent":27.0,
           "currentPeriod":{"type":"USAGE_PERIOD_TYPE_WEEKLY","start":"...","end":"..."},
           "billingPeriodEnd":"...",
           "onDemandCap":{"val":0},"onDemandUsed":{"val":0},"prepaidBalance":{"val":0}}}
```

`creditUsagePercent` is optional. grok 1.0.40 omitted it after the weekly reset on
2026-09-22 (period, `billingPeriodEnd`, and `subscription_tier` still present). It
was also absent in some 1.0.25 fetches mid-period on 2026-09-10, so a missing field
is not 0%. The probe prints `percent omitted` and still reports the reset clock.

Two traps that cost time:
- The method name in the binary is `x.ai/billing`, but the **wire name has a leading
  underscore**. `x.ai/billing` returns `-32601 Method not found`; `_x.ai/billing` works.
  Same for `_x.ai/auth/check_subscription`.
- No `session/new` needed. Params `{}`.

Dead ends, do not retry:
1. **Local cache** — `~/.grok` holds `totalTokens` and `costUsdTicks` only; `monthlyLimit`
   and `billingCycle` never touch disk. ccusage and TokenTracker have the same gap.
2. **`grok -p "/usage"`** — not routed as a slash command; goes to the model as a prompt.
   (It read `~/.claude/skills` and executed this very skill.)
3. **PTY** — `expect` driving the TUI returned nothing parseable.
4. **Browser** — grok.com returns **403 Cloudflare** to Playwright-driven Chrome even
   with real cookies copied from the user's profile. It fingerprints automation, not
   login state. The Playwright MCP extension route was never needed.

# Claude: optional signed-in browser source

Use a connected-browser tool actually available to the current agent, following the
user's browser preference. No named browser, connector, operating system or native
automation API is required by this skill. If no suitable tool is available, skip
this adapter and use the CLI; do not claim browser access or ask for installation. Do not
launch a separate browser, copy cookies, read browser profile files or start a login
flow to replace a working web login. The CLI and website have separate auth.

At the start of each `/uu` capture, run `python3 claude_browser.py --clear` so a
failed or unavailable browser tool cannot silently reuse the previous invocation's
observation. Use the platform's Python command (`py -3` on Windows) for these examples.
HTML Refresh does not clear observations; its reuse is labeled with the original time.

1. Find the Claude Usage tab (`https://claude.ai/new#settings/usage` or
   `https://claude.ai/settings/usage`) in the connected browser. Use the existing tab;
   if absent, open the known Usage URL in that same browser. Do not submit messages.
2. Refresh the Usage page once. Read the visible plan, current-session percent,
   weekly percent, quota-window reset clocks and the visible Limit resets section. Native accessibility
   reading through that same integration may be used if supported and its DOM API fails.
   Never click a reset redemption button. If the page is signed out, leave its login
   to the user and allow the launcher to try CLI auth.
3. Create a JSON file with only the observed fields below, then run
   `python3 claude_browser.py --save < /path/to/usage.json` in this skill directory.
   Use the actual observation time, never a prior screenshot's time. Reset timestamps
   must be timezone-aware. Convert visible relative reset dates using the client
   timezone and current date; ambiguous or missing fields must not be invented.
4. Run the normal canonical launcher. Its Claude probe prefers this fresh browser
   observation and bypasses the CLI, so an expired CLI login does not break web usage.

Schema (the numbers and time below are examples, not current usage):

```json
{
  "sourceUrl": "https://claude.ai/new#settings/usage",
  "browserName": "Chrome",
  "observedAt": "2026-11-07T08:15:00+08:00",
  "plan": "pro",
  "windows": {
    "5h": {"usedPercent": 0, "resetsAt": null},
    "week": {"usedPercent": 78, "resetsAt": "2026-11-09T17:00:00+08:00"}
  },
  "resetCredits": {"availableCount": 0, "credits": []}
}
```

Include only the usage windows actually visible, rather than inventing missing
weekly limits. A zero-used window may have `resetsAt: null`; a used window requires
a visible reset clock. `browserName` is optional; omitted or unsupported names show
`Browser` instead of assuming Chrome.

For a visible "No resets right now", use `availableCount: 0` and `credits: []`.
For available resets, record the observed count with `credits` entries containing
`status: "available"` and an aware `expiresAt` timestamp (or null if not shown).
Use `credits: null` when only the count is visible. If the reset section is not
visible, omit `resetCredits` or set it to null; report unavailable, never assume zero.

`claude_browser.py` validates percentages, source URL, aware timestamps and freshness.
It saves only usage fields in `~/.cache/ai-usage/claude-browser.json`, with mode 600 on POSIX (Windows uses the profile directory's ACL).
Observations expire after 5 minutes. The report labels the browser source and actual
check time. HTML Refresh may reuse a still-fresh observation but cannot itself drive
a connected browser; rerun `/uu` to capture new browser data. Never
describe this reuse as a new browser check. The launcher keeps its 20-second probe
budget. Browser reset epochs use the same hidden report metadata as CLI resets;
renderers never recover timestamps from the compact displayed date. If neither browser nor CLI works, show the failure and Usage page link.

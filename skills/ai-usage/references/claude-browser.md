# Claude: optional signed-in browser source

From the task workspace, clear the old observation with
`python3 "<skill-dir>/claude_browser.py" --clear` (use `py -3` on Windows).
Create a unique temporary result file and run
`python3 "<skill-dir>/run.py" --probe-claude "<result-file>"` with the same Python.
This runs OAuth and its CLI fallback within the normal 20-second budget.
If it prints `claude=direct`, skip the browser. If it prints `claude=browser-fallback`,
use an available connected browser, following the user's browser preference.

If no suitable browser is available, continue with the direct result and the other
providers. Use an existing browser session and read only the visible Usage page.
Leave login to the user and keep browser cookies and profile files private.
The CLI and website have separate sign-ins.

1. Find the Claude Usage tab (`https://claude.ai/new#settings/usage` or
   `https://claude.ai/settings/usage`) in the connected browser. Use the existing tab;
   if absent, open the known Usage URL in that same browser. Do not submit messages.
2. Refresh the Usage page once. Read the visible plan, current-session percent,
   weekly percent, quota-window reset clocks and the visible Limit resets section. Native accessibility
   reading through that same integration may be used if supported and its DOM API fails.
   Never click a reset redemption button. If the page is signed out, tell the user
   to sign in to Claude themselves and rerun `/uu`. Continue with the other providers.
3. Create a JSON file with only the observed fields below, then run
   `python3 claude_browser.py --save < /path/to/usage.json` in this skill directory.
   Use the actual observation time, never a prior screenshot's time. Reset timestamps
   must be timezone-aware. Convert visible relative reset dates using the client
   timezone and current date; ambiguous or missing fields must not be invented.

In all cases, run `python3 "<skill-dir>/run.py" --claude-result "<result-file>"`
and remove the temporary result file afterwards. The launcher reuses the direct
result and reads the browser observation only when direct usage was unavailable.

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
  "resetCredits": {"availableCount": 1, "credits": [
    {"status": "available", "expiresAt": "2026-12-11T06:00:00+08:00", "label": "Full reset"}]}
}
```

Include only the usage windows actually visible, rather than inventing missing
weekly limits. A zero-used window may have `resetsAt: null`; a used window requires
a visible reset clock. `browserName` is optional; omitted or unsupported names show
`Browser` instead of assuming Chrome.

For a visible "No resets right now", use `availableCount: 0` and `credits: []`.
For available resets, record the observed count with `credits` entries containing
`status: "available"`, an aware `expiresAt` timestamp (or null if not shown) and the
visible reset name as `label` (for example `"Full reset"` or `"Fable reset"`). Keep the
page's count; the report hides Fable resets and lowers the count, like the CLI path.
Use `credits: null` when only the count is visible. If the reset section is not
visible, omit `resetCredits` or set it to null; report unavailable, never assume zero.

`claude_browser.py` validates percentages, source URL, aware timestamps and freshness.
It saves only usage fields in `~/.cache/ai-usage/claude-browser.json`, with mode 600 on POSIX (Windows uses the profile directory's ACL).
Observations expire after 5 minutes. The report labels the browser source and actual
check time. HTML Refresh retries OAuth and CLI first, then may reuse a still-fresh
observation with its original time. Rerun `/uu` to capture new browser data. Browser
reset epochs use the same hidden report metadata as CLI resets. If neither the
direct probe nor the browser works, show the failure and Usage page link.

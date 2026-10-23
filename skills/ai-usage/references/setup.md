# Setup — choose which providers to report

`/ai-usage setup` (alias `/uu setup`) changes which providers the report covers and the output format. It does
not run the report. Provider ids: `claude` (Claude), `codex` (ChatGPT), `grok` (Grok),
`muse` (Muse), `agy` (Gemini).

1. Run the platform launcher with `--show-providers`; it prints `providers=<ids>`, the
   current selection (every provider when nothing is saved), and `installed=<ids>`, the
   providers whose CLI is present. Offer only installed providers; one that is not
   installed is never saved.
2. Ask about the providers — **keep first**, with one short question at a time.
   First show the current selection in the choice descriptions and ask `Keep or change?`
   with `Keep` first and `Change…` second. `Keep` saves nothing for this step.
   Only after `Change…`, use the host's actual picker capabilities:
   - **Multi-select available** (e.g. Claude Code `AskUserQuestion` with
     `multiSelect: true`): one option per installed provider, using its name as the
     label and current on/off state as the description. Preselect current choices
     only if supported; otherwise show those states without claiming boxes are checked.
     If the option limit is smaller than the list, use consecutive multi-select pages
     and combine their selections; do not replace the picker with typed numbers.
   - **Single-select only or no choice tool** (e.g. Codex
     `request_user_input_async`): show a numbered Markdown list in the normal chat
     message, one installed provider per line, including its current on/off state.
     Then ask one short free-text question: `Which numbers should be kept? (e.g. 1,2)`.
     Keep the list visible outside the question widget: its title may flatten newlines.
     Never paste the whole list into that title or ask separately for each provider.
     Accept comma-separated numbers, `keep`, `all`, or provider names. Map numbers
     to the exact displayed list; invalid or out-of-range choices save nothing.
   Keep changed choices in memory until the selection is complete. Cancellation
   leaves the saved selection unchanged. If the user already names the desired
   providers, use those names without repeating the picker.
3. Save with `--set-providers <ids>` (e.g. `--set-providers claude,codex`), or
   `--set-providers all` when every provider is chosen and every CLI is installed. It
   prints the saved `providers=<ids>`. Nothing chosen, a dismissed picker, or an invalid
   reply saves nothing: say the selection is unchanged.
4. Then ask the output format the same way — one single-select question, header
   `Output`: `Output — now: <HTML|Markdown>. Keep or change?` with options `Keep`
   (description: the current format) and the other format (`HTML` — a page opened in the
   browser, or `Markdown` — shown in chat). Without a choice tool, ask `keep`, `html` or
   `md`. Save only a change, with `--set-output html` or `--set-output md`; `Keep` or a
   dismissed question keeps the format.
5. Report one line: `Reporting: <names> · Not reported: <names> · Output: <HTML|Markdown>`,
   or `Reporting all providers · Output: <HTML|Markdown>`.

The selection is saved in `~/.config/ai-usage/config.json` (`$XDG_CONFIG_HOME` when set),
outside the skill folder, so reinstalling or updating the skill keeps it. Skipped
providers launch no CLI, so Muse spends no probe call while it is skipped.

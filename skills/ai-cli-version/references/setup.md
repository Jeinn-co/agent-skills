# Setup — choose which tools to check

`/ai-cli-version setup` (alias `/check-uu setup`) changes which tools the check runs and the output format. It
does not run the check or any updater. Tool ids: `claude`, `codex`, `grok`, `muse`, `agy`.

1. Run the platform launcher with `--show-tools`; it prints `tools=<ids>`, the current
   selection (every tool when nothing is saved), and `installed=<ids>`, the tools whose
   CLI is present. Offer only installed tools; a tool that is not installed is never
   saved, so it drops out of later checks.
2. Ask about the tools — **keep first**, with one short question at a time.
   First show the current selection in the choice descriptions and ask `Keep or change?`
   with `Keep` first and `Change…` second. `Keep` saves nothing for this step.
   Only after `Change…`, use the host's actual picker capabilities:
   - **Multi-select available** (e.g. Claude Code `AskUserQuestion` with
     `multiSelect: true`): one option per installed tool, using its name as the
     label and current on/off state as the description. Preselect current choices
     only if supported; otherwise show those states without claiming boxes are checked.
     If the option limit is smaller than the list, use consecutive multi-select pages
     and combine their selections; do not replace the picker with typed numbers.
   - **Single-select only or no choice tool** (e.g. Codex
     `request_user_input_async`): show a numbered Markdown list in the normal chat
     message, one installed tool per line, including its current on/off state.
     Then ask one short free-text question: `Which numbers should be kept? (e.g. 1,2)`.
     Keep the list visible outside the question widget: its title may flatten newlines.
     Never paste the whole list into that title or ask separately for each tool.
     Accept comma-separated numbers, `keep`, `all`, or tool names. Map numbers
     to the exact displayed list; invalid or out-of-range choices save nothing.
   Keep changed choices in memory until the selection is complete. Cancellation
   leaves the saved selection unchanged. If the user already names the desired
   tools, use those names without repeating the picker.
3. Save with `--set-tools <ids>` (comma-separated, e.g. `--set-tools claude,codex,grok`),
   or `--set-tools all` when every tool is chosen and every tool is installed. It prints the saved `tools=<ids>`.
   Nothing chosen, a dismissed picker, or an invalid reply saves nothing: say the
   selection is unchanged.
4. Then ask the output format the same way — one single-select question, header
   `Output`: `Output — now: <HTML|Markdown>. Keep or change?` with options `Keep`
   (description: the current format) and the other format (`HTML` — a page opened in the
   browser, or `Markdown` — shown in chat). Without a choice tool, ask `keep`, `html` or
   `md`. Save only a change, with `--set-output html` or `--set-output md`; `Keep` or a
   dismissed question keeps the format.
5. Report one line: `Checking: <names> · Not checked: <names> · Output: <HTML|Markdown>`,
   or `Checking all tools · Output: <HTML|Markdown>`.

The selection is saved in `~/.config/ai-cli-version/config.json` (`$XDG_CONFIG_HOME`
when set), outside the skill folder, so reinstalling or updating the skill keeps it.


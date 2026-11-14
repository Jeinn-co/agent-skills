# Skill resource refactoring

## Scope

Keep all three published skills independently installable. Consolidate manually maintained
report resources, not unrelated provider probes or update/server behavior.
The existing My usage changes are part of this refactor.

## Steps

1. [x] Inventory ai-usage, ai-cli-version and s-agent.
2. [x] Define canonical resources under shared/ and standalone distributed copies.
3. [x] Migrate report translations, language controls, logos and Gemini model facts.
4. [x] Update affected callers, regression fixtures and documentation; preserve local customizations.

Both local report installations received the refactored files. The ai-usage model /
bold effort display is unified in the source and local installation, without an age suffix.
Existing s-agent links already point to
this checkout. No publishing, provider probes or browser acceptance belong to this
implementation step.

## Ownership and sources

- shared/ owns report helpers, common translations, product marks and Gemini facts.
- Each report skill owns its locales/en.json and locales/zh-TW.json.
- shared/personal-choices.json owns personal daily and role display choices;
  ai-usage/guidance_data.py loads its distributed copy.
- Notion owns the actual s-agent role defaults. Personal report choices do not sync defaults.
- scripts/sync_shared.py distributes resources into the skill folders. Distributed
  copies are committed so installation and report generation need no build or sibling skill.
- i18next is pinned, vendored with its MIT license, and embedded in the exported HTML.
  Report generation makes no requests for translations or JavaScript.

## ai-model-compare

The other project uses i18next JSON locale files and distributed copies of the
same model catalog and personal profile. Use sync_shared.py --compare-dir to
distribute those files. Neither runtime reads a local sibling checkout.
Publishing and installing remain separate operations; do not publish this refactor automatically.

## Checks

Update regression coverage for data-driven translations, escaped interpolation,
standalone resources and dynamic report controls. Run only checks the user has
explicitly requested. Browser acceptance uses the connected Chrome integration.

## Runtime handoff

- The shared language button owns language changes. Report controllers subscribe
  to one `reportlanguagechange` event for their labels, timers and update controls.
- Server identity includes code/resource content. The next launcher invocation
  replaces a stale server only when it belongs to the same installed skill folder.
- Server-side page rendering uses captured data and current templates, preserving
  the capture time without running probes. Existing browser retries of timed-out
  rows remain separate.

# Shared skill resources

Edit these canonical files, then run `python3.11 scripts/sync_shared.py` from the
repository root to distribute the changed resources into the standalone skills.
Commit both the source and its distributed copies. Users install a skill folder;
they do not need this directory, a sibling skill, npm, a CDN or a build step.

| Resource | Consumers |
|---|---|
| `report_i18n.py`, `report-language.js`, `language-button.js` | ai-usage, ai-cli-version |
| `skill_runtime.py` | SKILL.md version loading and report server identity/ownership |
| `report-toolbar.html`, `globe.svg`, `logos.json` | ai-usage, ai-cli-version |
| `locales/en.json`, `locales/zh-TW.json` | common report controls |
| `gemini-models.json` | ai-usage model facts and s-agent effort validation |
| `personal-choices.json` | daily/role display choices and personal Gemini selection policy |
| `vendor/i18next.min.js` and its MIT license | both self-contained HTML reports |

Each report's own `locales/en.json` and `locales/zh-TW.json` live in that skill.
They use i18next keys and `{{variable}}` interpolation. Common messages are merged
first; skill-specific messages can override them. Python generates the bilingual
HTML from those catalogs; the browser uses i18next for dynamic text and plurals.
The language switch, refresh, theme, expiry timer and update queue use those same
resources. No translation resources are fetched when a report opens.

Page templates live in each skill's `templates/report.html`. Its browser controller,
toolbar styles and (for ai-usage) expiry timer live under `assets/`. Python owns
provider parsing and HTML rendering; the launchers keep probe/server orchestration.

Each skill's `SKILL.md` frontmatter `metadata.version` is its only release-version
source. The report launchers and update checks read it through `skill_runtime.py`;
Python does not carry a second version literal. ai-model-compare keeps its existing
`package.json` version source.

Server identities include a fingerprint of the installed Python and report resources.
On the next launcher run, changed files replace an older server from that same skill
folder, even when the version number is unchanged. Another installation's server is
left alone. The server renders saved raw reports with current templates and preserves
their capture time without running probes. The browser retains its existing initial-load
retry for rows whose earlier lookup timed out.

HTML interpolation values must be escaped at the renderer boundary. Browser
messages containing runtime values go into `textContent`, never `innerHTML`.
The controlled language-button label is the exception: it contains no runtime values.

`personal-choices.json` owns daily and role display choices; `guidance_data.py`
loads its distributed copy. The report's role choices are display preferences;
Notion still owns the actual s-agent dispatch defaults. An optional xhigh handoff
does not modify those defaults.

The complete Gemini catalog retains model IDs, supported efforts, defaults,
bilingual use cases, pricing and subscription information. To distribute both it
and personal choices into ai-model-compare, run from this repository:

```sh
python3.11 scripts/sync_shared.py --compare-dir ../ai-model-compare
```

Commit the distributed data in both repositories. Neither runtime depends on a
sibling checkout or an extra network lookup. The personal profile's `label` field
preserves a report-specific model spelling while `model` matches chart data names.

Product mark paths came from the existing report renderers, originally copied
from ai-model-compare and LobeHub Icons (MIT). i18next's pinned source and license
are recorded under `vendor/`.

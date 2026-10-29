"""Render run.py's tab-separated check lines as one self-contained HTML page.

No scripts and no external requests: the page only shows what run.py printed.
"""
import datetime
import html

NAMES = {"claude": "Claude Code", "codex": "Codex", "grok": "Grok Build", "muse": "Muse Code",
         "agy": "Antigravity"}
# Product marks as 24x24 SVG paths, copied from AI Model Compare (src/logos.ts), which takes
# them from LobeHub Icons (MIT). Muse uses the Meta AI mark; Grok follows the text colour.
LOGOS = {
    "claude": ("#d97757",
             "M20.998 10.949H24v3.102h-3v3.028h-1.487V20H18v-2.921h-1.487V20H15v-2.921H9V20H7.488v-2.921H6V20H4.487v-2.921H3V14.05H0V10.95h3V5h17.998v5.949zM6 10.949h1.488V8.102H6v2.847zm10.51 0H18V8.102h-1.49v2.847z"),
    "codex": ("#10a37f",
             "M8.086.457a6.105 6.105 0 013.046-.415c1.333.153 2.521.72 3.564 1.7a.117.117 0 00.107.029c1.408-.346 2.762-.224 4.061.366l.063.03.154.076c1.357.703 2.33 1.77 2.918 3.198.278.679.418 1.388.421 2.126a5.655 5.655 0 01-.18 1.631.167.167 0 00.04.155 5.982 5.982 0 011.578 2.891c.385 1.901-.01 3.615-1.183 5.14l-.182.22a6.063 6.063 0 01-2.934 1.851.162.162 0 00-.108.102c-.255.736-.511 1.364-.987 1.992-1.199 1.582-2.962 2.462-4.948 2.451-1.583-.008-2.986-.587-4.21-1.736a.145.145 0 00-.14-.032c-.518.167-1.04.191-1.604.185a5.924 5.924 0 01-2.595-.622 6.058 6.058 0 01-2.146-1.781c-.203-.269-.404-.522-.551-.821a7.74 7.74 0 01-.495-1.283 6.11 6.11 0 01-.017-3.064.166.166 0 00.008-.074.115.115 0 00-.037-.064 5.958 5.958 0 01-1.38-2.202 5.196 5.196 0 01-.333-1.589 6.915 6.915 0 01.188-2.132c.45-1.484 1.309-2.648 2.577-3.493.282-.188.55-.334.802-.438.286-.12.573-.22.861-.304a.129.129 0 00.087-.087A6.016 6.016 0 015.635 2.31C6.315 1.464 7.132.846 8.086.457zm-.804 7.85a.848.848 0 00-1.473.842l1.694 2.965-1.688 2.848a.849.849 0 001.46.864l1.94-3.272a.849.849 0 00.007-.854l-1.94-3.393zm5.446 6.24a.849.849 0 000 1.695h4.848a.849.849 0 000-1.696h-4.848z"),
    "grok": ("currentColor",
             "M9.27 15.29l7.978-5.897c.391-.29.95-.177 1.137.272.98 2.369.542 5.215-1.41 7.169-1.951 1.954-4.667 2.382-7.149 1.406l-2.711 1.257c3.889 2.661 8.611 2.003 11.562-.953 2.341-2.344 3.066-5.539 2.388-8.42l.006.007c-.983-4.232.242-5.924 2.75-9.383.06-.082.12-.164.179-.248l-3.301 3.305v-.01L9.267 15.292M7.623 16.723c-2.792-2.67-2.31-6.801.071-9.184 1.761-1.763 4.647-2.483 7.166-1.425l2.705-1.25a7.808 7.808 0 00-1.829-1A8.975 8.975 0 005.984 5.83c-2.533 2.536-3.33 6.436-1.962 9.764 1.022 2.487-.653 4.246-2.34 6.022-.599.63-1.199 1.259-1.682 1.925l7.62-6.815"),
    "muse": ("#9553ff",
             "M10.547.232c.776-.086 1.543.244 2.152.712.784.598 1.375 1.434 1.757 2.347.19.444.3.92.345 1.402.01.384.024.781-.108 1.148-.126.406-.362.795-.728 1.017-.352.236-.786.3-1.199.288-.84-.073-1.613-.52-2.212-1.106-.15-.1-.236-.263-.368-.38-.801-.97-1.394-2.203-1.324-3.496.048-.698.38-1.44 1.03-1.75.206-.1.428-.164.655-.182zM18.595 3.077c.52-.045 1.032.186 1.4.551.402.434.625 1.006.736 1.584.096.605.09 1.233-.048 1.83a5.97 5.97 0 01-.907 2.19c-.198.25-.382.519-.633.719-.493.45-1.181.725-1.848.598-.42-.08-.819-.306-1.085-.646-.514-.591-.687-1.403-.714-2.17a6.11 6.11 0 011.03-3.285c.237-.314.49-.62.797-.867.375-.27.805-.486 1.272-.504zM5.038 4.172c.618-.045 1.238.067 1.832.235.871.28 1.741.78 2.182 1.624.177.383.256.826.152 1.242-.097.442-.375.816-.71 1.105-.724.59-1.664.84-2.577.887a5.356 5.356 0 01-2.881-.675c-.39-.248-.765-.539-1.025-.93a1.9 1.9 0 01-.327-1.283c.067-.507.357-.968.741-1.289.723-.62 1.684-.873 2.613-.916zM4.87 10.369c.69-.06 1.465.223 1.811.866.213.349.278.763.29 1.166.006.528-.136 1.046-.34 1.529-.34.793-.893 1.478-1.538 2.036-.64.538-1.42.951-2.26 1.015a2.031 2.031 0 01-1.467-.398c-.353-.281-.578-.707-.662-1.15-.156-.8.077-1.62.445-2.327.196-.377.444-.724.72-1.044.767-.886 1.814-1.608 3.001-1.693zM20.391 11.05c.881-.087 1.872.116 2.477.822.473.58.534 1.425.239 2.102-.118.317-.32.59-.527.852-.877.962-2.11 1.553-3.379 1.744-.818.123-1.723.036-2.406-.477-.2-.161-.386-.346-.514-.573-.277-.436-.321-.994-.216-1.492.224-.904.92-1.594 1.676-2.073a5.874 5.874 0 012.65-.905zM7.553 15.523c.381-.052.775.004 1.118.184.344.154.613.427.866.702.866 1.097 1.267 2.549 1.146 3.944a4.476 4.476 0 01-.497 1.61c-.273.469-.663.91-1.187 1.08-.35.103-.731.118-1.077-.005a2.53 2.53 0 01-.959-.612c-.798-.859-1.236-2.02-1.343-3.185-.055-.646-.006-1.31.21-1.923.146-.471.384-.92.738-1.265.261-.277.62-.452.985-.53zM13.637 16.5a4.237 4.237 0 011.82.219c.795.286 1.542.724 2.148 1.323.535.504.963 1.162 1.099 1.899.055.379.038.785-.122 1.138-.19.465-.599.807-1.051.996-.883.364-1.887.253-2.76-.082a5.568 5.568 0 01-2.343-1.685c-.347-.445-.616-.968-.697-1.534-.042-.382-.036-.788.13-1.142.194-.418.55-.76.978-.925.25-.119.525-.174.798-.207z"),
    "agy": ("#3186ff",
             "M20.616 10.835a14.147 14.147 0 01-4.45-3.001 14.111 14.111 0 01-3.678-6.452.503.503 0 00-.975 0 14.134 14.134 0 01-3.679 6.452 14.155 14.155 0 01-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 000 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 014.45 3.001 14.112 14.112 0 013.679 6.453.502.502 0 00.975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 013.001-4.45 14.113 14.113 0 016.453-3.678.503.503 0 000-.975 13.245 13.245 0 01-2.003-.678z"),
}
COMPARE = "https://jeinn-co.github.io/ai-model-compare/"


def esc(text):
    return html.escape(str(text), quote=True)


def parse(lines):
    version, skipped, rows = "?", [], []
    for line in lines:
        line = line.rstrip("\n")
        if line.startswith("### ai-cli-version "):
            version = line.split()[-1]
        elif line.startswith("### skipped "):
            skipped = [NAMES.get(n, n) for n in line.split()[-1].split(",")]
        elif "\t" in line:
            name, _, rest = line.partition("\t")
            if name not in NAMES:
                continue
            if "=" not in rest:
                rows.append({"name": name, "note": rest.strip()})
                continue
            fields = dict(part.split("=", 1) for part in rest.split("\t") if "=" in part)
            fields["name"] = name
            rows.append(fields)
    return version, skipped, rows


def summary(lines):
    """The chat lines: the → summary, any `Not checked` line, and the y/Esc prompt."""
    _, skipped, rows = parse(lines)
    outdated = [NAMES[r["name"]] for r in rows if r.get("status") == "update available"]
    failed = [NAMES[r["name"]] for r in rows if r.get("note") not in (None, "not installed")]
    n = len(outdated)
    out = ["> **→ %d update%s available:** %s." % (n, "" if n == 1 else "s", ", ".join(outdated))
           if n else ("> **Check failed:** %s." % ", ".join(failed) if failed else
                      "> **All up to date.**")]
    if failed and n:
        out.append("_Check failed: %s_" % ", ".join(failed))
    if skipped:
        out.append("_Not checked (setup): %s_" % ", ".join(skipped))
    if n:
        out.append("")
        out.append("**Update the %s now?**" % ("1 outdated CLI" if n == 1 else "%d outdated CLIs" % n))
        out.append("`[y]` Update all · `[Esc]` Skip")
    return out


def logo(cli):
    color, path = LOGOS[cli]
    return ('<svg class="logo" viewBox="0 0 24 24" aria-hidden="true"><path fill="%s" '
            'fill-rule="evenodd" clip-rule="evenodd" d="%s"/></svg>' % (color, path))


def render(lines, now=None):
    now = now or datetime.datetime.now()
    version, skipped, rows = parse(lines)
    body = []
    outdated = []
    for r in rows:
        label = logo(r["name"]) + esc(NAMES[r["name"]])
        # data-row lets the served page swap one row after an update.
        row_id = ' data-row="%s"' % esc(r["name"])
        if "note" in r:
            kind = "muted" if r["note"] == "not installed" else "bad"
            body.append('<tr%s><td>%s</td><td colspan="2" class="%s">%s</td>'
                        '<td><span class="badge %s">%s</span></td></tr>'
                        % (row_id, label, kind, esc(r["note"]), kind,
                           "not installed" if kind == "muted" else "check failed"))
            continue
        released = r.get("released", "?")
        if r["name"] == "grok" and released != "?":
            released = "≤ " + released + " *"
        status = r.get("status", "?")
        if status == "update available":
            outdated.append(NAMES[r["name"]])
            badge = ('<span class="badge up">update</span> <code>%s</code>' % esc(r.get("update_cmd", "")))
        elif status == "up to date":
            badge = '<span class="badge ok">up to date</span>'
        else:
            badge = '<span class="badge muted">%s</span>' % esc(status)
        # data-tool marks rows the served page gives an Update button.
        marker = row_id + (' data-tool="%s"' % esc(r["name"]) if status == "update available" else "")
        body.append(
            "<tr%s><td>%s</td><td><b>%s</b> <span class=\"sub\">%s</span></td>"
            "<td><b>%s</b> <span class=\"sub\">released %s</span></td><td>%s"
            "<div class=\"sub\">channel %s</div></td></tr>"
            % (marker, label, esc(r.get("installed", "?")), esc(r.get("installed_at", "?")),
               esc(r.get("latest", "?")), esc(released), badge, esc(r.get("channel", "?"))))
    failed = [NAMES[r["name"]] for r in rows if r.get("note") not in (None, "not installed")]
    parts = []
    if outdated:
        parts.append("%d update%s available: %s" % (
            len(outdated), "" if len(outdated) == 1 else "s", ", ".join(outdated)))
    if failed:
        parts.append("Check failed: %s" % ", ".join(failed))
    kind = "up" if outdated else "bad" if failed else "ok"
    summary = '<p class="summary %s">%s</p>' % (kind, esc(" · ".join(parts) or "All up to date"))
    grok = any(r["name"] == "grok" and "note" not in r for r in rows)
    foot = ('<p class="foot">* Grok release time is approximate (third-party mirror); official: '
            'x.ai/build/changelog</p>' if grok else "")
    skip = ('<p class="foot">Not checked (setup): %s</p>' % esc(", ".join(skipped)) if skipped else "")
    page = PAGE
    for key, value in (("time", esc(now.strftime("%m-%d %H:%M"))), ("version", esc(version)),
                       ("rows", "".join(body)), ("summary", summary), ("foot", foot),
                       ("skipped", skip), ("compare", esc(COMPARE)), ("dark", DARK)):
        page = page.replace("@@%s@@" % key, value)
    return page


# Tailwind CSS 3.4 Slate with green/amber/red/blue, the same palette as ai-usage; every
# text colour is at least 4.5:1 on its card. Dark is used when the OS is dark, unless
# `data-theme` on <html> (set by the served page's Auto / Light / Dark switch) forces one.
DARK = ("--bg:#1e293b;--card:#334155;--text:#f1f5f9;--muted:#cbd5e1;--line:#475569;"
        "--track:#475569;--ok:#4ade80;--up:#fbbf24;--bad:#fca5a5;--accent:#93c5fd")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CLI Versions</title>
<style>
:root{--bg:#f1f5f9;--card:#ffffff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--track:#e2e8f0;--ok:#15803d;--up:#b45309;--bad:#dc2626;--accent:#2563eb}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){@@dark@@}}
:root[data-theme=dark]{@@dark@@}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:16px/1.6 "Inter","Segoe UI",system-ui,-apple-system,sans-serif;padding:40px 16px;-webkit-font-smoothing:antialiased}
main{max-width:1040px;margin:0 auto}h1{font-size:28px;font-weight:600;letter-spacing:-.01em;margin:0 0 4px}.top{color:var(--muted);margin:0 0 16px}
.summary{font-size:17px;font-weight:500;margin:0 0 18px}.summary.ok{color:var(--ok)}.summary.up{color:var(--up)}.summary.bad{color:var(--bad)}
.tablewrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
table{border-collapse:collapse;width:100%}.logo{width:16px;height:16px;margin-right:8px;vertical-align:-3px}th,td{padding:11px 14px;text-align:left;border-bottom:1px solid var(--line);
vertical-align:top}th{color:var(--muted);font-weight:500;font-size:13px;text-transform:uppercase;letter-spacing:.06em}tr:last-child td{border-bottom:0}
.sub{color:var(--muted);font-size:14px}.badge{display:inline-block;border-radius:999px;padding:1px 10px;font-size:13px;
font-weight:500;letter-spacing:.02em;border:1px solid currentColor}.badge.ok{color:var(--ok)}.badge.up{color:var(--up)}
.badge.bad{color:var(--bad)}.badge.muted{color:var(--muted)}td.bad{color:var(--bad)}td.muted{color:var(--muted)}
code{font-family:ui-monospace,Consolas,monospace;font-size:14px;background:var(--bg);padding:1px 6px;border-radius:6px}
.foot{color:var(--muted);font-size:14px;margin:10px 0}a{color:var(--accent)}
</style></head><body><main>
<h1>CLI Versions</h1><p class="top">@@time@@ · ai-cli-version @@version@@</p>
@@summary@@
<div class="tablewrap"><table><thead><tr><th>Tool</th><th>Installed</th><th>Latest</th><th>Status</th></tr></thead>
<tbody>@@rows@@</tbody></table></div>
@@foot@@@@skipped@@
<p>Compare models: <a href="@@compare@@" target="_blank" rel="noopener">AI Model Compare</a></p>
</main></body></html>
"""

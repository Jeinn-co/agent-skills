"""Render run.py's tab-separated check lines as one self-contained HTML page.

No scripts and no external requests: the page only shows what run.py printed.
"""
import datetime
import html

NAMES = {"claude": "Claude Code", "codex": "Codex", "grok": "Grok Build", "muse": "Muse Code",
         "agy": "Antigravity"}
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


def render(lines, now=None):
    now = now or datetime.datetime.now()
    version, skipped, rows = parse(lines)
    body = []
    outdated = []
    for r in rows:
        label = esc(NAMES[r["name"]])
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
table{border-collapse:collapse;width:100%}th,td{padding:11px 14px;text-align:left;border-bottom:1px solid var(--line);
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

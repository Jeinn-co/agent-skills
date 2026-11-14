"""Render run.py's tab-separated check lines as one self-contained HTML page.

No external requests: the page only shows what run.py printed.
"""
import datetime
import html
import sys
from pathlib import Path
import json

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from report_i18n import ReportI18n

I18N = ReportI18n(SKILL_DIR, "ai-cli-version-lang")

NAMES = {"claude": "Claude Code", "codex": "Codex", "grok": "Grok Build", "muse": "Muse Code",
         "agy": "Antigravity"}
# Product marks as 24x24 SVG paths, copied from AI Model Compare (src/logos.ts), which takes
# them from LobeHub Icons (MIT). Muse uses the Meta AI mark; Grok follows the text colour.
LOGOS = json.loads((SKILL_DIR / "data/logos.json").read_text(encoding="utf-8"))
COMPARE = "https://jeinn-co.github.io/ai-model-compare/"


def esc(text):
    return html.escape(str(text), quote=True)


bi = I18N.bi


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


# The cells of a row that is being checked; the served page also puts it into a row whose
# last check timed out, while that tool is checked again.
SKELETON = '<td colspan="3"><div class="skel"></div></td>'


def row(r, loading=False):
    """One tool's <tr>; `loading` draws the skeleton instead of its versions."""
    label = logo(r["name"]) + esc(NAMES[r["name"]])
    # data-row lets the served page swap one row after a check or an update.
    row_id = ' data-row="%s"' % esc(r["name"])
    if loading:
        return "<tr%s><td>%s</td>%s</tr>" % (row_id, label, SKELETON)
    if "note" in r:
        kind = "muted" if r["note"] == "not installed" else "bad"
        # data-timeout: the served page checks this tool again with a longer budget.
        late = ' data-timeout' if "timed out after" in r["note"] else ""
        return ('<tr%s%s><td>%s</td><td colspan="2" class="%s">%s</td>'
                '<td><span class="badge %s">%s</span></td></tr>'
                % (row_id, late, label, kind, bi('not_installed') if kind == "muted" else esc(r["note"]), kind,
                   bi('not_installed') if kind == "muted" else bi('check_failed')))
    released = r.get("released", "?")
    if r["name"] == "grok" and released != "?":
        released = "≤ " + released + " *"
    status = r.get("status", "?")
    if status == "update available":
        badge = ('<span class="badge up">%s</span> <code>%s</code>' % (bi('update_badge'), esc(r.get("update_cmd", ""))))
    elif status == "up to date":
        badge = '<span class="badge ok">%s</span>' % bi('up_to_date')
    else:
        badge = '<span class="badge muted">%s</span>' % esc(status)
    # data-tool marks rows the served page gives an Update button.
    marker = row_id + (' data-tool="%s"' % esc(r["name"]) if status == "update available" else "")
    return ("<tr%s><td>%s</td><td><b>%s</b> <span class=\"sub\">%s</span></td>"
            "<td><b>%s</b> <span class=\"sub\">%s %s</span></td><td>%s"
            "<div class=\"sub\">%s %s</div></td></tr>"
            % (marker, label, esc(r.get("installed", "?")), esc(r.get("installed_at", "?")),
               esc(r.get("latest", "?")), bi('released'), esc(released), badge, bi('channel'), esc(r.get("channel", "?"))))


def row_html(lines):
    """The <tr> for the one tool in `lines` (that tool's check output)."""
    return row(parse(lines)[2][0])


def render(lines, now=None, loading=False):
    """The whole page; `loading` shows every tool's row as a skeleton."""
    now = now or datetime.datetime.now()
    version, skipped, rows = parse(lines)
    body = "".join(row(r, loading) for r in rows)
    outdated = [NAMES[r["name"]] for r in rows if r.get("status") == "update available"]
    failed = [NAMES[r["name"]] for r in rows if r.get("note") not in (None, "not installed")]
    parts = []
    if outdated:
        parts.append(bi("updates_available", count=len(outdated),
                        suffix="" if len(outdated) == 1 else "s", names=esc(", ".join(outdated))))
    if failed:
        parts.append(bi("checks_failed", names=esc(", ".join(failed))))
    if loading:
        summary = '<p class="summary muted">%s</p>' % bi('checking_versions')
    else:
        kind = "up" if outdated else "bad" if failed else "ok"
        summary = '<p class="summary %s">%s</p>' % (kind, " · ".join(parts) or bi("all_up_to_date"))
    grok = not loading and any(r["name"] == "grok" and "note" not in r for r in rows)
    foot = '<p class="foot">%s</p>' % bi('grok_release_note') if grok else ''
    skip = '<p class="foot">%s %s</p>' % (bi('not_checked_label'), esc(', '.join(skipped))) if skipped else ''
    page = I18N.template(PAGE)
    for key, value in (("time", esc(now.strftime("%m-%d %H:%M"))), ("version", esc(version)),
                       ("rows", body), ("summary", summary), ("foot", foot),
                       ("skipped", skip), ("compare", esc(COMPARE)), ("dark", DARK),
                       ("language_button", I18N.language_button),
                       ("lang_head", I18N.head()), ("lang_script", I18N.language_script())):
        page = page.replace("@@%s@@" % key, value)
    return page


# Tailwind CSS 3.4 Slate with green/amber/red/blue, the same palette as ai-usage; every
# text colour is at least 4.5:1 on its card. Dark is used when the OS is dark, unless
# `data-theme` on <html> (set by the served page's Auto / Light / Dark switch) forces one.
DARK = ("--bg:#1e293b;--card:#334155;--text:#f1f5f9;--muted:#cbd5e1;--line:#475569;"
        "--track:#475569;--ok:#4ade80;--up:#fbbf24;--bad:#fca5a5;--accent:#93c5fd")

PAGE = (Path(__file__).resolve().parent / 'templates/report.html').read_text(encoding="utf-8")

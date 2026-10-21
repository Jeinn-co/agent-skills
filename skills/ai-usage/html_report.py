"""Render the launcher's raw report as one self-contained HTML page (`/ai-usage html`).

Input is exactly the text run.py prints; nothing is re-fetched. The page has no
scripts and no external requests, so opening it is safe and offline.
"""
import datetime
import html
import re

NAMES = {"CLAUDE": "Claude", "CHATGPT": "ChatGPT", "GROK": "Grok", "MUSE": "Muse",
         "GEMINI": "Gemini"}
CLI_NAMES = {"claude": "Claude", "codex": "ChatGPT", "grok": "Grok", "muse": "Muse",
             "agy": "Gemini"}
LABELS = {"short": "5h", "outer": "week"}
USAGE_PAGES = {"Claude": "https://claude.ai/new#settings/usage",
               "ChatGPT": "https://chatgpt.com/settings/usage?tab=overview",
               "Grok": "https://grok.com/?_s=home"}
COMPARE = "https://jeinn-co.github.io/ai-model-compare/"

WINDOW = re.compile(r"^(\S+)\s+(<1|[\d.]+)% used\s*(.*?)\s*bar \S+\s*$")
BENCH = re.compile(r"^(bench|pick)\s+(\S+)\s+(.*)$")
FIGURE = re.compile(r"\s+(score [\d.]+%|aa [\d.]+)\s+cost \$([\d.]+)(.*?)\s+cp ([\d.]+)(.*)$")


def esc(text):
    return html.escape(str(text), quote=True)


def clock(reset, now):
    """`Oct 21, 11:19am` -> `10-21 11:19`; other formats pass through without the `(…)`."""
    text = re.sub(r"\s*\(.*\)$", "", reset).strip()
    for fmt in ("%b %d, %I:%M%p", "%b %d, %I%p"):
        try:
            return datetime.datetime.strptime(text, fmt).strftime("%m-%d %H:%M")
        except ValueError:
            continue
    return text


def relative(reset, now):
    """Compact time-to-reset: the probe's own `(XdYh)` when present, else parsed."""
    found = re.search(r"\((\d+)d(\d+)h\)", reset)
    if found:
        days, hours = int(found.group(1)), int(found.group(2))
        return "%dd%dh" % (days, hours) if days else ("%dh" % hours if hours else "<1h")
    text = re.sub(r"\s*\(.*\)$", "", reset).strip()
    for fmt in ("%b %d, %I:%M%p", "%b %d, %I%p"):
        try:
            when = datetime.datetime.strptime(text, fmt).replace(year=now.year)
        except ValueError:
            continue
        if when < now - datetime.timedelta(days=180):
            when = when.replace(year=now.year + 1)
        minutes = max(0, int((when - now).total_seconds() // 60))
        days, rest = divmod(minutes, 1440)
        hours, mins = divmod(rest, 60)
        return "%dd%dh" % (days, hours) if days else "%dh%02dm" % (hours, mins)
    return ""


def parse(raw):
    report = {"version": "?", "skipped": [], "providers": [], "bench": {}, "pick": {}}
    current = None
    section = None
    for line in raw.splitlines():
        if line.startswith("### ai-usage "):
            report["version"] = line.split()[-1]
        elif line.startswith("### skipped "):
            report["skipped"] = [CLI_NAMES.get(c, c) for c in line.split()[-1].split(",")]
        elif line.startswith("### "):
            section = line[4:].strip()
            current = None
            if section in NAMES:
                current = {"name": NAMES[section], "plan": "?", "windows": [], "notes": [],
                           "model": None, "effort": None, "age": None}
                report["providers"].append(current)
        elif section == "CURSORBENCH":
            found = BENCH.match(line.strip())
            if found:
                report[found.group(1)][found.group(2)] = found.group(3).strip()
        elif current is not None and line.strip():
            text = line.strip()
            window = WINDOW.match(text)
            if text.startswith("plan:"):
                current["plan"] = text[5:].strip() or "?"
            elif window:
                label, pct, middle = window.groups()
                reset = re.search(r"resets (.+)$", middle)
                current["windows"].append({
                    "label": LABELS.get(label, label),
                    "pct": 0.5 if pct == "<1" else float(pct),
                    "shown": "<1%" if pct == "<1" else "%d%%" % round(float(pct)),
                    "reset": reset.group(1).strip() if reset else ""})
            elif text.startswith("session "):
                age = re.search(r"\(([^)]*)\)", text)
                current["age"] = age.group(1) if age else None
            elif text.startswith("model "):
                current["model"] = text[6:].strip()
            elif text.startswith("effort "):
                current["effort"] = text[7:].strip()
            else:
                current["notes"].append(text)
    return report


def figure(text):
    """`Opus 5.5 Medium  score 52.5%  cost $2.91 ... cp 18.0` -> (name, score, cost, cp, aa)."""
    found = FIGURE.search(text)
    if not found:
        return text, "", "", "", False
    name = text[:found.start()].strip()
    score = found.group(1).replace("score ", "").replace("aa ", "AA ")
    return name, score, "$" + found.group(2), found.group(4), "(AA)" in found.group(5)


def level(pct):
    return "red" if pct >= 80 else "amber" if pct >= 50 else "green"


def render(raw, now=None):
    now = now or datetime.datetime.now()
    data = parse(raw)
    cards = []
    for p in data["providers"]:
        rows = []
        for w in p["windows"]:
            when = w["reset"]
            rel = relative(when, now) if when else ""
            shown = clock(when, now) if when else ""
            rows.append(
                '<div class="row"><div class="lbl">%s</div>'
                '<div class="track"><div class="fill %s" style="width:%.1f%%"></div></div>'
                '<div class="pct %s">%s</div><div class="reset">%s%s</div></div>'
                % (esc(w["label"]), level(w["pct"]), min(w["pct"], 100), level(w["pct"]),
                   esc(w["shown"]), esc(shown),
                   ' <span class="rel">(%s)</span>' % esc(rel) if rel else ""))
        for note in p["notes"]:
            rows.append('<div class="note">%s</div>' % esc(note))
        now_line = ("<code>%s</code> · effort %s · %s ago" % (esc(p["model"]), esc(p["effort"] or "?"),
                                                            esc((p["age"] or "?").replace(" ago", "")))
                    if p["model"] else "no local session")
        link = USAGE_PAGES.get(p["name"])
        cards.append(
            '<section class="card"><header><h2>%s</h2><span class="plan">%s</span>%s</header>%s'
            '<div class="now">Now: %s</div></section>'
            % (esc(p["name"]), esc(p["plan"]),
               '<a class="usage" href="%s" target="_blank" rel="noopener">Usage page</a>' % esc(link) if link else "",
               "".join(rows), now_line))

    bench_rows = []
    for cli in CLI_NAMES:
        if cli not in data["pick"] and cli not in data["bench"]:
            continue
        b = data["bench"].get(cli, "")
        k = data["pick"].get(cli, "")
        bn, bs, bc, bp, baa = figure(b) if b else ("—", "", "", "", False)
        kn, ks, kc, kp, kaa = figure(k) if k else ("—", "", "", "", False)
        closest = "rule closest" in k
        bench_rows.append(
            "<tr><td>%s</td><td>%s <span class=\"score\">%s</span></td><td class=\"num\">%s</td>"
            "<td class=\"num\">%s</td><td>%s <span class=\"score\">%s</span>%s</td>"
            "<td class=\"num\">%s</td><td class=\"num\">%s</td></tr>"
            % (esc(CLI_NAMES[cli]), esc(bn), esc(bs), esc(bc), esc(bp), esc(kn), esc(ks),
               " *" if closest else "", esc(kc), esc(kp)))

    skipped = ('<p class="muted">Not checked (setup): %s</p>' % esc(", ".join(data["skipped"]))
               if data["skipped"] else "")
    page = PAGE
    for key, value in (("time", esc(now.strftime("%m-%d %H:%M"))), ("version", esc(data["version"])),
                       ("cards", "".join(cards)), ("bench", "".join(bench_rows)),
                       ("skipped", skipped), ("compare", esc(COMPARE))):
        page = page.replace("@@%s@@" % key, value)
    return page


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Usage</title>
<style>
:root{--bg:#e9e4de;--card:#fbf9f6;--text:#2b2926;--muted:#69635c;--line:#d3cbc1;--track:#dad2c8;--green:#6f8f69;--amber:#b5893f;--red:#a65f59;--accent:#55718d}
@media (prefers-color-scheme:dark){:root{--bg:#1d1c1a;--card:#2b2926;--text:#f4efe8;--muted:#c0b8ae;--line:#47433e;--track:#4b4742;--green:#acc7a5;--amber:#e3c088;--red:#dc9d96;--accent:#a9bfd4}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:16px/1.6 "Inter","Segoe UI",system-ui,-apple-system,sans-serif;padding:40px 16px;-webkit-font-smoothing:antialiased}
main{max-width:1040px;margin:0 auto}h1{font-size:28px;font-weight:600;letter-spacing:-.01em;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px}
.grid{display:grid;grid-template-columns:1fr;gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
header{display:flex;align-items:baseline;gap:10px;margin-bottom:12px}
h2{font-size:17px;font-weight:600;margin:0}.plan{color:var(--muted);font-size:14px;border:1px solid var(--line);
border-radius:999px;padding:1px 8px}.usage{margin-left:auto;font-size:14px;color:var(--accent);text-decoration:none}
.row{display:grid;grid-template-columns:64px 1fr 52px 200px;align-items:center;gap:10px;margin:8px 0}
.lbl{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.06em}.track{height:8px;background:var(--track);border-radius:999px;overflow:hidden}
.fill{height:100%;border-radius:999px}.fill.green{background:var(--green)}.fill.amber{background:var(--amber)}
.fill.red{background:var(--red)}.pct{text-align:right;font-weight:600;font-variant-numeric:tabular-nums}
.pct.green{color:var(--green)}.pct.amber{color:var(--amber)}.pct.red{color:var(--red)}
.reset{color:var(--muted);font-size:14px;font-variant-numeric:tabular-nums}.rel{opacity:.8}
.note{color:var(--muted);font-style:italic;margin:6px 0}
.now{margin-top:12px;padding-top:10px;border-top:1px dashed var(--line);color:var(--muted);font-size:14px}
code{font-family:ui-monospace,Consolas,monospace;color:var(--text)}
h3{font-size:15px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:36px 0 8px}.std{color:var(--muted);font-size:14px;margin:0 0 8px;font-style:italic}
.tablewrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:14px}
table{border-collapse:collapse;width:100%;font-size:15px}th,td{padding:9px 12px;text-align:left;
border-bottom:1px solid var(--line);white-space:nowrap}th{color:var(--muted);font-weight:500;font-size:13px;text-transform:uppercase;letter-spacing:.06em}
tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums}.score{color:var(--muted)}
.foot{color:var(--muted);font-size:14px;margin:8px 0}.muted{color:var(--muted)}
.links{margin-top:20px}a{color:var(--accent)}
@media (max-width:480px){.row{grid-template-columns:44px 1fr 40px}.reset{grid-column:2/4}}
</style></head><body><main>
<h1>AI Usage</h1><p class="sub">@@time@@ · ai-usage @@version@@</p>
<div class="grid">@@cards@@</div>
<h3>Qualified (CursorBench)</h3>
<p class="std">Standard: any of the provider's models ≥ 50% → highest CP among those · none reach 50% → its highest score</p>
<div class="tablewrap"><table><thead><tr><th>Provider</th><th>Now</th><th class="num">Now $</th>
<th class="num">Now CP</th><th>Qualified</th><th class="num">Qualified $</th><th class="num">Qualified CP</th></tr></thead>
<tbody>@@bench@@</tbody></table></div>
<p class="foot">$ = cost per task at API prices (AA rows: AA's cost per index task), not subscription quota.
CP = score points per US dollar; higher is better. * nothing from this provider reaches 50%: its highest.
AA = Artificial Analysis Intelligence Index (another test set): not comparable with CursorBench.</p>
@@skipped@@
<p class="links">Compare models: <a href="@@compare@@" target="_blank" rel="noopener">AI Model Compare</a></p>
</main></body></html>
"""

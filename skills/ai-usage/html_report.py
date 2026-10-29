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
    """`Oct 21, 11:19am` or `Oct 21 at 11:19am` -> `10-21 11:19`; other formats pass through without the `(…)`."""
    text = re.sub(r"\s*\(.*\)$", "", reset).strip().replace(" at ", ", ")
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
    text = re.sub(r"\s*\(.*\)$", "", reset).strip().replace(" at ", ", ")
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


WEEK_MINUTES = 7 * 24 * 60
FIVE_HOURS = 5 * 60


def remaining_minutes(reset, now):
    """Minutes until the reset clock; falls back to the probe's coarse `(XdYh)`."""
    text = re.sub(r"\s*\(.*\)$", "", reset).strip().replace(" at ", ", ")
    for fmt in ("%b %d, %I:%M%p", "%b %d, %I%p", "%m-%d %H:%M"):
        try:
            when = datetime.datetime.strptime(text, fmt).replace(year=now.year)
        except ValueError:
            continue
        if when < now - datetime.timedelta(days=180):
            when = when.replace(year=now.year + 1)
        return max(0, int((when - now).total_seconds() // 60))
    found = re.search(r"\((\d+)d(\d+)h\)", reset)
    if found:
        return int(found.group(1)) * 1440 + int(found.group(2)) * 60
    return None


CLOCK = ('<svg class="clock" viewBox="0 0 16 16" aria-hidden="true">'
         '<circle cx="8" cy="8" r="6.25"/><path d="M8 4.6V8l2.4 1.5"/></svg>')


def left_text(minutes):
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return "%dd%dh left" % (days, hours)
    if hours:
        return "%dh%02dm left" % (hours, mins)
    return "%dm left" % mins


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


def advice(raw, now=None):
    """The chat lines: a warning per week window over 80%, then `→ Use <tool> right now`."""
    now = now or datetime.datetime.now()
    data = parse(raw)
    clis = {name: cli for cli, name in CLI_NAMES.items()}
    lines, ranked = [], []
    for p in data["providers"]:
        for w in p["windows"]:
            if w["label"] != "5h" and w["pct"] > 80:
                left = relative(w["reset"], now) if w["reset"] else ""
                lines.append("> **Warning:** %s %s is %s used%s." % (
                    p["name"], w["label"], w["shown"], "; resets in " + left if left else ""))
        # Gemini's cl+gpt pool serves other vendors' models, so only its gemini pool counts.
        pcts = [0 if w["shown"] == "<1%" else w["pct"] for w in p["windows"]
                if p["name"] != "Gemini" or w["label"] == "gemini"]
        # A free plan shows nearly 100% left because it is not really used; never pick it.
        # `?` counts as free: Gemini's /usage names no plan, and there it means free.
        if pcts and p["plan"].lower() not in ("free", "?"):
            bench = data["bench"].get(clis.get(p["name"]), "")
            score = re.search(r"score ([\d.]+)%", bench)
            ranked.append((100 - max(pcts), float(score.group(1)) if score and "(AA)" not in bench
                           else None, p["name"]))
    if not ranked:
        return lines
    ranked.sort(key=lambda item: -item[0])
    best = ranked[0]
    if len(ranked) > 1:
        second = ranked[1]
        if (best[0] - second[0] <= 10 and best[1] is not None and second[1] is not None
                and second[1] > best[1]):
            best = second
    lines.append("> **→ Use %s right now:** %d%% left in its tightest window." % (best[2], round(best[0])))
    return lines


def hue(pct):
    # 0% green (120) -> 50% yellow (60) -> 100% red (0), continuous.
    return round(120 * (1 - min(max(pct, 0), 100) / 100.0))


def render(raw, now=None):
    now = now or datetime.datetime.now()
    data = parse(raw)
    cards = []
    for p in data["providers"]:
        rows = []
        for w in p["windows"]:
            when = w["reset"]
            shown = clock(when, now) if when else ""
            rows.append(
                '<div class="row" style="--h:%d"><div class="lbl">%s</div>'
                '<div class="track"><div class="fill" style="width:%.1f%%"></div></div>'
                '<div class="pct">%s</div><div class="reset">%s</div></div>'
                % (hue(w["pct"]), esc(w["label"]), min(w["pct"], 100),
                   esc(w["shown"]), esc(shown)))
            left = remaining_minutes(when, now) if when else None
            if left is not None:
                # Time bar: full length is the window (5h or 7 days); the remaining
                # time fills from the right, the elapsed part stays empty on the left.
                five = w["label"] == "5h"
                total = FIVE_HOURS if five else WEEK_MINUTES
                share = max(0.0, min(100.0, left * 100.0 / total))
                # One tick per hour (5h window) or per day (7-day window).
                n = 5 if five else 7
                unit = "h" if five else "d"
                # Scale labels read as time left at that tick: n at the left, 0 at the reset.
                scale = "".join(
                    '<span class="%s" style="left:%.4f%%">%s</span>'
                    % ("first" if i == 0 else "last" if i == n else "", i * 100.0 / n,
                       "0" if i == n else "%d%s" % (n - i, unit))
                    for i in range(n + 1))
                rows.append(
                    '<div class="row time"><div class="lbl"></div>'
                    '<div class="tbar" style="--n:%d"><div class="ticks"></div>'
                    '<div class="track thin"><div class="tfill" style="width:%.1f%%"></div></div>'
                    '<div class="scale">%s</div></div>'
                    '<div class="left">%s%s</div></div>'
                    % (n, share, scale, CLOCK, esc(left_text(left))))
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
                       ("skipped", skipped), ("compare", esc(COMPARE)), ("dark", DARK)):
        page = page.replace("@@%s@@" % key, value)
    return page


# Tailwind CSS 3.4 Slate with blue; usage colour is an HSL hue from hue(), and its
# lightness (--tl) keeps every text colour at least 4.5:1
# on its card. Dark is used when the OS is dark, unless `data-theme` on <html> forces one.
DARK = ("--bg:#1e293b;--card:#334155;--text:#f1f5f9;--muted:#cbd5e1;--line:#475569;"
        "--track:#475569;--tick:#94a3b8;--fl:55%;--tl:78%;"
        "--accent:#93c5fd")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Usage</title>
<style>
:root{--bg:#f1f5f9;--card:#ffffff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--track:#e2e8f0;--tick:#94a3b8;--fl:45%;--tl:25%;--accent:#2563eb}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){@@dark@@}}
:root[data-theme=dark]{@@dark@@}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:16px/1.6 "Inter","Segoe UI",system-ui,-apple-system,sans-serif;padding:40px 16px;-webkit-font-smoothing:antialiased}
main{max-width:1040px;margin:0 auto}h1{font-size:28px;font-weight:600;letter-spacing:-.01em;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px}
.grid{display:grid;grid-template-columns:1fr;gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
header{display:flex;align-items:baseline;gap:10px;margin-bottom:12px}
h2{font-size:17px;font-weight:600;margin:0}.plan{color:var(--muted);font-size:14px;border:1px solid var(--line);
border-radius:999px;padding:1px 8px}.usage{margin-left:auto;font-size:14px;color:var(--accent);text-decoration:none}
.row{display:grid;grid-template-columns:64px 1fr 56px 112px;align-items:center;gap:10px;margin:8px 0}
.lbl{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.06em}.track{height:8px;background:var(--track);border-radius:999px;overflow:hidden}
.row.time{margin:-2px 0 26px}.tbar{position:relative;height:14px;display:flex;align-items:center}
.ticks{position:absolute;inset:0;border-right:2px solid var(--tick);
background:repeating-linear-gradient(to right,var(--tick) 0 2px,transparent 2px calc(100% / var(--n)))}
.scale{position:absolute;left:0;right:0;top:17px;height:14px;font-size:12px;line-height:14px;color:var(--muted);
font-variant-numeric:tabular-nums}.scale span{position:absolute;transform:translateX(-50%);white-space:nowrap}
.scale span.first{transform:none}.scale span.last{transform:translateX(-100%)}
.track.thin{position:relative;flex:1;height:4px;display:flex;justify-content:flex-end}
.tfill{height:100%;border-radius:999px;background:var(--accent);opacity:.6}
.clock{width:13px;height:13px;margin-right:5px;vertical-align:-2px;fill:none;stroke:currentColor;
stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.left{grid-column:3/5;text-align:left;white-space:nowrap;color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
.fill{height:100%;border-radius:999px;background:hsl(var(--h) 80% var(--fl))}
.pct{text-align:right;font-weight:600;font-variant-numeric:tabular-nums;color:hsl(var(--h) 85% var(--tl))}
.reset{white-space:nowrap;color:var(--muted);font-size:14px;font-variant-numeric:tabular-nums}.rel{opacity:.8}
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
@media (max-width:480px){.row{grid-template-columns:44px 1fr 40px}.reset{grid-column:2/4}.left{grid-column:2/4}}
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

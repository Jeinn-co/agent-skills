"""Render the launcher's raw report as one self-contained HTML page (`/ai-usage html`).

Input is exactly the text run.py prints; nothing is re-fetched. A local timer updates
reset expiry reminders without external requests, so the report works offline.
"""
import datetime
import html
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from report_i18n import ReportI18n

I18N = ReportI18n(SKILL_DIR, "ai-usage-lang")

from guidance_data import DAILY_CHOICES, EXCLUDED_GEMINI_PICKS, GEMINI_MODELS, OPTIONAL_GEMINI_EFFORT, ROLE_ASSIGNMENTS

NAMES = {"CLAUDE": "Claude", "CHATGPT": "ChatGPT", "GROK": "Grok", "MUSE": "Muse",
         "GEMINI": "Gemini"}
CLI_NAMES = {"claude": "Claude", "codex": "ChatGPT", "grok": "Grok", "muse": "Muse",
             "agy": "Gemini"}
# Product marks as 24x24 SVG paths, copied from AI Model Compare (src/logos.ts), which takes
# them from LobeHub Icons (MIT). Muse uses the Meta AI mark; Grok follows the text colour.
LOGOS = json.loads((SKILL_DIR / "data/logos.json").read_text(encoding="utf-8"))
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


def note_html(note, expires_at=None):
    # Legacy text-only reports stay static: display text cannot identify a DST fold.
    if expires_at is None:
        return '<div class="note">%s</div>' % esc(note)
    try:
        prefix, remaining = note.rsplit(" · ", 1)
        if not note.startswith("Reset"):
            raise ValueError()
    except ValueError:
        return '<div class="note">%s</div>' % esc(note)
    return ('<div class="note" data-reset-expires="%d">%s · '
            '<span data-reset-remaining>%s</span></div>'
            % (expires_at, esc(prefix), esc(remaining)))


def clock(reset, now):
    """`Oct 21, 11:19am` or `Oct 21 at 11:19am` -> `10-21 11:19`; other formats pass through without the `(…)`."""
    text = re.sub(r"\s*\(.*\)$", "", reset).strip().replace(" at ", ", ")
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone().strftime("%m-%d %H:%M")
    except ValueError:
        pass
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
    try:
        when = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    else:
        return max(0, int((when.astimezone() - now.astimezone()).total_seconds() // 60))
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


bi = I18N.bi


CLOCK = ('<svg class="clock" viewBox="0 0 16 16" aria-hidden="true">'
         '<circle cx="8" cy="8" r="6.25"/><path d="M8 4.6V8l2.4 1.5"/></svg>')


def window_label(label):
    """A window's label; `week` also reads in Chinese, the rest are names or `5h`."""
    return bi('week') if label == "week" else esc(label)


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
                current = {"id": section, "name": NAMES[section], "plan": "?", "windows": [],
                           "notes": [], "reset_expiries": {}, "model": None, "effort": None, "age": None}
                report["providers"].append(current)
        elif section == "CURSORBENCH":
            found = BENCH.match(line.strip())
            if found:
                report[found.group(1)][found.group(2)] = found.group(3).strip()
        elif current is not None and line.strip():
            text = line.strip()
            window = WINDOW.match(text)
            if text.startswith("reset-expiry "):
                try:
                    value = json.loads(text[len("reset-expiry "):])
                    stamp = value["expiresAt"]
                    if isinstance(stamp, bool) or not isinstance(stamp, int) or not isinstance(value["note"], str):
                        raise ValueError()
                    datetime.datetime.fromtimestamp(stamp / 1000, datetime.timezone.utc)
                    # Metadata belongs to the preceding note; equal display labels can have different seconds.
                    if current["notes"] and current["notes"][-1] == value["note"]:
                        current["reset_expiries"][len(current["notes"]) - 1] = stamp
                except (ValueError, TypeError, KeyError, OverflowError, OSError):
                    pass
            elif text.startswith("plan:"):
                current["plan"] = text[5:].strip() or "?"
            elif window:
                label, pct, middle = window.groups()
                reset = re.search(r"resets (.+)$", middle)
                period = re.search(r"\bwindow (.*?)\s+(?:pool |resets |$)", middle + " ")
                duration = {"weekly": WEEK_MINUTES,
                            "5h": FIVE_HOURS, "24h": 1440, "168h": WEEK_MINUTES}.get(
                                period.group(1).strip() if period else label)
                if period is None and duration is None and current["id"] != "GEMINI":
                    duration = {"short": FIVE_HOURS, "week": WEEK_MINUTES,
                                "outer": WEEK_MINUTES}.get(label)
                current["windows"].append({
                    "label": LABELS.get(label, label),
                    # A Pro/Ultra pool has a weekly and a 5h row; tag the 5h one so they differ.
                    "display": {"gemini": "Gemini", "cl+gpt": "Claude / GPT"}.get(label, LABELS.get(label, label))
                               + (" 5h" if label in ("gemini", "cl+gpt") and duration == FIVE_HOURS else ""),
                    "duration": duration,
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
    score = found.group(1).replace("score ", "").replace("aa ", "")
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
                if (p["name"] != "Gemini" or w["label"] == "gemini")
                # A Claude per-model cap (fable) does not block the other models.
                and (p["name"] != "Claude" or w["label"] in ("5h", "week"))]
        # A free plan shows nearly 100% left because it is not really used; never pick it.
        # `?` counts as free: Gemini's /usage names no plan, and there it means free.
        if pcts and p["plan"].lower() not in ("free", "?"):
            bench = data["bench"].get(clis.get(p["name"]), "")
            score = re.search(r"\baa ([\d.]+)", bench)
            ranked.append((100 - max(pcts), float(score.group(1)) if score else None, p["name"]))
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


def logo(cli):
    color, path = LOGOS[cli]
    return ('<svg class="logo" viewBox="0 0 24 24" aria-hidden="true"><path fill="%s" '
            'fill-rule="evenodd" clip-rule="evenodd" d="%s"/></svg>' % (color, path))


# Placeholder bars while a provider is fetched; the page shell also puts it into a card
# whose last lookup timed out, while that card is fetched again.
SKELETON = ('<div class="skel-body"><div class="skel" style="width:85%"></div>'
            '<div class="skel" style="width:65%"></div><div class="skel" style="width:40%"></div></div>')
# run.py's text for a probe that ran out of time; such a card is fetched again by the page.
TIMED_OUT = "usage call timed out"


def card(p, now, loading=False):
    """One provider's <section>; `loading` draws the skeleton instead of its numbers."""
    rows = []
    # Claude with a Fable cap: each reset credit sits under the bar it clears.
    under, moved = {}, set()
    labels = set() if loading else {w["label"] for w in p["windows"]}
    if p["id"] == "CLAUDE" and {"week", "fable"} <= labels:
        for index, note in enumerate(p["notes"]):
            found = re.match(r"Reset \((\d+) left([^)]*)\)", note)
            if found:
                group = under.setdefault("fable" if "Fable only" in found.group(2) else "week", [0, []])
                group[0] += int(found.group(1))
                group[1].append(note_html(note, p.get("reset_expiries", {}).get(index)))
                moved.add(index)
        if moved:
            moved.update(i for i, note in enumerate(p["notes"]) if note.startswith("Limit resets:"))
    for w in [] if loading else p["windows"]:
        when = w["reset"]
        shown = clock(when, now) if when else ""
        if p["id"] == "CLAUDE" and w["label"] == "fable":
            rows.append('<hr>')
        rows.append(
            '<div class="row" style="--h:%d"><div class="lbl">%s</div>'
            '<div class="track"><div class="fill" style="width:%.1f%%"></div></div>'
            '<div class="pct">%s</div><div class="reset">%s</div></div>'
            % (hue(w["pct"]), window_label(w.get("display", w["label"])), min(w["pct"], 100),
               esc(w["shown"]), esc(shown)))
        left = remaining_minutes(when, now) if when else None
        total = w.get("duration")
        if left is not None and total is not None:
            # Draw a scale only for a period explicitly reported or known by the provider.
            share = max(0.0, min(100.0, left * 100.0 / total))
            n = 7 if total == WEEK_MINUTES else 4 if total == 1440 else 5
            unit = "d" if total == WEEK_MINUTES else "h"
            step = 6 if total == 1440 else 1
            # Scale labels read as time left at that tick: n at the left, 0 at the reset.
            scale = "".join(
                '<span class="%s" style="left:%.4f%%">%s</span>'
                % ("first" if i == 0 else "last" if i == n else "", i * 100.0 / n,
                   "0" if i == n else "%d%s" % ((n - i) * step, unit))
                for i in range(n + 1))
            rows.append(
                '<div class="row time"><div class="lbl"></div>'
                '<div class="tbar" style="--n:%d"><div class="ticks"></div>'
                '<div class="track thin"><div class="tfill" style="width:%.1f%%"></div></div>'
                '<div class="scale">%s</div></div>'
                '<div class="left">%s%s</div></div>'
                % (n, share, scale, CLOCK, bi("remaining", duration=esc(left_text(left)[:-5]))))
        if w["label"] in under:
            count, notes = under.pop(w["label"])
            rows.append('<fieldset class="reset-credits"><legend>Limit resets: %d available</legend>%s</fieldset>'
                        % (count, "".join(notes)))
    reset_group = False
    for index, note in enumerate([] if loading else p["notes"]):
        if index in moved:
            continue
        if reset_group and not re.match(r"Reset(?: \d+:| \(| details:)", note):
            rows.append('</fieldset>')
            reset_group = False
        if note.startswith(("Usage limit resets:", "Limit resets:")):
            rows.append('<fieldset class="reset-credits"><legend>%s</legend>' % esc(note))
            reset_group = True
        else:
            rows.append(note_html(note, p.get("reset_expiries", {}).get(index)))
    if reset_group:
        rows.append('</fieldset>')
    if not loading and p["id"] in ("CLAUDE", "CHATGPT") and any("not signed in" in note for note in p["notes"]):
        status_id = p["id"].lower() + "-login-status"
        rows.append('<button type="button" class="login" data-provider-login="%s" '
                    'data-provider-name="%s" hidden aria-describedby="%s">%s</button>'
                    '<p id="%s" class="note" role="status" hidden></p>' %
                    (p["id"], esc(p["name"]), status_id, bi("sign_in", name=esc(p["name"])), status_id))
    if loading:
        rows.append(SKELETON)
        now_line = '<span class="skel" style="display:inline-block;width:30%;vertical-align:middle"></span>'
    elif p["model"]:
        now_line = "<code>%s</code> / <strong>%s</strong>" % (
            esc(p["model"]), esc(p["effort"] or "?"))
    else:
        now_line = bi('no_local_session')
    timed_out = any(note.startswith(TIMED_OUT) for note in p["notes"])
    clis = {name: cli for cli, name in CLI_NAMES.items()}
    link = USAGE_PAGES.get(p["name"])
    return ('<section class="card" data-id="%s"%s><header><h2>%s%s</h2><span class="plan">%s</span>%s</header>%s'
            '<div class="now">%s%s</div></section>'
            % (esc(p["id"]), " data-timeout" if timed_out and not loading else "",
               logo(clis[p["name"]]), esc(p["name"]), "…" if loading else esc(p["plan"]),
               '<a class="usage" href="%s" target="_blank" rel="noopener">%s</a>'
               % (esc(link), bi('usage_page')) if link else "",
               "".join(rows), bi('now_label'), now_line))


# Row tint class per CLI; the CSS gives each the same --brand as its provider card.
BRAND = {"claude": "anth", "codex": "oai", "grok": "grok", "muse": "muse", "agy": "gemini"}


def bench_rows(data, loading=False):
    """The Qualified (AA) <tr>s; `loading` gives one skeleton row per provider."""
    if loading:
        return "".join('<tr><td colspan="7"><div class="skel"></div></td></tr>'
                       for _ in data["providers"])
    rows = []
    for cli in CLI_NAMES:
        if cli not in data["pick"] and cli not in data["bench"]:
            continue
        b = data["bench"].get(cli, "")
        k = data["pick"].get(cli, "")
        bn, bs, bc, bp, baa = figure(b) if b else ("—", "", "", "", False)
        kn, ks, kc, kp, kaa = figure(k) if k else ("—", "", "", "", False)
        closest = "rule closest" in k
        rows.append(
            "<tr class=\"%s\"><td>%s</td><td>%s <span class=\"score\">%s</span></td><td class=\"num\">%s</td>"
            "<td class=\"num\">%s</td><td>%s <span class=\"score\">%s</span>%s</td>"
            "<td class=\"num\">%s</td><td class=\"num\">%s</td></tr>"
            % (BRAND[cli], esc(CLI_NAMES[cli]), esc(bn), esc(bs), esc(bc), esc(bp), esc(kn), esc(ks),
               " *" if closest else "", esc(kc), esc(kp)))
    return "".join(rows)


def card_html(raw, now=None):
    """The card for the one provider section in `raw` (`### CLAUDE` plus its lines)."""
    return card(parse(raw)["providers"][0], now or datetime.datetime.now())


def bench_html(raw):
    """The Qualified (AA) rows for `raw` (`### CURSORBENCH` plus its lines)."""
    return bench_rows(parse(raw))


def role_rows():
    """Render the existing role table from its data records."""
    rows = []
    for role in ROLE_ASSIGNMENTS:
        cells = []
        for brand in ("anth", "oai", "gemini"):
            model, effort = role["models"][brand]
            cells.append('<td class="%s">%s / %s</td>' % (brand, esc(model), esc(effort)))
        label = '<b>%s</b>' % esc(role["role"])
        rows.append('<tr><td>%s</td>%s</tr>' % (
            bi(role["description"], role=label), ''.join(cells)))
    return ''.join(rows)


def render(raw, now=None, loading=False):
    """The whole page; `loading` shows every card and the bench table as skeletons."""
    now = now or datetime.datetime.now()
    data = parse(raw)
    cards = "".join(card(p, now, loading) for p in data["providers"])
    skipped = ('<p class="muted">%s%s</p>' % (bi('not_checked'),
                                             esc(", ".join(data["skipped"])))
               if data["skipped"] else "")
    page = I18N.template(PAGE)
    choices = {provider: esc(model + " / " + effort) for provider, (model, effort) in DAILY_CHOICES.items()}
    page = page.replace("@@my_usage_choices@@", bi("my_usage_choices", **choices))
    security = next(role["models"]["gemini"] for role in ROLE_ASSIGNMENTS if role["role"] == "Security")
    policy = bi("role_policy", daily=choices["gemini"], security=esc(" / ".join(security)),
                optional=esc(OPTIONAL_GEMINI_EFFORT),
                excluded=esc(", ".join(GEMINI_MODELS[model]["name"] for model in sorted(EXCLUDED_GEMINI_PICKS))))
    for key, value in (("time", esc(now.strftime("%m-%d %H:%M"))), ("version", esc(data["version"])),
                       ("cards", cards), ("bench", bench_rows(data, loading)), ("roles", role_rows()),
                       ("role_policy", policy),
                       ("skipped", skipped), ("compare", esc(COMPARE)), ("dark", DARK),
                       ("expiry_script", EXPIRY_SCRIPT), ("language_button", I18N.language_button), ("lang_head", LANG_HEAD),
                       ("lang_script", LANG_SCRIPT)):
        page = page.replace("@@%s@@" % key, value)
    return page


# Tailwind CSS 3.4 Slate with blue; usage colour is an HSL hue from hue(), and its
# lightness (--tl) keeps every text colour at least 4.5:1
# on its card. Dark is used when the OS is dark, unless `data-theme` on <html> forces one.
DARK = ("color-scheme:dark;--bg:#1e293b;--card:#334155;--text:#f1f5f9;--muted:#cbd5e1;--line:#475569;"
        "--track:#475569;--tick:#94a3b8;--fl:55%;--tl:78%;"
        "--accent:#93c5fd;--tint:.14")

EXPIRY_SCRIPT = (Path(__file__).resolve().parent / 'assets/reset-expiry.js').read_text(encoding="utf-8")

# Picks the language before the page paints: the last choice, else the browser's language.
LANG_HEAD = I18N.head()

# The switch names the other language and remembers the choice for the next report.
LANG_SCRIPT = I18N.language_script()

PAGE = (Path(__file__).resolve().parent / 'templates/report.html').read_text(encoding="utf-8")

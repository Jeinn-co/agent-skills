"""Render the launcher's raw report as one self-contained HTML page (`/ai-usage html`).

Input is exactly the text run.py prints; nothing is re-fetched. A local timer updates
reset expiry reminders without external requests, so the report works offline.
"""
import datetime
import html
import json
import re

NAMES = {"CLAUDE": "Claude", "CHATGPT": "ChatGPT", "GROK": "Grok", "MUSE": "Muse",
         "GEMINI": "Gemini"}
CLI_NAMES = {"claude": "Claude", "codex": "ChatGPT", "grok": "Grok", "muse": "Muse",
             "agy": "Gemini"}
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


def bi(en, zh):
    """Both languages; the page shows the one its switch is on. Arguments are HTML."""
    return '<span class="l-en">%s</span><span class="l-zh">%s</span>' % (en, zh)


CLOCK = ('<svg class="clock" viewBox="0 0 16 16" aria-hidden="true">'
         '<circle cx="8" cy="8" r="6.25"/><path d="M8 4.6V8l2.4 1.5"/></svg>')


def window_label(label):
    """A window's label; `week` also reads in Chinese, the rest are names or `5h`."""
    return bi("week", "週") if label == "week" else esc(label)


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
                if p["name"] != "Gemini" or w["label"] == "gemini"]
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
    for w in [] if loading else p["windows"]:
        when = w["reset"]
        shown = clock(when, now) if when else ""
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
                % (n, share, scale, CLOCK, bi(esc(left_text(left)), esc("剩 " + left_text(left)[:-5]))))
    reset_group = False
    for index, note in enumerate([] if loading else p["notes"]):
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
                    'data-provider-name="%s" hidden aria-describedby="%s">Sign in to %s</button>'
                    '<p id="%s" class="note" role="status" hidden></p>' %
                    (p["id"], esc(p["name"]), status_id, esc(p["name"]), status_id))
    if loading:
        rows.append(SKELETON)
        now_line = '<span class="skel" style="display:inline-block;width:30%;vertical-align:middle"></span>'
    elif p["model"]:
        head = "<code>%s</code> · effort %s · %s" % (
            esc(p["model"]), esc(p["effort"] or "?"), esc((p["age"] or "?").replace(" ago", "")))
        now_line = bi(head + " ago", head + " 前")
    else:
        now_line = bi("no local session", "沒有本機 session")
    timed_out = any(note.startswith(TIMED_OUT) for note in p["notes"])
    clis = {name: cli for cli, name in CLI_NAMES.items()}
    link = USAGE_PAGES.get(p["name"])
    return ('<section class="card" data-id="%s"%s><header><h2>%s%s</h2><span class="plan">%s</span>%s</header>%s'
            '<div class="now">%s%s</div></section>'
            % (esc(p["id"]), " data-timeout" if timed_out and not loading else "",
               logo(clis[p["name"]]), esc(p["name"]), "…" if loading else esc(p["plan"]),
               '<a class="usage" href="%s" target="_blank" rel="noopener">%s</a>'
               % (esc(link), bi("Usage page", "用量頁")) if link else "",
               "".join(rows), bi("Now: ", "目前："), now_line))


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
            "<tr><td>%s</td><td>%s <span class=\"score\">%s</span></td><td class=\"num\">%s</td>"
            "<td class=\"num\">%s</td><td>%s <span class=\"score\">%s</span>%s</td>"
            "<td class=\"num\">%s</td><td class=\"num\">%s</td></tr>"
            % (esc(CLI_NAMES[cli]), esc(bn), esc(bs), esc(bc), esc(bp), esc(kn), esc(ks),
               " *" if closest else "", esc(kc), esc(kp)))
    return "".join(rows)


def card_html(raw, now=None):
    """The card for the one provider section in `raw` (`### CLAUDE` plus its lines)."""
    return card(parse(raw)["providers"][0], now or datetime.datetime.now())


def bench_html(raw):
    """The Qualified (AA) rows for `raw` (`### CURSORBENCH` plus its lines)."""
    return bench_rows(parse(raw))


def render(raw, now=None, loading=False):
    """The whole page; `loading` shows every card and the bench table as skeletons."""
    now = now or datetime.datetime.now()
    data = parse(raw)
    cards = "".join(card(p, now, loading) for p in data["providers"])
    skipped = ('<p class="muted">%s%s</p>' % (bi("Not checked (setup): ", "未檢查（setup）："),
                                             esc(", ".join(data["skipped"])))
               if data["skipped"] else "")
    page = PAGE
    for key, value in (("time", esc(now.strftime("%m-%d %H:%M"))), ("version", esc(data["version"])),
                       ("cards", cards), ("bench", bench_rows(data, loading)),
                       ("skipped", skipped), ("compare", esc(COMPARE)), ("dark", DARK),
                       ("expiry_script", EXPIRY_SCRIPT), ("lang_head", LANG_HEAD),
                       ("lang_script", LANG_SCRIPT)):
        page = page.replace("@@%s@@" % key, value)
    return page


# Tailwind CSS 3.4 Slate with blue; usage colour is an HSL hue from hue(), and its
# lightness (--tl) keeps every text colour at least 4.5:1
# on its card. Dark is used when the OS is dark, unless `data-theme` on <html> forces one.
DARK = ("--bg:#1e293b;--card:#334155;--text:#f1f5f9;--muted:#cbd5e1;--line:#475569;"
        "--track:#475569;--tick:#94a3b8;--fl:55%;--tl:78%;"
        "--accent:#93c5fd;--anth:rgba(217,119,87,.16);--oai:rgba(16,163,127,.16)")

EXPIRY_SCRIPT = """function updateResetExpiry() {
  document.querySelectorAll('[data-reset-expires]').forEach(note => {
    const left = (Number(note.dataset.resetExpires) - Date.now()) / 60000;
    if (!Number.isFinite(left)) return;
    note.toggleAttribute('data-expiring', left <= 300);
    note.toggleAttribute('data-urgent', left <= 30);
    note.style.setProperty('--reset-hue', Math.max(0, Math.min(40, (left - 60) / 6)));
    const minutes = Math.max(0, Math.floor(left));
    const zh = Boolean(document.documentElement && document.documentElement.dataset.lang === 'zh');
    const units = [[Math.floor(minutes / 1440), zh ? '天' : 'day'],
      [Math.floor(minutes % 1440 / 60), zh ? '小時' : 'hour'], [minutes % 60, zh ? '分鐘' : 'minute']];
    const duration = (minutes >= 1440 ? units.slice(0, 2) : units)
      .filter(([n]) => n).map(([n, unit]) => n + ' ' + unit + (zh || n === 1 ? '' : 's')).join(' ');
    note.querySelector('[data-reset-remaining]').textContent = left <= 0 ? (zh ? '已過期' : 'expired') :
      zh ? '剩 ' + (duration || '不到一分鐘') : (duration || 'less than a minute') + ' left';
  });
}
updateResetExpiry();
setInterval(updateResetExpiry, 60000);
"""

# Picks the language before the page paints: the last choice, else the browser's language.
LANG_HEAD = """(function () {
  var lang;
  try { lang = localStorage.getItem('ai-usage-lang'); } catch (e) {}
  if (lang !== 'zh' && lang !== 'en') lang = /^zh/i.test(navigator.language || '') ? 'zh' : 'en';
  document.documentElement.dataset.lang = lang;
  document.documentElement.lang = lang === 'zh' ? 'zh-Hant' : 'en';
})();"""

# The switch names the other language and remembers the choice for the next report.
LANG_SCRIPT = """(function () {
  var root = document.documentElement, button = document.getElementById('lang');
  function label() {
    var zh = root.dataset.lang === 'zh';
    button.textContent = zh ? 'EN' : '中文';
    button.setAttribute('aria-label', zh ? 'Switch to English' : '切換成中文');
  }
  button.addEventListener('click', function () {
    var lang = root.dataset.lang === 'zh' ? 'en' : 'zh';
    root.dataset.lang = lang;
    root.lang = lang === 'zh' ? 'zh-Hant' : 'en';
    try { localStorage.setItem('ai-usage-lang', lang); } catch (e) {}
    label();
    if (typeof updateResetExpiry === 'function') updateResetExpiry();
  });
  label();
})();"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Usage</title>
<script>@@lang_head@@</script>
<style>
:root{--bg:#f1f5f9;--card:#ffffff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--track:#e2e8f0;--tick:#94a3b8;--fl:45%;--tl:25%;--accent:#2563eb;--anth:rgba(217,119,87,.07);--oai:rgba(16,163,127,.07)}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){@@dark@@}}
:root[data-theme=dark]{@@dark@@}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:16px/1.6 "Inter","Segoe UI",system-ui,-apple-system,sans-serif;padding:40px clamp(14px,4vw,40px) 48px;-webkit-font-smoothing:antialiased}
main{max-width:1040px;margin:0 auto}h1{font-size:28px;font-weight:600;letter-spacing:-.01em;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px}
.grid{display:grid;grid-template-columns:1fr;gap:20px}
.card{--brand:100,116,139;background:linear-gradient(180deg,rgba(var(--brand),.09),transparent 100px),var(--card);border:1px solid var(--line);border-left:4px solid rgb(var(--brand));border-radius:12px;padding:22px clamp(16px,3vw,28px) 20px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.card[data-id=CLAUDE],.anth{--brand:217,119,87}
.card[data-id=CHATGPT],.oai{--brand:16,163,127}
.card[data-id=GROK]{--brand:148,163,184}
.card[data-id=MUSE]{--brand:149,83,255}
.card[data-id=GEMINI],.gemini{--brand:49,134,255}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 10px;margin-bottom:16px}
h2{font-size:17px;font-weight:600;margin:0}.logo{width:18px;height:18px;margin-right:8px;vertical-align:-3px}.plan{color:var(--muted);font-size:14px;border:1px solid var(--line);
border-radius:999px;padding:1px 8px}.usage{margin-left:auto;font-size:14px;color:var(--accent);text-decoration:none}
.row{display:grid;grid-template-columns:64px 1fr 56px 112px;align-items:center;gap:6px 12px;margin:10px 0}
.lbl,.reset-credits{font-size:13px}
.lbl{color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.track{height:8px;background:var(--track);border-radius:999px;overflow:hidden}
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
.note{color:var(--muted);font-style:normal;font-size:13px;margin:6px 0}
.reset-credits{min-width:0;margin:14px 0 0;padding:4px 12px 8px;border:1px solid var(--line);
border-radius:8px;color:var(--muted);overflow-wrap:anywhere}
.reset-credits legend{padding:0 6px}
.reset-credits .note{font-size:inherit}
.note[data-expiring]{color:hsl(var(--reset-hue) 85% var(--tl))}
.note[data-urgent]{font-weight:700;border:1px solid currentColor;border-radius:4px;
padding:4px 8px;width:fit-content;max-width:100%}
.login{font:inherit;font-size:14px;min-height:32px;padding:6px 10px;margin:8px 0;
border:1px solid var(--accent);border-radius:6px;background:transparent;color:var(--accent);cursor:pointer}
.login:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.login:disabled{opacity:.65;cursor:wait}
.skel-body{display:grid;gap:14px;margin:14px 0 6px}
.skel{height:10px;border-radius:999px;background:linear-gradient(90deg,var(--track) 30%,var(--card) 50%,var(--track) 70%);
background-size:300% 100%;animation:shimmer 1.4s linear infinite}
@keyframes shimmer{from{background-position:100% 0}to{background-position:0 0}}
@media (prefers-reduced-motion:reduce){.skel{animation:none}}
.now{margin-top:18px;padding-top:14px;border-top:1px dashed var(--line);color:var(--muted);font-size:14px}
code{font-family:ui-monospace,Consolas,monospace;color:var(--text)}
h3{font-size:15px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:48px 0 10px}.std{color:var(--muted);font-size:14px;margin:0 0 14px;font-style:italic}.rule{color:var(--accent);font-size:18px;font-weight:700;border-left:4px solid var(--accent);padding:6px 14px;margin:0 0 12px}
.tablewrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:14px}
table{border-collapse:collapse;width:100%;font-size:15px}th,td{padding:10px 16px;text-align:left;
border-bottom:1px solid var(--line);white-space:nowrap}th{color:var(--muted);font-weight:500;font-size:13px;text-transform:uppercase;letter-spacing:.06em}
tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums}.score{color:var(--muted)}
.foot{color:var(--muted);font-size:14px;margin:10px 4px 0}.muted{color:var(--muted)}
.links{margin:32px 0 0}a{color:var(--accent)}
:root:not([data-lang=zh]) .l-zh,:root[data-lang=zh] .l-en{display:none}
.top{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.lang{font:inherit;font-size:14px;min-height:32px;padding:4px 14px;border:1px solid var(--accent);border-radius:999px;background:transparent;color:var(--accent);cursor:pointer}
.lang:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
tr.anth td,tr.oai td,tr.gemini td,td.anth,td.oai,td.gemini{background:rgba(var(--brand),.07)}
tr.anth td:first-child,tr.oai td:first-child,tr.gemini td:first-child{border-left:4px solid rgb(var(--brand))}
.usage-guide td{white-space:normal;min-width:140px}
@media (max-width:480px){.row{grid-template-columns:44px 1fr 40px}.reset{grid-column:2/4}.left{grid-column:2/4}
.row.time{row-gap:24px;margin-bottom:18px}h3{margin-top:40px}th,td{padding:9px 12px}}
</style></head><body><main>
<div class="top"><h1>AI Usage</h1><button type="button" class="lang" id="lang">中文</button></div><p class="sub">@@time@@ · ai-usage @@version@@</p>
<div class="grid">@@cards@@</div>
<h3><span class="l-en">My usage</span><span class="l-zh">我的用法</span></h3>
<p class="rule"><span class="l-en">Feels dumb or not proactive? Don't second-guess it: move up a step right away.</span><span class="l-zh">覺得它很笨、不主動？不要懷疑，馬上升級。</span></p>
<p class="std"><span class="l-en">Official guidance first, then my own habits (checked 2026-11-12). Claude Code: Anthropic recommends starting most coding and knowledge work on Opus 5.5 and moving up to Fable 5.2 for the most ambitious, open-ended work; Claude Code defaults to medium effort. <strong>Fable models are expensive (twice Opus 5.5&rsquo;s token rates): use them as little as possible, only when Opus 5.5 / high is not enough.</strong> My habit is Opus 5.5 / high (27 of my last 34 sessions), so routine work runs Opus 5.5 / medium &rarr; high. Simple tasks can step down to Sonnet 5.5 or Haiku 5.5. Lower effort changes the reasoning budget, not the token rates: per million input/output tokens, Opus 5.5 is $4/$20 and Fable 5.2 is $8/$40. Anthropic reports Fable 5.2 at lower effort matching Opus 5.5&rsquo;s top score at a lower cost per task on some benchmarks; Fable / low is not part of my routing. API prices do not establish subscription quota consumption.</span><span class="l-zh">官方建議優先，再加上我的使用習慣（2026-11-12 核對）。Claude Code：Anthropic 建議多數程式與知識工作從 Opus 5.5 開始，最有挑戰、開放式的工作再升到 Fable 5.2；Claude Code 預設 effort 是 medium。<strong>Fable 系列很貴（token 單價是 Opus 5.5 的 2 倍）：能少用就少用，只在 Opus 5.5 / high 不夠時才用。</strong>我的習慣是 Opus 5.5 / high（最近 34 個 session 有 27 個），所以日常用 Opus 5.5 / medium &rarr; high。簡單任務可降到 Sonnet 5.5 或 Haiku 5.5。降低 effort 只改變推理預算，不會降低 token 單價：每百萬輸入／輸出 token，Opus 5.5 為 $4/$20，Fable 5.2 為 $8/$40。Anthropic 表示 Fable 5.2 在部分測試以較低 effort 就能用更低的每題成本追平 Opus 5.5 最高分；Fable / low 不在我的用法裡。API 價格不代表訂閱額度消耗。</span></p>
<p class="foot"><span class="l-en">Sources: <a href="https://www.anthropic.com/claude-fable-and-mythos-5-2" target="_blank" rel="noopener">Anthropic model selection</a> · <a href="https://platform.claude.com/docs/en/about-claude/pricing" target="_blank" rel="noopener">Claude API pricing</a> · <a href="https://developers.openai.com/api/docs/models/gpt-6.1-sol" target="_blank" rel="noopener">OpenAI GPT-6.1-Sol</a> · <a href="https://ai.google.dev/gemini-api/docs/latest-model" target="_blank" rel="noopener">Google Gemini 4 Argon</a>.</span><span class="l-zh">依據：<a href="https://www.anthropic.com/claude-fable-and-mythos-5-2" target="_blank" rel="noopener">Anthropic 模型選擇</a> · <a href="https://platform.claude.com/docs/en/about-claude/pricing" target="_blank" rel="noopener">Claude API 定價</a> · <a href="https://developers.openai.com/api/docs/models/gpt-6.1-sol" target="_blank" rel="noopener">OpenAI GPT-6.1-Sol</a> · <a href="https://ai.google.dev/gemini-api/docs/latest-model" target="_blank" rel="noopener">Google Gemini 4 Argon</a>。</span></p>
<p class="std"><span class="l-en">Codex: OpenAI&rsquo;s default effort for GPT-6.1-Sol is medium (low through max are available). My habit is high (16 of my last 26 Sol threads), so routine work runs GPT-6.1-Sol / medium &rarr; high, and harder tasks high &rarr; max. GPT-6.1-Terra is for visual understanding and app operation. Gemini: Google recommends medium thinking for most tasks, including complex code and agentic work, and the lowest level that meets the quality bar. Gemini 4 Carbon is excluded because access is limited to selected cybersecurity defenders through Google&rsquo;s Fairwind program (checked 2026-11-10).</span><span class="l-zh">Codex：OpenAI 給 GPT-6.1-Sol 的預設 effort 是 medium（可選 low 到 max）。我的習慣是 high（最近 26 個 Sol thread 有 16 個），所以日常用 GPT-6.1-Sol / medium &rarr; high，進階任務用 high &rarr; max。GPT-6.1-Terra 用於視覺理解與操作 app。Gemini：Google 建議多數任務（含複雜程式與 agent 工作）用 medium thinking，並選達到品質要求的最低一檔。Gemini 4 Carbon 因僅透過 Google Fairwind 計畫開放給經挑選的資安防禦單位而不列入（2026-11-10 確認）。</span></p>
<div class="tablewrap"><table class="usage-guide"><thead><tr><th><span class="l-en">Platform</span><span class="l-zh">平台</span></th><th><span class="l-en">Daily default</span><span class="l-zh">平日預設</span></th><th><span class="l-en">Harder tasks</span><span class="l-zh">進階任務</span></th><th><span class="l-en">Special use</span><span class="l-zh">特殊用途</span></th></tr></thead><tbody>
<tr class="anth"><td>Claude Code</td><td>Opus 5.5 / medium &rarr; Opus 5.5 / high</td><td>Fable 5.2 / medium &rarr; Fable 5.2 / high <span class="l-en">(only when Opus 5.5 / high is not enough)</span><span class="l-zh">（Opus 5.5 / high 不夠時才用）</span></td><td><span class="l-en">Sonnet 5.5 or Haiku 5.5: simple tasks</span><span class="l-zh">Sonnet 5.5 或 Haiku 5.5：簡單任務</span></td></tr>
<tr class="oai"><td>Codex</td><td>GPT-6.1-Sol / medium &rarr; GPT-6.1-Sol / high</td><td>GPT-6.1-Sol / high &rarr; GPT-6.1-Sol / max</td><td><span class="l-en">GPT-6.1-Terra: visual understanding and app operation</span><span class="l-zh">GPT-6.1-Terra：視覺理解與操作 app</span></td></tr>
<tr class="gemini"><td>Gemini</td><td>Gemini 4 Argon / medium</td><td>Gemini 4 Argon / high</td><td>&mdash;</td></tr>
</tbody></table></div>
<p class="foot"><span class="l-en">Model availability depends on the account and current model list. These preferences do not change CLI settings.</span><span class="l-zh">模型能不能用，取決於帳號與目前的模型清單。這些偏好不會更改 CLI 設定。</span></p>
<h3><span class="l-en">Delegated roles</span><span class="l-zh">角色分派</span></h3>
<p class="std"><span class="l-en">s-agent role configuration snapshot, checked on 2026-11-10. Select roles for the task and start with one subagent; the full team is not launched every time.</span><span class="l-zh">s-agent 角色設定快照，2026-11-10 核對。依任務挑角色，先派一個子 agent；不會每次都跑完整團隊。</span></p>
<div class="tablewrap"><table class="usage-guide"><thead><tr><th><span class="l-en">Role / responsibility</span><span class="l-zh">角色／職責</span></th><th>Claude Code</th><th>Codex</th><th>Gemini</th></tr></thead><tbody>
<tr><td><span class="l-en">PM: requirements and planning</span><span class="l-zh">PM：需求與規劃</span></td><td class="anth">Opus 5.5 / medium</td><td class="oai">GPT-6.1-Sol / medium</td><td class="gemini">Gemini 4 Argon / medium</td></tr>
<tr><td><span class="l-en">Designer: UI, interaction and accessibility</span><span class="l-zh">Designer：UI、互動與無障礙</span></td><td class="anth">Opus 5.5 / medium</td><td class="oai">GPT-6.1-Terra / medium</td><td class="gemini">Gemini 4 Argon / medium</td></tr>
<tr><td><span class="l-en">Developer: implementation and bug fixes</span><span class="l-zh">Developer：實作與修 bug</span></td><td class="anth">Opus 5.5 / medium</td><td class="oai">GPT-6.1-Sol / medium</td><td class="gemini">Gemini 4 Argon / medium</td></tr>
<tr><td><span class="l-en">QA: reproduction and acceptance checks</span><span class="l-zh">QA：重現問題與驗收</span></td><td class="anth">Fable 5.2 / low</td><td class="oai">GPT-6.1-Sol / high</td><td class="gemini">Gemini 4 Argon / high</td></tr>
<tr><td><span class="l-en">Reviewer: independent review</span><span class="l-zh">Reviewer：獨立審查</span></td><td class="anth">Fable 5.2 / low</td><td class="oai">GPT-6.1-Sol / high</td><td class="gemini">Gemini 4 Argon / high</td></tr>
<tr><td><span class="l-en">DevOps: environments and operations</span><span class="l-zh">DevOps：環境與維運</span></td><td class="anth">Fable 5.2 / low</td><td class="oai">GPT-6.1-Sol / high</td><td class="gemini">Gemini 4 Argon / high</td></tr>
</tbody></table></div>
<p class="foot"><span class="l-en">Source: <a href="https://honorable-ground-e97.notion.site/s-agent-config-effort-4118e936085b810891bdc1a77dd59b63" target="_blank" rel="noopener">Notion s-agent role configuration</a>. This is a static snapshot, not a live Notion read or sync, and does not establish model access. Actual dispatch checks configuration, tools and account permissions separately.</span><span class="l-zh">來源：<a href="https://honorable-ground-e97.notion.site/s-agent-config-effort-4118e936085b810891bdc1a77dd59b63" target="_blank" rel="noopener">Notion s-agent 角色設定</a>。這是靜態快照，不是即時讀取或同步 Notion，也不代表帳號能用這些模型。實際派工時會另外檢查設定、工具與帳號權限。</span></p>
<h3><span class="l-en">Qualified (Artificial Analysis)</span><span class="l-zh">合格（Artificial Analysis）</span></h3>
<p class="std"><span class="l-en">Standard (the bar for important tasks): among eligible models, Artificial Analysis Intelligence Index ≥ 50 → highest CP; none reach 50 → highest score. Claude picks follow My usage, so Fable / low and minimal are left out, even though AA rates Fable 5.2 / low above Opus 5.5 / high on both score and cost; their measured results remain visible under Now.</span><span class="l-zh">標準（重要任務的門檻）：符合選用規則的模型中，Artificial Analysis Intelligence Index 達 50 分以上 → 取 CP 最高者；都未達 50 → 取最高分。Claude 的挑選依「我的用法」，所以不選 Fable / low 與 minimal，即使 AA 上 Fable 5.2 / low 的分數與成本都優於 Opus 5.5 / high；它們的實測結果仍會顯示在「目前」欄。</span></p>
<div class="tablewrap"><table><thead><tr><th><span class="l-en">Provider</span><span class="l-zh">供應商</span></th><th><span class="l-en">Now</span><span class="l-zh">目前</span></th><th class="num"><span class="l-en">Now $</span><span class="l-zh">目前 $</span></th>
<th class="num"><span class="l-en">Now CP</span><span class="l-zh">目前 CP</span></th><th><span class="l-en">Qualified</span><span class="l-zh">合格</span></th><th class="num"><span class="l-en">Qualified $</span><span class="l-zh">合格 $</span></th><th class="num"><span class="l-en">Qualified CP</span><span class="l-zh">合格 CP</span></th></tr></thead>
<tbody id="bench">@@bench@@</tbody></table></div>
<p class="foot"><span class="l-en">$ = Artificial Analysis's cost per index task at API prices, not subscription quota.
CP = index points per US dollar; higher is better. * nothing from this provider reaches 50: its highest.</span><span class="l-zh">$ = Artificial Analysis 每個指數任務的成本（API 價格），不是訂閱額度。
CP = 每 1 美元換到的指數分數，越高越好。* 這家沒有任何選項達 50：列出它的最高分。</span></p>
@@skipped@@
<p class="links"><span class="l-en">Compare models: </span><span class="l-zh">比較模型：</span><a href="@@compare@@" target="_blank" rel="noopener">AI Model Compare</a></p>
</main><script>@@lang_script@@
@@expiry_script@@</script></body></html>
"""

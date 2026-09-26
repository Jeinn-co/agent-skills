#!/usr/bin/env python3
"""CursorBench rows for the model + effort each CLI is running now.

Usage: cursorbench.py [cli=model:effort ...]    e.g. claude=claude-opus-5-5:high

Fetches the public leaderboard at https://cursor.com/cursorbench (one GET, no
credentials) and parses its first <table>: rank, model ("Opus 5.5 High"), score,
cost / task, tokens / task, steps / task. Found 2026-09-24; the page is server-rendered.

Each CLI's model id is mapped to CursorBench's display name by rule (NAME below) and
its effort to CursorBench's suffix (EFFORT). A model the leaderboard does not list
prints `not listed` -- never a neighbouring row.

cp = score / cost per task: points per US dollar at Cursor's API prices. It is not a
subscription cost.

Then one `pick` line per CLI, searched across every model and effort CursorBench lists
for that provider (FAMILY): the highest cp that scores at least TARGET; when nothing
from that provider reaches TARGET, its highest score, the closest it gets. The line
says which rule applied (`rule cp` / `rule closest`). A CLI whose current model is not
listed gets no pick: an unlisted model cannot be compared with a listed one.

When the current model is not listed, its `bench` and `pick` lines come from Artificial
Analysis instead (one GET of https://artificialanalysis.ai/models/releases/<model id>,
no credentials), marked `(AA)`: the AA Intelligence Index score, AA's weighted cost per
index task, and the same pick rule applied to that model's own efforts only. AA is a
different test set, so an `(AA)` score or cp is never compared with a CursorBench one.
Only when AA has no page for the model either does a `ref` line follow: the newest
same-provider CursorBench row at the same effort. Orientation only -- never a pick.
"""
import html, re, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

URL = "https://cursor.com/cursorbench"
EFFORT = {"minimal": "Minimal", "low": "Low", "medium": "Medium", "high": "High",
          "xhigh": "Extra High", "max": "Max"}
TARGET = 50.0  # CursorBench score, percent, to reach whenever the provider can
# Leaderboard names each CLI can run.
FAMILY = {"claude": r"(Opus|Sonnet|Fable|Haiku) ", "codex": r"GPT-", "grok": r"Grok ",
          "muse": r"Muse "}


def score_cost(cells):
    """(score %, cost $) from a leaderboard row, or None when either will not parse."""
    try:
        return float(cells[0].rstrip("%")), float(cells[1].lstrip("$"))
    except (ValueError, IndexError):
        return None


def pick(board, cli, base):
    """(label, score, cost, rule) across the provider's listed models: best cp at or
    above TARGET, else the highest score. False when `base` (the CLI's current model) is
    not listed at any effort, or the provider has no listed row at all."""
    if not any("%s %s" % (base, suffix) in board for suffix in EFFORT.values()):
        return False
    rows = []
    for label, cells in board.items():
        parsed = score_cost(cells)
        if parsed and parsed[1] > 0 and re.match(FAMILY.get(cli, r"$^"), label):
            rows.append((parsed[0] / parsed[1], label) + parsed)
    if not rows:
        return False
    ok = [r for r in rows if r[2] >= TARGET]
    if ok:
        return max(ok)[1:] + ("cp",)
    return max(rows, key=lambda r: r[2])[1:] + ("closest",)


def _effort_of(label):
    """CursorBench effort suffix of a leaderboard label, or None. Longest match
    first so "Extra High" is never mistaken for "High"."""
    for e in sorted(EFFORT.values(), key=len, reverse=True):
        if label.endswith(" " + e):
            return e
    return None


def ref(board, cli, base, suffix):
    """(label, score, cost) of the newest same-provider listed row at `suffix`
    effort, preferring the current model's variant on ties; None when the board
    has no such row. Orientation for an unlisted model -- never a pick."""
    base_tokens = [t for t in base.split() if not re.fullmatch(r"[\d.]+", t)]
    best = None
    for rank, (label, cells) in enumerate(board.items()):
        if _effort_of(label) != suffix or not re.match(FAMILY.get(cli, r"$^"), label):
            continue
        ver = re.search(r"\d+(?:\.\d+)*", label)
        parsed = score_cost(cells)
        if not ver or not parsed or parsed[1] <= 0:
            continue
        key = (tuple(int(x) for x in ver.group(0).split(".")),
               sum(1 for t in base_tokens if t in label.split()),
               -rank)
        if best is None or key > best[0]:
            best = (key, label, parsed[0], parsed[1])
    return best[1:] if best else None


def name(cli, model):
    """CLI model id -> CursorBench model name, or None when there is no rule."""
    m = model.lower()
    if cli == "claude":
        # claude-opus-5-5 -> Opus 5.5, claude-fable-5-1 -> Fable 5.1; an alias has no version
        hit = re.fullmatch(r"claude-([a-z]+)-(\d+)(?:-(\d+))?(?:-\d{8})?", m)
        return hit and "%s %s" % (hit[1].title(), hit[2] + ("." + hit[3] if hit[3] else ""))
    if cli == "codex":
        # gpt-6-sol -> GPT-6 Sol
        hit = re.fullmatch(r"gpt-([\d.]+)(?:-([a-z]+))?", m)
        return hit and "GPT-%s%s" % (hit[1], " " + hit[2].title() if hit[2] else "")
    if cli == "grok":
        hit = re.fullmatch(r"grok-([\d.]+)", m)
        return hit and "Grok %s" % hit[1]
    if cli == "muse":
        # CursorBench lists no -contributor variant; the catalog gives both the same specs
        hit = re.fullmatch(r"muse-([a-z]+)-([\d.]+)(-contributor)?", m)
        return hit and "Muse %s %s" % (hit[1].title(), hit[2])
    return None


AA_URL = "https://artificialanalysis.ai/models/releases/%s"
# AA slugs: <model> is the top effort, <model>-<effort> the others.
AA_EFFORT = ("minimal", "low", "medium", "high", "xhigh", "max")


def aa_rows(model):
    """{effort: (score, cost, output tokens per task)} for one CLI model id from its Artificial
    Analysis release page, or {} when AA has no page or no scored row for it. The page
    is server-rendered; each model object carries slug, name ("GPT-6 Sol (high)"),
    intelligenceIndex, intelligenceIndexCostPerTask.cost.total and
    intelligenceIndexOutputTokensPerTask.output (reasoning + answer; 0 when absent)."""
    slug = re.sub(r"-contributor$", "", model.lower()).replace(".", "-")
    request = urllib.request.Request(AA_URL % slug,
                                     headers={"User-Agent": "Mozilla/5.0 (ai-usage)"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", errors="replace").replace('\\"', '"')
    except Exception:  # noqa: BLE001 -- no AA page means no AA row, nothing more
        return {}
    out = {}
    for m in re.finditer(r'"slug":"([a-z0-9-]+)","name":"([^"]+)"', page):
        tail = m.group(1)[len(slug):].lstrip("-")
        if not m.group(1).startswith(slug) or (tail and tail not in AA_EFFORT):
            continue
        effort = tail or next((e for e in reversed(AA_EFFORT)
                               if re.search(r"\b%s\b" % e, m.group(2), re.I)), None)
        seg = page[m.end():m.end() + 6000]
        score = re.search(r'"intelligenceIndex":([\d.]+)', seg)
        cost = re.search(r'"intelligenceIndexCostPerTask":\{"cost":\{"total":([\d.]+)', seg)
        tokens = re.search(r'"intelligenceIndexOutputTokensPerTask":\{[^}]*"output":([\d.]+)', seg)
        if effort and score and cost and float(cost.group(1)) > 0:
            out.setdefault(effort, (float(score.group(1)), float(cost.group(1)),
                                    float(tokens.group(1)) if tokens else 0.0))
    return out


def aa_pick(board):
    """(effort, score, cost, rule) over one model's AA efforts, same rule as pick()."""
    ok = [(s / c, e, s, c) for e, (s, c, _) in board.items() if s >= TARGET]
    if ok:
        return max(ok)[1:] + ("cp",)
    e, (s, c, _) = max(board.items(), key=lambda kv: kv[1][0])
    return e, s, c, "closest"


def rows():
    request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (ai-usage)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8", errors="replace")
    table = re.search(r"<table.*?</table>", page, re.S)
    if not table:
        raise ValueError("no leaderboard table on the page")
    out = {}
    for tr in re.findall(r"<tr.*?</tr>", table.group(0), re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<td.*?</td>", tr, re.S)]
        if len(cells) == 6:
            out[cells[1]] = cells[2:]
    if not out:
        raise ValueError("leaderboard table has no rows")
    return out


def main():
    wanted = []
    for arg in sys.argv[1:]:
        cli, _, rest = arg.partition("=")
        model, _, effort = rest.rpartition(":")
        wanted.append((cli, model, effort))
    try:
        board = rows()
    except Exception as exc:  # noqa: BLE001 -- the usage report must survive this
        print("bench failed (%s)" % exc)
        return 1
    picks = []
    sources = [URL]
    for cli, model, effort in wanted:
        base = name(cli, model) if model and model != "?" else None
        suffix = EFFORT.get(effort.lower()) if effort else None
        if base:
            picks.append((cli, base, pick(board, cli, base)))
        note = "  (mapped from %s)" % model if model.endswith("-contributor") else ""
        if not base or not suffix:
            print("bench   %s  %s  %s  not listed%s"
                  % (cli, base or model or "?", effort or "?", note if base else ""))
            continue
        label = "%s %s" % (base, suffix)
        hit = board.get(label)
        aa = {} if hit else aa_rows(model)
        if aa:
            sources.append(AA_URL % re.sub(r"-contributor$", "", model.lower()).replace(".", "-"))
            now = aa.get(effort.lower())
            if now:
                print("bench   %s  %s  aa %.0f  cost $%.2f  output tokens %s  cp %.1f  (AA)"
                      % (cli, label, now[0], now[1], "{:,.0f}".format(now[2]) if now[2] else "?",
                         now[0] / now[1]))
            else:
                print("bench   %s  %s  not listed  (AA)" % (cli, label))
            e, s, c, rule = aa_pick(aa)
            picks[-1] = (cli, base, ("%s %s" % (base, EFFORT[e]), s, c, rule, "aa"))
            continue
        if not hit:
            print("bench   %s  %s  not listed" % (cli, label))
            r = ref(board, cli, base, suffix)
            if r:
                rlabel, rscore, rcost = r
                print("ref     %s  %s  score %.1f%%  cost $%.2f  cp %.1f"
                      % (cli, rlabel, rscore, rcost, rscore / rcost))
            continue
        score, cost, tokens, steps = hit
        try:
            cp = float(score.rstrip("%")) / float(cost.lstrip("$"))
        except (ValueError, ZeroDivisionError):
            cp = None
        print("bench   %s  %s  score %s  cost %s  tokens %s  steps %s  cp %s%s"
              % (cli, label, score, cost, tokens, steps, "%.1f" % cp if cp else "?", note))
    for cli, base, hit in picks:
        if hit and len(hit) == 5:
            label, score, cost, rule, _ = hit
            print("pick    %s  %s  aa %.0f  cost $%.2f  cp %.1f  rule %s  (AA)"
                  % (cli, label, score, cost, score / cost, rule))
        elif hit:
            label, score, cost, rule = hit
            print("pick    %s  %s  score %.1f%%  cost $%.2f  cp %.1f  rule %s"
                  % (cli, label, score, cost, score / cost, rule))
        else:
            print("pick    %s  %s  not listed" % (cli, base))
    for source in sources:
        print("source  %s" % source)
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
    for cli, model, effort in wanted:
        base = name(cli, model) if model and model != "?" else None
        suffix = EFFORT.get(effort.lower()) if effort else None
        if base:
            picks.append((cli, base, pick(board, cli, base)))
        if not base or not suffix:
            print("bench   %s  %s  %s  not listed" % (cli, model or "?", effort or "?"))
            continue
        label = "%s %s" % (base, suffix)
        hit = board.get(label)
        if not hit:
            print("bench   %s  %s  not listed" % (cli, label))
            continue
        score, cost, tokens, steps = hit
        try:
            cp = float(score.rstrip("%")) / float(cost.lstrip("$"))
        except (ValueError, ZeroDivisionError):
            cp = None
        note = "  (mapped from %s)" % model if model.endswith("-contributor") else ""
        print("bench   %s  %s  score %s  cost %s  tokens %s  steps %s  cp %s%s"
              % (cli, label, score, cost, tokens, steps, "%.1f" % cp if cp else "?", note))
    for cli, base, hit in picks:
        if hit:
            label, score, cost, rule = hit
            print("pick    %s  %s  score %.1f%%  cost $%.2f  cp %.1f  rule %s"
                  % (cli, label, score, cost, score / cost, rule))
        else:
            print("pick    %s  %s  not listed" % (cli, base))
    print("source  %s" % URL)
    return 0


if __name__ == "__main__":
    sys.exit(main())

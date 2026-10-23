#!/usr/bin/env python3
"""CursorBench rows for the model + effort each CLI is running now.

Usage: cursorbench.py [cli=model:effort ...]    e.g. claude=claude-opus-5-5:high

Reads the rows AI Model Compare publishes (https://jeinn-co.github.io/ai-model-compare/,
data/cursorbench.json and data/aa.json; one GET each, no credentials). That site scrapes
cursor.com/cursorbench and Artificial Analysis every six hours, so the scraping lives in
one place: rank, model ("Opus 5.5 High"), score, cost / task, tokens / task, steps / task.

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
An empty model means no local session: print that status and still select the
provider's Qualified model, independently of whether its CLI is installed.

When the current model is not listed, its `bench` and `pick` lines come from Artificial
Analysis instead (data/aa.json), marked `(AA)`: the AA Intelligence Index and AA's four other model-page
figures (cost per index task, median output speed, index verbosity, time to first
answer token), with the same pick rule applied to that model's own efforts only. AA is a
different test set, so an `(AA)` score or cp is never compared with a CursorBench one.
Only when AA has no page for the model either does a `ref` line follow: the newest
same-provider CursorBench row at the same effort. Orientation only -- never a pick.

AA_EXTRA lists models a provider is gaining that CursorBench does not list yet (GPT-6.1
Sol for Codex). When the provider's own pick only reached
`rule closest`, an extra whose AA pick reaches TARGET takes the pick line instead,
marked `(AA)`.
"""
import functools, json, re, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

DATA = "https://jeinn-co.github.io/ai-model-compare/data/%s.json"
URL = DATA % "cursorbench"
AA_URL = DATA % "aa"
EFFORT = {"minimal": "Minimal", "low": "Low", "medium": "Medium", "high": "High",
          "xhigh": "Extra High", "max": "Max"}
TARGET = 50.0  # CursorBench score, percent, to reach whenever the provider can
# Leaderboard names each CLI can run.
FAMILY = {"claude": r"(Opus|Sonnet|Fable|Haiku) ", "codex": r"GPT-", "grok": r"Grok ",
          "muse": r"Muse ", "agy": r"Gemini "}


def score_cost(cells):
    """(score %, cost $) from a leaderboard row, or None when either will not parse."""
    try:
        return float(cells[0].rstrip("%")), float(cells[1].lstrip("$"))
    except (ValueError, IndexError):
        return None


def pick(board, cli, base=None):
    """(label, score, cost, rule) across the provider's listed models: best cp at or
    above TARGET, else the highest score. False when `base` (the CLI's current model) is
    not listed at any effort, or the provider has no listed row at all. With no
    `base`, select across the provider without requiring a current model."""
    if base and not any("%s %s" % (base, suffix) in board for suffix in EFFORT.values()):
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
    if cli == "agy":
        # gemini-3.8-flash -> Gemini 3.8 Flash. Antigravity also offers Claude models;
        # those map by the Claude rule (claude-opus-4.6 -> Opus 4.6).
        if m.startswith("claude-"):
            return name("claude", m.replace(".", "-"))
        hit = re.fullmatch(r"gemini-([\d.]+)-([a-z]+)", m)
        return hit and "Gemini %s %s" % (hit[1], hit[2].title())
    if cli == "muse":
        # CursorBench lists no -contributor variant; the catalog gives both the same specs
        hit = re.fullmatch(r"muse-([a-z]+)-([\d.]+)(-contributor)?", m)
        return hit and "Muse %s %s" % (hit[1].title(), hit[2])
    return None


SUFFIX = {label: key for key, label in EFFORT.items()}


@functools.lru_cache(maxsize=None)
def published(url):
    """Rows of one AI Model Compare data file, in the source's rank order."""
    request = urllib.request.Request(url, headers={"User-Agent": "ai-usage"})
    with urllib.request.urlopen(request, timeout=portable.CALL_TIMEOUT) as response:
        rows = json.loads(response.read().decode("utf-8", errors="replace")).get("rows")
    if not rows:
        raise ValueError("no rows in %s" % url)
    return rows


def aa_rows(model):
    """{effort: (score, cost, tokens, speed, verbosity, latency)} for one model name
    ("GPT-6.1 Sol") from the Artificial Analysis rows, or {} when AA has no scored,
    costed row for it. Missing speed / verbosity / latency stay 0 and print as `?`."""
    try:
        rows = published(AA_URL)
    except Exception:  # noqa: BLE001 -- no AA data means no AA row, nothing more
        return {}
    out = {}
    for r in rows:
        effort = SUFFIX.get(r.get("effort"))
        if r.get("model") == model and effort and r.get("score") is not None and (r.get("cost") or 0) > 0:
            out.setdefault(effort, (float(r["score"]), float(r["cost"]), 0.0, float(r.get("speed") or 0),
                                    float(r.get("verbosity") or 0), float(r.get("latency") or 0)))
    return out


# Models a provider's CLI line-up is expected to gain that CursorBench does not list yet,
# scored on Artificial Analysis instead. When none of the provider's CursorBench rows
# reaches TARGET, an extra whose own AA pick does reaches the Qualified cell, marked
# (AA). It mixes test sets on purpose; the (AA) mark and footnote say so. GPT-6.1 Sol
# added 2026-10-05 (AA 50 vs CursorBench GPT-5.6 Sol Max 41.7%); Gemini 4 Argon dropped
# 2026-10-23 once CursorBench listed it.
AA_EXTRA = {"codex": ["GPT-6.1 Sol"]}


def extra_pick(cli):
    """(label, score, cost, "cp", "aa") for the best AA extra of `cli` whose own
    pick reaches TARGET, or None."""
    best = None
    for display in AA_EXTRA.get(cli, []):
        board = aa_rows(display)
        if not board:
            continue
        e, s, c, rule = aa_pick(board)
        if rule == "cp" and (best is None or s / c > best[1] / best[2]):
            best = ("%s %s" % (display, EFFORT[e]), s, c, rule, "aa")
    return best


def aa_pick(board):
    """(effort, score, cost, rule) over one model's AA efforts, same rule as pick()."""
    ok, best = [], None
    for e, row in board.items():
        s, c = row[0], row[1]
        if best is None or s > best[1]:
            best = (e, s, c)
        if s >= TARGET:
            ok.append((s / c, e, s, c))
    if ok:
        return max(ok)[1:] + ("cp",)
    e, s, c = best
    return e, s, c, "closest"


def _aa_speed(v):
    return "?" if not v else "%.1f/s" % v


def _aa_verbosity(v):
    if not v:
        return "?"
    if v >= 1e6:
        return "%.0fM" % round(v / 1e6)
    if v >= 1e3:
        return "%.0fK" % round(v / 1e3)
    return "%.0f" % v


def _aa_latency(v):
    return "?" if not v else "%.1fs" % v


def rows():
    """{label: [score, cost, tokens, steps]} as the leaderboard prints them, in rank order."""
    out = {}
    for r in published(URL):
        out[r["label"]] = ["%.1f%%" % r["score"], "$%.2f" % r["cost"],
                           "{:,}".format(r["tokens"]) if r.get("tokens") is not None else "?",
                           str(r.get("steps", "?"))]
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
        if not model:
            print("bench   %s  no local session" % cli)
            picks.append((cli, "?", pick(board, cli)))
            continue
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
        aa = {} if hit else aa_rows(base)
        if aa:
            sources.append(AA_URL)
            now = aa.get(effort.lower())
            if now:
                score, cost = now[0], now[1]
                extra = tuple(now) + (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                print("bench   %s  %s  aa %.0f  cost $%.2f  speed %s  verbosity %s  latency %s  cp %.1f  (AA)"
                      % (cli, label, score, cost, _aa_speed(extra[3]),
                         _aa_verbosity(extra[4]), _aa_latency(extra[5]), score / cost))
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
    for i, (cli, base, hit) in enumerate(picks):
        if hit and hit[3] == "cp":
            continue
        try:
            extra = extra_pick(cli)
        except Exception:  # noqa: BLE001 -- an optional extra must never take the table down
            extra = None
        if extra:
            sources.append(AA_URL)
            picks[i] = (cli, base, extra)
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
    for source in dict.fromkeys(sources):
        print("source  %s" % source)
    return 0


if __name__ == "__main__":
    sys.exit(main())

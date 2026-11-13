#!/usr/bin/env python3
"""Artificial Analysis rows for the model + effort each CLI is running now, and the
model + effort each provider qualifies with.

Usage: cursorbench.py [cli=model:effort ...]    e.g. claude=claude-opus-5-5:high

Reads the Artificial Analysis rows AI Model Compare publishes
(https://jeinn-co.github.io/ai-model-compare/data/aa.json; one GET, no credentials). That
site reads Artificial Analysis every six hours, so the scraping lives in one place.
(The file keeps its old name: run.py, the report and the tests call it by it.)

Each CLI's model id is mapped to AA's model name by rule (NAME below) and its effort to
AA's effort label (EFFORT). A model AA does not list prints `not listed` -- never a
neighbouring row. Each `bench` line gives the AA Intelligence Index and AA's other
model-page figures (cost per index task, median output speed, index verbosity, time to
first answer token).

cp = score / cost per task: index points per US dollar at API prices. It is not a
subscription cost.

Then one `pick` line per CLI, searched across every model and effort AA lists for that
provider (FAMILY): the highest cp that scores at least TARGET; when nothing from that
provider reaches TARGET, its highest score, the closest it gets. The line says which
rule applied (`rule cp` / `rule closest`). Models in UNAVAILABLE are never picked.
Claude picks never use Fable (too expensive), whatever its score; Fable rows remain
visible as current-model benchmarks but are excluded from Qualified picks. An
empty model means no local session: print that status and still select the provider's
Qualified model, independently of whether its CLI is installed.
"""
import functools, json, re, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable
from guidance_data import GEMINI_MODELS

portable.stdout_utf8()

AA_URL = "https://jeinn-co.github.io/ai-model-compare/data/aa.json"
EFFORT = {"minimal": "Minimal", "low": "Low", "medium": "Medium", "high": "High",
          "xhigh": "Extra High", "max": "Max"}
SUFFIX = {label: key for key, label in EFFORT.items()}
TARGET = 50.0  # AA Intelligence Index points to reach whenever the provider can
# Model names each CLI can run.
FAMILY = {"claude": r"(Opus|Sonnet|Fable|Haiku) ", "codex": r"GPT-", "grok": r"Grok ",
          "muse": r"Muse ", "agy": r"Gemini "}
# Scored on AA but not publicly available, so never a pick.
# shortcut: kept by hand; add a model only when its vendor's own page says it is not open.
# Empty since Google opened Gemini 4 Carbon to paying API developers (2026-11-10).
UNAVAILABLE = set()
# Documented thinking levels, independent of whether AA has measured a variant.
GEMINI_EFFORTS = {model: values["efforts"] for model, values in GEMINI_MODELS.items()}


def pick(rows, cli):
    """(label, score, cost, rule) over the provider's AA rows: best cp at or above TARGET,
    else the highest score, subject to personal task routing.
    None when the provider has no eligible scored, costed row."""
    found = []
    for r in rows:
        model, effort = r.get("model") or "", SUFFIX.get(r.get("effort"))
        allowed = GEMINI_EFFORTS.get(model.lower().replace(" ", "-")) if cli == "agy" else None
        if allowed is not None and effort not in allowed:
            continue
        # No Fable for Claude picks: twice Opus's token rates, whatever the score.
        if cli == "claude" and model.startswith("Fable "):
            continue
        if (effort and model not in UNAVAILABLE and re.match(FAMILY.get(cli, r"$^"), model + " ")
                and r.get("score") is not None and (r.get("cost") or 0) > 0):
            score, cost = float(r["score"]), float(r["cost"])
            found.append((score / cost, "%s %s" % (model, EFFORT[effort]), score, cost))
    if not found:
        return None
    ok = [f for f in found if f[2] >= TARGET]
    if ok:
        return max(ok)[1:] + ("cp",)
    return max(found, key=lambda f: f[2])[1:] + ("closest",)


def name(cli, model):
    """CLI model id -> CursorBench model name, or None when there is no rule."""
    # Some sessions record a provider-routed id (claude/claude-opus-5-5, codex/gpt-6.1-sol).
    m = model.lower().rsplit("/", 1)[-1]
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
        allowed = GEMINI_EFFORTS.get((model or "").lower().replace(" ", "-"))
        if allowed is not None and effort not in allowed:
            continue
        if r.get("model") == model and effort and r.get("score") is not None and (r.get("cost") or 0) > 0:
            out.setdefault(effort, (float(r["score"]), float(r["cost"]), 0.0, float(r.get("speed") or 0),
                                    float(r.get("verbosity") or 0), float(r.get("latency") or 0)))
    return out


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


def main():
    wanted = []
    for arg in sys.argv[1:]:
        cli, _, rest = arg.partition("=")
        model, _, effort = rest.rpartition(":")
        wanted.append((cli, model, effort))
    try:
        rows = published(AA_URL)
    except Exception as exc:  # noqa: BLE001 -- the usage report must survive this
        print("bench failed (%s)" % exc)
        return 1
    for cli, model, effort in wanted:
        if not model:
            print("bench   %s  no local session" % cli)
        else:
            base = name(cli, model) if model != "?" else None
            key = effort.lower() if effort else ""
            now = aa_rows(base).get(key) if base and key in EFFORT else None
            if now:
                score, cost = now[0], now[1]
                print("bench   %s  %s %s  aa %.1f  cost $%.2f  speed %s  verbosity %s  latency %s  cp %.1f  (AA)"
                      % (cli, base, EFFORT[key], score, cost, _aa_speed(now[3]),
                         _aa_verbosity(now[4]), _aa_latency(now[5]), score / cost))
            else:
                note = "  (mapped from %s)" % model if base and model.endswith("-contributor") else ""
                print("bench   %s  %s  %s  not listed%s" % (cli, base or model or "?", effort or "?", note))
        hit = pick(rows, cli)
        if hit:
            label, score, cost, rule = hit
            print("pick    %s  %s  aa %.1f  cost $%.2f  cp %.1f  rule %s  (AA)"
                  % (cli, label, score, cost, score / cost, rule))
        else:
            print("pick    %s  not listed" % cli)
    print("source  %s" % AA_URL)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Model and effort of the newest local session of one CLI.

Usage: session_info.py claude|codex|grok

Reads the session files each CLI already writes under the user's home. No network,
no credentials, nothing launched. Field names found 2026-09-22 on Windows 11:

  claude  ~/.claude/projects/<proj>/<id>.jsonl
          assistant lines: message.model, effort, perTurnEffort
  codex   ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
          last {"type":"turn_context"}: payload.model, effort
  grok    ~/.grok/sessions/<cwd>/<id>/summary.json: current_model_id, reasoning_effort

Then one `option` line per model the CLI offers, from its own model cache
(~/.codex/models_cache.json, ~/.grok/models_cache.json) with the vendor's description
and effort levels. Claude has no local cache; its lines are the documented /model aliases.

Every value is what the CLI recorded for its last turn, not what the config defaults to.
A field the files do not carry prints `?` rather than a guess.
"""
import datetime, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

HOME = Path.home()


def newest(paths):
    best = None
    for p in paths:
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if best is None or m > best[0]:
            best = (m, p)
    return best


def jsonl(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    pass
    except OSError:
        return


def ago(mtime):
    s = int(datetime.datetime.now().timestamp() - mtime)
    if s < 3600:
        rel = "%dm" % max(s // 60, 0)
    elif s < 86400:
        rel = "%dh%dm" % (s // 3600, s % 3600 // 60)
    else:
        rel = "%dd%dh" % (s // 86400, s % 86400 // 3600)
    return "%s (%s ago)" % (datetime.datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M"), rel)


def report(mtime, model, effort):
    print("session %s" % ago(mtime))
    print("model   %s" % (model or "?"))
    print("effort  %s" % (effort or "?"))


def claude():
    root = HOME / ".claude" / "projects"
    # top-level transcripts only; <id>/subagents/*.jsonl belong to a parent session.
    # Newest first, skipping any without a model reply: claude_usage.py's own
    # `claude -p "/usage"` leaves a fresh transcript that holds no assistant turn.
    files = []
    for p in root.glob("*/*.jsonl"):
        try:
            files.append((p.stat().st_mtime, p))
        except OSError:
            pass
    for mtime, path in sorted(files, reverse=True)[:20]:
        model = effort = None
        for d in jsonl(path):
            if d.get("type") == "assistant":
                msg = d.get("message")
                if isinstance(msg, dict) and msg.get("model") and msg["model"] != "<synthetic>":
                    model = msg["model"]
                effort = d.get("perTurnEffort") or d.get("effort") or effort
        if model:
            return report(mtime, model, effort)
    print("no local session")


def codex():
    hit = newest((HOME / ".codex" / "sessions").rglob("rollout-*.jsonl"))
    if not hit:
        return print("no local session")
    ctx = {}
    for d in jsonl(hit[1]):
        if d.get("type") == "turn_context":
            ctx = d.get("payload") or {}
    report(hit[0], ctx.get("model"), ctx.get("effort"))


def grok():
    hit = newest((HOME / ".grok").glob("sessions/*/*/summary.json"))
    if not hit:
        return print("no local session")
    try:
        s = json.loads(hit[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    report(hit[0], s.get("current_model_id"), s.get("reasoning_effort"))


def option(model, efforts, default, desc):
    print("option  %s  [%s%s]  %s" % (model, "/".join(efforts) or "?",
                                    ", default %s" % default if default else "", desc or ""))
    return model


def claude_options():
    # Claude Code has no local model catalogue. These are the /model aliases its docs
    # list; the plan decides which of them the account may pick.
    return [option(alias, (), None, desc)
            for alias, desc in (("opus", "most capable, spends quota fastest"),
                                ("opusplan", "opus in plan mode, sonnet for execution"),
                                ("sonnet", "everyday coding, cheaper per turn than opus"),
                                ("haiku", "fastest and cheapest, simple tasks"),
                                ("fable", "Fable 5.1, for very long tasks"))]


def codex_options():
    try:
        d = json.loads((HOME / ".codex" / "models_cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [option(m.get("slug"), [x.get("effort") for x in m.get("supported_reasoning_levels") or []],
                   m.get("default_reasoning_level"), m.get("description"))
            for m in sorted(d.get("models") or [], key=lambda m: m.get("priority", 99))
            if m.get("visibility") == "list"]


def grok_options():
    try:
        d = json.loads((HOME / ".grok" / "models_cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ids = []
    for mid, v in (d.get("models") or {}).items():
        i = v.get("info") or {}
        if i.get("hidden"):
            continue
        effs = i.get("reasoning_efforts") or []
        ids.append(option(mid, [e.get("id") for e in effs],
                          next((e.get("id") for e in effs if e.get("default")), None),
                          i.get("description")))
    return ids


def value(cli, ids):
    """The shared model + effort pick from value.json, or `stale` when the model list moved.

    value.json is evaluated once and committed, so every user of the skill reads the same
    pick. It records the model ids it was judged against; any id added or dropped since
    means a new model shipped and the pick needs redoing.
    """
    try:
        v = json.loads((Path(__file__).resolve().parent / "value.json").read_text(encoding="utf-8"))
        e = v["providers"][cli]
    except (OSError, ValueError, KeyError):
        return print("value   stale  (no evaluation yet)")
    new = [m for m in ids if m not in e.get("models", [])]
    gone = [m for m in e.get("models", []) if m not in ids]
    if ids and (new or gone):
        return print("value   stale  new: %s  gone: %s  (evaluated %s)"
                     % (",".join(new) or "-", ",".join(gone) or "-", v.get("evaluated", "?")))
    print("value   %s + %s  %s  (evaluated %s)" % (e["pick"], e["effort"], e.get("why", ""),
                                                  v.get("evaluated", "?")))
    if v.get("positioning"):
        print("profile %s" % v["positioning"])


PROBES = {"claude": claude, "codex": codex, "grok": grok}
OPTIONS = {"claude": claude_options, "codex": codex_options, "grok": grok_options}

if len(sys.argv) != 2 or sys.argv[1] not in PROBES:
    print("usage: session_info.py claude|codex|grok")
    sys.exit(2)
try:
    PROBES[sys.argv[1]]()
    value(sys.argv[1], OPTIONS[sys.argv[1]]())
except Exception as e:  # a format change must not take the usage report down with it
    print("session read failed (%s)" % e)

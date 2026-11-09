#!/usr/bin/env python3
"""Model and effort of the newest local session of one CLI.

Usage: session_info.py claude|codex|grok|muse|agy

Reads the session files each CLI already writes under the user's home. No network,
no credentials, nothing launched. Field names found 2026-09-22 on Windows 11:

  claude  ~/.claude/projects/<proj>/<id>.jsonl
          assistant lines: message.model, effort, perTurnEffort
  codex   ~/.codex/state_*.sqlite (found 2026-10-29): newest row of `threads` by
          updated_at: model, reasoning_effort. Rollout files stop being touched after a
          thread's first turns (a thread updated 10-29 kept a 10-27 mtime), so the newest
          file can be an older thread. Fallback when the index is missing or unreadable:
          ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl,
          last {"type":"turn_context"}: payload.model, effort
  grok    ~/.grok/sessions/<cwd>/<id>/summary.json: current_model_id, reasoning_effort
  muse    ~/.local/share/muse/sessions/YYYY/MM/DD/<id>/session.jsonl (found 2026-09-24):
          last run.model.configured: payload.record.model_id; effort from the turn
          records that carry one (command intake, queued prompts). Muse's automated
          reviewer logs its own model/effort under event.model; that is not the user's.
          Sessions rooted in muse_usage.PROBE_DIR are the usage probe's and are skipped.
          TUI turns log no effort, and the /model and /effort pickers write
          ~/.config/muse/settings.json (`model`, `reasoning_effort`) instead, so a
          settings value newer than the last matching session record wins. When
          neither carries one, Muse ran at its documented default (`muse --help`:
          "default: high"), printed as `high (default)`.
  agy     ~/.gemini/antigravity/conversation_summaries.db or conversations/<id>.db
          (also under the older antigravity-cli root). Uses the newest database mtime
          and cli.log or log/cli-*.log for the last selected model label. Summary
          databases can coexist with logs in the other storage layout.
          Without a database, uses the newest log carrying a model selection and its
          mtime. Logs without a model selection, such as /usage probes, are skipped.
          A log fallback records CLI model selection, which may precede any model call.

Every value is what the CLI recorded for its last turn, not what the config defaults to.
A field the files do not carry prints `?` rather than a guess.
"""
import datetime, json, os, re, sqlite3, sys
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
    # /usage can create any number of newer transcripts without model replies.
    for mtime, path in sorted(files, reverse=True):
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
    db = newest((HOME / ".codex").glob("state_*.sqlite"))
    if db:
        try:
            con = sqlite3.connect("file:%s?mode=ro" % db[1].as_posix(), uri=True)
            try:
                row = con.execute("SELECT updated_at, model, reasoning_effort FROM threads"
                                  " WHERE model IS NOT NULL ORDER BY updated_at DESC LIMIT 1").fetchone()
            finally:
                con.close()
            if row:
                return report(row[0], row[1], row[2])
        except sqlite3.Error:
            pass
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


def find_key(obj, key):
    """First value stored under `key` anywhere in a JSON tree, or None."""
    if isinstance(obj, dict):
        if isinstance(obj.get(key), str):
            return obj[key]
        obj = list(obj.values())
    if isinstance(obj, list):
        for item in obj:
            hit = find_key(item, key)
            if hit is not None:
                return hit
    return None


def same_dir(a, b):
    # Muse may record a Windows root in extended-length form: \\?\C:\...
    a, b = (p[4:] if p.startswith("\\\\?\\") else p for p in (a, b))
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


MUSE_DEFAULT_EFFORT = "high"


def muse():
    from muse_usage import PROBE_DIR
    files = []
    for p in (HOME / ".local" / "share" / "muse" / "sessions").glob("*/*/*/*/session.jsonl"):
        try:
            files.append((p.stat().st_mtime, p))
        except OSError:
            pass
    settings_at, settings = 0.0, {}
    config = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "muse" / "settings.json"
    try:
        settings_at = config.stat().st_mtime
        settings = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    for mtime, path in sorted(files, reverse=True)[:20]:
        model = effort = root = None
        model_at = effort_at = 0.0  # seconds; records carry recorded_at in microseconds
        for d in jsonl(path):
            payload = d.get("payload") if isinstance(d.get("payload"), dict) else {}
            kind = d.get("payload_type")
            at = d.get("recorded_at") / 1e6 if isinstance(d.get("recorded_at"), int) else 0.0
            found = None
            if kind == "run.model.configured":
                found = (payload.get("record") or {}).get("model_id")
                if found:
                    model, model_at = found, at
            elif kind == "runtime.command_intake.received":
                cmd = ((payload.get("record") or {}).get("command") or {}).get("payload") or {}
                found = cmd.get("reasoning_effort")
            elif kind == "runtime.session":
                event = payload.get("event") or {}
                inner = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                found = inner.get("reasoning_effort")
            if found and kind != "run.model.configured":
                effort, effort_at = found, at
            if root is None:
                root = find_key(d, "workspace_root")
        if root and same_dir(root, PROBE_DIR):
            continue
        if model:
            if settings.get("model") and settings_at > model_at:
                model = settings["model"]
            if settings.get("reasoning_effort") and settings_at > effort_at:
                effort = settings["reasoning_effort"]
            # nothing recorded -> Muse ran at its own default (`muse --help`: "default: high")
            return report(mtime, model, effort or MUSE_DEFAULT_EFFORT + " (default)")
    print("no local session")


AGY_DIRS = [HOME / ".gemini" / folder for folder in ("antigravity", "antigravity-cli")]
AGY_LABEL = re.compile(r'selected model override to backend: label="([^"]+)"')


def agy_model_id(label):
    """'Gemini 3.8 Flash (High)' -> ('gemini-3.8-flash', 'high'). The effort is the
    parenthesised suffix; the rest is the model id the CLI lists in `agy models`."""
    m = re.fullmatch(r"(.+?)\s*\(([^)]+)\)", label.strip())
    name, effort = (m.group(1), m.group(2)) if m else (label.strip(), None)
    return re.sub(r"\s+", "-", name.strip().lower()), effort and effort.strip().lower()


def agy():
    databases = [folder / "conversation_summaries.db" for folder in AGY_DIRS]
    databases.extend(path for folder in AGY_DIRS for path in (folder / "conversations").glob("*.db"))
    hit = newest(databases)
    model = effort = None
    logs = []
    roots = (AGY_DIRS if not hit or hit[1].name == "conversation_summaries.db"
             else [hit[1].parent.parent])
    for folder in roots:
        for p in [folder / "cli.log", *(folder / "log").glob("cli-*.log")]:
            try:
                modified = p.stat().st_mtime
                started = (datetime.datetime.strptime(p.stem[4:], "%Y%m%d_%H%M%S").timestamp()
                           if p.name != "cli.log" else modified)
            except (OSError, ValueError):
                continue
            if not hit or started <= hit[0] + 1:
                logs.append((started if hit else modified, p))
    for _, path in sorted(logs, reverse=True):
        try:
            labels = AGY_LABEL.findall(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if labels:
            model, effort = agy_model_id(labels[-1])
            if not hit:
                hit = newest([path])
            break

    # Fallback to ~/.gemini/settings.json if model wasn't explicitly logged in cli.log
    if not model:
        settings_file = HOME / ".gemini" / "settings.json"
        if settings_file.is_file():
            try:
                cfg = json.loads(settings_file.read_text(encoding="utf-8", errors="replace"))
                raw_model = (cfg.get("model") or {}).get("name")
                if raw_model:
                    model = re.sub(r"^gemini/", "", raw_model).strip()
            except Exception:
                pass

    if hit:
        report(hit[0], model or "gemini-3.8-flash", effort or "high")
    elif model:
        report(datetime.datetime.now().timestamp(), model, effort or "high")
    else:
        print("no local session")


PROBES = {"claude": claude, "codex": codex, "grok": grok, "muse": muse, "agy": agy}

if len(sys.argv) != 2 or sys.argv[1] not in PROBES:
    print("usage: session_info.py claude|codex|grok|muse|agy")
    sys.exit(2)
try:
    PROBES[sys.argv[1]]()
except Exception as e:  # a format change must not take the usage report down with it
    print("session read failed (%s)" % e)

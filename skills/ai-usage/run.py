#!/usr/bin/env python3
"""/ai-usage entry point. Reads AI subscription usage. No browser, no stored credentials.

Each probe runs as a separate process with *this* interpreter (`sys.executable`), so
there is no dependency on a `python3` on PATH -- on Windows that name is often absent,
or worse, a Microsoft Store stub that opens the store instead of running anything.

Verified 2026-09-12 on macOS, 2026-09-14 on Windows 11. See README for platform notes.
"""
import json, os, re, shutil, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable

portable.stdout_utf8()

if "--version" in sys.argv:
    print("ai-usage %s" % portable.VERSION)
    sys.exit(0)

HERE = Path(__file__).resolve().parent

# claude -p --output-format json "/usage"          -- live, see claude_usage.py
# codex app-server  -> JSON-RPC account/rateLimits/read  -- live, see codex_usage.py
# grok agent stdio  -> ACP extension _x.ai/billing       -- live, see grok_usage.py
# muse serve        -> MSP usage/read after one tiny turn -- live, see muse_usage.py
# agy -p "/usage"   -> Antigravity CLI quota pools (Gemini) -- live, see agy_usage.py
# session_info.py <cli>  -> newest local session file     -- model/effort/permission
# cursorbench.py cli=model:effort ...  -> cursor.com/cursorbench rows for those models
PROBES = (("CLAUDE", "claude_usage.py", "claude"),
          ("CHATGPT", "codex_usage.py", "codex"),
          ("GROK", "grok_usage.py", "grok"),
          ("MUSE", "muse_usage.py", "muse"),
          ("GEMINI", "agy_usage.py", "agy"))

NAMES = {"claude": "Claude", "codex": "ChatGPT", "grok": "Grok", "muse": "Muse",
         "agy": "Gemini"}
IDS = [cli for _, _, cli in PROBES]
CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME")
                      or os.path.join(os.path.expanduser("~"), ".config"),
                      "ai-usage", "config.json")


OUTPUTS = ("html", "md")


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data):
    """Write the config; an empty one removes the file so defaults apply."""
    data = {key: value for key, value in data.items() if value is not None}
    if not data:
        if os.path.exists(CONFIG):
            os.remove(CONFIG)
        return
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def output_format():
    """`html` unless setup saved `md`."""
    value = load_config().get("output")
    return value if value in OUTPUTS else "html"


def selected():
    """Providers chosen with --set-providers; every provider when nothing valid is saved."""
    chosen = load_config().get("providers")
    picked = [cli for cli in IDS if isinstance(chosen, list) and cli in chosen]
    return picked or IDS


def installed():
    """Providers whose CLI is present (agy only at ~/.gemini/bin, never the IDE launcher)."""
    agy = os.path.join(os.path.expanduser("~"), ".gemini", "bin",
                       "agy.exe" if os.name == "nt" else "agy")
    found = {cli: shutil.which(cli) is not None for cli in ("claude", "codex", "grok", "muse")}
    found["agy"] = os.path.isfile(agy)
    return [cli for cli in IDS if found[cli]]


def set_providers(arg):
    """Save the providers to report; `all` removes the config."""
    config = load_config()
    if arg.strip().lower() == "all":
        config.pop("providers", None)
        save_config(config)
        return IDS
    names = [n.strip().lower() for n in arg.split(",") if n.strip()]
    unknown = [n for n in names if n not in IDS]
    if unknown or not names:
        sys.exit("unknown provider(s): %s; choose from %s or all"
                 % (", ".join(unknown) or "none given", ",".join(IDS)))
    picked = [cli for cli in IDS if cli in names]
    config["providers"] = picked
    save_config(config)
    return picked


SKILL_URL = "https://raw.githubusercontent.com/Jeinn-co/agent-skills/main/skills/ai-usage/SKILL.md"


def check_skill():
    """Compare this skill with the SKILL.md published on GitHub main."""
    def key(text):
        return tuple(int(part) for part in re.findall(r"\d+", text)[:3])
    try:
        request = urllib.request.Request(SKILL_URL, headers={"User-Agent": "ai-usage"})
        with urllib.request.urlopen(request, timeout=portable.CALL_TIMEOUT) as response:
            text = response.read().decode("utf-8", errors="replace")
        found = re.search(r'^\s*version:\s*"([^"]+)"', text, re.M)
        if not found:
            raise RuntimeError("no version in the published SKILL.md")
        latest = found.group(1)
    except Exception as exc:  # noqa: BLE001 -- the check must never block the report
        return "skill check failed (%s)" % exc
    status = "update available" if key(latest) > key(portable.VERSION) else "up to date"
    return ("skill installed=%s latest=%s status=%s update_cmd=npx -y skills update -g ai-usage"
            % (portable.VERSION, latest, status))


if "--check-skill" in sys.argv:
    print(check_skill())
    sys.exit(0)
if "--show-providers" in sys.argv:
    print("providers=" + ",".join(selected()))
    print("installed=" + ",".join(installed()))
    print("output=" + output_format())
    sys.exit(0)
if len(sys.argv) == 3 and sys.argv[1] == "--set-output":
    if sys.argv[2] not in OUTPUTS:
        sys.exit("unknown output: %s; choose html or md" % sys.argv[2])
    config = load_config()
    config["output"] = None if sys.argv[2] == "html" else sys.argv[2]
    save_config(config)
    print("output=" + output_format())
    sys.exit(0)
if len(sys.argv) == 3 and sys.argv[1] == "--set-providers":
    print("providers=" + ",".join(set_providers(sys.argv[2])))
    sys.exit(0)

SKIPPED = [cli for cli in IDS if cli not in selected()]
PROBES = tuple(probe for probe in PROBES if probe[2] not in SKIPPED)


def usage(script):
    try:
        result = portable.run_bounded(
            [sys.executable, "-u", str(HERE / script)],
            timeout=portable.CALL_TIMEOUT, stdout=subprocess.PIPE,
            **portable.text_kwargs())
        return result.stdout
    except subprocess.TimeoutExpired:
        return "usage call timed out after %gs; skipped\n" % portable.CALL_TIMEOUT


def session(cli):
    try:
        return portable.run_bounded(
            [sys.executable, str(HERE / "session_info.py"), cli],
            timeout=portable.CALL_TIMEOUT, stdout=subprocess.PIPE,
            **portable.text_kwargs()).stdout
    except subprocess.TimeoutExpired:
        return "session lookup timed out after %gs; skipped\n" % portable.CALL_TIMEOUT


def benchmark(now):
    try:
        # Buffer the table: a timed-out lookup must not leave half a set of picks.
        return portable.run_bounded(
            [sys.executable, str(HERE / "cursorbench.py"), *now],
            timeout=portable.CALL_TIMEOUT, stdout=subprocess.PIPE,
            **portable.text_kwargs()).stdout
    except subprocess.TimeoutExpired:
        return "bench failed (lookup timed out after %gs; skipped)\n" % portable.CALL_TIMEOUT

# Setup decides the output format; html unless `--set-output md` was saved.
HTML = output_format() == "html"
if HTML:
    # Keep a copy of everything printed so html_report can render the same data.
    import io
    _real_stdout = sys.stdout
    _captured = io.StringIO()

    class _Tee:
        def write(self, text):
            _captured.write(text)
            return _real_stdout.write(text)

        def flush(self):
            _real_stdout.flush()

    sys.stdout = _Tee()

try:
    print("### ai-usage %s" % portable.VERSION)
    if SKIPPED:
        print("### skipped " + ",".join(SKIPPED))
    print()
    sys.stdout.flush()
    with ThreadPoolExecutor(max_workers=2 * len(PROBES)) as pool:
        # Start every CLI and local session read before waiting for any result.
        calls = [pool.submit(usage, script) for _, script, _ in PROBES]
        sessions = [pool.submit(session, cli) for _, _, cli in PROBES]
        infos = [future.result() for future in sessions]
        now = []  # Every provider; an empty model means no local session.
        for (_, _, cli), info in zip(PROBES, infos):
            fields = dict(line.split(None, 1) for line in info.splitlines()
                          if line.startswith(("model ", "effort ")))
            if "model" in fields:
                now.append("%s=%s:%s" % (cli, fields["model"].strip(),
                                         (fields.get("effort") or "?").split()[0]))
            else:
                now.append("%s=:" % cli)
        # Benchmark needs model/effort, not usage: overlap its network calls too.
        bench = pool.submit(benchmark, now)
        for i, ((header, _, _), call, info) in enumerate(zip(PROBES, calls, infos)):
            if i:
                print()
            print("### %s" % header)
            print(call.result(), end="")
            print(info, end="")
            sys.stdout.flush()
        print()
        print("### CURSORBENCH")
        print(bench.result(), end="")
    if HTML:
        import tempfile, webbrowser
        import html_report
        out = Path(tempfile.gettempdir()) / "ai-usage" / "report.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_report.render(_captured.getvalue()), encoding="utf-8")
        opened = webbrowser.open(out.as_uri())
        print()
        print("### HTML %s%s" % (out, "" if opened else "  (could not open a browser)"))
except BrokenPipeError:
    # someone piped us into `head` and walked away. Point the fd at devnull so the
    # interpreter's shutdown flush does not print a second traceback on top.
    import os
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    sys.exit(0)

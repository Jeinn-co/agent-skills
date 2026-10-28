#!/usr/bin/env python3
"""/ai-usage entry point. Reads AI subscription usage. No browser, no stored credentials.

Each probe runs as a separate process with *this* interpreter (`sys.executable`), so
there is no dependency on a `python3` on PATH -- on Windows that name is often absent,
or worse, a Microsoft Store stub that opens the store instead of running anything.

Verified 2026-09-12 on macOS, 2026-09-14 on Windows 11. See README for platform notes.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
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
# Local report page with a Refresh button that re-runs the report (reload only re-reads
# the last one). Fixed port so /ai-usage can tell whether one is already running.
SERVE_PORT = 47821
SERVE_URL = "http://127.0.0.1:%d/" % SERVE_PORT
PAGE = Path(tempfile.gettempdir()) / "ai-usage" / "report.html"
# /ping answer: version and location, so a server left from an older or moved copy of
# this skill is not mistaken for this one (its Refresh would run that other run.py).
PING = ("ai-usage %s %s" % (portable.VERSION, HERE)).encode("utf-8")
# Set on the child run that the server starts: HTML page, no new browser tab.
SERVED = os.environ.get("AI_USAGE_SERVED") == "1"
# `/` is this shell: the last report in an iframe plus a Refresh button. Reload only
# re-reads the last report; the button re-runs it, then reloads just the iframe.
SHELL = """<!doctype html><html><head><meta charset="utf-8"><title>AI Usage</title>
<style>:root{color-scheme:light;--page:#f8fafc;--edge:#e2e8f0;--frame:#f1f5f9;--btn:#e2e8f0}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;
--page:#020617;--edge:#334155;--frame:#0f172a;--btn:#334155}}
:root[data-theme=dark]{color-scheme:dark;--page:#020617;--edge:#334155;--frame:#0f172a;
--btn:#334155}
html,body{margin:0;height:100%}body{box-sizing:border-box;padding:16px;display:flex;
flex-direction:column;gap:12px;background:var(--page)}
iframe{flex:1;min-height:0;width:100%;box-sizing:border-box;border:1px solid var(--edge);
border-radius:12px;background:var(--frame)}
#bar{display:flex;justify-content:space-between;gap:12px;align-items:center;
font:12px system-ui,sans-serif;color:CanvasText}
#bar h1{font-size:20px;font-weight:600;margin:0 0 2px}#meta{opacity:.7}
#updated:not(:empty)::after{content:" · "}#tools{display:flex;gap:8px}
button,select{padding:5px 12px;border:0;border-radius:12px;font:inherit;background:var(--btn);
color:inherit;cursor:pointer}</style>
</head><body><header id="bar"><div><h1>AI Usage</h1><div id="meta"><span id="updated"></span><span>ai-usage __VERSION__</span></div></div>
<div id="tools"><select id="theme" aria-label="Theme"><option value="auto">Auto</option>
<option value="light">Light</option><option value="dark">Dark</option></select>
<button id="refresh">Refresh</button></div></header><iframe id="report"></iframe><script>
const frame = document.getElementById("report"), button = document.getElementById("refresh");
const picker = document.getElementById("theme");
let theme = "auto";  // Auto follows the OS; the choice is kept per browser
try { theme = localStorage.getItem("aiu-theme") || "auto"; } catch (e) {}
picker.value = theme;
const applyTheme = doc => {
  if (theme === "auto") delete doc.documentElement.dataset.theme;
  else doc.documentElement.dataset.theme = theme;
};
// Puts the theme on the page before it renders, so it never flashes in the other one.
const show = html => {
  frame.srcdoc = theme === "auto" ? html :
    html.replace(/<html\\b/i, '<html data-theme="' + theme + '"');
};
applyTheme(document);
picker.onchange = () => {
  theme = picker.value;
  try { localStorage.setItem("aiu-theme", theme); } catch (e) {}
  applyTheme(document);
  if (frame.contentDocument) applyTheme(frame.contentDocument);
};
const stamp = ms => {  // when the shown report was produced, in local time
  const d = new Date(ms), p = n => String(n).padStart(2, "0");
  document.getElementById("updated").textContent = ms ? "Updated " + p(d.getMonth() + 1) + "-" +
    p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds()) : "";
};
stamp(__UPDATED__);
frame.onload = () => {
  const main = frame.contentDocument.querySelector("main");
  if (main) {
    main.querySelector("h1")?.remove();
    main.querySelector(".sub")?.remove();
    frame.contentDocument.body.style.paddingTop = "20px";
  }
};
// Replaces the report while fetching or after a failure, so old numbers never look current.
const notice = text => '<html><meta charset="utf-8"><style>__NOTICE_CSS__</style>' + text;
fetch("/last?" + Date.now())
  .then(r => r.ok ? r.text() : Promise.reject(r.status + " " + r.statusText))
  .then(show)
  .catch(e => show(notice("Could not load the report (" + e + ").")));
button.onclick = () => {
  button.disabled = true;
  button.textContent = "Refreshing\\u2026";
  stamp(0);
  show(notice("Fetching data\\u2026"));
  fetch("/report", {method: "POST", headers: {"X-AI-Usage": "1"}})
    .then(r => r.ok ? r.text() : Promise.reject(r.status + " " + r.statusText))
    .then(written => fetch("/last?" + Date.now()).then(r => r.ok ? r.text() :
      Promise.reject(r.status + " " + r.statusText)).then(html => {
      show(html);
      stamp(Number(written));
      button.textContent = "Refresh";
    }))
    .catch(e => {
      show(notice("Fetch failed (" + e + "). Press Retry."));
      button.textContent = "Retry";
    })
    .finally(() => { button.disabled = false; });
};
</script></body></html>"""
# Placeholder pages in the iframe (fetching, failed, no report yet). `data-theme` on
# <html> forces light or dark; without it the OS setting decides.
NOTICE_CSS = (":root{--b:#f1f5f9;--t:#0f172a}"
              "@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--b:#0f172a;--t:#f1f5f9}}"
              ":root[data-theme=dark]{--b:#0f172a;--t:#f1f5f9}"
              "body{margin:0;height:100vh;display:grid;place-items:center;"
              "font:15px system-ui,sans-serif;background:var(--b);color:var(--t)}")
EMPTY_PAGE = ('<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>'
              "<body>No report yet. Press Refresh.</body></html>" % NOTICE_CSS)


def ping():
    """What answers /ping on SERVE_PORT: PING for this copy, other bytes, or None."""
    try:  # no proxy: a corporate HTTP_PROXY must not intercept 127.0.0.1
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(SERVE_URL + "ping", timeout=0.5) as reply:
            return reply.read()
    except OSError:
        return None


def start_server():
    """Start `--serve` detached so it outlives this run; True once it answers."""
    args = [sys.executable, str(HERE / "run.py"), "--serve", "--no-open"]
    quiet = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, close_fds=True)
    try:
        if os.name == "nt":
            # CREATE_NO_WINDOW (not DETACHED_PROCESS): the server keeps a hidden console
            # its CLI children share; with no console each child opens its own window.
            # CREATE_BREAKAWAY_FROM_JOB so a host that runs commands in a job object does
            # not kill it when the command ends.
            try:
                subprocess.Popen(args, creationflags=0x08000000 | 0x01000000, **quiet)
            except OSError:
                # The job forbids breakaway. The server then stays in it and may stop
                # when the host's command ends; the next run just starts it again.
                subprocess.Popen(args, creationflags=0x08000000, **quiet)
        else:
            subprocess.Popen(args, start_new_session=True, **quiet)
    except OSError:
        return False
    for _ in range(30):
        if ping() == PING:
            return True
        time.sleep(0.1)
    return False


def write_page(html):
    """Swap in a complete report so a reader never sees half a page."""
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PAGE.with_name("report.%d.tmp" % os.getpid())
    try:
        tmp.write_text(html, encoding="utf-8")
        for attempt in range(10):
            try:
                os.replace(tmp, PAGE)
                return
            except PermissionError:  # Windows: the server is reading the page right now
                if attempt == 9:
                    raise
                time.sleep(0.1)
    finally:
        tmp.unlink(missing_ok=True)


if "--serve" in sys.argv:
    import threading, webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    # Threaded so /ping and /last answer during a ~10 s refresh; this lock still keeps
    # refreshes to one at a time.
    refresh_lock = threading.Lock()

    def written_ms():
        """When the report on disk was written (ms since epoch), "0" if there is none."""
        try:
            return str(int(PAGE.stat().st_mtime * 1000))
        except OSError:
            return "0"

    class Handler(BaseHTTPRequestHandler):
        def local(self):
            # DNS-rebinding guard: only answer pages that address us as localhost.
            if self.headers.get("Host") in ("127.0.0.1:%d" % SERVE_PORT,
                                            "localhost:%d" % SERVE_PORT):
                return True
            self.send_error(403)
            return False

        def do_GET(self):
            path = self.path.partition("?")[0]
            if not self.local():
                return
            if path == "/ping":
                self.reply(PING, "text/plain; charset=utf-8")
            elif path == "/":
                self.reply(SHELL.replace("__UPDATED__", written_ms())
                           .replace("__VERSION__", portable.VERSION)
                           .replace("__NOTICE_CSS__", NOTICE_CSS).encode("utf-8"),
                           "text/html; charset=utf-8")
            elif path == "/last":
                try:
                    body = PAGE.read_bytes()
                except OSError:
                    body = EMPTY_PAGE.encode("utf-8")
                self.reply(body, "text/html; charset=utf-8")
            else:
                self.send_error(404)

        def do_POST(self):
            # The custom header makes a cross-site request need a CORS preflight, which
            # this server never grants, so other pages cannot start runs.
            if not self.local():
                return
            if self.path != "/report" or self.headers.get("X-AI-Usage") != "1":
                self.send_error(404)
                return
            with refresh_lock:
                try:
                    code = portable.run_bounded(
                        [sys.executable, str(HERE / "run.py")],
                        timeout=4 * portable.CALL_TIMEOUT, stdout=subprocess.DEVNULL,
                        env=dict(os.environ, AI_USAGE_SERVED="1")).returncode
                except (subprocess.TimeoutExpired, OSError) as exc:
                    code = exc
            if code != 0:  # the old report and its time stay on the page
                self.send_error(500, "report failed: %s" % code)
                return
            self.reply(written_ms().encode("ascii"), "text/plain")

        def end_headers(self):
            # No framing by other sites, so none can trick a click on Refresh.
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            super().end_headers()

        def reply(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = None
    holder = ping()
    if holder == PING:
        print("already serving %s" % SERVE_URL)
    elif holder:
        sys.exit("port %d is held by another ai-usage server (%s); stop that process first"
                 % (SERVE_PORT, holder.decode("utf-8", "replace")))
    else:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", SERVE_PORT), Handler)
        except OSError as exc:
            sys.exit("port %d is busy (%s)" % (SERVE_PORT, exc))
        print("serving %s  (Refresh re-runs the report, Ctrl+C stops)" % SERVE_URL, flush=True)
    if "--no-open" not in sys.argv:
        webbrowser.open(SERVE_URL)
    if server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
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
HTML = output_format() == "html" or SERVED
# Keep a copy of everything printed so html_report can build the advice and the page.
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
    import html_report
    print()
    print("### ADVICE")
    for line in html_report.advice(_captured.getvalue()):
        print(line)
    if HTML:
        import webbrowser
        write_page(html_report.render(_captured.getvalue()))
        # Prefer the local server, whose page has a Refresh button; fall back to the file.
        note = ""
        if SERVED:
            shown, opened = PAGE, True
        else:
            holder = ping()
            if holder == PING or (holder is None and start_server()):
                shown, opened = SERVE_URL, webbrowser.open(SERVE_URL)
            else:
                shown, opened = PAGE, webbrowser.open(PAGE.as_uri())
                note = ("  (Refresh unavailable: port %d is held by another ai-usage server; "
                        "stop it)" % SERVE_PORT if holder else
                        "  (Refresh unavailable: could not start a server on port %d)" % SERVE_PORT)
        print()
        print("### HTML %s%s%s" % (shown, note, "" if opened else "  (could not open a browser)"))
except BrokenPipeError:
    # someone piped us into `head` and walked away. Point the fd at devnull so the
    # interpreter's shutdown flush does not print a second traceback on top.
    import os
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    sys.exit(0)

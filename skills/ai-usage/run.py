#!/usr/bin/env python3
"""/ai-usage entry point. Reads AI subscription usage without browser automation.

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

# Claude OAuth GET /api/oauth/usage               -- live, see claude_usage.py
# codex app-server  -> JSON-RPC account/rateLimits/read  -- live, see codex_usage.py
# grok agent stdio  -> ACP extension _x.ai/billing       -- live, see grok_usage.py
# muse serve        -> MSP usage/read after one tiny turn -- live, see muse_usage.py
# agy -p "/usage"   -> Antigravity CLI quota pools (Gemini) -- live, see agy_usage.py
# session_info.py <cli>  -> newest local session file     -- model/effort/permission
# cursorbench.py cli=model:effort ...  -> Artificial Analysis rows and picks for those models
PROBES = (("CLAUDE", "claude_usage.py", "claude"),
          ("CHATGPT", "codex_usage.py", "codex"),
          ("GROK", "grok_usage.py", "grok"),
          ("MUSE", "muse_usage.py", "muse"),
          ("GEMINI", "agy_usage.py", "agy"))

NAMES = {"claude": "Claude", "codex": "ChatGPT", "grok": "Grok", "muse": "Muse",
         "agy": "Gemini"}
IDS = [cli for _, _, cli in PROBES]
CONFIG = portable.config_path()


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


def selected():
    """Providers chosen with --set-providers; every provider when nothing valid is saved."""
    chosen = load_config().get("providers")
    picked = [cli for cli in IDS if isinstance(chosen, list) and cli in chosen]
    return picked or IDS


AGY_POOLS = ("gemini", "cl+gpt")


def agy_pools():
    """Gemini quota pools to show: both unless setup saved `gemini` only."""
    return ["gemini"] if load_config().get("agy_pools") == ["gemini"] else list(AGY_POOLS)


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
    print("agy_pools=" + ",".join(agy_pools()))
    sys.exit(0)
if len(sys.argv) == 3 and sys.argv[1] == "--set-agy-pools":
    if sys.argv[2] not in ("gemini", "all"):
        sys.exit("unknown agy pools: %s; choose gemini or all" % sys.argv[2])
    config = load_config()
    config["agy_pools"] = ["gemini"] if sys.argv[2] == "gemini" else None
    save_config(config)
    print("agy_pools=" + ",".join(agy_pools()))
    sys.exit(0)
if len(sys.argv) == 3 and sys.argv[1] == "--set-providers":
    print("providers=" + ",".join(set_providers(sys.argv[2])))
    sys.exit(0)
# Local report page with a Refresh button that re-runs the report (reload only re-reads
# the last one). Fixed port so /ai-usage can tell whether one is already running.
SERVE_PORT = 47821
SERVE_URL = "http://127.0.0.1:%d/" % SERVE_PORT
PAGE = Path(tempfile.gettempdir()) / "ai-usage" / "report.html"
RAW = PAGE.with_name("report.txt")  # the text behind PAGE, so the page can update one card
# Per-lookup budget for the page. Each card fetches on its own, so a slow CLI only keeps
# its own skeleton up and can be given longer than the chat report's 20 s.
PAGE_TIMEOUT = 90
# /ping answer: version and location, so a server left from an older or moved copy of
# this skill is not mistaken for this one (its Refresh would run that other run.py).
PING = ("ai-usage %s %s" % (portable.VERSION, HERE)).encode("utf-8")
# `/` is the last report itself, with Theme and Refresh added to its own header next to the
# language switch (no iframe). Reload only re-reads the last report; Refresh swaps in
# skeleton cards under the header and fetches each provider with its own request, so
# every card fills in as soon as its CLI answers.
GLOBE_ICON = '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.25"/><path d="M1.75 8h12.5M8 1.75c1.8 1.9 2.6 3.9 2.6 6.25S9.8 12.35 8 14.25C6.2 12.35 5.4 10.35 5.4 8S6.2 3.65 8 1.75"/></svg>'
SERVE_TOOLS = ('<div class="tools"><button type="button" class="lang" id="lang"><svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.25"/><path d="M1.75 8h12.5M8 1.75c1.8 1.9 2.6 3.9 2.6 6.25S9.8 12.35 8 14.25C6.2 12.35 5.4 10.35 5.4 8S6.2 3.65 8 1.75"/></svg><span>中文</span></button>'
               '<label class="sel"><svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.25"/><path d="M8 1.75a6.25 6.25 0 0 1 0 12.5z" fill="currentColor"/></svg><select id="theme" aria-label="Theme"><option value="auto">Auto</option>'
               '<option value="light">Light</option><option value="dark">Dark</option></select>'
               '<svg class="chev" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.75l3 3 3-3"/></svg></label>'
               '<button type="button" class="lang" id="refresh"><svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M13.25 8A5.25 5.25 0 1 1 11.7 4.3"/><path d="M12.25 1.75v3h-3"/></svg><span>Refresh</span></button></div>')
SERVE_CSS = """.top{flex-wrap:wrap;align-items:center;position:sticky;top:0;z-index:10;background:var(--card);margin:-40px calc(50% - 50vw) 16px;padding:14px calc(50vw - 50%);border-bottom:1px solid var(--line)}body{overflow-x:clip}.tools{display:flex;flex-wrap:wrap;gap:8px}
.sel{position:relative;display:inline-flex;font-size:14px;border:1px solid var(--accent);border-radius:4px;color:var(--accent)}
.sel select{appearance:none;-webkit-appearance:none;font:inherit;color:inherit;background:transparent;border:0;
min-height:30px;padding:0 28px 0 34px;border-radius:4px;cursor:pointer}.sel select:focus{outline:0}
:root:not(.mouse) .sel:has(select:focus-visible){outline:2px solid var(--accent);outline-offset:3px}
.sel option{background:var(--card);color:var(--text)}
.sel .chev{position:absolute;right:11px;top:50%;width:10px;height:10px;margin-top:-5px;pointer-events:none;
fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
#refresh:disabled{opacity:.6;cursor:progress}
.tools .lang{display:inline-flex;align-items:center;gap:6px}
.ico{width:14px;height:14px;flex:none;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.sel>.ico{position:absolute;left:14px;top:50%;margin-top:-7px;pointer-events:none}"""
SHELL = """const SKELETON = __SKELETON__;
const root = document.documentElement;
const button = document.getElementById("refresh"), picker = document.getElementById("theme");
const WORDS = {refresh: ["Refresh", "重新整理"], busy: ["Refreshing\\u2026", "更新中\\u2026"],
  retry: ["Retry", "重試"], auto: ["Auto", "自動"], light: ["Light", "淺色"], dark: ["Dark", "深色"]};
let state = "refresh";
const word = key => WORDS[key][root.dataset.lang === "zh" ? 1 : 0];
const GLOBE = __GLOBE__;
// The report's own switch rewrites the language button as plain text, so its icon is put back here.
const relabel = () => {
  const lang = document.getElementById("lang");
  lang.innerHTML = GLOBE + "<span>" + (root.dataset.lang === "zh" ? "EN" : "中文") + "</span>";
  button.querySelector("span").textContent = word(state);
  for (const option of picker.options) option.textContent = word(option.value);
};
// The report's own script switches the language first; this then renames the tools.
document.getElementById("lang").addEventListener("click", relabel);
const THEMES = ["auto", "light", "dark"];
let theme = "auto";  // Auto follows the OS; the choice is kept per browser
try { theme = localStorage.getItem("aiu-theme") || "auto"; } catch (e) {}
if (!THEMES.includes(theme)) theme = "auto";
picker.value = theme;
const applyTheme = () => {
  if (theme === "auto") delete root.dataset.theme;
  else root.dataset.theme = theme;
};
applyTheme();
relabel();
picker.onchange = () => {
  theme = THEMES.includes(picker.value) ? picker.value : "auto";
  try { localStorage.setItem("aiu-theme", theme); } catch (e) {}
  applyTheme();
};
// Chrome treats a mouse-focused <select> as :focus-visible, so the ring is keyed to the last input.
addEventListener("pointerdown", () => root.classList.add("mouse"), true);
addEventListener("keydown", () => root.classList.remove("mouse"), true);
const ok = r => r.ok ? r : Promise.reject(r.status + " " + r.statusText);
const get = path => fetch(path + "?" + Date.now()).then(ok).then(r => r.text());
const post = (path, body) => fetch(path, {method: "POST", body: JSON.stringify(body || {}),
  headers: {"X-AI-Usage": "1", "Content-Type": "application/json"}}).then(ok).then(r => r.json());
function bindProviderLogin(doc) {
  doc.querySelectorAll('[data-provider-login]').forEach(signIn => {
    const provider = signIn.dataset.providerLogin, name = signIn.dataset.providerName;
    const command = provider === 'CLAUDE' ? 'claude auth login' : 'codex login';
    signIn.hidden = false;
    signIn.onclick = async () => {
      const status = doc.getElementById(provider.toLowerCase() + '-login-status');
      signIn.disabled = true;
      signIn.textContent = 'Signing in…';
      status.hidden = false;
      status.textContent = 'Complete ' + name + ' authorization in the browser that opens. This may take up to 5 minutes.';
      try {
        const result = await post('/login', {id: provider});
        status.textContent = result.message;
        if (result.ok) button.click();
      } catch (error) {
        status.textContent = 'Could not start sign-in. Try again, or run ' + command + ' in a terminal.';
      } finally {
        signIn.disabled = false;
        signIn.textContent = 'Sign in to ' + name;
      }
    };
  });
}
// Everything in <main> under the header.
const below = () => [...document.querySelector("main").children].filter(el => !el.matches(".top"));
// Puts a freshly fetched page's content under this header, keeping the header itself.
const swap = html => {
  const fresh = new DOMParser().parseFromString(html, "text/html").querySelector("main");
  fresh.querySelector(".top")?.remove();
  below().forEach(el => el.remove());
  document.querySelector("main").append(...fresh.children);
};
// Replaces the report after a failure, so old numbers never look current.
const notice = text => {
  below().forEach(el => el.remove());
  const note = document.createElement("p");
  note.className = "note";
  note.textContent = text;
  document.querySelector("main").append(note);
};
// One request per provider (and one for the benchmark), none waiting for another. A
// failed card says so in place; once all have answered the merged report is saved.
const update = (ids, bench) => {
  const sections = [];
  const jobs = ids.map(id => post("/card", {id}).then(r => {
    sections.push(r.raw);
    document.querySelector('.card[data-id="' + id + '"]').outerHTML = r.html;
    window.updateResetExpiry?.();
    bindProviderLogin(document);
  }, e => {
    sections.push("### " + id + "\\nusage call failed (" + e + ")\\n");
    const note = document.createElement("div");
    note.className = "note";
    note.textContent = "Fetch failed (" + e + "). Press Refresh.";
    document.querySelector('.card[data-id="' + id + '"] .skel-body')?.replaceWith(note);
  }));
  if (bench) jobs.push(post("/bench").then(r => {
    sections.push(r.raw);
    document.getElementById("bench").innerHTML = r.html;
  }, e => {
    sections.push("### CURSORBENCH\\nbench failed (" + e + ")\\n");
    document.getElementById("bench").innerHTML = "";
  }));
  return Promise.all(jobs).then(() => post("/finish", {sections}));
};
const busy = work => {
  button.disabled = true;
  state = "busy";
  relabel();
  return work()
    .then(() => { state = "refresh"; })
    .catch(e => {
      notice("Fetch failed (" + e + "). Press Retry.");
      state = "retry";
    })
    .finally(() => { button.disabled = false; relabel(); });
};
bindProviderLogin(document);
button.onclick = () => busy(() => get("/skeleton").then(html => {
  swap(html);
  return update([...document.querySelectorAll(".card[data-id]")].map(card => card.dataset.id), true);
}));
if (root.dataset.empty) {
  button.click();  // no report on disk yet
} else {
  // A card whose lookup ran out of the chat report's 20 s is fetched again here,
  // with the page's longer budget.
  const late = [...document.querySelectorAll(".card[data-timeout]")];
  if (late.length) {
    late.forEach(card => {
      card.querySelectorAll(".row, .note").forEach(el => el.remove());
      card.querySelector(".now").insertAdjacentHTML("beforebegin", SKELETON);
    });
    busy(() => update(late.map(card => card.dataset.id), false));
  }
}"""


def serve_page(page, empty=False):
    """The report page with the served tools in its header and the refresh script."""
    import html_report
    page = page.replace('<button type="button" class="lang" id="lang">中文</button>', SERVE_TOOLS, 1)
    page = page.replace("</head>", "<style>%s</style></head>" % SERVE_CSS, 1)
    script = SHELL.replace("__GLOBE__", json.dumps(GLOBE_ICON)).replace("__SKELETON__", json.dumps(html_report.SKELETON))
    page = page.replace("</body>", "<script>%s</script></body>" % script, 1)
    return page.replace("<html", '<html data-empty="1"', 1) if empty else page


def ping():
    """What answers /ping on SERVE_PORT: PING for this copy, other bytes, or None."""
    try:  # no proxy: a corporate HTTP_PROXY must not intercept 127.0.0.1
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(SERVE_URL + "ping", timeout=0.5) as reply:
            return reply.read()
    except OSError:
        return None


def port_pid():
    """PID listening on SERVE_PORT, or None when it cannot be found."""
    try:
        if os.name == "nt":  # match the foreign address, not the state: netstat localises it
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                                 text=True, timeout=5).stdout
            for row in out.splitlines():
                cols = row.split()
                if len(cols) == 5 and cols[1] == "127.0.0.1:%d" % SERVE_PORT \
                        and cols[2] == "0.0.0.0:0":
                    return int(cols[4])
        else:
            out = subprocess.run(["lsof", "-t", "-sTCP:LISTEN", "-iTCP:%d" % SERVE_PORT],
                                 capture_output=True, text=True, timeout=5).stdout.split()
            return int(out[0]) if out else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def take_over(holder):
    """Stop a server left running by an older version of this same copy, so updating the
    skill does not leave Refresh broken. Returns what holds the port afterwards."""
    if holder in (None, PING) or holder.split(b" ", 2)[2:] != [str(HERE).encode("utf-8")]:
        return holder  # free, ours, or another copy's server: leave it alone
    pid = port_pid()
    if pid:
        try:
            os.kill(pid, 15)  # SIGTERM; TerminateProcess on Windows
        except OSError:
            return holder
        for _ in range(30):
            if ping() is None:
                return None
            time.sleep(0.1)
    return ping()


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


def write_page(html, raw):
    """Swap in a complete report so a reader never sees half a page; RAW keeps its text."""
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    for target, text in ((RAW, raw), (PAGE, html)):
        tmp = target.with_name("%s.%d.tmp" % (target.stem, os.getpid()))
        try:
            tmp.write_text(text, encoding="utf-8")
            for attempt in range(10):
                try:
                    os.replace(tmp, target)
                    break
                except PermissionError:  # Windows: the server is reading the page right now
                    if attempt == 9:
                        raise
                    time.sleep(0.1)
        finally:
            tmp.unlink(missing_ok=True)


def active():
    """PROBES chosen in setup; read each time, since the server outlives a setup change."""
    chosen = selected()
    return tuple(probe for probe in PROBES if probe[2] in chosen)


def head():
    """A report's first lines: version, the providers setup leaves out, a blank line."""
    skipped = [cli for cli in IDS if cli not in selected()]
    return "### ai-usage %s\n%s\n" % (
        portable.VERSION, "### skipped %s\n" % ",".join(skipped) if skipped else "")


def child_env(timeout):
    """Environment that gives a probe's own CLI calls the same budget as the probe."""
    return dict(os.environ, AI_USAGE_TIMEOUT="%g" % timeout, AI_USAGE_METADATA="1")


def usage(script, timeout=portable.CALL_TIMEOUT):
    try:
        result = portable.run_bounded(
            [sys.executable, "-u", str(HERE / script)],
            timeout=timeout, stdout=subprocess.PIPE, env=child_env(timeout),
            **portable.text_kwargs())
        out = result.stdout
    except subprocess.TimeoutExpired as error:
        # Optional details must not erase complete, validated usage already received.
        import html_report
        output = error.output or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        complete = [line for line in output.splitlines(keepends=True) if line.endswith("\n")]
        windows = []
        for line in complete:
            match = html_report.WINDOW.match(line.strip())
            if match:
                try:
                    used = 0.5 if match.group(2) == "<1" else float(match.group(2))
                    if 0 <= used <= 100:
                        windows.append(line)
                except ValueError:
                    pass
        if windows:
            plan = next((line for line in complete if line.startswith("plan:")), "")
            detail = ("Limit resets: unavailable (timed out)" if script == "claude_usage.py" else
                      "Additional details unavailable (lookup timed out)")
            return plan + "".join(windows) + detail + "\n"
        return "usage call timed out after %gs; skipped\n" % timeout
    if script == "agy_usage.py" and agy_pools() == ["gemini"]:
        # Setup hid the Claude/GPT pool: drop its row before cards and advice see it.
        out = "".join(line for line in out.splitlines(True) if not line.startswith("cl+gpt "))
    return out


def session(cli):
    try:
        return portable.run_bounded(
            [sys.executable, str(HERE / "session_info.py"), cli],
            timeout=portable.CALL_TIMEOUT, stdout=subprocess.PIPE,
            **portable.text_kwargs()).stdout
    except subprocess.TimeoutExpired:
        return "session lookup timed out after %gs; skipped\n" % portable.CALL_TIMEOUT


def benchmark(now, timeout=portable.CALL_TIMEOUT):
    try:
        # Buffer the table: a timed-out lookup must not leave half a set of picks.
        return portable.run_bounded(
            [sys.executable, str(HERE / "cursorbench.py"), *now],
            timeout=timeout, stdout=subprocess.PIPE, env=child_env(timeout),
            **portable.text_kwargs()).stdout
    except subprocess.TimeoutExpired:
        return "bench failed (lookup timed out after %gs; skipped)\n" % timeout


def now_args(probes, infos):
    """cursorbench.py arguments `cli=model:effort`; an empty model means no local session."""
    now = []
    for (_, _, cli), info in zip(probes, infos):
        fields = dict(line.split(None, 1) for line in info.splitlines()
                      if line.startswith(("model ", "effort ")))
        if "model" in fields:
            now.append("%s=%s:%s" % (cli, fields["model"].strip(),
                                     (fields.get("effort") or "?").split()[0]))
        else:
            now.append("%s=:" % cli)
    return now


def sections_of(raw):
    """`### NAME` -> the lines under it, for each section of a report's text."""
    found, name = {}, None
    for line in raw.splitlines():
        if line.startswith("### "):
            name = line[4:].strip()
            found[name] = []
        elif name is not None:
            found[name].append(line)
    return {key: "".join(line + "\n" for line in lines).strip("\n") + "\n"
            for key, lines in found.items()}


def merged(updates):
    """The last report's text with the provider and CURSORBENCH sections in `updates`
    put over it, laid out as the launcher prints it."""
    try:
        old = sections_of(RAW.read_text(encoding="utf-8"))
    except OSError:
        old = {}
    probes = active()
    known = {header for header, _, _ in probes} | {"CURSORBENCH"}
    old.update((key, text) for key, text in sections_of(updates).items() if key in known)
    return (head() + "\n".join("### %s\n%s" % (header, old.get(header, ""))
                               for header, _, _ in probes)
            + "\n### CURSORBENCH\n" + old.get("CURSORBENCH", ""))


if "--serve" in sys.argv:
    import threading, webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import html_report

    # Threaded so every card's request runs at the same time; this lock keeps the
    # saves of finished refreshes from interleaving.
    save_lock = threading.Lock()

    def skeleton():
        """The report with every active provider's card and the bench table loading."""
        raw = head() + "".join("### %s\n" % header for header, _, _ in active())
        return html_report.render(raw, loading=True)

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
                try:
                    page, empty = PAGE.read_text(encoding="utf-8"), False
                except OSError:
                    page, empty = skeleton(), True
                self.reply(serve_page(page, empty).encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/skeleton":
                self.reply(skeleton().encode("utf-8"), "text/html; charset=utf-8")
            else:
                self.send_error(404)

        def do_POST(self):
            # The custom header makes a cross-site request need a CORS preflight, which
            # this server never grants, so other pages cannot start runs.
            if not self.local():
                return
            path = self.path.partition("?")[0]
            if path not in ("/card", "/bench", "/finish", "/login") or self.headers.get("X-AI-Usage") != "1":
                self.send_error(404)
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))
                                  or b"{}")
            except ValueError:
                body = None
            if not isinstance(body, dict):
                self.send_error(400)
                return
            if path == "/login":
                if body.get("id") not in ("CLAUDE", "CHATGPT") or self.headers.get("Origin") not in (
                        None, "http://" + self.headers.get("Host", "")):
                    self.send_error(403)
                    return
                import provider_login
                self.send_json(provider_login.sign_in(body["id"]))
            elif path == "/card":  # one provider: its usage probe and its newest session
                probe = {p[0]: p for p in active()}.get(body.get("id"))
                if not probe:
                    self.send_error(404)
                    return
                header, script, cli = probe
                with ThreadPoolExecutor(max_workers=1) as pool:
                    info = pool.submit(session, cli)
                    raw = "### %s\n%s%s" % (header, usage(script, PAGE_TIMEOUT), info.result())
                self.send_json({"raw": raw, "html": html_report.card_html(raw)})
            elif path == "/bench":  # needs every provider's model, which is read locally
                probes = active()
                with ThreadPoolExecutor(max_workers=max(1, len(probes))) as pool:
                    infos = list(pool.map(session, [cli for _, _, cli in probes]))
                raw = "### CURSORBENCH\n" + benchmark(now_args(probes, infos), PAGE_TIMEOUT)
                self.send_json({"raw": raw, "html": html_report.bench_html(raw)})
            else:  # save the sections the page fetched over the last report
                sections = body.get("sections")
                with save_lock:
                    raw = merged("".join(s for s in sections if isinstance(s, str))
                                 if isinstance(sections, list) else "")
                    write_page(html_report.render(raw), raw)
                self.send_json({"written": written_ms()})

        def send_json(self, data):
            self.reply(json.dumps(data).encode("utf-8"), "application/json")

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
    holder = take_over(ping())
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

# The report is always the HTML page; AI_USAGE_NO_PAGE=1 (tests) prints the text only.
HTML = not os.environ.get("AI_USAGE_NO_PAGE")
# Keep a copy of everything printed so html_report can build the advice and the page.
import io
_real_stdout = sys.stdout
_captured = io.StringIO()


class _Tee:
    def write(self, text):
        _captured.write(text)
        _real_stdout.write("".join(line for line in text.splitlines(keepends=True)
                                  if not line.startswith("reset-expiry ")))
        return len(text)

    def flush(self):
        _real_stdout.flush()


sys.stdout = _Tee()

try:
    print(head(), end="")
    sys.stdout.flush()
    probes = active()
    with ThreadPoolExecutor(max_workers=2 * len(probes)) as pool:
        # Start every CLI and local session read before waiting for any result.
        calls = [pool.submit(usage, script) for _, script, _ in probes]
        sessions = [pool.submit(session, cli) for _, _, cli in probes]
        infos = [future.result() for future in sessions]
        # Benchmark needs model/effort, not usage: overlap its network calls too.
        bench = pool.submit(benchmark, now_args(probes, infos))
        for i, ((header, _, _), call, info) in enumerate(zip(probes, calls, infos)):
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
        write_page(html_report.render(_captured.getvalue()), _captured.getvalue())
        # Prefer the local server, whose page has a Refresh button; fall back to the file.
        note = ""
        holder = take_over(ping())
        if holder == PING or (holder is None and start_server()):
            shown, opened = SERVE_URL, webbrowser.open(SERVE_URL)
        else:
            shown, opened = PAGE, webbrowser.open(PAGE.as_uri())
            note = ("  (Refresh unavailable: port %d is held by %s; stop it)"
                    % (SERVE_PORT, holder.decode("utf-8", "replace")) if holder else
                    "  (Refresh unavailable: could not start a server on port %d)" % SERVE_PORT)
        print()
        print("### HTML %s%s%s" % (shown, note, "" if opened else "  (could not open a browser)"))
except BrokenPipeError:
    # someone piped us into `head` and walked away. Point the fd at devnull so the
    # interpreter's shutdown flush does not print a second traceback on top.
    import os
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    sys.exit(0)

#!/usr/bin/env python3
"""Report installed vs latest versions of the Claude Code, Codex, Grok Build, Muse Code and
Antigravity (Gemini) CLIs.

For each tool: the installed version and when it was installed on this machine, and the
latest version and when it was released. Check only -- this script never installs or
updates anything.

Standard library only. The Python code makes HTTP requests to the npm registry, the
GitHub API, Muse's public release channel and the Antigravity CLI's auto-updater;
everything else is read from the local CLIs and the filesystem.
"""

import datetime
import glob
import gzip
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_runtime import server_identity, server_owned_by

# Bumped by hand. `metadata.version` in SKILL.md mirrors this; keep them equal.
VERSION = "1.16.3"

# Seconds per check. The chat report keeps 20; the browser page, which shows each tool
# as soon as it answers, passes a longer one to its probes in AI_CLI_VERSION_TIMEOUT.
TIMEOUT = float(os.environ.get("AI_CLI_VERSION_TIMEOUT") or 20)
# Per-check budget on the page: each row checks on its own, so a slow tool only keeps
# its own skeleton up and can be given longer than the chat report's 20 s.
PAGE_TIMEOUT = 90
HOME = os.path.expanduser("~")
# Both CLIs let the user move their home directory; the installers honour these variables.
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude")
CODEX_DIR = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")
# npm extracts package files with a fixed 1985 timestamp; anything this old is not an
# install time.
OLDEST_PLAUSIBLE_YEAR = 2015
_SHIM = (".cmd", ".bat")


def stdout_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # not a TextIOWrapper; nothing to fix


def argv(name, *args):
    """Argument list that launches `name` on this OS, or None if it is not installed."""
    path = shutil.which(name)
    if not path:
        return None
    if os.name == "nt" and os.path.splitext(path)[1].lower() in _SHIM:
        return ["cmd", "/c", path, *args]
    return [path, *args]


def run(cmd, env=None):
    """Run a command and return its stdout decoded as UTF-8, or raise."""
    proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT,
                          env={**os.environ, **env} if env else None)
    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err.splitlines()[-1] if err else f"exit {proc.returncode}")
    return out


def get_json(url, headers=None):
    # gzip: the full npm document for @openai/codex is ~18 MB raw, ~1.6 MB compressed.
    request = urllib.request.Request(url, headers={"User-Agent": "ai-cli-version",
                                                   "Accept-Encoding": "gzip", **(headers or {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return json.loads(body.decode("utf-8", errors="replace"))


def get_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ai-cli-version"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_version(text):
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def fmt(version):
    if version and len(version) == 5:  # Muse: 1.3.0-R3401.1, parsed by muse_version()
        build = "R%d" % version[3] + (".%d" % version[4] if version[4] else "")
        return "%d.%d.%d-%s" % (version[:3] + (build,))
    return ".".join(str(part) for part in version) if version else "?"


def muse_version(text):
    """'1.3.0-R3401.1' -> (1, 3, 0, 3401, 1). The R build number orders releases that
    share a semver."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)-R(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(part or 0) for part in match.groups()) if match else None


def local_from_iso(value):
    """ISO-8601 timestamp -> local 'MM/DD HH:MM', or None."""
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone().strftime("%m/%d %H:%M")


def install_time(path):
    """Best available 'installed at' for a path -> local 'MM/DD HH:MM', or None.

    Windows: st_ctime is creation time. macOS: st_birthtime. Linux has neither in os.stat,
    so st_mtime is used, which is the time the folder was last written.
    """
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    if os.name == "nt":
        stamp = stat.st_ctime
    else:
        stamp = getattr(stat, "st_birthtime", None) or stat.st_mtime
    moment = datetime.datetime.fromtimestamp(stamp)
    if moment.year < OLDEST_PLAUSIBLE_YEAR:
        return None
    return moment.strftime("%m/%d %H:%M")


def first_match(pattern):
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else None


def package_dir_time(name):
    """Fallback install time: the real executable behind `name`, else its folder.

    The file comes first because some installers reuse one folder across versions — the
    macOS/Linux Grok installer keeps every build in ~/.grok/downloads as
    grok-<platform>, so the folder's time is the first install, not the current one.
    """
    path = shutil.which(name)
    if not path:
        return None
    real = os.path.realpath(path)
    return install_time(real) or install_time(os.path.dirname(real))


def npm_package(package):
    """(dist-tags, publish times) straight from the npm registry; npm itself is not needed."""
    data = get_json("https://registry.npmjs.org/" + package.replace("/", "%2F"), {"Accept": "application/json"})
    return data.get("dist-tags", {}), data.get("time", {})


def claude_channel():
    try:
        with open(os.path.join(CLAUDE_DIR, "settings.json"), encoding="utf-8") as handle:
            return json.load(handle).get("autoUpdatesChannel") or "latest"
    except (OSError, ValueError):
        return "latest"


def emit(name, installed, installed_at, latest, released, released_note, channel, update_cmd):
    if installed is None or latest is None:
        state = "unknown"
    elif installed < latest:
        state = "update available"
    elif installed > latest:
        state = "ahead of channel"
    else:
        state = "up to date"
    print("\t".join([
        name,
        f"installed={fmt(installed)}",
        f"installed_at={installed_at or '?'}",
        f"latest={fmt(latest)}",
        f"released={released or '?'}",
        f"released_note={released_note}",
        f"channel={channel}",
        f"status={state}",
        f"update_cmd={update_cmd}",
    ]))


def check_claude():
    cmd = argv("claude", "--version")
    if cmd is None:
        print("claude\tnot installed")
        return
    try:
        installed = parse_version(run(cmd))
        channel = claude_channel()
        tags, times = npm_package("@anthropic-ai/claude-code")
        if channel not in tags:
            raise RuntimeError(f"npm dist-tag '{channel}' not found")
        latest = parse_version(tags[channel])
        installed_at = install_time(
            os.path.join(HOME, ".local", "share", "claude", "versions", fmt(installed))
        ) or package_dir_time("claude")
        released = local_from_iso(times.get(fmt(latest)))
        emit("claude", installed, installed_at, latest, released, "npm publish", channel, "claude update")
    except Exception as exc:  # noqa: BLE001
        print(f"claude\tcheck failed ({exc})")


def check_codex():
    cmd = argv("codex", "--version")
    if cmd is None:
        print("codex\tnot installed")
        return
    try:
        installed = parse_version(run(cmd))
        tags, times = npm_package("@openai/codex")
        latest = parse_version(tags.get("latest"))
        installed_at = install_time(
            first_match(os.path.join(CODEX_DIR, "packages", "standalone", "releases", f"{fmt(installed)}-*"))
        ) or package_dir_time("codex")
        released = local_from_iso(times.get(fmt(latest)))
        emit("codex", installed, installed_at, latest, released, "npm publish", "latest", "codex update")
    except Exception as exc:  # noqa: BLE001
        print(f"codex\tcheck failed ({exc})")


def check_grok():
    cmd = argv("grok", "update", "--check", "--json")
    if cmd is None:
        print("grok\tnot installed")
        return
    try:
        data = json.loads(run(cmd).strip().splitlines()[-1])
        if data.get("error"):
            raise RuntimeError(data["error"])
        installed = parse_version(data.get("currentVersion"))
        latest = parse_version(data.get("latestVersion"))
        installed_at = install_time(
            first_match(os.path.join(HOME, ".grok", "downloads", f"grok-{fmt(installed)}-*"))
        ) or package_dir_time("grok")
        try:
            release = get_json(
                f"https://api.github.com/repos/timoteuszelle/x.ai-grok/releases/tags/v{fmt(latest)}",
                {"Accept": "application/vnd.github+json"},
            )
            released = local_from_iso(release.get("published_at"))
        except Exception:  # noqa: BLE001
            released = None
        emit(
            "grok",
            installed,
            installed_at,
            latest,
            released,
            "approx: third-party mirror detected it; official release is no later than this",
            data.get("channel") or "?",
            "grok update",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"grok\tcheck failed ({exc})")


def check_muse():
    # The launcher kicks off a background self-update when it runs; this is a check.
    cmd = argv("muse", "--version")
    if cmd is None:
        print("muse	not installed")
        return
    try:
        installed = muse_version(run(cmd, {"MUSE_NO_AUTO_UPDATE": "1"}))
        if installed is None:
            raise RuntimeError("unrecognised `muse --version` output")
        home = os.path.dirname(os.path.realpath(shutil.which("muse")))
        channel = os.environ.get("MUSE_CHANNEL")
        if not channel:
            try:
                with open(os.path.join(home, ".muse-channel"), encoding="utf-8") as handle:
                    channel = handle.read().strip()
            except OSError:
                pass
        channel = channel or "muse-stable"
        # The same unauthenticated manifest the launcher reads. It names no date.
        manifest = get_json("https://api.meta.ai/muse-code/channels/" + channel,
                            {"Accept": "application/json"})
        latest = muse_version(manifest.get("version"))
        if latest is None:
            raise RuntimeError("channel manifest has no version")
        installed_at = install_time(
            first_match(os.path.join(home, f"muse-bin-{fmt(installed)}*"))
        ) or package_dir_time("muse")
        # Single quotes: bash and PowerShell both leave `$env` alone inside them.
        update = ("powershell -NoProfile -Command '$env:MUSE_SYNC_UPDATE=1; muse --version'"
                  if os.name == "nt" else "MUSE_SYNC_UPDATE=1 muse --version")
        emit("muse", installed, installed_at, latest, None,
             "not published: the release channel carries no date", channel, update)
    except Exception as exc:  # noqa: BLE001
        print(f"muse	check failed ({exc})")


# The Antigravity CLI's own auto-updater. Its root answers in plain text, e.g.
# "Antigravity CLI auto updater is running! Stable Version: 1.2.14. Rolled out to 100%".
# `/releases` lists versions without dates, so there is no release time.
AGY_UPDATER = "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app"


def check_agy():
    # ~/.gemini/bin/agy, never `agy` on PATH: the Antigravity IDE installs an editor
    # launcher with the same name, and running that opens a window.
    cli = os.path.join(HOME, ".gemini", "bin", "agy.exe" if os.name == "nt" else "agy")
    if not os.path.isfile(cli):
        print("agy\tnot installed")
        return
    try:
        # The CLI updates itself on start; this keeps the check read-only.
        installed = parse_version(run([cli, "--version"], {"AGY_CLI_DISABLE_AUTO_UPDATE": "1"}))
        if installed is None:
            raise RuntimeError("unrecognised `agy --version` output")
        page = get_text(AGY_UPDATER)
        match = re.search(r"Stable Version:\s*(\d+\.\d+\.\d+)", page)
        if not match:
            raise RuntimeError("updater page names no stable version")
        latest = parse_version(match.group(1))
        rollout = re.search(r"Rolled out to\s*(\d+%)", page)
        note = "not published: the updater lists versions without dates"
        if rollout:
            note += "; rolled out to " + rollout.group(1)
        update = '"%s" update' % cli if " " in cli else "%s update" % cli
        emit("agy", installed, install_time(cli), latest, None, note, "stable", update)
    except Exception as exc:  # noqa: BLE001
        print(f"agy\tcheck failed ({exc})")


SKILL_URL = "https://raw.githubusercontent.com/Jeinn-co/agent-skills/main/skills/ai-cli-version/SKILL.md"


def version_key(text):
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def check_skill():
    """Compare this skill with the SKILL.md published on GitHub main."""
    try:
        found = re.search(r'^\s*version:\s*"([^"]+)"', get_text(SKILL_URL), re.M)
        if not found:
            raise RuntimeError("no version in the published SKILL.md")
        latest = found.group(1)
    except Exception as exc:  # noqa: BLE001 -- the check must never block the report
        print(f"skill\tcheck failed ({exc})")
        return
    status = "update available" if version_key(latest) > version_key(VERSION) else "up to date"
    print(f"skill\tinstalled={VERSION}\tlatest={latest}\tstatus={status}"
          "\tupdate_cmd=npx -y skills update -g ai-cli-version")


CHECKS = {"claude": check_claude, "codex": check_codex, "grok": check_grok,
          "muse": check_muse, "agy": check_agy}


CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"),
                      "ai-cli-version", "config.json")


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


def selected_tools():
    """Tools chosen with --set-tools; every tool when there is no valid config."""
    tools = load_config().get("tools")
    picked = [name for name in CHECKS if isinstance(tools, list) and name in tools]
    return picked or list(CHECKS)


def installed_tools():
    """Tools whose CLI is present, using the same lookups as the checks."""
    agy = os.path.join(HOME, ".gemini", "bin", "agy.exe" if os.name == "nt" else "agy")
    found = {name: shutil.which(name) is not None for name in ("claude", "codex", "grok", "muse")}
    found["agy"] = os.path.isfile(agy)
    return [name for name in CHECKS if found[name]]


def set_tools(arg):
    """Save the tools to check; `all` removes the config so every tool is checked."""
    config = load_config()
    if arg.strip().lower() == "all":
        config.pop("tools", None)
        save_config(config)
        return list(CHECKS)
    names = [n.strip().lower() for n in arg.split(",") if n.strip()]
    unknown = [n for n in names if n not in CHECKS]
    if unknown or not names:
        raise SystemExit("unknown tool(s): %s; choose from %s or all"
                         % (", ".join(unknown) or "none given", ",".join(CHECKS)))
    picked = [name for name in CHECKS if name in names]
    config["tools"] = picked
    save_config(config)
    return picked


def stop_tree(proc):
    """Stop a child started with start_new_session (POSIX) and every process under it."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.kill()
    proc.wait()


def check_tool(name, timeout=TIMEOUT):
    """Isolate each check so its total deadline can stop CLI descendants too."""
    kwargs = {"start_new_session": True} if os.name != "nt" else {}
    proc = subprocess.Popen([sys.executable, __file__, "--probe", name],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            encoding="utf-8", errors="replace",
                            env=dict(os.environ, AI_CLI_VERSION_TIMEOUT="%g" % timeout),
                            **kwargs)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop_tree(proc)
        proc.stdout.close()
        proc.stderr.close()
        return "%s\tcheck failed (lookup timed out after %gs; skipped)\n" % (name, timeout)
    if proc.returncode:
        reason = err.strip().splitlines()
        return "%s\tcheck failed (%s)\n" % (name, reason[-1] if reason else "no result")
    return out


# Local report page with a Refresh button that checks every tool again, one request per
# tool (reload only re-reads the last report). Fixed port so a run can reuse a running
# server; one above ai-usage's 47821.
SERVE_PORT = 47822
SERVE_URL = "http://127.0.0.1:%d/" % SERVE_PORT
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(tempfile.gettempdir(), "ai-cli-version", "report.html")
# /ping answer: version and location, so a server left from an older or moved copy of
# this skill is not mistaken for this one (its Refresh would run that other run.py).
PING = server_identity("ai-cli-version", VERSION, HERE)
# `/` is the last report itself, with Theme, Update all and Refresh added to its own header
# next to the language switch (no iframe). Refresh shows skeleton rows under the header and
# checks each tool with its own request, so every row fills in as soon as its tool answers.
SERVE_CSS = (Path(__file__).resolve().parent / 'assets/toolbar.css').read_text(encoding="utf-8")
SHELL = (Path(__file__).resolve().parent / 'assets/report.js').read_text(encoding="utf-8")


def serve_page(page, empty=False):
    """The report page with the served tools in its header and the refresh script."""
    import html_report
    if 'data-report-i18n' not in page:
        page = page.replace('<head>', '<head><script data-report-i18n>' + html_report.I18N.head() + '</script>', 1)
    page = page.replace(html_report.I18N.language_button, html_report.I18N.toolbar('<button type="button" class="lang" id="all" hidden></button>'), 1)
    page = page.replace("</head>", "<style>%s</style></head>" % SERVE_CSS, 1)
    script = SHELL.replace("__GLOBE__", json.dumps(html_report.I18N.globe)).replace("__SKELETON__", json.dumps(html_report.SKELETON)).replace("__VERSION__", VERSION)
    page = page.replace("</body>", "<script>%s</script></body>" % script, 1)
    return page.replace("<html", '<html data-empty="1"', 1) if empty else page


UPDATE_TIMEOUT = 300


def update_plan(name):
    """(argv, extra env) for `name`'s updater: what its update_cmd runs, without a shell,
    so no quoting rules or shell PATH apply. None as argv when it is not installed."""
    if name == "muse":
        return argv("muse", "--version"), {"MUSE_SYNC_UPDATE": "1"}
    if name == "agy":
        cli = os.path.join(HOME, ".gemini", "bin", "agy.exe" if os.name == "nt" else "agy")
        return ([cli, "update"] if os.path.isfile(cli) else None), {}
    return argv(name, "update"), {}


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def run_update(name, on_line=lambda line: None):
    """Run `name`'s updater when a fresh check still offers an update. Each output line
    goes to on_line as it arrives, so the page can show which step the updater is on."""
    on_line("checking for the update")
    row = check_tool(name, PAGE_TIMEOUT)
    if "status=up to date" in row:
        return {"ok": True, "output": "already up to date"}
    if "status=update available" not in row:
        return {"ok": False, "error": row.strip().split("\t")[-1][:300]}
    args, extra = update_plan(name)
    if not args:
        return {"ok": False, "error": "not installed"}
    env = dict(os.environ, **extra)
    if os.name == "nt":
        # Windows' own tar first: Git's GNU tar on PATH makes the Codex installer fail.
        system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        env["PATH"] = system32 + os.pathsep + env.get("PATH", "")
    kwargs = {"start_new_session": True} if os.name != "nt" else {}
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                            env=env, **kwargs)
    timed_out = threading.Event()

    def give_up():
        timed_out.set()
        stop_tree(proc)

    timer = threading.Timer(UPDATE_TIMEOUT, give_up)
    timer.start()
    last = ""
    try:
        # Text mode splits on "\r" too, so installers' redrawn progress lines arrive one by one.
        for line in proc.stdout:
            line = ANSI.sub("", line).strip()
            if line:
                last = line[:300]
                on_line(last)
        proc.wait()
    finally:
        timer.cancel()
        proc.stdout.close()
    if timed_out.is_set():
        return {"ok": False, "error": "timed out after %ds" % UPDATE_TIMEOUT}
    if proc.returncode:
        return {"ok": False, "error": last or "exit %d" % proc.returncode}
    return {"ok": True, "output": last}


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
    if holder in (None, PING) or not server_owned_by(holder, HERE):
        return holder  # free, ours, or another copy's server: leave it alone
    pid = port_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)  # TerminateProcess on Windows
        except OSError:
            return holder
        for _ in range(30):
            if ping() is None:
                return None
            time.sleep(0.1)
    return ping()


def start_server():
    """Start `--serve` detached so it outlives this run; True once it answers."""
    args = [sys.executable, __file__, "--serve", "--no-open"]
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


# The check's raw lines behind the report, so the server can redraw one tool's row.
LINES = PAGE + ".lines"


def write_atomic(path, text):
    """Swap in a complete file so a reader never sees half of it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # Windows: the server is reading the file right now
                if attempt == 9:
                    raise
                time.sleep(0.1)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def write_page(html, lines):
    write_atomic(LINES, json.dumps(lines))
    write_atomic(PAGE, html)


def skeleton():
    """The report with a loading row for every selected tool."""
    import html_report
    tools = selected_tools()
    return html_report.render(head_lines(tools) + ["%s\tchecking" % name for name in tools], loading=True)


def written_ms():
    """When the report on disk was written (ms since epoch), "0" if there is none."""
    try:
        return str(int(os.path.getmtime(LINES if os.path.exists(LINES) else PAGE) * 1000))
    except OSError:
        return "0"


def head_lines(tools):
    """A report's first lines: version, and the tools setup leaves out."""
    lines = [f"### ai-cli-version {VERSION}"]
    skipped = [name for name in CHECKS if name not in tools]
    if skipped:
        lines.append("### skipped " + ",".join(skipped))
    return lines


def saved_lines():
    """The check lines behind the saved report, or [] when there are none."""
    try:
        with open(LINES, encoding="utf-8") as fh:
            lines = json.load(fh)
    except (OSError, ValueError):
        return []
    return lines if isinstance(lines, list) else []


def saved_page():
    """Apply the current renderer to captured checks without checking tools again."""
    import html_report
    lines = saved_lines()
    if not lines:
        with open(PAGE, encoding="utf-8") as stream:
            return stream.read()
    lines = ['### ai-cli-version ' + VERSION if line.startswith('### ai-cli-version ') else line
             for line in lines]
    captured_at = datetime.datetime.fromtimestamp(os.path.getmtime(LINES))
    return html_report.render(lines, now=captured_at)


def serve():
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    # Updates run one at a time, including requests from other tabs; saves of the
    # report never interleave with them.
    refresh_lock = threading.Lock()
    progress = {"active": ("", "")}

    sys.path.insert(0, HERE)
    import html_report

    def tool_of(line):
        return line.split("\t", 1)[0] if isinstance(line, str) and "\t" in line else None

    def redraw_row(name):
        """Re-check one tool, put its new row into the saved report and return the page;
        None when the saved lines are missing or do not include that tool."""
        fresh = [line for line in check_tool(name, PAGE_TIMEOUT).splitlines() if line.strip()]
        lines = saved_lines()
        kept = [line for line in lines if tool_of(line) != name]
        if len(kept) == len(lines):
            return None
        at = next(i for i, line in enumerate(lines) if tool_of(line) == name)
        lines = kept[:at] + fresh + kept[at:]
        page = html_report.render(lines)
        write_page(page, lines)
        return page

    def merged(fresh):
        """The saved report's lines with every tool in `fresh` replaced by its new lines,
        in setup's tool order."""
        tools = selected_tools()
        by_tool = {}
        for line in saved_lines():
            by_tool.setdefault(tool_of(line), []).append(line)
        new = {}
        for line in fresh:
            if tool_of(line) in tools:
                new.setdefault(tool_of(line), []).append(line)
        by_tool.update(new)
        return head_lines(tools) + [line for name in tools for line in by_tool.get(name, [])]

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
                    page, empty = saved_page(), False
                except OSError:
                    page, empty = skeleton(), True
                page = serve_page(page, empty).replace("__UPDATED__", written_ms())
                self.reply(page.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/skeleton":
                self.reply(skeleton().encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/progress":
                tool, line = progress["active"]
                self.reply(json.dumps({"tool": tool, "line": line}).encode("utf-8"),
                           "application/json")
            else:
                self.send_error(404)

        def do_POST(self):
            # The custom header makes a cross-site request need a CORS preflight, which
            # this server never grants, so other pages cannot start runs or updates.
            if not self.local():
                return
            path, _, query = self.path.partition("?")
            if (path not in ("/row", "/finish", "/update")
                    or self.headers.get("X-AI-CLI-Version") != "1"):
                self.send_error(404)
                return
            if path == "/update":
                # Only a known tool name is accepted; the updater comes from update_plan.
                name = urllib.parse.parse_qs(query).get("tool", [""])[0]
                if name not in CHECKS:
                    self.send_error(404)
                    return
                with refresh_lock:
                    progress["active"] = (name, "checking for the update")

                    def on_line(line):
                        progress["active"] = (name, line)
                    try:
                        try:
                            result = run_update(name, on_line)
                        except OSError as exc:
                            result = {"ok": False, "error": str(exc)}
                        on_line("checking the installed version")
                        result["page"] = redraw_row(name)
                        result["written"] = written_ms()
                    finally:
                        progress["active"] = ("", "")
                self.reply(json.dumps(result).encode("utf-8"), "application/json")
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))
                                  or b"{}")
            except ValueError:
                body = None
            if not isinstance(body, dict):
                self.send_error(400)
                return
            if path == "/row":  # one tool, under the page's longer budget
                name = body.get("tool")
                if name not in selected_tools():
                    self.send_error(404)
                    return
                lines = [line for line in check_tool(name, PAGE_TIMEOUT).splitlines()
                         if line.strip()] or ["%s\tcheck failed (no result)" % name]
                self.send_json({"lines": lines, "html": html_report.row_html(lines)})
                return
            fresh = body.get("lines")  # /finish: save what the page checked
            with refresh_lock:
                lines = merged(fresh if isinstance(fresh, list) else [])
                page = html_report.render(lines)
                write_page(page, lines)
            self.send_json({"page": page, "written": written_ms()})

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
        raise SystemExit("port %d is held by another ai-cli-version server (%s); stop that "
                         "process first" % (SERVE_PORT, holder.decode("utf-8", "replace")))
    else:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", SERVE_PORT), Handler)
        except OSError as exc:
            raise SystemExit("port %d is busy (%s)" % (SERVE_PORT, exc))
        print("serving %s  (Refresh re-runs the check, Ctrl+C stops)" % SERVE_URL, flush=True)
    if "--no-open" not in sys.argv:
        webbrowser.open(SERVE_URL)
    if server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main():
    stdout_utf8()
    if "--version" in sys.argv:
        print(VERSION)
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--probe":
        CHECKS[sys.argv[2]]()
        return
    if "--check-skill" in sys.argv:
        check_skill()
        return
    if "--show-tools" in sys.argv:
        print("tools=" + ",".join(selected_tools()))
        print("installed=" + ",".join(installed_tools()))
        print("output=" + output_format())
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--set-output":
        if sys.argv[2] not in OUTPUTS:
            raise SystemExit("unknown output: %s; choose html or md" % sys.argv[2])
        config = load_config()
        config["output"] = None if sys.argv[2] == "html" else sys.argv[2]
        save_config(config)
        print("output=" + output_format())
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--set-tools":
        print("tools=" + ",".join(set_tools(sys.argv[2])))
        return
    if "--serve" in sys.argv:
        serve()
        return
    tools = selected_tools()
    lines = head_lines(tools)
    print(chr(10).join(lines), flush=True)
    with ThreadPoolExecutor(max_workers=len(tools)) as pool:
        # Submit every selected check before collecting; keep the report's tool order.
        results = [pool.submit(check_tool, name) for name in tools]
        for result in results:
            text = result.result()
            lines.extend(text.splitlines())
            print(text, end="", flush=True)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import html_report
    print("### SUMMARY")
    print(chr(10).join(html_report.summary(lines)), flush=True)
    if output_format() == "html":
        import webbrowser
        write_page(html_report.render(lines), lines)
        # Prefer the local server, whose page has a Refresh button; fall back to the file.
        note = ""
        holder = take_over(ping())
        if holder == PING or (holder is None and start_server()):
            shown, opened = SERVE_URL, webbrowser.open(SERVE_URL)
        else:
            shown = PAGE
            opened = webbrowser.open("file:///" + PAGE.replace(os.sep, "/").lstrip("/"))
            note = ("  (Refresh unavailable: port %d is held by %s; stop it)"
                    % (SERVE_PORT, holder.decode("utf-8", "replace")) if holder else
                    "  (Refresh unavailable: could not start a server on port %d)" % SERVE_PORT)
        print("### HTML %s%s%s" % (shown, note, "" if opened else "  (could not open a browser)"))


if __name__ == "__main__":
    main()

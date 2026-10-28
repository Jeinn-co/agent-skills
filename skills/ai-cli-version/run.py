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
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Bumped by hand. `metadata.version` in SKILL.md mirrors this; keep them equal.
VERSION = "1.10.1"

TIMEOUT = 20
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


def check_tool(name):
    """Isolate each check so its total deadline can stop CLI descendants too."""
    kwargs = {"start_new_session": True} if os.name != "nt" else {}
    proc = subprocess.Popen([sys.executable, __file__, "--probe", name],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            encoding="utf-8", errors="replace",
                            **kwargs)
    try:
        out, err = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
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
        proc.stdout.close()
        proc.stderr.close()
        return "%s\tcheck failed (lookup timed out after %gs; skipped)\n" % (name, TIMEOUT)
    if proc.returncode:
        reason = err.strip().splitlines()
        return "%s\tcheck failed (%s)\n" % (name, reason[-1] if reason else "no result")
    return out


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
    tools = selected_tools()
    lines = [f"### ai-cli-version {VERSION}"]
    skipped = [name for name in CHECKS if name not in tools]
    if skipped:
        lines.append("### skipped " + ",".join(skipped))
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
        import tempfile
        import webbrowser
        out = os.path.join(tempfile.gettempdir(), "ai-cli-version", "report.html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html_report.render(lines))
        opened = webbrowser.open("file:///" + out.replace(os.sep, "/").lstrip("/"))
        print("### HTML %s%s" % (out, "" if opened else "  (could not open a browser)"))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Report installed vs latest versions of the Claude Code, Codex and Grok Build CLIs.

For each tool: the installed version and when it was installed on this machine, and the
latest version and when it was released. Check only -- this script never installs or
updates anything.

Standard library only. The Python code makes HTTP requests to the npm registry and to
the GitHub API; everything else is read from the local CLIs and the filesystem.
"""

import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

# Bumped by hand. `metadata.version` in SKILL.md mirrors this; keep them equal.
VERSION = "1.1.0"

TIMEOUT = 60
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


def run(cmd):
    """Run a command and return its stdout decoded as UTF-8, or raise."""
    proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT)
    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err.splitlines()[-1] if err else f"exit {proc.returncode}")
    return out


def get_json(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": "ai-cli-version", **(headers or {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def parse_version(text):
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def fmt(version):
    return ".".join(str(part) for part in version) if version else "?"


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


def main():
    stdout_utf8()
    if "--version" in sys.argv:
        print(VERSION)
        return
    print(f"### ai-cli-version {VERSION}")
    check_claude()
    check_codex()
    check_grok()


if __name__ == "__main__":
    main()

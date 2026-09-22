#!/usr/bin/env python3
"""Cross-platform helpers shared by the three probes.

Windows needs two things POSIX does not:

  * **stdout that survives non-ASCII.** On a redirected stream Python uses the
    locale encoding (cp950, cp1252), not UTF-8, so a `·` in Claude's output
    raises UnicodeEncodeError -- and a redirected stream is the normal case here,
    because the agent captures the output.
  * **.cmd/.bat shims resolved to a full path.** npm installs `claude.cmd`;
    `shutil.which` finds it but CreateProcess cannot execute one directly, so
    `Popen(["claude"])` raises FileNotFoundError.

Neither has any effect on macOS or Linux.
"""
import atexit, os, shutil, sys

# Bumped by hand. `metadata.version` in SKILL.md mirrors this; keep them equal.
VERSION = "1.2.0"

_SHIM = (".cmd", ".bat")


def _devnull_stdout():
    try:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except Exception:
        pass


def _on_exit():
    # The reader (`| head`) can close the pipe while we are still printing. Python
    # would otherwise print a BrokenPipeError traceback from its shutdown flush,
    # which looks like a crash in output the user already stopped reading. Each
    # probe is its own process, so every one of them needs this, not just run.py.
    #
    # This covers stdout ONLY, at interpreter shutdown. A broken pipe to a *CLI we
    # launched* is a different event entirely -- it means that CLI died before
    # answering -- and each probe must catch that at its own stdin boundary and
    # report a failed row. Silencing it here would turn "codex is not signed in"
    # into a blank section and a zero exit code.
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        _devnull_stdout()
    except Exception:
        pass


def stdout_utf8():
    """UTF-8 stdout/stderr, and a quiet exit when the reader closes the pipe."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # not a TextIOWrapper; nothing to fix
    atexit.register(_on_exit)


def text_kwargs():
    """subprocess kwargs that decode a launched CLI's output as UTF-8.

    `text=True` alone decodes with `locale.getpreferredencoding(False)`, which is
    cp950/cp1252/etc on non-English Windows, not UTF-8. Every CLI probed here
    (claude, codex, grok) emits UTF-8, so a stray bullet or middot in the output
    raises UnicodeDecodeError under that locale encoding on Windows. macOS's
    preferred encoding is already UTF-8, so pinning it here changes nothing there.
    """
    return dict(encoding="utf-8", errors="replace")


def argv(name, *args):
    """Argument list that actually launches `name` on this OS, or None if absent.

    Returning None rather than raising lets each probe print `not installed` and
    exit 0, which is what the skill contract promises.
    """
    path = shutil.which(name)
    if not path:
        return None
    if os.name == "nt" and os.path.splitext(path)[1].lower() in _SHIM:
        return ["cmd", "/c", path, *args]
    return [path, *args]

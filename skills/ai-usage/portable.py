#!/usr/bin/env python3
"""Cross-platform helpers shared by the probes.

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
VERSION = "1.7.4"

# 20 cells. Each cell is 5 points; the partial cell is one of 8 eighths, so the
# scale is 0.625 points. The old 10-cell bar rounded 28% and 30% to the same glyph.
BAR_CELLS = 20
_BAR_EIGHTH = "▏▎▍▌▋▊▉"  # 1/8 .. 7/8, left-aligned; 8/8 is █

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


def usage_bar(percent):
    """20-cell gauge for a 0–100 usage percent.

    Empty track is ░, a full cell is █, and the remainder is ▏▎▍▌▋▊▉.
    0% is twenty ░. 100% is twenty █. A non-zero percent that would round to
    zero eighths still shows ▏, so 1% does not look unused.
    """
    try:
        value = float(percent)
    except (TypeError, ValueError):
        value = 0.0
    if value < 0:
        value = 0.0
    elif value > 100:
        value = 100.0
    eighths = int(round(value * BAR_CELLS * 8 / 100.0))
    if value > 0 and eighths < 1:
        eighths = 1
    if eighths > BAR_CELLS * 8:
        eighths = BAR_CELLS * 8
    full, rem = divmod(eighths, 8)
    body = "█" * full
    if rem:
        body += _BAR_EIGHTH[rem - 1]
    return body + "░" * (BAR_CELLS - len(body))


def format_bar(percent):
    """Probe suffix. The report copies this string; it does not redraw the bar."""
    return "bar %s" % usage_bar(percent)

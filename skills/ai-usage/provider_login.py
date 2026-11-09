"""User-triggered official CLI sign-in; no auth tokens pass through the report."""
import json
import subprocess
import threading

import portable

_lock = threading.Lock()
PROVIDERS = {
    "CLAUDE": {"cli": "claude", "name": "Claude", "login": ("auth", "login", "--claudeai"),
               "status": ("auth", "status"), "manual": "claude auth login"},
    "CHATGPT": {"cli": "codex", "name": "ChatGPT", "login": ("login",),
                "status": ("login", "status"), "manual": "codex login"},
}


def signed_in(provider):
    spec = PROVIDERS[provider]
    command = portable.argv(spec["cli"], *spec["status"])
    if command is None:
        return False
    result = portable.run_bounded(command, timeout=10, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  **portable.text_kwargs())
    if provider == "CLAUDE":
        return json.loads(result.stdout or "{}").get("loggedIn") is True
    text = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0 and "logged in using chatgpt" in text.lower()


def requires_auth(error):
    if not isinstance(error, dict):
        return False
    text = str(error.get("message", "")).lower()
    if error.get("code") == 407 or "proxy authentication" in text:
        return False
    return error.get("code") == 401 or any(phrase in text for phrase in (
        "not authenticated", "not logged in", "authentication required", "unauthorized",
        "refresh token expired", "refresh_token_expired", "reauthentication_required",
        "refresh_token_reused", "token_invalidated"))


def sign_in(provider):
    if provider not in PROVIDERS:
        return {"ok": False, "message": "Unsupported sign-in provider."}
    spec = PROVIDERS[provider]
    if not _lock.acquire(blocking=False):
        return {"ok": False, "message": "Sign-in is already in progress. Complete it in the browser."}
    try:
        command = portable.argv(spec["cli"], *spec["login"])
        if command is None:
            return {"ok": False, "message": "%s CLI is not installed on the report server." % spec["name"]}
        # A deliberate click may be repairing server-rejected credentials that look cached locally.
        result = portable.run_bounded(command, timeout=300, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0 and signed_in(provider):
            return {"ok": True, "message": "Signed in to %s. Refreshing usage." % spec["name"]}
        return {"ok": False, "message": "Sign-in was not completed. Try again, or run %s in a terminal." % spec["manual"]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Sign-in timed out after 5 minutes. Click Sign in to %s to retry." % spec["name"]}
    except Exception:
        return {"ok": False, "message": "Could not complete sign-in. Run %s in a terminal, then Refresh." % spec["manual"]}
    finally:
        _lock.release()

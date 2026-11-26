"""Load the bundled model facts and personal display choices.

Personal choices start from the bundled copy. refresh_live() replaces them with the copy
AI Model Compare publishes from the owner's Notion config page; any failure keeps what is
loaded. The containers are updated in place so modules that imported them see the change.
"""
from pathlib import Path
import json
import urllib.request

_DATA = Path(__file__).with_name("data")
_CATALOG = json.loads((_DATA / "gemini-models.json").read_text(encoding="utf-8"))
LIVE_URL = "https://jeinn-co.github.io/ai-model-compare/data/personal-choices.json"
BRANDS = {"anth", "oai", "gemini"}

GEMINI_MODELS = {
    model["id"]: {"name": model["model"], "efforts": tuple(model["efforts"]),
                  "default_effort": model["defaultEffort"], "use_cases": tuple(model["useCases"])}
    for model in _CATALOG["models"]
}


def _pair(choice):
    pair = (choice.get("label", choice["model"]), choice["effort"])
    if not all(isinstance(value, str) and value for value in pair):
        raise ValueError("model and effort must be text")
    return pair


def _parse(personal):
    """(daily, roles, excluded Gemini picks), validated."""
    daily = {choice["provider"]: _pair(choice) for choice in personal["daily"]}
    if not {"claude", "codex", "gemini"}.issubset(daily):
        raise ValueError("daily choices need claude, codex and gemini")
    roles = []
    for role in personal["roles"].values():
        models = {brand: tuple(choice) for brand, choice in role["models"].items()}
        if set(models) != BRANDS or not all(len(c) == 2 and all(isinstance(v, str) for v in c)
                                            for c in models.values()):
            raise ValueError("every role needs anth, oai and gemini model/effort")
        if not isinstance(role["role"], str) or not isinstance(role["description"], str):
            raise ValueError("every role needs a name and description key")
        roles.append({**role, "models": models})
    if not {"Reviewer", "Security"}.issubset({role["role"] for role in roles}):
        raise ValueError("roles need Reviewer and Security")
    return daily, roles, set(personal["excludedGeminiPicks"])


DAILY_CHOICES, ROLE_ASSIGNMENTS, EXCLUDED_GEMINI_PICKS = _parse(
    json.loads((_DATA / "personal-choices.json").read_text(encoding="utf-8")))


def refresh_live(timeout=3):
    """Use the published choices when they load and validate; True when they did."""
    try:
        request = urllib.request.Request(LIVE_URL, headers={"User-Agent": "ai-usage"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            daily, roles, excluded = _parse(json.loads(response.read().decode("utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    DAILY_CHOICES.clear()
    DAILY_CHOICES.update(daily)
    ROLE_ASSIGNMENTS[:] = roles
    EXCLUDED_GEMINI_PICKS.clear()
    EXCLUDED_GEMINI_PICKS.update(excluded)
    return True

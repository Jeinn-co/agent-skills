"""Load the bundled model facts and personal display choices; no network I/O."""
from pathlib import Path
import json

_DATA = Path(__file__).with_name("data")
_CATALOG = json.loads((_DATA / "gemini-models.json").read_text(encoding="utf-8"))
_PERSONAL = json.loads((_DATA / "personal-choices.json").read_text(encoding="utf-8"))

GEMINI_MODELS = {
    model["id"]: {"name": model["model"], "efforts": tuple(model["efforts"]),
                  "default_effort": model["defaultEffort"], "use_cases": tuple(model["useCases"])}
    for model in _CATALOG["models"]
}
DAILY_CHOICES = {choice["provider"]: (choice.get("label", choice["model"]), choice["effort"])
                 for choice in _PERSONAL["daily"]}
ROLE_ASSIGNMENTS = tuple(
    {**role, "models": {provider: tuple(choice) for provider, choice in role["models"].items()}}
    for role in _PERSONAL["roles"].values()
)
EXCLUDED_GEMINI_PICKS = set(_PERSONAL["excludedGeminiPicks"])
OPTIONAL_GEMINI_EFFORT = _PERSONAL["optionalGeminiEffort"]

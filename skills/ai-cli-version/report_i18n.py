"""Canonical report resources; distributed by scripts/sync_shared.py."""
import json
import re
from pathlib import Path


class ReportI18n:
    def __init__(self, folder, storage_key):
        self.folder = Path(folder)
        self.storage_key = storage_key
        self.resources = {}
        for language, filename in (("en", "en.json"), ("zh", "zh-TW.json")):
            common = json.loads((self.folder / "locales/common" / filename).read_text(encoding="utf-8"))
            local = json.loads((self.folder / "locales" / filename).read_text(encoding="utf-8"))
            self.resources[language] = {**common, **local}

    def text(self, key, language="en", **values):
        """Values are already escaped when the destination is HTML."""
        message = self.resources[language].get(key, self.resources["en"].get(key))
        if message is None:
            raise KeyError("Unknown translation: " + key)
        return re.sub(r"\{\{(\w+)\}\}", lambda match: str(values[match[1]]), message)

    @staticmethod
    def pair(en, zh):
        """Render bilingual HTML data, such as personal role descriptions."""
        return '<span class="l-en">%s</span><span class="l-zh">%s</span>' % (en, zh)

    def bi(self, key, **values):
        return self.pair(self.text(key, "en", **values), self.text(key, "zh", **values))

    def template(self, page):
        return re.sub(r"@@i18n_([a-z0-9_]+)@@", lambda match: self.bi(match[1]), page)

    @property
    def language_button(self):
        return '<button type="button" class="lang" id="lang">%s</button>' % self.text("language_target")

    @property
    def globe(self):
        return (self.folder / "assets/globe.svg").read_text(encoding="utf-8").strip()

    def toolbar(self, extra_buttons=""):
        markup = (self.folder / "assets/report-toolbar.html").read_text(encoding="utf-8")
        markup = markup.replace("@@globe@@", self.globe).replace("@@extra_buttons@@", extra_buttons)
        return re.sub(r"@@(\w+)@@", lambda match: self.text(match[1]), markup)

    def head(self):
        library = (self.folder / "assets/i18next.min.js").read_text(encoding="utf-8")
        runtime = (self.folder / "assets/report-language.js").read_text(encoding="utf-8")
        resources = {language: {"translation": messages} for language, messages in self.resources.items()}
        payload = json.dumps({"storageKey": self.storage_key, "resources": resources}, ensure_ascii=False).replace("<", "\\u003c")
        return library + "\n;window.reportLocale = " + payload + ";\n" + runtime

    def language_script(self):
        return (self.folder / "assets/language-button.js").read_text(encoding="utf-8")

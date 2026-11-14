"""Distribute canonical resources so each skill installs without sibling folders."""
from pathlib import Path
import argparse
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ("ai-usage", "ai-cli-version")


def sync(compare_dir=None):
    if compare_dir is not None:
        compare_dir = Path(compare_dir).resolve()
        package = json.loads((compare_dir / 'package.json').read_text(encoding='utf-8'))
        if package.get('name') != 'ai-model-compare':
            raise ValueError('--compare-dir must identify the ai-model-compare repository')
    for name in REPORTS:
        target = ROOT / "skills" / name
        files = {
            "report_i18n.py": "report_i18n.py",
            "report-language.js": "assets/report-language.js",
            "language-button.js": "assets/language-button.js",
            "globe.svg": "assets/globe.svg",
            "report-toolbar.html": "assets/report-toolbar.html",
            "vendor/i18next.min.js": "assets/i18next.min.js",
            "vendor/i18next.LICENSE": "assets/i18next.LICENSE",
            "locales/en.json": "locales/common/en.json",
            "locales/zh-TW.json": "locales/common/zh-TW.json",
            "logos.json": "data/logos.json",
        }
        for source, destination in files.items():
            destination = target / destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "shared" / source, destination)
    for name in (*REPORTS, 's-agent'):
        for resource in ('skill_runtime.py', 'skill_update.py'):
            shutil.copyfile(ROOT / 'shared' / resource, ROOT / 'skills' / name / resource)
    for name in ("ai-usage", "s-agent"):
        target = ROOT / "skills" / name / "data/gemini-models.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "shared/gemini-models.json", target)
    shutil.copyfile(ROOT / 'shared/personal-choices.json', ROOT / 'skills/ai-usage/data/personal-choices.json')
    if compare_dir is not None:
        target = compare_dir / 'public/data'
        target.mkdir(parents=True, exist_ok=True)
        for name in ('gemini-models.json', 'personal-choices.json'):
            shutil.copyfile(ROOT / 'shared' / name, target / name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare-dir', help='Also distribute model facts and personal choices to ai-model-compare')
    sync(parser.parse_args().compare_dir)

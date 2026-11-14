"""Report localization and standalone packaging; no provider APIs or browser sessions."""
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shared_report_i18n", ROOT / "shared/report_i18n.py")
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)
runtime_spec = importlib.util.spec_from_file_location("shared_skill_runtime", ROOT / "shared/skill_runtime.py")
runtime = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime)


class ReportResourcesTests(unittest.TestCase):
    def test_version_only_comes_from_skill_frontmatter_metadata(self):
        self.assertEqual(runtime.metadata_version(
            '---\r\nname: report\r\nmetadata:\r\n  author: Example\r\n  version: "9.8.7"\r\n---\r\n'), '9.8.7')
        for text in (
            '---\nname: report\n---\nmetadata:\n  version: "9.8.7"\n',
            '---\nversion: "9.8.7"\n---\n',
            '---\nother:\n  version: "9.8.7"\nmetadata:\n  author: Example\n---\n',
            '---\nmetadata:\n  version: "next"\n---\n',
        ):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'metadata.version'):
                runtime.metadata_version(text)

    def test_changing_only_metadata_updates_cli_and_report_versions(self):
        for skill, head in (("ai-usage", "run.head()"),
                            ("ai-cli-version", "run.head_lines([])")):
            with self.subTest(skill=skill), tempfile.TemporaryDirectory() as folder:
                installed = Path(folder) / skill
                shutil.copytree(ROOT / 'skills' / skill, installed,
                                ignore=shutil.ignore_patterns('__pycache__'))
                metadata = installed / 'SKILL.md'
                metadata.write_text(re.sub(r'(^  version: )"[^"]+"', r'\g<1>"9.8.7"',
                                           metadata.read_text(encoding='utf-8'), count=1, flags=re.M),
                                    encoding='utf-8')
                for args, expected in (
                    (['run.py', '--version'], '9.8.7'),
                    (['-c', 'import run,html_report; print(html_report.render(' + head + '))'],
                     skill + ' 9.8.7'),
                ):
                    result = subprocess.run([sys.executable, *args], cwd=installed,
                                            env={**os.environ, 'PYTHONPATH': ''}, text=True,
                                            capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(expected, result.stdout)

    def test_translation_fallback_and_literal_interpolation(self):
        catalog = resources.ReportI18n(ROOT / "skills/ai-usage", "test-language")
        catalog.resources["en"]["fixture"] = "{{value}} left"
        self.assertEqual(catalog.text("fixture", "zh", value="{{other}}"), "{{other}} left")
        with self.assertRaisesRegex(KeyError, "Unknown translation"):
            catalog.text("missing_translation")

    def test_distributed_resources_match_their_canonical_sources(self):
        for skill in ("ai-usage", "ai-cli-version"):
            for canonical, installed in (
                ("report_i18n.py", "report_i18n.py"),
                ("skill_runtime.py", "skill_runtime.py"),
                ("report-language.js", "assets/report-language.js"),
                ("language-button.js", "assets/language-button.js"),
                ("report-toolbar.html", "assets/report-toolbar.html"),
                ("logos.json", "data/logos.json"),
                ("locales/en.json", "locales/common/en.json"),
                ("locales/zh-TW.json", "locales/common/zh-TW.json"),
                ("vendor/i18next.min.js", "assets/i18next.min.js"),
                ("vendor/i18next.LICENSE", "assets/i18next.LICENSE"),
            ):
                with self.subTest(skill=skill, resource=canonical):
                    self.assertEqual((ROOT / "shared" / canonical).read_bytes(),
                                     (ROOT / "skills" / skill / installed).read_bytes())
        for skill in ('ai-usage', 'ai-cli-version', 's-agent'):
            for helper in ('skill_runtime.py', 'skill_update.py'):
                self.assertEqual((ROOT / 'shared' / helper).read_bytes(),
                                 (ROOT / 'skills' / skill / helper).read_bytes())
        for skill in ("ai-usage", "s-agent"):
            self.assertEqual((ROOT / "shared/gemini-models.json").read_bytes(),
                             (ROOT / "skills" / skill / "data/gemini-models.json").read_bytes())
        self.assertEqual((ROOT / 'shared/personal-choices.json').read_bytes(),
                         (ROOT / 'skills/ai-usage/data/personal-choices.json').read_bytes())

    def test_each_report_renders_from_an_independent_installation(self):
        for skill, value, expected in (("ai-usage", "''", "我的用法"),
                                       ("ai-cli-version", "[]", "已安裝")):
            with self.subTest(skill=skill), tempfile.TemporaryDirectory() as folder:
                installed = Path(folder) / skill
                shutil.copytree(ROOT / "skills" / skill, installed, ignore=shutil.ignore_patterns("__pycache__"))
                result = subprocess.run(
                    [sys.executable, "-c", "import html_report; print(html_report.render(" + value + "))"],
                    cwd=installed, env={**os.environ, "PYTHONPATH": ""}, text=True,
                    capture_output=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertIn("i18next", result.stdout)
                self.assertNotIn("@@i18n_", result.stdout)

    def test_same_version_with_changed_assets_has_a_new_server_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            installed = Path(folder)
            (installed / 'assets').mkdir()
            script = installed / 'assets/report.js'
            script.write_text('original')
            before = runtime.server_identity('report', '1.0', installed)
            (installed / 'README.md').write_text('Documentation-only change')
            self.assertEqual(runtime.server_identity('report', '1.0', installed), before)
            script.write_text('changed')
            after = runtime.server_identity('report', '1.0', installed)
            self.assertNotEqual(after, before)
            self.assertTrue(runtime.server_owned_by(before, installed))
            self.assertTrue(runtime.server_owned_by(after, installed))
            legacy = ('report 0.9 ' + str(installed.resolve())).encode()
            self.assertTrue(runtime.server_owned_by(legacy, installed))
            self.assertFalse(runtime.server_owned_by(after, installed / 'other-copy'))
            self.assertFalse(runtime.server_owned_by(b'', installed))


if __name__ == "__main__":
    unittest.main()

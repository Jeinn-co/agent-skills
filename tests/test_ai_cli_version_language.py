import importlib.util
import unittest
from pathlib import Path


class LanguageTests(unittest.TestCase):
    def test_bilingual_rows_keep_diagnostics_escaped(self):
        path = Path(__file__).resolve().parents[1] / "skills/ai-cli-version/html_report.py"
        spec = importlib.util.spec_from_file_location("version_html", path)
        report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(report)
        page = report.render([
            "### ai-cli-version 1.15.1",
            "codex\tinstalled=1\tlatest=2\tstatus=update available",
            "claude\tnot installed",
            "grok\tfailed <script>alert(1)</script>",
        ])
        self.assertIn('class="l-zh">可更新</span>', page)
        self.assertIn('class="l-en">update</span>', page)
        self.assertIn('class="l-zh">未安裝</span>', page)
        self.assertIn('ai-cli-version-lang', page)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', page)
        self.assertNotIn('<script>alert(1)</script>', page)

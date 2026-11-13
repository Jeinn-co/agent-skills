"""Regression for the model choices users see in the rendered daily-use guide."""
import unittest
import contextlib
import io
import copy
from unittest.mock import patch

import runpy
import tempfile
from pathlib import Path

import html_report
import cursorbench


class UsageGuidanceTests(unittest.TestCase):
    def test_my_usage_paragraph_lists_my_choices(self):
        page = html_report.render("")
        self.assertIn('Claude Code mainly Opus 5.5 / high', page)
        self.assertIn('Codex GPT-6.1-Sol / high', page)
        self.assertIn('Claude Code 主要用 Opus 5.5 / high', page)

    def test_qualified_claude_pick_never_uses_fable(self):
        rows = [
            {'model': 'Fable 5.2', 'effort': 'Low', 'score': 54, 'cost': 1},
            {'model': 'Fable 5.2', 'effort': 'Medium', 'score': 57, 'cost': 3},
            {'model': 'Fable 5.2', 'effort': 'High', 'score': 60, 'cost': 4},
            {'model': 'Opus 5.5', 'effort': 'Low', 'score': 48, 'cost': 1},
        ]
        self.assertEqual(cursorbench.pick(rows, 'claude')[0], 'Opus 5.5 Low')
        rows[-1]['score'] = 51
        self.assertEqual(cursorbench.pick(rows, 'claude')[0], 'Opus 5.5 Low')

    def test_hydrogen_all_levels_and_missing_benchmarks(self):
        self.assertEqual(cursorbench.GEMINI_EFFORTS['gemini-4-hydrogen'],
                         ('low', 'medium', 'high', 'xhigh'))
        self.assertEqual(cursorbench.name('agy', 'gemini/gemini-4-hydrogen'), 'Gemini 4 Hydrogen')
        # Empty and null-score source rows must never invent an AA score or a pick.
        for rows in ([], [{'model': 'Gemini 4 Hydrogen', 'effort': 'High', 'score': None, 'cost': None}]):
            with patch.object(cursorbench, 'published', return_value=rows):
                self.assertEqual(cursorbench.aa_rows('Gemini 4 Hydrogen'), {})
                self.assertIsNone(cursorbench.pick(rows, 'agy'))
                for effort in cursorbench.GEMINI_EFFORTS['gemini-4-hydrogen']:
                    output = io.StringIO()
                    with patch('sys.argv', ['cursorbench.py', f'agy=gemini-4-hydrogen:{effort}']), contextlib.redirect_stdout(output):
                        self.assertEqual(cursorbench.main(), 0)
                    self.assertIn(f'Gemini 4 Hydrogen  {effort}  not listed', output.getvalue())
                    page = html_report.render('### GEMINI\nmodel   gemini-4-hydrogen\neffort  ' + effort + '\n' + output.getvalue())
                    self.assertIn('gemini-4-hydrogen', page)

    def test_hydrogen_effort_labels_and_known_gemini_constraints(self):
        with tempfile.TemporaryDirectory() as folder, patch('pathlib.Path.home', return_value=Path(folder)), \
                patch('sys.argv', ['session_info.py', 'agy']), contextlib.redirect_stdout(io.StringIO()):
            parse_model = runpy.run_path(str(Path(__file__).with_name('session_info.py')))['agy_model_id']
        for effort, label in (('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('xhigh', 'Extra High')):
            self.assertEqual(parse_model(f'Gemini 4 Hydrogen ({label})'),
                             ('gemini-4-hydrogen', effort))
        row = {'model': 'Gemini 4 Carbon', 'effort': 'Extra High', 'score': 1, 'cost': 1}
        with patch.object(cursorbench, 'published', return_value=[row]):
            self.assertEqual(cursorbench.aa_rows('Gemini 4 Carbon'), {})
            self.assertIsNone(cursorbench.pick([row], 'agy'))
        page = html_report.render('')
        self.assertIn('Gemini 4 Hydrogen / high', page)
        self.assertIn('2026-11-18', page)

    def test_role_and_model_data_changes_render_without_template_edits(self):
        roles = copy.deepcopy(html_report.ROLE_ASSIGNMENTS)
        executor = next(role for role in roles if role['role'] == 'Executor')
        executor['models']['gemini'] = ('Gemini Fixture <script>', 'xhigh')
        executor['gemini_note'] = ('Condition <script>', '條件 <script>')
        fixture = {'name': 'Gemini Fixture', 'efforts': ('high', 'xhigh'),
                   'default_effort': 'high', 'use_cases': ('Fixture task', '測試任務')}
        with patch.object(html_report, 'ROLE_ASSIGNMENTS', roles), \
                patch.dict(html_report.GEMINI_MODELS, {'gemini-fixture': fixture}):
            page = html_report.render('')
        self.assertIn('Gemini Fixture &lt;script&gt; / xhigh', page)
        self.assertIn('Condition &lt;script&gt;', page)
        self.assertIn('Gemini Fixture: high (official default) / xhigh', page)
        self.assertIn('high (official default) / xhigh', page)
        self.assertNotIn('@@roles@@', page)

    def test_personal_gemini_policy_excludes_argon_but_keeps_security_carbon(self):
        # Synthetic benchmark rows: even an attractive Argon result is not a personal pick.
        argon = {'model': 'Gemini 4 Argon', 'effort': 'High', 'score': 99, 'cost': 0.01}
        hydrogen = {'model': 'Gemini 4 Hydrogen', 'effort': 'High', 'score': 51, 'cost': 1}
        self.assertEqual(cursorbench.pick([argon, hydrogen], 'agy')[0], 'Gemini 4 Hydrogen High')
        self.assertIsNone(cursorbench.pick([argon], 'agy'))
        for role in html_report.ROLE_ASSIGNMENTS:
            expected = 'Gemini 4 Carbon' if role['role'] == 'Security' else 'Gemini 4 Hydrogen'
            effort = 'high'
            self.assertEqual(role['models']['gemini'], (expected, effort))
        page = html_report.render('')
        self.assertNotIn('本機選型草案', page)
        self.assertNotIn('尚未同步 Notion', page)
        self.assertIn('high 仍無法釐清跨模組限制或相依關係時，升 xhigh', page)
        self.assertIn('安全及權限風險交由 Carbon / high', page)

    def test_only_fable_has_no_qualified_pick(self):
        rows = [{'model': 'Fable 5.2', 'effort': 'High', 'score': 60, 'cost': 4}]
        self.assertIsNone(cursorbench.pick(rows, 'claude'))


if __name__ == '__main__':
    unittest.main()

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


class LiveChoicesTests(unittest.TestCase):
    """refresh_live swaps in the published Notion choices only when they validate."""

    def setUp(self):
        import guidance_data
        self.data = guidance_data
        saved = (dict(guidance_data.DAILY_CHOICES), list(guidance_data.ROLE_ASSIGNMENTS),
                 set(guidance_data.EXCLUDED_GEMINI_PICKS))

        def restore():
            daily, roles, excluded = saved
            guidance_data.DAILY_CHOICES.clear(); guidance_data.DAILY_CHOICES.update(daily)
            guidance_data.ROLE_ASSIGNMENTS[:] = roles
            guidance_data.EXCLUDED_GEMINI_PICKS.clear(); guidance_data.EXCLUDED_GEMINI_PICKS.update(excluded)
        self.addCleanup(restore)

    def serve(self, body):
        response = io.BytesIO(body.encode('utf-8'))
        return patch('urllib.request.urlopen', return_value=contextlib.nullcontext(response))

    def test_valid_published_choices_replace_the_bundled_ones_in_the_report(self):
        import json
        live = json.loads((Path(self.data.__file__).with_name('data') / 'personal-choices.json').read_text(encoding='utf-8'))
        live['daily'][1] = {'provider': 'codex', 'model': 'GPT-9 Sol', 'effort': 'low'}
        with self.serve(json.dumps(live)):
            self.assertTrue(self.data.refresh_live())
        page = html_report.render('')
        self.assertIn('Codex GPT-9 Sol / low.', page)
        self.assertNotIn('CLI defaults', page)

    def test_invalid_or_unreachable_choices_keep_the_bundled_ones(self):
        before = dict(self.data.DAILY_CHOICES)
        with self.serve('{"daily": [{"provider": "codex", "model": "x", "effort": "low"}]}'):
            self.assertFalse(self.data.refresh_live())
        with patch('urllib.request.urlopen', side_effect=OSError('offline')):
            self.assertFalse(self.data.refresh_live())
        self.assertEqual(self.data.DAILY_CHOICES, before)


class UsageGuidanceTests(unittest.TestCase):
    def test_now_line_shows_model_and_bold_effort_without_age(self):
        card = html_report.card_html(
            '### CLAUDE\nsession local (6h34m ago)\nmodel claude-opus-5-5\neffort high\n')
        self.assertIn('<code>claude-opus-5-5</code> / <strong>high</strong>', card)
        self.assertNotIn('6h34m', card)
        self.assertNotIn(' · effort ', card)

    def test_my_usage_paragraph_keeps_daily_choices_separate_from_roles(self):
        page = html_report.render("")
        usage = page.split('<h2><span class="l-en">My usage</span>', 1)[1].split('</section>', 1)[0]
        self.assertIn('Claude Code mainly Opus 5.5 / high', usage)
        self.assertIn('Codex GPT-6.2-Sol / high', usage)
        self.assertIn('Claude Code 主要用 Opus 5.5 / high', usage)
        self.assertIn('Codex GPT-6.2-Sol / high.<br>Gemini uses Gemini 4 Hydrogen / high.', usage)
        self.assertIn('Codex 用 GPT-6.2-Sol / high。<br>Gemini 用 Gemini 4 Hydrogen / high。', usage)
        self.assertNotIn('xhigh', usage)

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
            with patch.object(cursorbench, 'published', return_value=rows), \
                    patch.object(cursorbench.guidance_data, 'refresh_live', return_value=False):
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

    def test_daily_choices_and_roles_render_without_template_edits(self):
        roles = copy.deepcopy(html_report.ROLE_ASSIGNMENTS)
        executor = next(role for role in roles if role['role'] == 'Executor')
        executor['models']['gemini'] = ('Gemini Fixture <script>', 'xhigh')
        choices = {
            'claude': ('Claude Fixture <script>', 'low'),
            'codex': ('Codex Fixture', 'medium'),
            'gemini': ('Gemini Fixture', 'xhigh'),
        }
        with patch.object(html_report, 'ROLE_ASSIGNMENTS', roles), \
                patch.object(html_report, 'DAILY_CHOICES', choices):
            page = html_report.render('')
        self.assertIn('Gemini Fixture &lt;script&gt; / xhigh', page)
        for text in (
            'Claude Code mainly Claude Fixture &lt;script&gt; / low.',
            'Claude Code 主要用 Claude Fixture &lt;script&gt; / low。',
            'Codex Codex Fixture / medium.',
            'Codex 用 Codex Fixture / medium。',
            'Gemini uses Gemini Fixture / xhigh.',
            'Gemini 用 Gemini Fixture / xhigh。',
        ):
            with self.subTest(text=text):
                self.assertIn(text, page)
        self.assertNotIn('@@daily_', page)
        self.assertNotIn('@@roles@@', page)

    def test_personal_gemini_policy_excludes_argon_but_keeps_security_carbon(self):
        # Synthetic benchmark rows: even an attractive Argon result is not a personal pick.
        argon = {'model': 'Gemini 4 Argon', 'effort': 'High', 'score': 99, 'cost': 0.01}
        hydrogen = {'model': 'Gemini 4 Hydrogen', 'effort': 'High', 'score': 51, 'cost': 1}
        self.assertEqual(cursorbench.pick([argon, hydrogen], 'agy')[0], 'Gemini 4 Hydrogen High')
        self.assertIsNone(cursorbench.pick([argon], 'agy'))
        # Displayed Gemini roles follow My usage roleOverrides, not s-agent's Argon dispatch.
        for role in html_report.ROLE_ASSIGNMENTS:
            expected = 'Gemini 4 Neon'
            effort = {'Designer': 'medium', 'Executor': 'low', 'DevOps': 'medium', 'Security': 'xhigh'}.get(role['role'], 'high')
            self.assertEqual(role['models']['gemini'], (expected, effort))
        page = html_report.render('')
        self.assertNotIn('本機選型草案', page)
        self.assertNotIn('尚未同步 Notion', page)
        choice, roles = page.split('<h2><span class="l-en">Delegated roles</span>', 1)
        self.assertNotIn('安全工作使用 Carbon / high', choice)
        self.assertIn('Gemini selection', roles)
        self.assertIn('Gemini 選型', roles)
        self.assertEqual(page.count('日常工作使用 Gemini 4 Neon / medium。安全工作使用 Gemini 4 Neon / xhigh，以安全性與正確性優先。因成本排除 Gemini 4 Argon。'), 1)
        self.assertIn('日常工作使用 Gemini 4 Neon / medium', roles.split('<table', 1)[0])
        self.assertNotIn('Upgrade to xhigh', roles)
        self.assertEqual(roles.count('<td class="gemini">Gemini 4 Neon / high</td>'), 2)
        self.assertEqual(roles.count('<td class="gemini">Gemini 4 Neon / medium</td>'), 2)
        self.assertEqual(roles.count('<td class="gemini">Gemini 4 Neon / low</td>'), 1)
        self.assertEqual(roles.count('<td class="gemini">Gemini 4 Neon / xhigh</td>'), 1)

    def test_only_fable_has_no_qualified_pick(self):
        rows = [{'model': 'Fable 5.2', 'effort': 'High', 'score': 60, 'cost': 4}]
        self.assertIsNone(cursorbench.pick(rows, 'claude'))


if __name__ == '__main__':
    unittest.main()

"""Regression for the model choices users see in the rendered daily-use guide."""
import unittest

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

    def test_only_fable_has_no_qualified_pick(self):
        rows = [{'model': 'Fable 5.2', 'effort': 'High', 'score': 60, 'cost': 4}]
        self.assertIsNone(cursorbench.pick(rows, 'claude'))


if __name__ == '__main__':
    unittest.main()

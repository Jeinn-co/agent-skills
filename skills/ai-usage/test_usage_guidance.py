"""Regression for the model choices users see in the rendered daily-use guide."""
import html
import re
import unittest

import html_report
import cursorbench


class UsageGuidanceTests(unittest.TestCase):
    def test_claude_daily_and_hard_tasks_use_distinct_models(self):
        page = html_report.render("")
        row = re.search(r'<tr class="anth"><td>Claude Code</td>(.*?)</tr>', page).group(1)
        daily, harder, special = [html.unescape(re.sub(r'<[^>]+>', '', cell))
                                  for cell in re.findall(r'<td>(.*?)</td>', row)]
        self.assertIn('Opus 5.5 / low', daily)
        self.assertIn('Opus 5.5 / medium', daily)
        self.assertNotIn('Fable', daily)
        self.assertIn('Fable 5.2 / medium', harder)
        self.assertIn('Fable 5.2 / high', harder)

    def test_qualified_claude_pick_respects_task_routing(self):
        rows = [
            {'model': 'Fable 5.2', 'effort': 'Low', 'score': 54, 'cost': 1},
            {'model': 'Fable 5.2', 'effort': 'Medium', 'score': 57, 'cost': 3},
            {'model': 'Fable 5.2', 'effort': 'High', 'score': 60, 'cost': 4},
            {'model': 'Opus 5.5', 'effort': 'Low', 'score': 48, 'cost': 1},
        ]
        self.assertEqual(cursorbench.pick(rows, 'claude')[0], 'Fable 5.2 Medium')
        rows[-1]['score'] = 51
        self.assertEqual(cursorbench.pick(rows, 'claude')[0], 'Opus 5.5 Low')

    def test_only_fable_low_has_no_qualified_pick(self):
        rows = [{'model': 'Fable 5.2', 'effort': 'Low', 'score': 54, 'cost': 1}]
        self.assertIsNone(cursorbench.pick(rows, 'claude'))


if __name__ == '__main__':
    unittest.main()

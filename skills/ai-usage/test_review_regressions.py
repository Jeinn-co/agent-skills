"""Isolated deadline and timestamp regressions; no live CLI/auth/network calls."""
import ast
import contextlib
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

import html_report
import limit_resets
import portable
import claude_browser

HERE = Path(__file__).parent


def launcher_function(name, namespace):
    node = next(n for n in ast.parse((HERE / 'run.py').read_text()).body
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'run.py', 'exec'), namespace)
    return namespace[name]


class DeadlineTests(unittest.TestCase):
    def test_real_child_timeout_keeps_completed_quota(self):
        # Any stall after complete quota lines (here: a hung exit) must keep those lines.
        child = '''import time
print('plan: pro')
print('5h      12.0% used  bar x')
print('week    78.0% used  bar x', flush=True)
time.sleep(3)
'''
        real = portable.run_bounded
        captured = []
        def child_process(args, **kwargs):
            try:
                return real([sys.executable, '-u', '-c', child], cwd=HERE, **kwargs)
            except subprocess.TimeoutExpired as error:
                captured.append(error.output)
                raise
        usage = launcher_function('usage', {'portable': portable, 'sys': sys, 'HERE': HERE,
                                           'subprocess': subprocess, 'child_env': lambda timeout: dict(os.environ)})
        with patch('portable.run_bounded', side_effect=child_process):
            result = usage('claude_usage.py', timeout=.7)
        self.assertTrue(captured, 'test must reach the real outer timeout')
        self.assertIn('12.0% used', result)
        self.assertIn('78.0% used', result)
        self.assertIn('Limit resets: unavailable', result)
        self.assertNotIn('data-timeout', html_report.card_html('### CLAUDE\n' + result))

    def test_timeout_rejects_invalid_or_unfinished_windows(self):
        usage = launcher_function('usage', {'portable': portable, 'sys': sys, 'HERE': HERE,
                                           'subprocess': subprocess, 'child_env': lambda timeout: {}})
        for text in ('plan: pro\n5h 999% used bar x\n', 'plan: pro\n5h 12% used bar x'):
            with patch('portable.run_bounded', side_effect=subprocess.TimeoutExpired([], 20, output=text)):
                self.assertNotIn('plan: pro', usage('claude_usage.py'))
        with patch('portable.run_bounded', side_effect=subprocess.TimeoutExpired([], 20,
                   output='plan: pro\n5h <1% used bar x\n')):
            self.assertIn('5h <1% used', usage('claude_usage.py'))

    def test_reset_requests_use_only_remaining_deadline(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.StringIO(json.dumps({
            'cedar_ember': {'eligible': False, 'ineligible_reason': 'no_grant', 'grants': []}}))
        with patch.dict(os.environ, {'CLAUDE_CODE_OAUTH_TOKEN': 'fake-secret'}), \
                patch('time.monotonic', return_value=100), \
                patch('urllib.request.build_opener', return_value=opener):
            lines = limit_resets.claude_report('2.1.318', deadline=100.25)
        self.assertIn('0 available', lines[0])
        self.assertLessEqual(opener.open.call_args.kwargs['timeout'], .25)
        with patch('time.monotonic', return_value=101), \
                patch('urllib.request.build_opener') as network:
            lines = limit_resets.claude_report('2.1.318', deadline=100)
        self.assertIn('timed out', lines[0])
        network.assert_not_called()

    def test_keychain_time_reduces_http_budget(self):
        clock = [100.0]
        def keychain(*args, **kwargs):
            self.assertEqual(kwargs['timeout'], 3)
            clock[0] += 2.5
            return subprocess.CompletedProcess([], 0, stdout=json.dumps({
                'claudeAiOauth': {'accessToken': 'fake-secret'}}))
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.StringIO(json.dumps({
            'cedar_ember': {'eligible': False, 'ineligible_reason': 'no_grant', 'grants': []}}))
        with patch.dict(os.environ, {'CLAUDE_CODE_OAUTH_TOKEN': ''}), \
                patch('limit_resets.sys.platform', 'darwin'), patch('time.monotonic', side_effect=lambda: clock[0]), \
                patch('subprocess.run', side_effect=keychain), \
                patch('urllib.request.build_opener', return_value=opener):
            with patch.dict(os.environ):
                os.environ.pop('CLAUDE_CONFIG_DIR', None)
                lines = limit_resets.claude_report('2.1.318', deadline=104)
        self.assertIn('0 available', lines[0])
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 1.5)

    def test_cli_calls_share_a_deadline_and_fallback_keeps_oauth_reason(self):
        clock = [100.0]
        timeouts = []
        def reply(args, **kwargs):
            timeouts.append(kwargs['timeout'])
            clock[0] += 7
            if args[1:] == ['--version']:
                text = '2.1.318 (Claude Code)'
            elif args[1:] == ['auth', 'status']:
                text = json.dumps({'loggedIn': True, 'subscriptionType': 'pro'})
            else:
                text = json.dumps({'result': 'Current session: 12% used\nCurrent week (all models): 78% used'})
            return subprocess.CompletedProcess(args, 0, stdout=text)
        out = io.StringIO()
        with patch('portable.CALL_TIMEOUT', 21), patch('time.monotonic', side_effect=lambda: clock[0]), \
                patch('portable.argv', side_effect=lambda name,*args:[name,*args]), \
                patch('subprocess.run', side_effect=reply), patch('claude_browser.current_report', return_value=None), \
                patch('limit_resets.fetch_claude', side_effect=TimeoutError()), contextlib.redirect_stdout(out):
            runpy.run_path(str(HERE / 'claude_usage.py'))
        self.assertEqual(len(timeouts), 3)
        self.assertTrue(timeouts[0] > timeouts[1] > timeouts[2], timeouts)
        self.assertIn('12.0% used', out.getvalue())
        self.assertIn('Limit resets: unavailable (timed out)', out.getvalue())


class ExpiryMetadataTests(unittest.TestCase):
    def lines(self, stamp):
        return limit_resets.codex_lines({'availableCount': 1, 'credits': [
            {'status': 'available', 'expiresAt': stamp.isoformat()}]}, stamp-dt.timedelta(days=1))

    def epoch(self, page):
        return int(re.search(r'data-reset-expires="(\d+)"', page).group(1))

    @unittest.skipUnless(hasattr(time, 'tzset'), 'POSIX timezone fixture')
    def test_dst_fold_keeps_original_epoch(self):
        stamp = dt.datetime(2026, 11, 1, 6, 30, tzinfo=dt.timezone.utc)
        try:
            with patch.dict(os.environ, {'TZ': 'America/New_York', 'AI_USAGE_METADATA': '1'}), \
                    patch('portable.report_timezone', return_value=None):
                time.tzset()
                page = html_report.render('### CHATGPT\n' + '\n'.join(self.lines(stamp)))
                self.assertIn('2026-11-01 01:30', page)
                self.assertEqual(self.epoch(page), int(stamp.timestamp()*1000))
        finally:
            time.tzset()

    def test_seconds_and_both_provider_metadata_paths(self):
        stamp = dt.datetime(2026, 12, 1, 3, 22, 47, 123000, tzinfo=dt.timezone.utc)
        with patch.dict(os.environ, {'AI_USAGE_METADATA': '1'}):
            codex = self.lines(stamp)
            claude = limit_resets.claude_lines({'eligible': True, 'grants': [
                {'resets_left': 1, 'ends_at': stamp.isoformat()}]}, stamp-dt.timedelta(days=1))
        for provider, lines in (('CHATGPT', codex), ('CLAUDE', claude)):
            raw = '### ' + provider + '\n' + '\n'.join(lines)
            self.assertEqual(self.epoch(html_report.render(raw)), int(stamp.timestamp()*1000))
            self.assertNotIn('reset-expiry', html_report.render(raw))
            self.assertEqual(self.epoch(html_report.card_html(raw)), int(stamp.timestamp()*1000))

    def test_equal_display_notes_keep_distinct_grant_seconds(self):
        stamp = dt.datetime(2026, 12, 1, 3, 22, 9, tzinfo=dt.timezone.utc)
        later = stamp + dt.timedelta(seconds=40)
        with patch.dict(os.environ, {'AI_USAGE_METADATA': '1'}):
            lines = limit_resets.claude_lines({'eligible': True, 'grants': [
                {'resets_left': 1, 'ends_at': stamp.isoformat()},
                {'resets_left': 1, 'ends_at': later.isoformat()}]}, stamp-dt.timedelta(days=1))
        visible = [line for line in lines if line.startswith('Reset (')]
        self.assertEqual(visible[0], visible[1], 'fixture must expose identical display labels')
        page = html_report.render('### CLAUDE\n' + '\n'.join(lines))
        epochs = [int(value) for value in re.findall(r'data-reset-expires="(\d+)"', page)]
        self.assertEqual(epochs, [int(stamp.timestamp()*1000), int(later.timestamp()*1000)])

    def test_legacy_dates_are_static_and_cli_has_no_metadata(self):
        raw = '### CHATGPT\nUsage limit resets: 1 available\nReset 1: expires 2026-11-01 01:30 · 1 hour left'
        self.assertNotIn('data-reset-expires=', html_report.render(raw))
        self.assertIn('expires 2026-11-01 01:30', html_report.render(raw))
        with patch.dict(os.environ, {'AI_USAGE_METADATA': ''}):
            self.assertFalse(any(line.startswith('reset-expiry ') for line in self.lines(dt.datetime.now(dt.timezone.utc))))

    def test_launcher_hides_metadata_but_retains_it_for_html(self):
        child_env = launcher_function('child_env', {'os': os})(20)
        self.assertEqual(child_env['AI_USAGE_METADATA'], '1')
        self.assertEqual(child_env['AI_USAGE_TIMEOUT'], '20')
        raw = 'Reset 1: expires 2026-12-01 03:22 · 1 hour left\nreset-expiry {"note":"Reset 1", "expiresAt":1796066520123}\n'
        visible = io.StringIO(); captured = io.StringIO()
        tee = launcher_function('_Tee', {'_captured': captured, '_real_stdout': visible})()
        tee.write(raw)
        self.assertEqual(captured.getvalue(), raw)
        self.assertNotIn('reset-expiry', visible.getvalue())

    def test_browser_and_finish_merge_keep_the_same_epoch(self):
        stamp = dt.datetime(2026, 12, 1, 3, 22, 47, tzinfo=dt.timezone.utc)
        data = {'sourceUrl': 'https://claude.ai/new#settings/usage',
                'observedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'plan': 'pro',
                'windows': {'5h': {'usedPercent': 0, 'resetsAt': None}},
                'resetCredits': {'availableCount': 1, 'credits': [
                    {'status': 'available', 'expiresAt': stamp.isoformat()}]}}
        with patch.dict(os.environ, {'AI_USAGE_METADATA': '1'}):
            browser_raw = '### CLAUDE\n' + '\n'.join(claude_browser.report(data))
            codex_raw = '### CHATGPT\n' + '\n'.join(self.lines(stamp))
        self.assertEqual(self.epoch(html_report.card_html(browser_raw)), int(stamp.timestamp()*1000))
        raw_file = MagicMock(); raw_file.read_text.return_value = ''
        namespace = {'RAW': raw_file, 'active': lambda: (('CLAUDE', '', ''), ('CHATGPT', '', '')),
                     'head': lambda: '### ai-usage test\n'}
        launcher_function('sections_of', namespace)
        merged = launcher_function('merged', namespace)(browser_raw + '\n' + codex_raw)
        page = html_report.render(merged)
        self.assertEqual(page.count('data-reset-expires="%d"' % int(stamp.timestamp()*1000)), 2)
        self.assertNotIn('reset-expiry', page)

    def test_invalid_metadata_never_becomes_a_visible_note_or_timer(self):
        for value in ('null', '{}', '[]', '{"note": "Reset 1", "expiresAt": true}', 'not-json'):
            page = html_report.render('### CHATGPT\nreset-expiry ' + value)
            self.assertNotIn('reset-expiry', page)
            self.assertNotIn('data-reset-expires=', page)


if __name__ == '__main__':
    unittest.main()

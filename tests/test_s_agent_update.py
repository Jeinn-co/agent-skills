import importlib.util
from pathlib import Path
import unittest
from unittest import mock
import urllib.error

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/s-agent/scripts/check_update.py'
spec = importlib.util.spec_from_file_location('s_agent_update', SCRIPT)
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


def skill(version):
    return f'---\nname: s-agent\nmetadata:\n  version: "{version}"\n---\n'


class UpdateTests(unittest.TestCase):
    def check(self, installed, published=None, error=None):
        with mock.patch.object(update, 'SKILL') as local, \
                mock.patch.object(update.urllib.request, 'urlopen') as request:
            local.read_text.return_value = skill(installed)
            if error:
                request.side_effect = error
            else:
                request.return_value.__enter__.return_value.read.return_value = published.encode()
            result = update.check_skill()
            call = request.call_args
            self.assertEqual(call.args[0].full_url, update.SKILL_URL)
            self.assertFalse(call.args[0].has_header('Authorization'))
            self.assertEqual(call.kwargs['timeout'], 10)
            request.assert_called_once()
        return result

    def test_newer_semantic_version_offers_update(self):
        result = self.check('1.9.0', skill('1.10.0'))
        self.assertIn('installed=1.9.0 latest=1.10.0 status=update available', result)
        self.assertIn('update_cmd=npx -y skills update -g s-agent', result)

    def test_equal_or_older_published_version_never_offers_downgrade(self):
        for published in ['1.2.0', '1.1.9']:
            with self.subTest(published=published):
                self.assertIn('status=up to date', self.check('1.2.0', skill(published)))

    def test_unreachable_github_does_not_block_invocation(self):
        result = self.check('1.2.0', error=urllib.error.URLError('offline'))
        self.assertTrue(result.startswith('skill check failed ('), result)
        self.assertNotIn('status=up to date', result)

    def test_invalid_remote_version_is_not_used(self):
        for published in ['not markdown', skill('next'), skill('1.2')]:
            with self.subTest(published=published):
                self.assertTrue(self.check('1.2.0', published).startswith('skill check failed ('))

    def test_body_version_does_not_replace_missing_metadata(self):
        with self.assertRaises(ValueError):
            update.metadata_version('---\nname: s-agent\n---\n  version: "9.0.0"\n')


if __name__ == '__main__':
    unittest.main()

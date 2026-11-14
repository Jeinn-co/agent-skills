"""Isolated update coverage for all public skills; network responses are fixtures."""
import io
import base64
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared'))
import skill_update as update


def skill(version):
    return f'---\nname: s-agent\nmetadata:\n  version: "{version}"\n---\n'


def published(version):
    return json.dumps({'content': base64.b64encode(skill(version).encode()).decode()}).encode()


class UpdateTests(unittest.TestCase):
    def installed(self, root, name, version='1.0.0'):
        folder = root / name
        folder.mkdir()
        (folder / 'SKILL.md').write_text(skill(version))
        (folder / 'old-marker').write_text('keep on failure')
        return folder

    def archive(self, name, extra=None, incomplete=False):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as bundle:
            prefix = 'agent-skills-main/skills/' + name + '/'
            for file in (ROOT / 'skills' / name).rglob('*'):
                if not file.is_file() or '__pycache__' in file.parts:
                    continue
                if incomplete and file.name == 'skill_update.py':
                    continue
                relative = file.relative_to(ROOT / 'skills' / name).as_posix()
                if relative == 'SKILL.md':
                    body = re.sub(r'(^  version: )"[^"\n]+"', r'\g<1>"9.8.7"',
                                  file.read_text(), count=1, flags=re.M)
                    bundle.writestr(prefix + relative, body)
                else:
                    bundle.write(file, prefix + relative)
            if extra:
                bundle.writestr(prefix + extra, 'unsafe')
        return stream.getvalue()

    def test_all_skills_update_only_the_requested_standalone_copy(self):
        for name in update.SKILLS:
            with self.subTest(skill=name), tempfile.TemporaryDirectory() as work:
                root = Path(work)
                folder = self.installed(root, name)
                settings = root / 'user-settings.json'
                settings.write_text('preserve')
                sibling = self.installed(root, 'another-skill')
                with mock.patch.object(update, '_download', side_effect=[published('9.8.7'), self.archive(name)]):
                    result = update.check_skill_update(name, folder, apply=True)
                self.assertIn('installed=9.8.7 latest=9.8.7 status=updated', result)
                self.assertFalse((folder / 'old-marker').exists())
                self.assertTrue((folder / 'skill_update.py').is_file())
                self.assertEqual(settings.read_text(), 'preserve')
                self.assertTrue((sibling / 'old-marker').exists())

    def test_check_only_and_equal_or_older_remote_do_not_install(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.installed(Path(work), 's-agent', '1.9.0')
            for version, apply, status in [('1.10.0', False, 'update available'),
                                           ('1.9.0', True, 'up to date'), ('1.8.0', True, 'up to date')]:
                with self.subTest(version=version, apply=apply), \
                        mock.patch.object(update, '_download', return_value=published(version)), \
                        mock.patch.object(update, '_install') as install:
                    self.assertIn('status=' + status, update.check_skill_update('s-agent', folder, apply=apply))
                    install.assert_not_called()

    def test_network_or_invalid_metadata_keeps_installed_copy(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.installed(Path(work), 's-agent')
            for value in [urllib.error.URLError('offline'), b'not markdown', published('next')]:
                patch = (mock.patch.object(update, '_download', side_effect=value) if isinstance(value, Exception)
                         else mock.patch.object(update, '_download', return_value=value))
                with self.subTest(value=value), patch:
                    self.assertIn('update failed', update.check_skill_update('s-agent', folder, apply=True))
                    self.assertEqual(update.skill_version(folder), '1.0.0')
                    self.assertTrue((folder / 'old-marker').exists())

    def test_raw_endpoint_remains_available_when_public_api_is_rate_limited(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.installed(Path(work), 's-agent')
            with mock.patch.object(update, '_download', side_effect=[
                    urllib.error.HTTPError(update.CONTENTS, 403, 'rate limited', {}, None),
                    skill('9.8.7').encode()]):
                self.assertIn('status=update available', update.check_skill_update('s-agent', folder))
            self.assertTrue((folder / 'old-marker').exists())

    def test_unsafe_or_incomplete_archives_never_replace_installation(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.installed(Path(work), 's-agent')
            for archive in [self.archive('s-agent', '../escape'), self.archive('s-agent', 'C:escape'),
                            self.archive('s-agent', incomplete=True), b'not a zip']:
                with mock.patch.object(update, '_download', side_effect=[published('9.8.7'), archive]):
                    self.assertIn('update failed', update.check_skill_update('s-agent', folder, apply=True))
                    self.assertEqual(update.skill_version(folder), '1.0.0')

    def test_replacement_failure_restores_previous_installation(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.installed(Path(work), 's-agent')
            replace = os.replace
            def fail_incoming(source, destination):
                if Path(source).name == 'incoming':
                    raise OSError('replacement failed')
                return replace(source, destination)
            with mock.patch.object(update, '_download', side_effect=[published('9.8.7'), self.archive('s-agent')]), \
                    mock.patch.object(update.os, 'replace', side_effect=fail_incoming):
                self.assertIn('update failed', update.check_skill_update('s-agent', folder, apply=True))
            self.assertEqual(update.skill_version(folder), '1.0.0')
            self.assertTrue((folder / 'old-marker').exists())

    def test_development_checkout_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            (root / '.git').mkdir()
            (root / 'skills').mkdir()
            folder = self.installed(root / 'skills', 's-agent')
            with mock.patch.object(update, '_download', return_value=published('9.8.7')) as download:
                self.assertIn('development checkout', update.check_skill_update('s-agent', folder, apply=True))
                download.assert_called_once()
            self.assertTrue((folder / 'old-marker').exists())


if __name__ == '__main__':
    unittest.main()

"""Update one installed skill from its public GitHub source using only the stdlib."""
from pathlib import Path, PurePosixPath
import base64
import io
import json
import os
import shutil
import stat
import tempfile
import urllib.request
import zipfile

from skill_runtime import metadata_version, skill_version

SOURCE = 'https://raw.githubusercontent.com/Jeinn-co/agent-skills/main/skills/'
CONTENTS = 'https://api.github.com/repos/Jeinn-co/agent-skills/contents/skills/'
ARCHIVE = 'https://codeload.github.com/Jeinn-co/agent-skills/zip/refs/heads/main'
SKILLS = ('ai-usage', 'ai-cli-version', 's-agent')
MAX_BYTES = 64 * 1024 * 1024


def _version(value):
    return tuple(map(int, value.split('.')))


def _download(url, timeout):
    request = urllib.request.Request(url, headers={'User-Agent': 'agent-skills-updater',
                                                  'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError('skill download exceeds 64 MiB')
    return body


def _required_files(name):
    files = ['skill_update.py', 'skill_runtime.py']
    files += (['scripts/check_update.py', 'scripts/sync_roles.py', 'references/source.json',
               'data/gemini-models.json'] if name == 's-agent' else
              ['run.py', 'html_report.py', 'report_i18n.py', 'templates/report.html',
               'assets/report.js', 'locales/en.json', 'locales/common/en.json'])
    if name == 'ai-usage':
        files.append('portable.py')
    return files


def _install(name, folder, latest, timeout):
    if (folder.parent.parent / '.git').exists():
        raise ValueError('development checkout; update the repository instead')
    backup = folder.with_name('.' + name + '-previous')
    if backup.exists():
        raise ValueError(f'previous installation backup needs attention: {backup}')
    archive = _download(ARCHIVE, timeout)
    with tempfile.TemporaryDirectory(prefix='.' + name + '-update-', dir=folder.parent) as work:
        stage = Path(work) / 'incoming'
        stage.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            prefix = 'agent-skills-main/skills/' + name + '/'
            members = [entry for entry in bundle.infolist() if entry.filename.startswith(prefix)]
            if sum(entry.file_size for entry in members) > MAX_BYTES:
                raise ValueError('expanded skill exceeds 64 MiB')
            for entry in members:
                relative = PurePosixPath(entry.filename[len(prefix):])
                mode = entry.external_attr >> 16
                if ('..' in relative.parts or relative.is_absolute()
                        or '\\' in str(relative) or ':' in str(relative)):
                    raise ValueError('unsafe archive path')
                if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError('unsupported archive file type')
                target = stage.joinpath(*relative.parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(entry))
                if mode & 0o777:
                    target.chmod(mode & 0o777)
        current = skill_version(stage)
        if _version(current) < _version(latest):
            raise ValueError('downloaded skill is older than the published version')
        if any(not (stage / file).is_file() for file in _required_files(name)):
            raise ValueError('downloaded skill is incomplete')
        if _version(current) < _version(skill_version(folder)):
            raise ValueError('installation changed during download; keeping its newer version')
        os.replace(folder, backup)
        try:
            os.replace(stage, folder)
        except OSError:
            try:
                os.replace(backup, folder)
            except OSError as error:
                raise OSError(f'could not restore installation; previous copy remains at {backup}') from error
            raise
    shutil.rmtree(backup, ignore_errors=True)
    return current


def _latest(name, timeout):
    try:
        document = _download(CONTENTS + name + '/SKILL.md?ref=main', timeout)
    except OSError:  # The raw endpoint still works when the public API is unavailable/rate-limited.
        return metadata_version(_download(SOURCE + name + '/SKILL.md', timeout).decode('utf-8'))
    content = json.loads(document)['content']
    return metadata_version(base64.b64decode(content).decode('utf-8'))


def check_skill_update(name, folder, *, apply=False, timeout=10):
    """Check by default; an explicit apply call replaces only this installation."""
    try:
        if name not in SKILLS:
            raise ValueError('unknown skill')
        folder = Path(folder).resolve()
        installed = skill_version(folder)
        latest = _latest(name, timeout)
        status = 'update available' if _version(latest) > _version(installed) else 'up to date'
        if status == 'update available' and apply:
            installed = _install(name, folder, latest, timeout)
            status = 'updated'
        return f'skill installed={installed} latest={latest} status={status}'
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        message = f'skill {"update" if apply else "check"} failed ({error})'
        try:
            folder = Path(folder).resolve()
            local = skill_version(folder)
            if name in SKILLS and all((folder / file).is_file() for file in _required_files(name)):
                return f'{message}; fallback=local installed={local} action=continue'
        except (OSError, ValueError, TypeError):
            pass
        return f'{message}; fallback=none action=stop'

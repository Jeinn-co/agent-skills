"""Read skill metadata and identify report servers without user configuration."""
import hashlib
from pathlib import Path
import re


def metadata_version(text):
    frontmatter = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)', text, re.S)
    metadata = re.search(r'^metadata:\s*\n((?:[ \t]+[^\n]*(?:\n|$))*)', frontmatter[1], re.M) if frontmatter else None
    version = re.search(r'^  version: "(\d+\.\d+\.\d+)"\s*$', metadata[1], re.M) if metadata else None
    if not version:
        raise ValueError('no metadata.version in SKILL.md')
    return version[1]


def skill_version(folder):
    return metadata_version((Path(folder) / 'SKILL.md').read_text(encoding='utf-8'))


def server_identity(name, version, folder):
    folder = Path(folder).resolve()
    files = [path for path in folder.glob('*.py') if not path.name.startswith('test_')]
    for directory in ('assets', 'templates', 'data', 'locales'):
        files.extend(path for path in (folder / directory).rglob('*') if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(folder)).encode('utf-8') + b'\0')
        digest.update(path.read_bytes() + b'\0')
    return ('%s %s %s\n%s' % (name, version, folder, digest.hexdigest()[:16])).encode('utf-8')


def server_owned_by(holder, folder):
    if not holder:
        return False
    header = holder.partition(b'\n')[0]
    return header.split(b' ', 2)[2:] == [str(Path(folder).resolve()).encode('utf-8')]

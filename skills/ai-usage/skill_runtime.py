"""Identify the code loaded by a report server without reading user configuration."""
import hashlib
from pathlib import Path


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

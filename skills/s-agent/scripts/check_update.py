#!/usr/bin/env python3.11
"""Check the published S-Agent version without installing or changing anything."""
from pathlib import Path
import re
import urllib.request

SKILL = Path(__file__).resolve().parents[1] / 'SKILL.md'
SKILL_URL = 'https://raw.githubusercontent.com/Jeinn-co/agent-skills/main/skills/s-agent/SKILL.md'


def metadata_version(text):
    frontmatter = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)', text, re.S)
    version = re.search(r'^  version: "(\d+\.\d+\.\d+)"\s*$', frontmatter[1], re.M) if frontmatter else None
    if not version:
        raise ValueError('no metadata.version in SKILL.md')
    return version[1]


def check_skill():
    try:
        installed = metadata_version(SKILL.read_text(encoding='utf-8'))
        request = urllib.request.Request(SKILL_URL, headers={'User-Agent': 's-agent'})
        with urllib.request.urlopen(request, timeout=10) as response:
            latest = metadata_version(response.read().decode('utf-8'))
    except (OSError, ValueError) as error:
        return f'skill check failed ({error})'
    status = ('update available' if tuple(map(int, latest.split('.'))) >
              tuple(map(int, installed.split('.'))) else 'up to date')
    return (f'skill installed={installed} latest={latest} status={status}'
            ' update_cmd=npx -y skills update -g s-agent')


if __name__ == '__main__':
    print(check_skill())

#!/usr/bin/env python3.11
"""Validate a role policy and preview or atomically apply local model/effort changes."""
import argparse
import copy
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tomllib
import uuid

ROLES = {
    'planner': 'Turn a request into an executable plan: scope, acceptance criteria, steps and checks.',
    'designer': 'Design usable flows, accessible interactions, layouts and states.',
    'executor': 'Implement an approved plan step by step and verify each step.',
    'reviewer': 'Independently review and test changes: correctness, security, regressions and acceptance.',
    'devops': 'Investigate CI/CD, environments, deployment configuration and reliability.',
    'security': 'Scan code, dependencies and configuration for vulnerabilities and leaked secrets.',
}
PLATFORMS = {'codex', 'claude'}
# Known model-specific constraints; other models still require a verified runtime catalog.
_CATALOG = json.loads((Path(__file__).resolve().parents[1] / 'data/gemini-models.json').read_text(encoding='utf-8'))
GEMINI_EFFORTS = {model['id']: set(model['efforts']) for model in _CATALOG['models']}


def exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'{label}: expected exactly {sorted(keys)}')


def token(value, label):
    if (not isinstance(value, str) or not 1 <= len(value) <= 200
            or value != value.strip() or any(not character.isprintable() for character in value)):
        raise ValueError(f'{label}: expected a nonempty model/effort identifier')


def validate(policy, catalog=None):
    exact_keys(policy, {'schema_version', 'roles'}, 'policy')
    if type(policy['schema_version']) is not int or policy['schema_version'] != 1:
        raise ValueError('schema_version must be 1')
    exact_keys(policy['roles'], ROLES, 'roles')
    platforms = set(policy['roles']['planner']) if isinstance(policy['roles']['planner'], dict) else set()
    if platforms not in (PLATFORMS, PLATFORMS | {'gemini'}):
        raise ValueError('roles require codex and claude, with optional gemini on all roles')
    if catalog is not None:
        exact_keys(catalog, platforms, 'catalog')
        for platform, models in catalog.items():
            if not isinstance(models, dict) or not models:
                raise ValueError(f'catalog.{platform}: expected model-to-effort lists')
            for model, efforts in models.items():
                token(model, 'catalog model')
                if not isinstance(efforts, list) or not efforts:
                    raise ValueError('catalog efforts must be a nonempty list')
                for effort in efforts:
                    token(effort, 'catalog effort')
    for role, settings in policy['roles'].items():
        exact_keys(settings, platforms, role)
        for platform, values in settings.items():
            exact_keys(values, {'model', 'effort'}, f'{role}.{platform}')
            for key, value in values.items():
                token(value, f'{role}.{platform}.{key}')
            allowed = GEMINI_EFFORTS.get(values['model']) if platform == 'gemini' else None
            if allowed is not None and values['effort'] not in allowed:
                raise ValueError(f'{role}.gemini: unsupported effort for {values["model"]}: {values["effort"]}')
            if catalog is not None and values['effort'] not in catalog[platform].get(values['model'], []):
                raise ValueError(f'{role}.{platform}: unavailable model/effort {values}')


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read_json(path):
    text = sys.stdin.read() if path == '-' else Path(path).read_text(encoding='utf-8')
    return json.loads(text, object_pairs_hook=json_object)



def string_state(line, state):
    """Track TOML strings so prompt contents never become candidate assignments."""
    index = 0
    while index < len(line):
        if state:
            if state.startswith('"') and line[index] == "\\":
                index += 2
                continue
            if line.startswith(state, index):
                index += len(state)
                state = None
            else:
                index += 1
        elif line[index] == '#':
            break
        elif line[index] in ('"', "'"):
            state = line[index] * (3 if line.startswith(line[index] * 3, index) else 1)
            index += len(state)
        else:
            index += 1
    return state


def update_toml(text, changes):
    """Patch scalar lines, then prove the entire parsed document changed only as intended."""
    original = tomllib.loads(text)
    expected = copy.deepcopy(original)
    for section, values in changes.items():
        table = expected if section == '' else expected.get(section)
        if not isinstance(table, dict):
            raise ValueError(f'missing or unsupported TOML table: {section}')
        table.update(values)
    lines = text.splitlines(keepends=True)
    section = ''
    found = set()
    state = None
    for index, line in enumerate(lines):
        inside_string = state is not None
        state = string_state(line, state)
        if inside_string:
            continue
        header = re.fullmatch(r'\s*\[([a-z]+)\]\s*(?:#.*)?\r?\n?', line)
        if header:
            section = header[1]
        elif re.match(r'\s*\[', line):
            section = None
        match = re.match(r'^(\s*)([A-Za-z_][A-Za-z_0-9]*)(\s*=\s*)(.*?)(\r?\n)?$', line)
        if match and section in changes and match[2] in changes[section]:
            key = (section, match[2])
            if key in found:
                raise ValueError('ambiguous TOML assignments')
            found.add(key)
            # Multiline targeted values cannot be safely patched as one scalar line.
            if match[4].lstrip().startswith(('"""', "'''")):
                raise ValueError('multiline model/effort is unsupported')
            scalar = re.fullmatch(r'''(?:"(?:[^"\\]|\\.)*"|'[^']*')(\s*#.*)?\s*''', match[4])
            if not scalar:
                raise ValueError('unsupported TOML model/effort scalar')
            suffix = scalar[1] or ''
            lines[index] = (match[1] + match[2] + match[3] +
                            json.dumps(changes[section][match[2]]) +
                            suffix + (match[5] or '\n'))
    required = {(section, key) for section, values in changes.items() for key in values}
    if found != required:
        raise ValueError('missing or unsupported TOML model/effort assignments')
    result = ''.join(lines)
    if tomllib.loads(result) != expected:
        raise ValueError('unsupported TOML layout; no files changed')
    return result



def yaml_scalar(raw):
    """Accept a conservative single-line YAML scalar, returning its comment tail."""
    if raw.startswith('"'):
        try:
            value, finish = json.JSONDecoder().raw_decode(raw)
        except ValueError as error:
            raise ValueError('unsupported YAML quoted scalar') from error
        tail = raw[finish:]
        if not isinstance(value, str) or not re.fullmatch(r'\s*(?:#.*)?', tail):
            raise ValueError('unsupported YAML quoted scalar')
        return tail
    if raw.startswith("'"):
        match = re.fullmatch(r"'(?:[^']|'')*'(\s*(?:#.*)?)", raw)
        if not match:
            raise ValueError('unsupported YAML quoted scalar')
        return match[1]
    comment = re.search(r'\s+#.*$', raw)
    value = raw[:comment.start()] if comment else raw
    if (not value or value[0] in '-?:,[]{}#&*!|>\'"%@`'
            or re.search(r':(?:\s|$)|[\[\]{}]', value)):
        raise ValueError('unsupported YAML plain scalar')
    return comment[0] if comment else ''


def yaml_value(raw):
    if not raw.startswith('['):
        yaml_scalar(raw)
        return
    # Only flat, single-line flow lists; reject nested collections and aliases.
    position = 1
    while True:
        while position < len(raw) and raw[position].isspace():
            position += 1
        if position < len(raw) and raw[position] == ']':
            if not re.fullmatch(r'\s*(?:#.*)?', raw[position + 1:]):
                raise ValueError('unsupported YAML list suffix')
            return
        item = re.match(r"""(?:"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^,\[\]{}'"#]+)""", raw[position:])
        if not item:
            raise ValueError('unsupported YAML flow list')
        yaml_scalar(item[0].strip())
        position += item.end()
        while position < len(raw) and raw[position].isspace():
            position += 1
        if position >= len(raw) or raw[position] not in ',]':
            raise ValueError('unterminated YAML flow list')
        if raw[position] == ',':
            position += 1
        # A closing bracket is consumed by the next iteration.


def update_claude(text, name, values):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip('\r\n') != '---':
        raise ValueError('Claude role requires YAML frontmatter')
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip('\r\n') == '---'), None)
    if end is None:
        raise ValueError('unterminated Claude frontmatter')
    seen = {}
    block_indent = None
    in_block = False
    for index in range(1, end):
        line = lines[index].rstrip('\r\n')
        if not line.strip():
            continue
        if in_block and line.startswith(' '):
            indentation = len(line) - len(line.lstrip(' '))
            if block_indent is None:
                block_indent = indentation
            if indentation < block_indent or '\t' in line[:indentation]:
                raise ValueError('unsupported YAML block indentation')
            continue
        in_block = False
        if line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z_][\w-]*):[ \t]*(.*)', line)
        if not match:
            raise ValueError('unsupported Claude frontmatter; only flat keys are supported')
        key, raw = match.groups()
        if key in seen:
            raise ValueError(f'duplicate Claude key: {key}')
        seen[key] = (index, raw)
        if re.fullmatch(r'[|>][+-]?(?:[ \t]+#.*)?', raw):
            if key in ('model', 'effort', 'name'):
                raise ValueError(f'unsupported Claude {key} block scalar')
            in_block = True
            block_indent = None
        else:
            yaml_value(raw)
    if 'name' in seen:
        raw = seen['name'][1]
        if raw not in (name, json.dumps(name), "'" + name + "'"):
            raise ValueError('Claude role name does not match filename')
    additions = []
    for key, value in values.items():
        if key in seen:
            index, raw = seen[key]
            tail = yaml_scalar(raw)
            lines[index] = f'{key}: {json.dumps(value)}' + tail + '\n'
        else:
            additions.append(f'{key}: {json.dumps(value)}\n')
    lines[end:end] = additions
    return ''.join(lines)


def safe_path(root, path):
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError(f'symlink target is unsupported: {current}')
        current = current.parent
    if root.is_symlink():
        raise ValueError('root cannot be a symlink')


def plan(root, policy, source_url=None):
    outputs = {}
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    for name, responsibility in ROLES.items():
        settings = policy['roles'][name]
        codex = root / '.codex/agents' / (name + '.toml')
        claude = root / '.claude/agents' / (name + '.md')
        shared = root / '.agents/roles' / (name + '.toml')
        for path in (codex, claude, shared):
            safe_path(root, path)
        codex_values = {'model': settings['codex']['model'], 'model_reasoning_effort': settings['codex']['effort']}
        if codex.exists():
            content = codex.read_text(encoding='utf-8')
            parsed = tomllib.loads(content)
            if parsed.get('name', name) != name:
                raise ValueError(f'{codex}: name mismatch')
            outputs[codex] = update_toml(content, {'': codex_values})
        else:
            outputs[codex] = '\n'.join(f'{key} = {quote(value)}' for key, value in {
                'name': name, 'description': responsibility, **codex_values,
                'developer_instructions': responsibility + ' Follow the coordinating agent’s task scope and applicable project instructions.'}.items()) + '\n'
        outputs[claude] = (update_claude(claude.read_text(encoding='utf-8'), name, settings['claude'])
                           if claude.exists() else
                           f'---\nname: {quote(name)}\ndescription: {quote(responsibility)}\nmodel: {quote(settings["claude"]["model"])}\neffort: {quote(settings["claude"]["effort"])}\n---\n\n{responsibility} Follow the coordinating agent’s task scope and applicable project instructions.\n')
        if shared.exists():
            content = shared.read_text(encoding='utf-8')
            if 'gemini' in settings and 'gemini' not in tomllib.loads(content):
                content += '\n[gemini]\n' + ''.join(
                    f'{key} = {quote(value)}\n' for key, value in settings['gemini'].items())
            outputs[shared] = update_toml(content, settings)
        elif 'gemini' in settings:
            outputs[shared] = f'name = {quote(name)}\n' + ''.join(
                f'\n[{platform}]\n' + ''.join(f'{key} = {quote(value)}\n' for key, value in values.items())
                for platform, values in settings.items())
        if 'gemini' in settings:
            gemini = root / '.gemini/config/agents' / (name + '.md')
            safe_path(root, gemini)
            # Exact model/effort are session flags; native subagents only support model tiers.
            if gemini.exists():
                content = gemini.read_text(encoding='utf-8')
                outputs[gemini] = update_claude(content, name, {'model': 'inherit'})
            else:
                outputs[gemini] = (
                    f'---\nname: {quote(name)}\ndescription: {quote(responsibility)}\n'
                    'model: "inherit"\n---\n\n' + responsibility +
                    ' Follow the coordinating agent’s task scope and applicable project instructions.\n')
    if source_url is not None:
        if not re.fullmatch(r'https://[^\s]+', source_url):
            raise ValueError('source-url must be an HTTPS URL')
        path = root / '.agents/s-agent-source.json'
        safe_path(root, path)
        outputs[path] = json.dumps({'schema_version': 1, 'source_url': source_url}, indent=2) + '\n'
    result = []
    for path, content in outputs.items():
        before = path.read_bytes() if path.exists() else None
        after = content.encode('utf-8')
        if before != after:
            result.append((path, before, after))
    return result


def atomic_write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply(root, changes):
    if not changes:
        return None
    backup = root / '.agents/s-agent-backups' / uuid.uuid4().hex
    safe_path(root, backup)
    modes = {}
    for path, before, after in changes:
        safe_path(root, path)
        if (path.read_bytes() if path.exists() else None) != before:
            raise ValueError(f'file changed during validation: {path}')
        modes[path] = path.stat().st_mode & 0o777 if before is not None else 0o644
    # Finish every backup before writing any live profile.
    for path, before, after in changes:
        if before is not None:
            target = backup / path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    backup.mkdir(parents=True, exist_ok=True)
    (backup / 'manifest.json').write_text(json.dumps({str(path.relative_to(root)): before is not None for path, before, _ in changes}, indent=2) + '\n')
    written = []
    try:
        for path, before, after in changes:
            written.append((path, before))
            atomic_write(path, after, modes[path])
    except BaseException:
        for path, before in reversed(written):
            if before is None:
                path.unlink(missing_ok=True)
            else:
                # Restore via a separate replacement so an injected write failure cannot skip rollback.
                restore = backup / path.relative_to(root)
                temporary = path.with_name(path.name + '.restore-' + uuid.uuid4().hex)
                try:
                    shutil.copy2(restore, temporary)
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
        raise
    return backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('policy', help='policy JSON file, or - for stdin')
    parser.add_argument('--root', type=Path, default=Path.home(), help='home directory (use a temporary root for tests)')
    parser.add_argument('--catalog', help='JSON of actual host model/effort capabilities; required for --apply')
    parser.add_argument('--source-url', help='record the policy source HTTPS URL locally')
    parser.add_argument('--apply', action='store_true', help='write validated changes; default is preview only')
    parser.add_argument('--validate-only', action='store_true', help='validate policy and optional catalog without reading local profiles')
    args = parser.parse_args(argv)
    try:
        if args.apply and args.validate_only:
            raise ValueError('--apply and --validate-only cannot be combined')
        if args.apply and not args.catalog:
            raise ValueError('--apply requires --catalog from actual host capabilities')
        policy = read_json(args.policy)
        catalog = read_json(args.catalog) if args.catalog else None
        validate(policy, catalog)
        if args.validate_only:
            print('Validated 6 policy roles.' + (' Catalog verified.' if catalog else ' Catalog not supplied.'))
            print('Validation only: no local profiles read or written. No agents were executed.')
            return 0
        root = args.root.absolute()
        changes = plan(root, policy, args.source_url)
        print('Validated %d roles.' % len(ROLES) + (' Catalog verified.' if catalog else ' Catalog not supplied; apply is unavailable.'))
        # Display only changed settings, never unrelated prompt or permission content.
        for path, before, after in changes:
            print(('Update: ' if before is not None else 'Create: ') + str(path))
            print(''.join(difflib.unified_diff(
                (before or b'').decode('utf-8').splitlines(keepends=True),
                after.decode('utf-8').splitlines(keepends=True),
                fromfile=str(path), tofile=str(path), n=0)), end='')
        if args.apply:
            backup = apply(root, changes)
            print(f'Applied {len(changes)} changed files.' + (f' Backup: {backup}' if backup else ' No writes needed.'))
            print('Reload/restart configured hosts to pick up role settings. Gemini model/effort use session flags. No agents were executed.')
        else:
            print(f'Preview only: {len(changes)} files would change. No files written.')
        return 0
    except (ValueError, OSError, TypeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

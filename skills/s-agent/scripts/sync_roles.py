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
    'reviewer': 'Independently review and test changes: correctness, security, regressions and acceptance. Use playwright-cli for UI QA.',
    'security': 'Scan code, dependencies and configuration for vulnerabilities and leaked secrets (read-only).',
}
LEGACY_ROLES = ('planner', 'designer', 'executor', 'devops')
PLATFORMS = {'codex', 'claude'}
# Claude Code settings.json accepts only these saved effort levels (higher ones are per-session only).
CLAUDE_SAVED_EFFORTS = {'low', 'medium', 'high', 'xhigh'}
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
    roles = policy['roles']
    allowed_roles = set(ROLES) | set(LEGACY_ROLES)
    if not isinstance(roles, dict) or not set(ROLES).issubset(roles) or not set(roles).issubset(allowed_roles):
        raise ValueError(f'roles: expected {sorted(ROLES)} (optional legacy: {sorted(LEGACY_ROLES)})')
    platforms = set(roles['reviewer']) if isinstance(roles['reviewer'], dict) else set()
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
    for role, settings in roles.items():
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
            lines[index] = (f'{key}: {json.dumps(value)}' + tail
                            + ('\r\n' if lines[index].endswith('\r\n') else '\n'))
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


def parse_daily(value, platform, catalog=None):
    """Parse a main-loop `daily` choice given as MODEL:EFFORT (model ID, not display name)."""
    model, separator, effort = value.rpartition(':')
    if not separator:
        raise ValueError(f'--{platform}-daily: expected MODEL:EFFORT')
    token(model, f'{platform}-daily model')
    token(effort, f'{platform}-daily effort')
    if platform == 'claude' and effort not in CLAUDE_SAVED_EFFORTS:
        raise ValueError(f'claude-daily: settings.json can only save effort {sorted(CLAUDE_SAVED_EFFORTS)}')
    if catalog is not None and effort not in catalog.get(platform, {}).get(model, []):
        raise ValueError(f'{platform}-daily: unavailable model/effort {model}:{effort}')
    return model, effort


def update_json_settings(path, raw, change):
    """Apply `change` to a settings.json object without reformatting the file (CRLF is kept)."""
    exists = raw is not None
    raw = raw if exists else '{}\n'
    data = json.loads(raw, object_pairs_hook=json_object)
    indent = re.search(r'\n( +)"', raw)
    newline = '\r\n' if '\r\n' in raw else '\n'
    dump = lambda value: (json.dumps(value, indent=len(indent[1]) if indent else 2, ensure_ascii=False)
                          + ('\n' if raw.endswith('\n') else '')).replace('\n', newline)
    if not isinstance(data, dict) or (exists and dump(data) != raw):
        raise ValueError(f'{path}: unsupported settings.json layout; no files changed')
    change(data)
    return dump(data)


def update_claude_settings(path, raw, model, effort):
    """Set Claude Code's main-loop model and its saved effort without reformatting settings.json."""
    def change(data):
        settings = data.setdefault('modelSettings', {})
        if not isinstance(settings, dict) or not isinstance(settings.setdefault(model, {}), dict):
            raise ValueError(f'{path}: unsupported modelSettings layout; no files changed')
        data['model'] = model
        settings[model]['effortLevel'] = effort
    return update_json_settings(path, raw, change)


def plan(root, policy, source_url=None, codex_daily=None, claude_daily=None, gemini_daily=None):
    outputs = {}
    snapshot = {}
    quote = lambda value: json.dumps(value, ensure_ascii=False)

    def read(path):
        # Read raw bytes once: no newline translation, and `before` is exactly what `after` came from.
        snapshot[path] = path.read_bytes() if path.exists() else None
        return None if snapshot[path] is None else snapshot[path].decode('utf-8')

    if gemini_daily is not None:
        # agy saves the `/model` choice by its label, which already includes the effort variant.
        agy_settings = root / '.gemini/antigravity-cli/settings.json'
        safe_path(root, agy_settings)
        outputs[agy_settings] = update_json_settings(agy_settings, read(agy_settings),
                                                     lambda data: data.update(model=gemini_daily))
    if claude_daily is not None:
        # Notion `My usage` daily is the Claude Code main-loop default; only model and its effort change.
        settings_path = root / '.claude/settings.json'
        safe_path(root, settings_path)
        outputs[settings_path] = update_claude_settings(settings_path, read(settings_path), *claude_daily)
    if codex_daily is not None:
        # Notion `My usage` daily is the Codex main-loop default; only these two top-level keys change.
        codex_daily = dict(zip(('model', 'model_reasoning_effort'), codex_daily))
        config = root / '.codex/config.toml'
        safe_path(root, config)
        content = read(config) or ''
        present = tomllib.loads(content)
        newline = '\r\n' if '\r\n' in content else '\n'
        content = ''.join(f'{key} = {quote(value)}{newline}' for key, value in codex_daily.items()
                          if key not in present) + content
        outputs[config] = update_toml(content, {'': codex_daily})
    for name, responsibility in ROLES.items():
        settings = policy['roles'][name]
        codex = root / '.codex/agents' / (name + '.toml')
        claude = root / '.claude/agents' / (name + '.md')
        shared = root / '.agents/roles' / (name + '.toml')
        for path in (codex, claude, shared):
            safe_path(root, path)
        codex_values = {'model': settings['codex']['model'], 'model_reasoning_effort': settings['codex']['effort']}
        content = read(codex)
        if content is not None:
            parsed = tomllib.loads(content)
            if parsed.get('name', name) != name:
                raise ValueError(f'{codex}: name mismatch')
            outputs[codex] = update_toml(content, {'': codex_values})
        else:
            outputs[codex] = '\n'.join(f'{key} = {quote(value)}' for key, value in {
                'name': name, 'description': responsibility, **codex_values,
                'developer_instructions': responsibility + ' Follow the coordinating agent’s task scope and applicable project instructions.'}.items()) + '\n'
        content = read(claude)
        outputs[claude] = (update_claude(content, name, settings['claude'])
                           if content is not None else
                           f'---\nname: {quote(name)}\ndescription: {quote(responsibility)}\nmodel: {quote(settings["claude"]["model"])}\neffort: {quote(settings["claude"]["effort"])}\n---\n\n{responsibility} Follow the coordinating agent’s task scope and applicable project instructions.\n')
        content = read(shared)
        if content is not None:
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
            content = read(gemini)
            if content is not None:
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
        before = snapshot[path] if path in snapshot else (path.read_bytes() if path.exists() else None)
        after = content.encode('utf-8')
        if before != after:
            result.append((path, before, after))
    return result


class WriteConflict(ValueError):
    """The target changed after planning; it was not replaced and must not be rolled back."""


def current_bytes(path):
    return path.read_bytes() if path.exists() else None


def atomic_write(path, content, mode=0o644, expected=...):
    """Replace `path`; with `expected`, refuse if the file changed since it was planned."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        # Re-check at the last moment so a save made while the temp file was written is kept.
        if expected is not ... and current_bytes(path) != expected:
            raise WriteConflict(f'file changed during apply: {path}')
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass  # A locked temp file (e.g. antivirus on Windows) must not mask the real outcome.


def apply(root, changes):
    if not changes:
        return None
    backup = root / '.agents/s-agent-backups' / uuid.uuid4().hex
    safe_path(root, backup)
    modes = {}
    for path, before, after in changes:
        safe_path(root, path)
        if current_bytes(path) != before:
            raise ValueError(f'file changed during validation: {path}')
        modes[path] = path.stat().st_mode & 0o777 if before is not None else 0o644
    # Backups may hold tokens from config files; keep the folder private to this user.
    backup.mkdir(parents=True, exist_ok=True)
    backup.chmod(0o700)
    # Finish every backup before writing any live profile.
    for path, before, after in changes:
        if before is not None:
            target = backup / path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (backup / 'manifest.json').write_text(json.dumps({str(path.relative_to(root)): before is not None for path, before, _ in changes}, indent=2) + '\n')
    written = []
    attempted = None
    try:
        for path, before, after in changes:
            attempted = (path, before, after)
            atomic_write(path, after, modes[path], expected=before)
            # Record only completed replacements; a failed write left its original untouched.
            written.append(attempted)
            attempted = None
    except BaseException as error:
        failed, conflicts = [], []
        # A refused write never replaced its target; never treat it as ours to roll back.
        if attempted is not None and not isinstance(error, WriteConflict):
            try:
                if current_bytes(attempted[0]) == attempted[2]:
                    # Interrupted after the replace but before it was recorded (e.g. Ctrl+C).
                    written.append(attempted)
            except OSError:
                failed.append(str(attempted[0]))
        for path, before, after in reversed(written):
            try:
                if before is None:
                    if current_bytes(path) != after:
                        conflicts.append(str(path))
                    else:
                        path.unlink(missing_ok=True)
                else:
                    restore = backup / path.relative_to(root)
                    # mkstemp creates the copy as 0600, so credentials are never briefly world-readable.
                    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.restore-')
                    os.close(descriptor)
                    temporary = Path(name)
                    try:
                        shutil.copyfile(restore, temporary)
                        shutil.copystat(restore, temporary)
                        # Compare after preparing the restore copy, right before replacing.
                        if current_bytes(path) != after:
                            # Saved again after this sync wrote it: keep the newer content, report it.
                            conflicts.append(str(path))
                        else:
                            os.replace(temporary, path)
                    finally:
                        try:
                            temporary.unlink(missing_ok=True)
                        except OSError:
                            pass  # Leftover temp copy only; the restore outcome is already decided.
            except OSError:
                # Keep restoring the rest; report every file that could not be rolled back.
                failed.append(str(path))
        if failed or conflicts:
            raise OSError(f'{error}; rollback failed for {failed}; kept newer saves in {conflicts}; '
                          f'backup: {backup}') from error
        raise
    return backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('policy', help='policy JSON file, or - for stdin')
    parser.add_argument('--root', type=Path, default=Path.home(), help='home directory (use a temporary root for tests)')
    parser.add_argument('--catalog', help='JSON of actual host model/effort capabilities; required for --apply')
    parser.add_argument('--source-url', help='record the policy source HTTPS URL locally')
    parser.add_argument('--codex-daily', metavar='MODEL:EFFORT',
                        help='Notion My usage Codex daily as model ID:effort; aligns ~/.codex/config.toml top-level model/model_reasoning_effort')
    parser.add_argument('--claude-daily', metavar='MODEL:EFFORT',
                        help='Notion My usage Claude daily as full model ID:effort; aligns ~/.claude/settings.json model and modelSettings.<model>.effortLevel')
    parser.add_argument('--gemini-daily', metavar='LABEL',
                        help='Notion My usage Gemini daily as the `agy models` label, e.g. "Gemini 4 Hydrogen (High)"; aligns ~/.gemini/antigravity-cli/settings.json model')
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
        codex_daily = parse_daily(args.codex_daily, 'codex', catalog) if args.codex_daily is not None else None
        claude_daily = parse_daily(args.claude_daily, 'claude', catalog) if args.claude_daily is not None else None
        if args.gemini_daily is not None:
            # `is not None`: an empty label must be rejected, not silently written as model "".
            token(args.gemini_daily, 'gemini-daily label')
        if args.validate_only:
            print(f'Validated {len(ROLES)} policy roles.' + (' Catalog verified.' if catalog else ' Catalog not supplied.'))
            print('Validation only: no local profiles read or written. No agents were executed.')
            return 0
        root = args.root.absolute()
        changes = plan(root, policy, args.source_url, codex_daily, claude_daily, args.gemini_daily)
        print('Validated %d roles.' % len(ROLES) + (' Catalog verified.' if catalog else ' Catalog not supplied; apply is unavailable.'))
        # Display only changed settings, never unrelated prompt or permission content.
        main_configs = {root / '.codex/config.toml': codex_daily, root / '.claude/settings.json': claude_daily,
                        root / '.gemini/antigravity-cli/settings.json': args.gemini_daily}
        for path, before, after in changes:
            print(('Update: ' if before is not None else 'Create: ') + str(path))
            if path in main_configs:
                # These files can hold credentials, and a neighbouring line may change (e.g. an added comma).
                print(f'  main-loop daily -> {main_configs[path]} (diff hidden: this file can hold credentials)')
                continue
            print(''.join(difflib.unified_diff(
                (before or b'').decode('utf-8').splitlines(keepends=True),
                after.decode('utf-8').splitlines(keepends=True),
                fromfile=str(path), tofile=str(path), n=0)), end='')
        if args.apply:
            backup = apply(root, changes)
            print(f'Applied {len(changes)} changed files.' + (f' Backup: {backup}' if backup else ' No writes needed.'))
            print('Reload/restart configured hosts to pick up role and main-loop settings; Gemini subagent model/effort still use agy session flags. No agents were executed.')
        else:
            print(f'Preview only: {len(changes)} files would change. No files written.')
        return 0
    except (ValueError, OSError, TypeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

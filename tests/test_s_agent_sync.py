import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/s-agent/scripts/sync_roles.py'
spec = importlib.util.spec_from_file_location('s_agent_sync', SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'home'
        self.policy = {'schema_version': 1, 'roles': {
            role: {platform: {'model': platform + '-future-9', 'effort': 'ultra'}
                   for platform in ('codex', 'claude')} for role in sync.ROLES}}
        self.catalog = {platform: {platform + '-future-9': ['ultra']}
                        for platform in ('codex', 'claude')}
        self.policy_path = Path(self.temp.name) / 'policy.json'
        self.catalog_path = Path(self.temp.name) / 'catalog.json'
        self.catalog_path.write_text(json.dumps(self.catalog))

    def run_cli(self, apply=False, catalog=True):
        self.policy_path.write_text(json.dumps(self.policy))
        argv = [str(self.policy_path), '--root', str(self.root)]
        if catalog:
            argv += ['--catalog', str(self.catalog_path)]
        if apply:
            argv += ['--apply']
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return sync.main(argv)

    def seed(self):
        for role in sync.ROLES:
            files = {
                f'.codex/agents/{role}.toml': (
                    f'name = "{role}"\nmodel = "old" # keep\nmodel_reasoning_effort = "low"\n'
                    'developer_instructions = """Preserve my prompt\nmodel = \\\"quoted text\\\"\n"""\n'
                    'sandbox_mode = "read-only"\n[tools]\nshell = false\n'),
                f'.claude/agents/{role}.md': (
                    f'---\nname: {role}\nmodel: old\neffort: low\n'
                    'tools: [Read, Grep]\npermissionMode: plan\ndescription: |\n  Preserve description\n'
                    '---\n\nPreserve my prompt exactly.\n'),
                f'.agents/roles/{role}.toml': (
                    f'name = "{role}"\ninstructions = "Do my job"\n'
                    '[codex]\nmodel = "old"\neffort = "low"\n'
                    '[claude]\nmodel = "old"\neffort = "low"\n'),
            }
            for name, value in files.items():
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_preview_does_not_create_root(self):
        self.assertEqual(self.run_cli(catalog=False), 0)
        self.assertFalse(self.root.exists())

    def test_apply_bootstraps_and_accepts_future_catalog_models(self):
        self.assertEqual(self.run_cli(apply=True), 0)
        self.assertEqual(len(list((self.root / '.codex/agents').glob('*.toml'))), len(sync.ROLES))
        self.assertEqual(len(list((self.root / '.claude/agents').glob('*.md'))), len(sync.ROLES))
        parsed = tomllib.loads((self.root / '.codex/agents/reviewer.toml').read_text())
        self.assertEqual(parsed['model'], 'codex-future-9')
        self.assertEqual(parsed['model_reasoning_effort'], 'ultra')

    def test_apply_preserves_prompts_permissions_and_shared_sources(self):
        self.seed()
        self.assertEqual(self.run_cli(apply=True), 0)
        for role in sync.ROLES:
            codex = (self.root / f'.codex/agents/{role}.toml').read_text()
            parsed = tomllib.loads(codex)
            self.assertEqual(parsed['sandbox_mode'], 'read-only')
            self.assertEqual(parsed['tools'], {'shell': False})
            self.assertIn('Preserve my prompt', parsed['developer_instructions'])
            self.assertIn(' # keep', codex)
            claude = (self.root / f'.claude/agents/{role}.md').read_text()
            self.assertIn('tools: [Read, Grep]\npermissionMode: plan\n', claude)
            self.assertTrue(claude.endswith('Preserve my prompt exactly.\n'))
            shared = tomllib.loads((self.root / f'.agents/roles/{role}.toml').read_text())
            self.assertEqual(shared['instructions'], 'Do my job')
            self.assertEqual(shared['codex'], self.policy['roles'][role]['codex'])
        self.assertEqual(len(list((self.root / '.agents/s-agent-backups').glob('*/.codex/agents/reviewer.toml'))), 1)

    def test_repeated_apply_does_not_rewrite_or_backup(self):
        self.assertEqual(self.run_cli(apply=True), 0)
        before = {path: path.stat().st_mtime_ns for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(self.run_cli(apply=True), 0)
        self.assertEqual(before, {path: path.stat().st_mtime_ns for path in self.root.rglob('*') if path.is_file()})

    def test_invalid_policy_or_capabilities_never_writes(self):
        self.seed()
        baseline = self.snapshot()
        original = copy.deepcopy(self.policy)
        for mutate in (
            lambda p: p['roles']['reviewer']['codex'].update(model='unknown'),
            lambda p: p['roles']['reviewer']['codex'].update(effort='unknown'),
            lambda p: p['roles'].update(intruder=p['roles']['reviewer']),
            lambda p: p['roles']['reviewer']['codex'].update(instructions='execute'),
            lambda p: p.update(tools=['shell']),
            lambda p: p.update(schema_version=True),
        ):
            with self.subTest(mutate=mutate):
                self.policy = copy.deepcopy(original)
                mutate(self.policy)
                self.assertEqual(self.run_cli(apply=True), 1)
                self.assertEqual(self.snapshot(), baseline)

    def test_existing_preview_and_invalid_json_do_not_write(self):
        self.seed()
        before = self.snapshot()
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(before, self.snapshot())
        self.policy_path.write_text('{broken json')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sync.main([str(self.policy_path), '--root', str(self.root),
                                        '--catalog', str(self.catalog_path), '--apply']), 1)
        self.assertEqual(before, self.snapshot())

    def test_unknown_complex_toml_is_rejected_before_writes(self):
        self.seed()
        target = self.root / '.codex/agents/devops.toml'
        target.write_text('model = """old"""\nmodel_reasoning_effort = "low"\n')
        before = self.snapshot()
        self.assertEqual(self.run_cli(apply=True), 1)
        self.assertEqual(before, self.snapshot())

    def test_existing_modes_and_unrelated_roles_are_preserved(self):
        self.seed()
        target = self.root / '.codex/agents/reviewer.toml'
        target.chmod(0o600)
        unrelated = self.root / '.codex/agents/custom.toml'
        unrelated.write_text('model = "custom"\n')
        before = unrelated.read_bytes()
        self.assertEqual(self.run_cli(apply=True), 0)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(unrelated.read_bytes(), before)

    def test_catalog_can_add_future_model_notation_without_code_changes(self):
        for role in self.policy['roles'].values():
            role['claude']['model'] = 'claude-next[1m]'
        self.catalog['claude'] = {'claude-next[1m]': ['ultra']}
        self.catalog_path.write_text(json.dumps(self.catalog))
        self.assertEqual(self.run_cli(apply=True), 0)
        self.assertEqual(self.run_cli(apply=True), 0)

    def test_apply_requires_catalog(self):
        self.assertEqual(self.run_cli(apply=True, catalog=False), 1)
        self.assertFalse(self.root.exists())

    def configure_gemini(self):
        for role in self.policy['roles'].values():
            role['gemini'] = {'model': 'gemini-4-argon', 'effort': 'medium'}
        self.catalog['gemini'] = {'gemini-4-argon': ['medium', 'high']}
        self.catalog_path.write_text(json.dumps(self.catalog))

    def test_gemini_creates_shared_exact_settings_and_native_inherited_profile(self):
        self.configure_gemini()
        self.assertEqual(self.run_cli(apply=True), 0)
        shared = tomllib.loads((self.root / '.agents/roles/executor.toml').read_text())
        self.assertEqual(shared['gemini'], self.policy['roles']['executor']['gemini'])
        native = (self.root / '.gemini/config/agents/executor.md').read_text()
        self.assertIn('model: "inherit"\n', native)
        self.assertNotIn('effort:', native)
        self.assertNotIn('gemini-4-argon', native)
        before = {path: path.stat().st_mtime_ns for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(self.run_cli(apply=True), 0)
        self.assertEqual(before, {path: path.stat().st_mtime_ns for path in self.root.rglob('*') if path.is_file()})

    def test_gemini_extends_shared_source_and_preserves_native_prompt_and_permissions(self):
        self.seed()
        self.configure_gemini()
        target = self.root / '.gemini/config/agents/reviewer.md'
        target.parent.mkdir(parents=True)
        target.write_text('---\nname: reviewer\nmodel: flash\ntools: [view_file]\n'
                          'commandExecutionPolicy: off\n---\n\nKeep this prompt.\n')
        self.assertEqual(self.run_cli(apply=True), 0)
        native = target.read_text()
        self.assertIn('tools: [view_file]\ncommandExecutionPolicy: off\n', native)
        self.assertTrue(native.endswith('Keep this prompt.\n'))
        shared = tomllib.loads((self.root / '.agents/roles/reviewer.toml').read_text())
        self.assertEqual(shared['instructions'], 'Do my job')
        self.assertEqual(shared['gemini'], self.policy['roles']['reviewer']['gemini'])

    def test_partial_or_unsupported_gemini_policy_does_not_write(self):
        self.configure_gemini()
        del self.policy['roles']['reviewer']['gemini']
        self.assertEqual(self.run_cli(apply=True), 1)
        self.assertFalse(self.root.exists())
        self.policy['roles']['reviewer']['gemini'] = {'model': 'gemini-4-argon', 'effort': 'max'}
        self.assertEqual(self.run_cli(apply=True), 1)
        self.assertFalse(self.root.exists())

    def test_hydrogen_levels_sync_and_other_gemini_models_reject_xhigh(self):
        self.configure_gemini()
        self.catalog['gemini']['gemini-4-hydrogen'] = ['low', 'medium', 'high', 'xhigh']
        for effort in ('low', 'medium', 'high', 'xhigh'):
            with self.subTest(effort=effort):
                self.policy['roles']['executor']['gemini'] = {'model': 'gemini-4-hydrogen', 'effort': effort}
                self.catalog_path.write_text(json.dumps(self.catalog))
                self.assertEqual(self.run_cli(apply=True), 0)
                shared = tomllib.loads((self.root / '.agents/roles/executor.toml').read_text())
                self.assertEqual(shared['gemini'], self.policy['roles']['executor']['gemini'])
        baseline = self.snapshot()
        for model in sync.GEMINI_EFFORTS:
            invalid = 'minimal' if model == 'gemini-4-hydrogen' else 'xhigh'
            self.policy['roles']['executor']['gemini'] = {'model': model, 'effort': invalid}
            # Even a mistaken runtime catalog must not bypass known model constraints.
            self.catalog['gemini'][model] = [invalid]
            self.catalog_path.write_text(json.dumps(self.catalog))
            self.assertEqual(self.run_cli(apply=True), 1)
            self.assertEqual(self.snapshot(), baseline)
            with self.assertRaisesRegex(ValueError, 'unsupported effort'):
                sync.validate(self.policy)

    def test_bad_last_target_prevents_entire_batch(self):
        self.seed()
        (self.root / '.claude/agents/devops.md').write_text('---\nmodel: *alias\n---\n')
        before = self.snapshot()
        self.assertEqual(self.run_cli(apply=True), 1)
        self.assertEqual(before, self.snapshot())

    def test_indented_delimiter_in_block_description_is_preserved(self):
        self.seed()
        target = self.root / '.claude/agents/reviewer.md'
        description = 'description: |\n  instructions\n  ---\n  other\n'
        target.write_text('---\nname: reviewer\nmodel: old\n' + description +
                          'tools: [Read, Grep]\n---\n\nPreserve body.\n')
        self.assertEqual(self.run_cli(apply=True), 0)
        after = target.read_text()
        self.assertIn(description + 'tools: [Read, Grep]\n', after)
        self.assertIn('tools: [Read, Grep]\neffort: "ultra"\n---\n', after)
        self.assertEqual(after.count('model:'), 1)
        self.assertTrue(after.endswith('Preserve body.\n'))
        self.assertEqual(self.run_cli(apply=True), 0)

    def test_malformed_flow_list_and_unsupported_yaml_never_write(self):
        self.seed()
        target = self.root / '.claude/agents/devops.md'
        for invalid in ('tools: [Read, Grep', 'tools: [Read, [Grep]]',
                        'tools: [Read, "Grep]', 'tools: {Read: true}',
                        'permissions:\n  mode: bypassPermissions',
                        'description: text\n  illegal continuation'):
            with self.subTest(frontmatter=invalid):
                target.write_text('---\nname: devops\nmodel: old\neffort: low\n' + invalid + '\n---\nPrompt\n')
                before = self.snapshot()
                self.assertEqual(self.run_cli(apply=True), 1)
                self.assertEqual(before, self.snapshot())

    def test_validate_only_ignores_broken_profiles_and_does_not_write(self):
        self.seed()
        (self.root / '.claude/agents/devops.md').write_text('not valid frontmatter')
        self.policy_path.write_text(json.dumps(self.policy))
        before = self.snapshot()
        with mock.patch.object(sync, 'plan', side_effect=AssertionError('profiles must not be read')):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(sync.main([str(self.policy_path), '--root', str(self.root),
                                            '--catalog', str(self.catalog_path), '--validate-only']), 0)
                self.assertEqual(sync.main([str(self.policy_path), '--root', str(self.root),
                                            '--validate-only', '--apply']), 1)
        self.assertEqual(before, self.snapshot())

    def test_failure_rolls_back_existing_and_new_files(self):
        for seed in (False, True):
            with self.subTest(seed=seed):
                if seed:
                    self.seed()
                before = {key: value for key, value in self.snapshot().items() if 's-agent-backups' not in key}
                changes = sync.plan(self.root, self.policy)
                real_write = sync.atomic_write
                count = 0
                def fail_third(*args):
                    nonlocal count
                    count += 1
                    if count == 3:
                        raise OSError('injected write failure')
                    real_write(*args)
                with mock.patch.object(sync, 'atomic_write', side_effect=fail_third):
                    with self.assertRaisesRegex(OSError, 'injected'):
                        sync.apply(self.root, changes)
                after = {key: value for key, value in self.snapshot().items() if 's-agent-backups' not in key}
                self.assertEqual(before, after)

    def test_stdin_policy_and_source_url(self):
        with mock.patch.object(sync.sys, 'stdin', io.StringIO(json.dumps(self.policy))):
            self.assertEqual(sync.read_json('-'), self.policy)
        changes = sync.plan(self.root, self.policy, 'https://notion.so/policy')
        sync.apply(self.root, changes)
        record = json.loads((self.root / '.agents/s-agent-source.json').read_text())
        self.assertEqual(record['source_url'], 'https://notion.so/policy')

    def test_duplicate_json_and_symlinks_rejected(self):
        self.policy_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            sync.read_json(str(self.policy_path))
        self.root.mkdir()
        (self.root / '.codex').symlink_to(Path(self.temp.name), target_is_directory=True)
        self.assertEqual(self.run_cli(apply=True), 1)
        self.assertFalse((Path(self.temp.name) / 'agents').exists())


if __name__ == '__main__':
    unittest.main()

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI))
import apply as renderer  # noqa: E402
import check as checker  # noqa: E402
import preflight  # noqa: E402
import settings  # noqa: E402

BASE = {'repository': 'acme/widget', 'stack': 'node',
        'production_reviewer': {'login': 'boss', 'id': 42}}


def project(config=None, version='1.2.3'):
    scratch = tempfile.TemporaryDirectory()
    root = Path(scratch.name)
    (root / '.github').mkdir()
    (root / '.github/cicd.json').write_text(json.dumps({**BASE, **(config or {})}))
    (root / 'package.json').write_text(json.dumps({'name': 'widget', 'version': version}))
    return scratch, root


def render(root, **options):
    return renderer.main(['--target', str(root), *options.get('args', [])])


class RenderTest(unittest.TestCase):
    def test_renders_full_gitflow_release_pipeline(self):
        scratch, root = project()
        self.addCleanup(scratch.cleanup)
        self.assertEqual(render(root), 0)
        for name in ['.github/gitflow.json', '.github/workflows/ci.yml', '.github/workflows/release.yml',
                     '.github/dependabot.yml', 'tool/release.py', 'tool/ci-step.sh', 'ci.mk',
                     'docs/GITFLOW.md', 'docs/DEPLOYMENT.md', 'CHANGELOG.md']:
            self.assertTrue((root / name).is_file(), name)
        self.assertTrue((root / 'tool/ci-step.sh').stat().st_mode & 0o100)
        self.assertFalse((root / 'tool/container.py').exists())
        policy = json.loads((root / '.github/gitflow.json').read_text())
        self.assertEqual((policy['production'], policy['integration']), ('main', 'develop'))
        ci = (root / '.github/workflows/ci.yml').read_text()
        self.assertIn("startsWith(github.head_ref, 'codex/hotfix/')", ci)
        self.assertIn('actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0', ci)
        self.assertEqual(checker.check(root)[0], [])

    def test_rendered_tool_tests_pass(self):
        scratch, root = project()
        self.addCleanup(scratch.cleanup)
        render(root)
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'test/tool', '-p', 'test_*.py'],
                                cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dry_run_changes_nothing_and_rerun_is_idempotent(self):
        scratch, root = project()
        self.addCleanup(scratch.cleanup)
        render(root, args=['--dry-run'])
        self.assertFalse((root / '.github/workflows').exists())
        render(root)
        before = {p: p.read_text() for p in root.rglob('*') if p.is_file()}
        render(root)
        self.assertEqual(before, {p: p.read_text() for p in root.rglob('*') if p.is_file()})

    def test_seed_and_hand_edited_files_are_protected_unless_forced(self):
        scratch, root = project()
        self.addCleanup(scratch.cleanup)
        render(root)
        (root / 'CHANGELOG.md').write_text('mine')
        (root / 'docs/GITFLOW.md').write_text('mine')
        render(root)
        self.assertEqual((root / 'docs/GITFLOW.md').read_text(), 'mine')
        render(root, args=['--force'])
        self.assertNotEqual((root / 'docs/GITFLOW.md').read_text(), 'mine')
        self.assertEqual((root / 'CHANGELOG.md').read_text(), 'mine')

    def test_container_and_pages_repo_features(self):
        scratch, root = project({'features': {'container': True, 'pages_repo': True},
                                 'pages_repo': {'repository': 'acme/site'}})
        self.addCleanup(scratch.cleanup)
        render(root)
        release = (root / '.github/workflows/release.yml').read_text()
        for expected in ['packages: write', 'container.py publish', 'publish_website.py', 'secrets.DEPLOY_TOKEN']:
            self.assertIn(expected, release)
        self.assertNotIn('deploy-pages', release)
        self.assertTrue((root / 'tool/container.py').is_file() and (root / 'Dockerfile').is_file())
        self.assertIn('image.test', (root / 'ci.mk').read_text())
        self.assertEqual(checker.check(root)[0], [])

    def test_same_repo_pages_feature(self):
        scratch, root = project({'features': {'pages': True}})
        self.addCleanup(scratch.cleanup)
        render(root)
        release = (root / '.github/workflows/release.yml').read_text()
        self.assertIn('deploy-pages@', release)
        self.assertIn('pages: write', release)
        self.assertNotIn('packages: write', release)

    def test_tag_prefix_and_custom_branches(self):
        scratch, root = project({'tag_prefix': 'v', 'production_branch': 'trunk', 'integration_branch': 'dev'})
        self.addCleanup(scratch.cleanup)
        render(root)
        self.assertIn("github.base_ref == 'dev'", (root / '.github/workflows/ci.yml').read_text())
        self.assertIn('refs/heads/trunk', (root / '.github/workflows/release.yml').read_text())
        self.assertEqual(json.loads((root / '.github/cicd.json').read_text())['tag_prefix'], 'v')

    def test_every_stack_renders_a_consistent_pipeline(self):
        for stack in renderer.STACKS:
            scratch, root = project({'stack': stack})
            self.addCleanup(scratch.cleanup)
            self.assertEqual(render(root), 0, stack)
            (root / 'package.json').unlink()
            stack_cfg = json.loads((root / '.github/cicd.json').read_text())
            versions = {'node': '{"version": "1.0.0"}', 'flutter': 'version: 1.0.0\n',
                        'go': '1.0.0\n', 'static': '1.0.0\n'}
            (root / stack_cfg['version_file']).write_text(versions.get(stack, 'version = "1.0.0"\n'))
            self.assertEqual(checker.check(root)[0], [], stack)


class ReleaseBundleTest(unittest.TestCase):
    def test_prepare_verify_roundtrip_detects_tampering(self):
        scratch, root = project()
        self.addCleanup(scratch.cleanup)
        render(root)
        (root / 'CHANGELOG.md').write_text('# Changelog\n\n## [1.2.3] - 2026-10-21\n\nFirst.\n')
        (root / 'dist').mkdir()
        (root / 'dist/index.html').write_text('hi')
        for command in (['init', '-q'], ['add', '-A'], ['-c', 'user.name=t', '-c', 'user.email=t@t',
                                                       'commit', '-qm', 'init']):
            subprocess.run(['git', *command], cwd=root, check=True)

        def tool(*args):
            return subprocess.run([sys.executable, 'tool/release.py', *args], cwd=root,
                                  capture_output=True, text=True)
        self.assertEqual(tool('prepare').returncode, 0)
        self.assertEqual(tool('verify', '--extract', 'build/site').returncode, 0)
        self.assertEqual((root / 'build/site/index.html').read_text(), 'hi')
        (root / 'build/release/widget-1.2.3.tar.gz').write_bytes(b'tampered')
        self.assertNotEqual(tool('verify').returncode, 0)


class ValidationTest(unittest.TestCase):
    def resolve(self, **changes):
        return renderer.resolve({**BASE, **changes})

    def test_rejects_bad_configuration(self):
        for changes in [{'repository': ''}, {'repository': 'nope'}, {'stack': 'cobol'},
                        {'project': 'Bad Name'}, {'production_branch': 'develop'},
                        {'tag_prefix': 'v 1'}, {'features': {'pages': True, 'pages_repo': True}},
                        {'commands': {'verify': 'a\nb'}}, {'commands': {'verify': '{{x}}'}},
                        {'artifact_dir': '../out'}, {'agent_prefixes': ['Bad']},
                        {'production_reviewer': {'login': 'x', 'id': 'one'}},
                        {'features': {'pages_repo': True}, 'pages_repo': {'repository': 'bad'}}]:
            with self.assertRaises(renderer.ConfigError, msg=str(changes)):
                self.resolve(**changes)

    def test_missing_reviewer_is_a_warning_not_an_error(self):
        cfg = renderer.resolve({'repository': 'a/b', 'stack': 'go'})
        self.assertTrue(renderer.warnings(cfg))

    def test_cli_reports_config_errors_with_exit_2(self):
        scratch, root = project({'stack': 'cobol'})
        self.addCleanup(scratch.cleanup)
        self.assertEqual(render(root), 2)

    def test_pins_are_full_commit_shas(self):
        for name, entry in renderer.load_pins().items():
            if not name.startswith('_'):
                self.assertRegex(entry['sha'], r'^[0-9a-f]{40}$', name)


class CheckTest(unittest.TestCase):
    def rendered(self):
        scratch, root = project()
        self.addCleanup(scratch.cleanup)
        render(root)
        return root

    def test_detects_unpinned_actions(self):
        root = self.rendered()
        workflow = root / '.github/workflows/ci.yml'
        workflow.write_text(workflow.read_text().replace('actions/checkout@', 'actions/checkout@v7 #', 1))
        self.assertTrue(any('not pinned' in e for e in checker.check(root)[0]))

    def test_detects_required_check_without_job(self):
        root = self.rendered()
        workflow = root / '.github/workflows/ci.yml'
        workflow.write_text(workflow.read_text().replace('name: Security', 'name: Sec'))
        self.assertTrue(any('"Security"' in e for e in checker.check(root)[0]))

    def test_detects_leftover_placeholders_and_missing_files(self):
        root = self.rendered()
        (root / 'ci.mk').write_text('{{CMD_DEPS}}')
        (root / 'tool/release.py').unlink()
        errors = checker.check(root)[0]
        self.assertTrue(any('unresolved placeholder' in e for e in errors))
        self.assertTrue(any('tool/release.py: missing' in e for e in errors))

    def test_detects_bad_version(self):
        root = self.rendered()
        (root / 'package.json').write_text('{"version": "1.2"}')
        self.assertTrue(any('MAJOR.MINOR.PATCH' in e for e in checker.check(root)[0]))


class SettingsTest(unittest.TestCase):
    def test_branch_protection_and_production_environment(self):
        cfg = renderer.resolve(BASE)
        planned = settings.calls(cfg)
        paths = [path for _, path, _ in planned]
        self.assertIn('/repos/acme/widget/branches/main/protection', paths)
        self.assertIn('/repos/acme/widget/branches/develop/protection', paths)
        protection = planned[0][2]
        self.assertEqual(protection['required_status_checks']['contexts'], ['Branch policy', 'Verify', 'Security'])
        self.assertFalse(protection['allow_force_pushes'])
        environment = next(p for _, path, p in planned if path.endswith('/environments/production'))
        self.assertEqual(environment['reviewers'], [{'type': 'User', 'id': 42}])
        self.assertEqual(planned[-1][2], {'name': 'main', 'type': 'branch'})

    def test_requires_reviewer(self):
        with self.assertRaises(renderer.ConfigError):
            settings.calls(renderer.resolve({'repository': 'a/b', 'stack': 'go'}))


class FakeGitHub:
    def __init__(self, existing):
        self.existing = existing

    def __call__(self, path):
        return self.existing.get(path)


SOURCE = {'/repos/acme/widget': {'permissions': {'admin': True}},
          '/repos/acme/widget/branches/main': {}, '/repos/acme/widget/branches/develop': {},
          '/users/boss': {'id': 42}}


class PreflightTest(unittest.TestCase):
    site = {'features': {'pages_repo': True}, 'pages_repo': {'repository': 'acme/site'}}

    def run_preflight(self, existing, **changes):
        cfg = renderer.resolve({**BASE, **changes})
        return preflight.preflight(cfg, FakeGitHub(existing))

    def test_passes_when_everything_exists(self):
        existing = {**SOURCE, '/repos/acme/site': {'permissions': {'push': True}},
                    '/repos/acme/site/branches/main': {}}
        self.assertEqual(self.run_preflight(existing, **self.site)[0], [])

    def test_requires_the_site_repository_to_exist(self):
        errors = self.run_preflight(SOURCE, **self.site)[0]
        self.assertTrue(any('acme/site' in e and 'does not exist' in e for e in errors))

    def test_site_branch_must_exist(self):
        existing = {**SOURCE, '/repos/acme/site': {}}
        self.assertTrue(any('branch "main"' in e for e in self.run_preflight(existing, **self.site)[0]))

    def test_missing_source_repo_branches_and_wrong_reviewer_id(self):
        self.assertTrue(any('not found' in e for e in self.run_preflight({})[0]))
        existing = {'/repos/acme/widget': {}, '/users/boss': {'id': 7}}
        errors = self.run_preflight(existing)[0]
        self.assertTrue(any('"develop" does not exist' in e for e in errors))
        self.assertTrue(any('should be 7' in e for e in errors))

    def test_no_site_checks_without_the_feature(self):
        self.assertEqual(self.run_preflight(SOURCE)[0], [])


class SecretTest(unittest.TestCase):
    def test_secret_command_targets_production_environment_without_value_in_argv(self):
        cfg = renderer.resolve({**BASE, 'features': {'pages_repo': True},
                                'pages_repo': {'repository': 'acme/site', 'secret': 'SITE_TOKEN'}})
        command = settings.secret_command(cfg)
        self.assertEqual(command, ['gh', 'secret', 'set', 'SITE_TOKEN', '--env', 'production', '--repo', 'acme/widget'])
        with self.assertRaises(renderer.ConfigError):
            settings.secret_command(renderer.resolve(BASE))


if __name__ == '__main__':
    unittest.main()

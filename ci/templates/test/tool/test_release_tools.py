import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[2] / 'tool'
sys.path.insert(0, str(TOOL))
import gitflow_check  # noqa: E402
import release  # noqa: E402
import release_guard  # noqa: E402

POLICY = json.loads((TOOL.parent / '.github/gitflow.json').read_text())
SHA = 'a' * 40


class GitflowTest(unittest.TestCase):
    def test_accepts_standard_flows(self):
        main, dev = POLICY['production'], POLICY['integration']
        for head, base in [('feature/x', dev), ('codex/bugfix/fix-1', dev), ('hotfix/urgent', main),
                           ('release/1.2.3', dev), (dev, main), ('dependabot/npm/x', dev)]:
            gitflow_check.check(head, base, POLICY)

    def test_rejects_wrong_direction_and_names(self):
        main, dev = POLICY['production'], POLICY['integration']
        for head, base in [('feature/x', main), ('hotfix/x', dev), ('release/v1.2', dev),
                           ('random-branch', dev), ('feature/Bad Name', dev)]:
            with self.assertRaises(ValueError, msg=head):
                gitflow_check.check(head, base, POLICY)


class ReleaseTest(unittest.TestCase):
    def test_release_plan_never_moves_tags_or_replaces_assets(self):
        expected = {'a.tgz': {'bytes': 1, 'sha256': 'x'}}
        name = release.tag_for('1.0.0')
        self.assertEqual(release.release_plan('1.0.0', SHA, None, None, expected), ['a.tgz'])
        with self.assertRaises(ValueError):
            release.release_plan('1.0.0', SHA, {'object': {'type': 'commit', 'sha': 'b' * 40}}, None, expected)
        published = {'tag_name': name, 'body': f'Source: {release.REPOSITORY}@{SHA}', 'draft': False,
                     'assets': [{'name': 'a.tgz', 'state': 'uploaded', 'size': 2, 'digest': 'sha256:x'}]}
        with self.assertRaises(ValueError):
            release.release_plan('1.0.0', SHA, {'object': {'type': 'commit', 'sha': SHA}}, published, expected)

    def test_unsafe_archive_paths_are_rejected(self):
        for name in ['../x', '/etc/passwd', 'a\\b']:
            with self.assertRaises(ValueError):
                release.safe_path(name)

    def test_site_files_fingerprints_regular_files_only(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / 'a.txt').write_text('hi')
            self.assertEqual(list(release.site_files(root)), ['a.txt'])
            os.symlink(root / 'a.txt', root / 'link')
            with self.assertRaises(ValueError):
                release.site_files(root)

    def test_approval_needs_the_configured_human_and_no_rejection(self):
        release_guard.OWNER_ID = 42
        review = {'state': 'approved', 'user': {'type': 'User', 'id': 42},
                  'environments': [{'id': 7, 'name': 'production'}]}
        self.assertTrue(release_guard.approved([review], 7))
        self.assertFalse(release_guard.approved([{**review, 'user': {'type': 'Bot', 'id': 42}}], 7))
        self.assertFalse(release_guard.approved([review, {**review, 'state': 'rejected'}], 7))


if __name__ == '__main__':
    unittest.main()

"""Tests for the git information of the caption files."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))

from utils.git_info import (GitCaptionState, compute_diff,  # noqa: E402
                            find_repository_root, split_tags)


def run_git(repository_root: Path, *args: str):
    subprocess.run(['git', *args], cwd=repository_root, check=True,
                   capture_output=True)


class SplitTagsTest(unittest.TestCase):
    def test_splits_a_comma_separated_caption(self):
        self.assertEqual(split_tags('1girl, smiling, solo'),
                         ['1girl', 'smiling', 'solo'])

    def test_splits_a_row_based_caption(self):
        self.assertEqual(split_tags('1girl\nsmiling\nsolo'),
                         ['1girl', 'smiling', 'solo'])

    def test_skips_comments_and_empty_tags(self):
        self.assertEqual(split_tags('# comment\n1girl, , solo'),
                         ['1girl', 'solo'])


class ComputeDiffTest(unittest.TestCase):
    def test_added_and_removed_tags(self):
        diff = compute_diff(['a', 'b', 'c'], ['a', 'c', 'd'])
        self.assertTrue(diff.is_modified)
        self.assertEqual(diff.added_tags, ['d'])
        self.assertEqual(diff.removed_tags, ['b'])

    def test_unchanged_caption_is_not_modified(self):
        diff = compute_diff(['a', 'b'], ['a', 'b'])
        self.assertFalse(diff.is_modified)
        self.assertEqual(diff.added_tags, [])
        self.assertEqual(diff.removed_tags, [])

    def test_untracked_file_has_all_tags_as_added(self):
        diff = compute_diff(None, ['a', 'b'])
        self.assertTrue(diff.is_modified)
        self.assertTrue(diff.is_new)
        self.assertEqual(diff.added_tags, ['a', 'b'])


class GitCaptionStateTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        run_git(self.root, 'init')
        run_git(self.root, 'config', 'user.email', 'test@example.com')
        run_git(self.root, 'config', 'user.name', 'Test')
        # The global configuration may sign the commits, which fails without
        # a key.
        run_git(self.root, 'config', 'commit.gpgsign', 'false')
        self.caption_path = self.root / 'photo.txt'
        self.caption_path.write_text('mytrigger, 1girl, smiling')
        run_git(self.root, 'add', 'photo.txt')
        run_git(self.root, 'commit', '-m', 'initial')

    def tearDown(self):
        self.directory.cleanup()

    def test_finds_the_repository_root(self):
        # The root is resolved, because git reports the real path.
        self.assertEqual(find_repository_root(self.root), self.root.resolve())

    def test_no_repository_outside_a_repository(self):
        with tempfile.TemporaryDirectory() as outside:
            # A directory outside any repository has no root.
            self.assertIsNone(find_repository_root(Path(outside)))

    def test_unchanged_caption_has_no_diff(self):
        state = GitCaptionState(self.root)
        diff = state.get_diff(self.caption_path, ['mytrigger', '1girl',
                                                  'smiling'])
        self.assertFalse(diff.is_modified)

    def test_changed_caption_reports_the_changes(self):
        self.caption_path.write_text('mytrigger, 1girl, hat')
        state = GitCaptionState(self.root)
        diff = state.get_diff(self.caption_path, ['mytrigger', '1girl', 'hat'])
        self.assertTrue(diff.is_modified)
        self.assertEqual(diff.added_tags, ['hat'])
        self.assertEqual(diff.removed_tags, ['smiling'])

    def test_untracked_caption_is_reported_as_new(self):
        new_path = self.root / 'new.txt'
        new_path.write_text('mytrigger, solo')
        state = GitCaptionState(self.root)
        diff = state.get_diff(new_path, ['mytrigger', 'solo'])
        self.assertTrue(diff.is_modified)
        self.assertTrue(diff.is_new)

    def test_batch_diffs_cover_every_changed_caption(self):
        second_path = self.root / 'second.txt'
        second_path.write_text('mytrigger, 1girl')
        run_git(self.root, 'add', 'second.txt')
        run_git(self.root, 'commit', '-m', 'second')
        second_path.write_text('mytrigger, 1girl, hat')
        self.caption_path.write_text('mytrigger, 1girl, smiling, hat')
        state = GitCaptionState(self.root)
        diffs = state.get_diffs(
            [self.caption_path, second_path],
            {self.caption_path: ['mytrigger', '1girl', 'smiling', 'hat'],
             second_path: ['mytrigger', '1girl', 'hat']})
        self.assertEqual(set(diffs), {self.caption_path, second_path})
        self.assertEqual(diffs[self.caption_path].added_tags, ['hat'])
        self.assertEqual(diffs[second_path].added_tags, ['hat'])

    def test_unchanged_captions_are_left_out_of_the_batch(self):
        state = GitCaptionState(self.root)
        diffs = state.get_diffs([self.caption_path],
                                {self.caption_path: ['mytrigger', '1girl',
                                                     'smiling']})
        self.assertEqual(diffs, {})


if __name__ == '__main__':
    unittest.main()

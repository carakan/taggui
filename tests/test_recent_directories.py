"""Tests for the list of the directories that were opened last.

The tests check the list that is kept between the runs, and the
`Open Recent` menu of the file menu.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))
sys.path.insert(0, str(Path(__file__).parent))

# The tests use settings of their own, to keep away from the ones
# of the user.
import settings_isolation  # noqa: E402,F401

from utils.recent_directories import (MAXIMUM,  # noqa: E402
                                      add_recent_directory,
                                      clear_recent_directories,
                                      get_recent_directories,
                                      remove_missing_directories)


class RecentDirectoriesTest(unittest.TestCase):
    """The list of the directories that were opened last."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.first = self.root / 'first'
        self.second = self.root / 'second'
        self.first.mkdir()
        self.second.mkdir()
        self._clear()

    def tearDown(self):
        self._clear()
        self.directory.cleanup()

    def _clear(self):
        clear_recent_directories()

    def test_the_list_is_empty_at_the_start(self):
        self.assertEqual(get_recent_directories(), [])

    def test_a_directory_is_added_to_the_list(self):
        add_recent_directory(self.first)
        self.assertEqual(get_recent_directories(), [self.first])

    def test_the_most_recent_directory_comes_first(self):
        add_recent_directory(self.first)
        add_recent_directory(self.second)
        self.assertEqual(get_recent_directories(), [self.second, self.first])

    def test_a_directory_is_not_added_twice(self):
        add_recent_directory(self.first)
        add_recent_directory(self.second)
        add_recent_directory(self.first)
        self.assertEqual(get_recent_directories(), [self.first, self.second])

    def test_the_oldest_directory_is_dropped_when_the_list_is_full(self):
        for index in range(MAXIMUM + 2):
            directory = self.root / f'folder{index}'
            directory.mkdir()
            add_recent_directory(directory)
        directories = get_recent_directories()
        self.assertEqual(len(directories), MAXIMUM)
        self.assertEqual(directories[0].name, f'folder{MAXIMUM + 1}')

    def test_a_directory_that_is_gone_is_dropped(self):
        add_recent_directory(self.first)
        add_recent_directory(self.second)
        self.second.rmdir()
        self.assertEqual(remove_missing_directories(), [self.first])
        self.assertEqual(get_recent_directories(), [self.first])

    def test_the_list_is_cleared(self):
        add_recent_directory(self.first)
        clear_recent_directories()
        self.assertEqual(get_recent_directories(), [])


class RecentDirectoriesMenuTest(unittest.TestCase):
    """The `Open Recent` menu of the file menu."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.folder = self.root / 'morenada-shots'
        self.folder.mkdir()
        clear_recent_directories()
        # The window restores the directory of the last run, which would
        # put a directory in the list before the test starts.
        self._clear_directory_path()

    def tearDown(self):
        clear_recent_directories()
        self._clear_directory_path()
        self.directory.cleanup()

    def _clear_directory_path(self):
        from utils.settings import get_settings
        get_settings().remove('directory_path')

    def _make_window(self):
        from widgets.main_window import MainWindow
        window = MainWindow(self.app)
        window.update_recent_directories_menu()
        return window

    def test_the_menu_is_empty_without_recent_directories(self):
        window = self._make_window()
        texts = [action.text() for action in
                 window.recent_directories_menu.actions()]
        self.assertEqual(texts, ['No recent directories'])

    def test_the_directory_is_remembered(self):
        from utils.settings import get_settings
        window = self._make_window()
        window.load_directory(self.folder)
        self.assertEqual(get_settings().value('directory_path', type=str),
                         str(self.folder))

    def test_the_last_project_is_open_when_the_app_starts(self):
        from utils.settings import get_settings
        get_settings().setValue('directory_path', str(self.folder))
        window = self._make_window()
        self.assertEqual(window.directory_path, self.folder)

    def test_a_directory_of_the_menu_is_remembered(self):
        # A project that is opened from the menu is the one the app comes
        # back to.
        from utils.settings import get_settings
        window = self._make_window()
        window.load_directory(self.folder)
        action = [a for a in window.recent_directories_menu.actions()
                  if a.text().startswith('morenada-shots')][0]
        action.trigger()
        self.assertEqual(get_settings().value('directory_path', type=str),
                         str(self.folder))

    def test_a_loaded_directory_is_in_the_menu(self):
        window = self._make_window()
        window.load_directory(self.folder)
        texts = [action.text() for action in
                 window.recent_directories_menu.actions()]
        self.assertIn(f'morenada-shots — {self.root.name}', texts)

    def test_the_menu_has_a_clear_list_action(self):
        window = self._make_window()
        window.load_directory(self.folder)
        texts = [action.text() for action in
                 window.recent_directories_menu.actions()]
        self.assertIn('Clear List', texts)

    def test_the_list_is_cleared_from_the_menu(self):
        window = self._make_window()
        window.load_directory(self.folder)
        window.clear_recent_directories_menu()
        texts = [action.text() for action in
                 window.recent_directories_menu.actions()]
        self.assertEqual(texts, ['No recent directories'])
        self.assertEqual(get_recent_directories(), [])

    def test_an_action_loads_its_directory(self):
        window = self._make_window()
        window.load_directory(self.folder)
        action = window.recent_directories_menu.actions()[0]
        other = self.root / 'other'
        other.mkdir()
        window.load_directory(other)
        # The menu was rebuilt, so the action of the folder is found again.
        action = [a for a in window.recent_directories_menu.actions()
                  if a.text().startswith('morenada-shots')][0]
        action.trigger()
        self.assertEqual(window.directory_path, self.folder)


if __name__ == '__main__':
    unittest.main()

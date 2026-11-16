"""Tests for the deletion of the ignore tags and the base tags.

The tests check the files of the vocabulary directly, and the buttons of
the utilities panel with a stub for the picker dialog.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))

from tagging.vocabulary import (IGNORE_SOURCE_FILE,  # noqa: E402
                                IGNORE_SOURCE_GLOBAL, IGNORE_SOURCE_SECTION,
                                Vocabulary, find_dataset_root, list_base_tags,
                                list_ignore_section_folders, list_ignore_tags,
                                list_shared_section_tags, remove_base_tags,
                                remove_ignore_tags)


class VocabularyRemovalTest(unittest.TestCase):
    """The removal of the tags of the vocabulary files."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.folder = self.root / 'myfolder'
        self.folder.mkdir()
        (self.root / '.ignoretags').write_text(
            'global1, global2\n'
            '#myfolder\n'
            'section1, section2\n'
            '#other\n'
            'other1\n')
        (self.folder / '.ignoretags').write_text('file1\nfile2\n')
        (self.root / '.basetags').write_text('baseroot1\nbaseroot2\n')
        (self.folder / '.basetags').write_text('basefile1\n')

    def tearDown(self):
        self.directory.cleanup()

    def ignore_text(self) -> str:
        return (self.root / '.ignoretags').read_text()

    def base_text(self) -> str:
        return (self.root / '.basetags').read_text()


class ListIgnoreTagsTest(VocabularyRemovalTest):
    """The listing of the ignore tags with their source."""

    def test_every_source_is_listed(self):
        entries = list_ignore_tags(self.root, self.folder)
        self.assertIn(('global1', IGNORE_SOURCE_GLOBAL), entries)
        self.assertIn(('section1', IGNORE_SOURCE_SECTION), entries)
        self.assertIn(('file1', IGNORE_SOURCE_FILE), entries)

    def test_the_other_sections_are_not_listed(self):
        entries = list_ignore_tags(self.root, self.folder)
        self.assertNotIn('other1', [tag for tag, _ in entries])

    def test_a_tag_in_two_sources_is_listed_twice(self):
        (self.root / '.ignoretags').write_text('shared\n#myfolder\nshared\n')
        entries = list_ignore_tags(self.root, self.folder)
        self.assertEqual(
            sorted(source for tag, source in entries if tag == 'shared'),
            [IGNORE_SOURCE_GLOBAL, IGNORE_SOURCE_SECTION])


class ListSharedSectionTagsTest(VocabularyRemovalTest):
    """The listing of the section tags that other projects have too."""

    def test_a_tag_of_one_project_only_is_not_shared(self):
        shared = list_shared_section_tags(self.root, self.folder)
        self.assertNotIn('section1', shared)

    def test_a_tag_of_several_projects_is_shared(self):
        other = self.root / 'otherfolder'
        other.mkdir()
        (self.root / '.ignoretags').write_text(
            '#myfolder\nshared\n'
            '#otherfolder\nshared\n')
        shared = list_shared_section_tags(self.root, self.folder)
        self.assertEqual(shared, {'shared': ['otherfolder']})

    def test_a_section_that_names_several_folders_shares_its_tags(self):
        other = self.root / 'otherfolder'
        other.mkdir()
        (self.root / '.ignoretags').write_text(
            '#myfolder, otherfolder\nshared\n')
        shared = list_shared_section_tags(self.root, self.folder)
        self.assertEqual(shared, {'shared': ['otherfolder']})

    def test_the_global_tags_are_not_shared(self):
        # The global block is shared with every project by itself.
        shared = list_shared_section_tags(self.root, self.folder)
        self.assertNotIn('global1', shared)


class ListBaseTagsTest(VocabularyRemovalTest):
    """The listing of the base tags of a folder."""

    def test_the_root_and_the_folder_tags_are_listed(self):
        tags = list_base_tags(self.root, self.folder)
        self.assertIn('baseroot1', tags)
        self.assertIn('basefile1', tags)

    def test_the_root_tags_come_first(self):
        tags = list_base_tags(self.root, self.folder)
        self.assertEqual(tags[:2], ['baseroot1', 'baseroot2'])

    def test_a_tag_in_both_files_is_listed_once(self):
        (self.root / '.basetags').write_text('baseroot1\n')
        (self.folder / '.basetags').write_text('baseroot1\n')
        tags = list_base_tags(self.root, self.folder)
        self.assertEqual(tags.count('baseroot1'), 1)


class ListIgnoreSectionFoldersTest(VocabularyRemovalTest):
    """The folders that share the `.ignoretags` section of a folder."""

    def test_a_section_of_one_folder_names_that_folder(self):
        self.assertEqual(
            list_ignore_section_folders(self.root, self.folder),
            ['myfolder'])

    def test_a_shared_section_names_every_folder(self):
        (self.root / '.ignoretags').write_text(
            '#myfolder, otherfolder\nshared\n')
        self.assertEqual(
            sorted(list_ignore_section_folders(self.root, self.folder)),
            ['myfolder', 'otherfolder'])

    def test_a_folder_without_a_section_names_nothing(self):
        other = self.root / 'otherfolder'
        other.mkdir()
        self.assertEqual(list_ignore_section_folders(self.root, other), [])


class FindDatasetRootTest(unittest.TestCase):
    """The directory the vocabulary files are read from."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.folder = self.root / 'myfolder'
        self.folder.mkdir()

    def tearDown(self):
        self.directory.cleanup()

    def test_the_directory_itself_is_the_root(self):
        self.assertEqual(find_dataset_root(self.folder), self.folder)

    def test_the_parent_is_the_root_when_it_holds_the_ignore_file(self):
        (self.root / '.ignoretags').write_text('global\n')
        self.assertEqual(find_dataset_root(self.folder), self.root)

    def test_the_parent_is_not_the_root_without_the_ignore_file(self):
        self.assertEqual(find_dataset_root(self.folder), self.folder)

    def test_only_the_parent_is_looked_at(self):
        # The grandparent is not searched, so a dataset of nested
        # projects is not looked at any deeper.
        (self.root / '.ignoretags').write_text('global\n')
        deeper = self.folder / 'deeper'
        deeper.mkdir()
        # The parent of 'deeper' holds no `.ignoretags` file, so 'deeper'
        # is its own root; the grandparent is not searched.
        self.assertEqual(find_dataset_root(deeper), deeper)

    def test_the_root_of_the_filesystem_is_the_root(self):
        self.assertEqual(find_dataset_root(Path('/')), Path('/'))


class RemoveIgnoreTagsTest(VocabularyRemovalTest):
    """The removal of the ignore tags."""

    def test_a_global_tag_is_removed(self):
        removed = remove_ignore_tags(
            self.root, self.folder, [('global1', IGNORE_SOURCE_GLOBAL)])
        self.assertEqual(removed, [('global1', IGNORE_SOURCE_GLOBAL)])
        self.assertNotIn('global1', self.ignore_text())

    def test_the_other_global_tags_are_kept(self):
        remove_ignore_tags(self.root, self.folder,
                           [('global1', IGNORE_SOURCE_GLOBAL)])
        self.assertIn('global2', self.ignore_text())

    def test_a_section_tag_is_removed(self):
        removed = remove_ignore_tags(
            self.root, self.folder, [('section1', IGNORE_SOURCE_SECTION)])
        self.assertEqual(removed, [('section1', IGNORE_SOURCE_SECTION)])
        self.assertNotIn('section1', self.ignore_text())

    def test_the_other_sections_are_kept(self):
        remove_ignore_tags(self.root, self.folder,
                           [('section1', IGNORE_SOURCE_SECTION)])
        self.assertIn('#other', self.ignore_text())
        self.assertIn('other1', self.ignore_text())

    def test_a_folder_file_tag_is_removed(self):
        removed = remove_ignore_tags(
            self.root, self.folder, [('file1', IGNORE_SOURCE_FILE)])
        self.assertEqual(removed, [('file1', IGNORE_SOURCE_FILE)])
        self.assertNotIn('file1',
                         (self.folder / '.ignoretags').read_text())

    def test_the_other_folder_file_tags_are_kept(self):
        remove_ignore_tags(self.root, self.folder,
                           [('file1', IGNORE_SOURCE_FILE)])
        self.assertIn('file2', (self.folder / '.ignoretags').read_text())

    def test_a_global_tag_is_kept_when_a_section_tag_is_removed(self):
        remove_ignore_tags(self.root, self.folder,
                           [('section1', IGNORE_SOURCE_SECTION)])
        self.assertIn('global1', self.ignore_text())

    def test_a_tag_that_is_in_two_sources_is_removed_from_one_only(self):
        (self.root / '.ignoretags').write_text('shared\n#myfolder\nshared\n')
        remove_ignore_tags(self.root, self.folder,
                           [('shared', IGNORE_SOURCE_GLOBAL)])
        self.assertIn('shared', self.ignore_text())
        vocabulary = Vocabulary(self.root)
        self.assertIn('shared', vocabulary.ignore_tags(self.folder))

    def test_a_section_tag_is_removed_from_the_merged_list(self):
        remove_ignore_tags(self.root, self.folder,
                           [('section1', IGNORE_SOURCE_SECTION)])
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('section1', vocabulary.ignore_tags(self.folder))

    def test_a_global_tag_is_removed_from_the_merged_list(self):
        remove_ignore_tags(self.root, self.folder,
                           [('global1', IGNORE_SOURCE_GLOBAL)])
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('global1', vocabulary.ignore_tags(self.folder))

    def test_the_whole_line_is_removed_when_it_is_empty(self):
        remove_ignore_tags(self.root, self.folder,
                           [('section1', IGNORE_SOURCE_SECTION),
                            ('section2', IGNORE_SOURCE_SECTION)])
        self.assertNotIn('section1, section2', self.ignore_text())
        self.assertIn('#myfolder', self.ignore_text())

    def test_a_comment_is_kept(self):
        (self.root / '.ignoretags').write_text(
            '# a comment\nglobal1\n#myfolder\nsection1\n')
        remove_ignore_tags(self.root, self.folder,
                           [('global1', IGNORE_SOURCE_GLOBAL)])
        self.assertIn('# a comment', self.ignore_text())

    def test_a_tag_that_is_not_there_is_not_reported(self):
        removed = remove_ignore_tags(
            self.root, self.folder, [('nosuchtag', IGNORE_SOURCE_GLOBAL)])
        self.assertEqual(removed, [])

    def test_no_file_is_created_when_there_is_none(self):
        (self.root / '.ignoretags').unlink()
        remove_ignore_tags(self.root, self.folder,
                           [('global1', IGNORE_SOURCE_GLOBAL)])
        self.assertFalse((self.root / '.ignoretags').exists())

    def test_a_shared_section_is_edited_and_kept_as_one_section(self):
        # A section that names several folders is one block. The tag is
        # removed from all of them, and the header stays as it is, so
        # that the file does not fill up with a section per project.
        other = self.root / 'otherfolder'
        other.mkdir()
        (self.root / '.ignoretags').write_text(
            '#myfolder, otherfolder\nshared\n')
        remove_ignore_tags(self.root, self.folder,
                           [('shared', IGNORE_SOURCE_SECTION)])
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('shared', vocabulary.ignore_tags(self.folder))
        self.assertNotIn('shared', vocabulary.ignore_tags(other))
        self.assertIn('#myfolder, otherfolder', self.ignore_text())

    def test_a_tag_that_other_projects_have_too_is_removed_from_them(self):
        # The sections of a dataset are often copies of each other, and
        # removing the tag from one of them only would ask for the same
        # work in every other project.
        other = self.root / 'otherfolder'
        other.mkdir()
        (self.root / '.ignoretags').write_text(
            '#myfolder\nshared\n'
            '#otherfolder\nshared\n')
        removed = remove_ignore_tags(self.root, self.folder,
                                     [('shared', IGNORE_SOURCE_SECTION)])
        self.assertEqual(removed, [('shared', IGNORE_SOURCE_SECTION)])
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('shared', vocabulary.ignore_tags(self.folder))
        self.assertNotIn('shared', vocabulary.ignore_tags(other))

    def test_a_tag_of_one_project_only_is_removed_from_it_only(self):
        other = self.root / 'otherfolder'
        other.mkdir()
        (self.root / '.ignoretags').write_text(
            '#myfolder\nmine\n'
            '#otherfolder\ntheirs\n')
        remove_ignore_tags(self.root, self.folder,
                           [('mine', IGNORE_SOURCE_SECTION)])
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('mine', vocabulary.ignore_tags(self.folder))
        self.assertIn('theirs', vocabulary.ignore_tags(other))

    def test_a_tag_is_reported_once_when_several_projects_have_it(self):
        other = self.root / 'otherfolder'
        other.mkdir()
        (self.root / '.ignoretags').write_text(
            '#myfolder\nshared\n'
            '#otherfolder\nshared\n')
        removed = remove_ignore_tags(self.root, self.folder,
                                     [('shared', IGNORE_SOURCE_SECTION)])
        self.assertEqual(removed, [('shared', IGNORE_SOURCE_SECTION)])

    def test_the_root_folder_has_no_folder_file_source(self):
        # The root `.ignoretags` file holds the global block and the
        # sections, so it is not listed as a folder file as well.
        entries = list_ignore_tags(self.root, self.root)
        self.assertNotIn(IGNORE_SOURCE_FILE,
                         [source for _, source in entries])

    def test_a_global_tag_of_the_root_folder_is_removed(self):
        remove_ignore_tags(self.root, self.root,
                           [('global1', IGNORE_SOURCE_GLOBAL)])
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('global1', vocabulary.ignore_tags(self.root))


class RemoveBaseTagsTest(VocabularyRemovalTest):
    """The removal of the base tags."""

    def test_a_root_tag_is_removed(self):
        removed = remove_base_tags(self.root, self.folder, ['baseroot1'])
        self.assertEqual(removed, ['baseroot1'])
        self.assertNotIn('baseroot1', self.base_text())

    def test_the_other_root_tags_are_kept(self):
        remove_base_tags(self.root, self.folder, ['baseroot1'])
        self.assertIn('baseroot2', self.base_text())

    def test_a_folder_tag_is_removed(self):
        removed = remove_base_tags(self.root, self.folder, ['basefile1'])
        self.assertEqual(removed, ['basefile1'])
        self.assertNotIn('basefile1',
                         (self.folder / '.basetags').read_text())

    def test_a_tag_in_both_files_is_removed_from_both(self):
        (self.root / '.basetags').write_text('shared\n')
        (self.folder / '.basetags').write_text('shared\n')
        remove_base_tags(self.root, self.folder, ['shared'])
        self.assertNotIn('shared', self.base_text())
        self.assertNotIn('shared',
                         (self.folder / '.basetags').read_text())

    def test_the_tag_is_not_a_base_tag_any_more(self):
        remove_base_tags(self.root, self.folder, ['baseroot1'])
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('baseroot1', vocabulary.basetags(self.folder))

    def test_a_tag_that_is_not_there_is_not_reported(self):
        removed = remove_base_tags(self.root, self.folder, ['nosuchtag'])
        self.assertEqual(removed, [])

    def test_no_file_is_created_when_there_is_none(self):
        (self.root / '.basetags').unlink()
        remove_base_tags(self.root, self.folder, ['baseroot1'])
        self.assertFalse((self.root / '.basetags').exists())


class UtilitiesDeletionTest(unittest.TestCase):
    """The delete buttons of the utilities panel, with a stub for the
    picker dialog."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.folder = self.root / 'myfolder'
        self.folder.mkdir()
        (self.root / '.ignoretags').write_text(
            'global1\n#myfolder\nsection1\n')
        (self.folder / '.ignoretags').write_text('file1\n')
        (self.root / '.basetags').write_text('baseroot1\n')
        (self.folder / '.basetags').write_text('basefile1\n')
        self.checked_items: list[tuple[str, str]] = []
        # The sort option is remembered between the runs, so it is cleared
        # to keep the tests independent of each other.
        self._clear_sort_setting()
        self._install_stub()

    def tearDown(self):
        self._restore_stub()
        self._clear_sort_setting()
        self.directory.cleanup()

    def _clear_sort_setting(self):
        from utils.settings import get_settings
        get_settings().remove('utilities_sort_alphabetically')

    def _install_stub(self):
        """Replaces the tag picker and the message boxes with stubs."""
        import widgets.utilities as utilities_module
        from PySide6.QtWidgets import QDialog, QMessageBox

        utilities = self

        class StubPicker:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def exec(self):
                return QDialog.DialogCode.Accepted

            def get_checked_items(self):
                return utilities.checked_items

            def get_checked_tags(self):
                return [tag for tag, _ in utilities.checked_items]

        self.original_picker = utilities_module.TagPickerDialog
        self.original_information = QMessageBox.information
        utilities_module.TagPickerDialog = StubPicker
        QMessageBox.information = staticmethod(
            lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    def _restore_stub(self):
        import widgets.utilities as utilities_module
        from PySide6.QtWidgets import QMessageBox

        utilities_module.TagPickerDialog = self.original_picker
        QMessageBox.information = self.original_information

    def make_utilities(self):
        """Builds the utilities panel with a fake image list model."""
        from PySide6.QtWidgets import QApplication

        from utils.image import Image
        from widgets.utilities import Utilities

        class FakeModel:
            def __init__(self, images):
                self.images = images

        image_path = self.folder / 'img0.jpg'
        image_path.write_bytes(b'\xff\xd8\xff\xe0fake')
        images = [Image(image_path, (640, 480), ['mytrigger', '1girl'])]
        app = QApplication.instance() or QApplication([])
        utilities = Utilities(FakeModel(images))
        utilities.set_directory_path(self.root)
        return utilities

    def test_the_delete_buttons_exist(self):
        utilities = self.make_utilities()
        self.assertTrue(utilities.delete_ignore_tags_button.isEnabled())
        self.assertTrue(utilities.delete_base_tags_button.isEnabled())

    def test_the_delete_buttons_are_disabled_without_a_directory(self):
        from PySide6.QtWidgets import QApplication

        from widgets.utilities import Utilities

        class FakeModel:
            images = []

        app = QApplication.instance() or QApplication([])
        utilities = Utilities(FakeModel())
        self.assertFalse(utilities.delete_ignore_tags_button.isEnabled())
        self.assertFalse(utilities.delete_base_tags_button.isEnabled())

    def test_delete_ignore_tags_removes_the_selected_tags(self):
        utilities = self.make_utilities()
        self.checked_items = [('global1', IGNORE_SOURCE_GLOBAL)]
        utilities.delete_ignore_tags()
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('global1', vocabulary.ignore_tags(self.folder))
        self.assertIn('section1', vocabulary.ignore_tags(self.folder))

    def test_delete_ignore_tags_removes_a_section_tag(self):
        utilities = self.make_utilities()
        self.checked_items = [('section1', IGNORE_SOURCE_SECTION)]
        utilities.delete_ignore_tags()
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('section1', vocabulary.ignore_tags(self.folder))

    def test_delete_ignore_tags_removes_a_folder_file_tag(self):
        utilities = self.make_utilities()
        self.checked_items = [('file1', IGNORE_SOURCE_FILE)]
        utilities.delete_ignore_tags()
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('file1', vocabulary.ignore_tags(self.folder))

    def test_delete_base_tags_removes_the_selected_tags(self):
        utilities = self.make_utilities()
        self.checked_items = [('baseroot1', '')]
        utilities.delete_base_tags()
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('baseroot1', vocabulary.basetags(self.folder))
        self.assertIn('basefile1', vocabulary.basetags(self.folder))

    def test_delete_base_tags_removes_a_folder_tag(self):
        utilities = self.make_utilities()
        self.checked_items = [('basefile1', '')]
        utilities.delete_base_tags()
        vocabulary = Vocabulary(self.root)
        self.assertNotIn('basefile1', vocabulary.basetags(self.folder))

    def test_the_ignore_sources_use_the_names_of_the_script(self):
        utilities = self.make_utilities()
        labels = utilities.get_ignore_source_labels(self.folder)
        self.assertEqual(labels[IGNORE_SOURCE_GLOBAL], 'global')
        self.assertEqual(labels[IGNORE_SOURCE_SECTION], '#myfolder')
        self.assertEqual(labels[IGNORE_SOURCE_FILE], 'folder file')

    def test_the_description_names_the_shared_section(self):
        utilities = self.make_utilities()
        (self.root / '.ignoretags').write_text(
            '#myfolder, otherfolder\nshared\n')
        description = utilities.get_ignore_description(self.folder)
        self.assertIn('#myfolder', description)
        self.assertIn('otherfolder', description)

    def test_the_description_says_when_a_section_is_not_shared(self):
        utilities = self.make_utilities()
        description = utilities.get_ignore_description(self.folder)
        self.assertIn('belongs to this project only', description)

    def test_the_tags_keep_their_order_by_default(self):
        utilities = self.make_utilities()
        items = [('zebra', '1'), ('apple', '2')]
        self.assertEqual(utilities.order_items(items), items)

    def test_the_tags_are_sorted_alphabetically_with_the_option(self):
        utilities = self.make_utilities()
        utilities.sort_alphabetically_check_box.setChecked(True)
        items = [('zebra', '1'), ('apple', '2')]
        self.assertEqual(utilities.order_items(items),
                         [('apple', '2'), ('zebra', '1')])

    def test_the_option_is_off_by_default(self):
        utilities = self.make_utilities()
        self.assertFalse(utilities.sort_alphabetically_check_box.isChecked())


if __name__ == '__main__':
    unittest.main()

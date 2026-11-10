"""Tests for the dataset utilities.

The tests use a stub for the tag picker dialog, so that the writing of the
vocabulary files can be checked without a mouse.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))

from tagging.vocabulary import (Vocabulary, count_tags,  # noqa: E402
                                get_most_common_first_tag)

CAPTIONS = [
    ['mytrigger', '1girl', 'smiling', 'solo'],
    ['mytrigger', '1girl', 'smiling', 'hat'],
    ['mytrigger', '1girl', 'dress', 'outdoors'],
]


class CountTagsTest(unittest.TestCase):
    def test_counts_every_tag_once_per_caption(self):
        counts, caption_count = count_tags(CAPTIONS)
        self.assertEqual(caption_count, 3)
        self.assertEqual(counts['mytrigger'], 3)
        self.assertEqual(counts['smiling'], 2)
        self.assertEqual(counts['solo'], 1)

    def test_counts_are_lowercased(self):
        counts, _ = count_tags([['Solo', 'SOLO']])
        self.assertEqual(counts, {'solo': 1})

    def test_empty_captions(self):
        counts, caption_count = count_tags([])
        self.assertEqual(counts, {})
        self.assertEqual(caption_count, 0)


class MostCommonFirstTagTest(unittest.TestCase):
    def test_finds_the_trigger(self):
        self.assertEqual(get_most_common_first_tag(CAPTIONS), 'mytrigger')

    def test_empty_captions_have_no_trigger(self):
        self.assertEqual(get_most_common_first_tag([[], []]), '')


class UtilitiesTest(unittest.TestCase):
    """The utilities of the GUI, with a stub for the picker dialog."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.folder = self.root / 'myfolder'
        self.folder.mkdir()
        self.picked_tags: list[str] = []
        self._install_stub()

    def tearDown(self):
        self.directory.cleanup()

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

            def get_checked_tags(self):
                return utilities.picked_tags

        self.original_picker = utilities_module.TagPickerDialog
        self.original_information = QMessageBox.information
        utilities_module.TagPickerDialog = StubPicker
        # The message boxes are modal, so they would block the test.
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

        images = []
        for index, tags in enumerate(CAPTIONS):
            image_path = self.folder / f'img{index}.jpg'
            image_path.write_bytes(b'\xff\xd8\xff\xe0fake')
            images.append(Image(image_path, (640, 480), list(tags)))
        model = FakeModel(images)
        # The panel needs a QApplication for its widgets.
        app = QApplication.instance() or QApplication([])
        utilities = Utilities(model)
        utilities.set_directory_path(self.root)
        return utilities

    def test_ranked_tags_are_sorted_by_frequency(self):
        utilities = self.make_utilities()
        ranked = utilities.get_ranked_tags(self.folder)
        # The tags with the same count are sorted alphabetically.
        self.assertEqual(ranked[:2], [('1girl', 3), ('mytrigger', 3)])
        counts = [count for _, count in ranked]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_trigger_is_the_first_tag(self):
        utilities = self.make_utilities()
        self.assertEqual(utilities.get_trigger(self.folder), 'mytrigger')

    def test_skip_tags_hold_the_trigger_and_the_folder_name(self):
        utilities = self.make_utilities()
        self.assertEqual(utilities.get_skip_tags(self.folder),
                         {'mytrigger', 'myfolder'})

    def test_generate_ignore_tags_writes_the_section(self):
        utilities = self.make_utilities()
        self.picked_tags = ['solo', 'hat']
        try:
            utilities.generate_ignore_tags()
        finally:
            self._restore_stub()
        ignore_path = self.root / '.ignoretags'
        self.assertTrue(ignore_path.exists())
        text = ignore_path.read_text()
        self.assertIn('#myfolder', text)
        self.assertIn('solo', text)
        self.assertIn('hat', text)

    def test_generate_base_tags_writes_one_tag_per_row(self):
        utilities = self.make_utilities()
        self.picked_tags = ['dress', 'outdoors']
        try:
            utilities.generate_base_tags()
        finally:
            self._restore_stub()
        base_tag_path = self.folder / '.basetags'
        self.assertTrue(base_tag_path.exists())
        self.assertEqual(base_tag_path.read_text().splitlines(),
                         ['dress', 'outdoors'])

    def test_the_written_tags_are_merged_by_the_vocabulary(self):
        utilities = self.make_utilities()
        self.picked_tags = ['solo']
        try:
            utilities.generate_ignore_tags()
            self.picked_tags = ['dress']
            utilities.generate_base_tags()
        finally:
            self._restore_stub()
        vocabulary = Vocabulary(self.root)
        self.assertIn('solo', vocabulary.ignore_tags(self.folder))
        self.assertIn('dress', vocabulary.basetags(self.folder))


if __name__ == '__main__':
    unittest.main()

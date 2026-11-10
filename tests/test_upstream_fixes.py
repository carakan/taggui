"""Tests for the fixes ported from the upstream fork.

The changes come from the `StableLlama/taggui` fork:
- the models reset themselves with `beginResetModel()`/`endResetModel()`,
  instead of emitting `modelReset` directly,
- the `AND` and `OR` filters do not crash when they have no right operand,
- the images can be dragged out of the image list.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))

from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


class UpstreamFixesTest(unittest.TestCase):
    """The fixes ported from the upstream fork."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.app = QApplication.instance() or QApplication([])
        from widgets.main_window import MainWindow

        for index in range(3):
            (self.root / f'i{index}.jpg').write_bytes(b'\xff\xd8\xff\xe0fake')
            (self.root / f'i{index}.txt').write_text('mytrigger, solo')
        self.main_window = MainWindow(self.app)
        self.main_window.load_directory(self.root)
        self.image_list = self.main_window.image_list
        self.list_view = self.image_list.list_view

    def tearDown(self):
        self.main_window.close()
        self.directory.cleanup()

    def test_loading_a_directory_does_not_reset_the_models_improperly(self):
        """The models reset themselves with `begin`/`endResetModel()`.

        Emitting `modelReset` directly makes the proxy models warn about a
        missing `beginResetModel()` call.
        """
        import io
        from contextlib import redirect_stderr

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.main_window.load_directory(self.root)
        self.assertNotIn('endResetModel', stderr.getvalue())

    def test_the_and_filter_without_a_right_operand_does_not_crash(self):
        proxy_model = self.main_window.proxy_image_list_model
        from utils.image import Image

        image = Image(self.root / 'i0.jpg', (10, 10), ['solo'])
        # The right operand of the filter is missing.
        self.assertFalse(proxy_model.does_image_match_filter(
            image, ['tags', 'AND']))

    def test_the_or_filter_without_a_right_operand_does_not_crash(self):
        proxy_model = self.main_window.proxy_image_list_model
        from utils.image import Image

        image = Image(self.root / 'i0.jpg', (10, 10), ['solo'])
        self.assertFalse(proxy_model.does_image_match_filter(
            image, ['chars', 'OR']))

    def test_the_images_can_be_dragged_out_of_the_image_list(self):
        self.assertTrue(self.list_view.dragEnabled())

    def test_the_dragged_data_holds_the_selected_images_only(self):
        selection_model = self.list_view.selectionModel()
        selection_model.clearSelection()
        for row in (0, 2):
            selection_model.select(
                self.main_window.proxy_image_list_model.index(row, 0),
                QItemSelectionModel.SelectionFlag.Select)
        self.app.processEvents()
        mime_data = self.list_view.model().mimeData(
            self.list_view.selectedIndexes())
        self.assertEqual([url.toString() for url in mime_data.urls()],
                         [f'file://{self.root / "i0.jpg"}',
                          f'file://{self.root / "i2.jpg"}'])


if __name__ == '__main__':
    unittest.main()

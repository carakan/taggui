"""Tests for sending images from the image list to the AI tagger."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))

from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


class SendToTaggerTest(unittest.TestCase):
    """The image list action and button that send images to the tagger."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.app = QApplication.instance() or QApplication([])
        from PySide6.QtWidgets import QMessageBox

        from widgets.main_window import MainWindow

        # The message boxes are modal, so they would block the test.
        self.original_information = QMessageBox.information
        self.original_critical = QMessageBox.critical
        QMessageBox.information = staticmethod(
            lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        QMessageBox.critical = staticmethod(
            lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        # The images of the dataset.
        for index in range(3):
            (self.root / f'i{index}.jpg').write_bytes(b'\xff\xd8\xff\xe0fake')
            (self.root / f'i{index}.txt').write_text('mytrigger, solo')
        self.main_window = MainWindow(self.app)
        self.main_window.load_directory(self.root)
        self.image_list = self.main_window.image_list
        self.list_view = self.image_list.list_view

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self.original_information
        QMessageBox.critical = self.original_critical
        self.main_window.close()
        self.directory.cleanup()

    def select(self, *rows: int):
        """Selects the images of the given rows."""
        selection_model = self.list_view.selectionModel()
        selection_model.clearSelection()
        for row in rows:
            selection_model.select(
                self.main_window.proxy_image_list_model.index(row, 0),
                QItemSelectionModel.SelectionFlag.Select)
        self.app.processEvents()

    def test_button_is_disabled_without_a_selection(self):
        self.list_view.selectionModel().clearSelection()
        self.app.processEvents()
        self.assertFalse(self.image_list.send_to_tagger_button.isEnabled())

    def test_button_is_enabled_with_a_selection(self):
        self.select(0)
        self.assertTrue(self.image_list.send_to_tagger_button.isEnabled())

    def test_button_shows_the_number_of_selected_images(self):
        self.select(0, 1)
        self.assertEqual(self.image_list.send_to_tagger_button.text(),
                         'Send 2 Images to AI Tagger')

    def test_button_shows_a_single_image(self):
        self.select(0)
        self.assertEqual(self.image_list.send_to_tagger_button.text(),
                         'Send to AI Tagger')

    def test_context_menu_action_shows_the_number_of_images(self):
        self.select(0, 1)
        self.assertEqual(
            self.list_view.send_to_tagger_action.text(),
            'Send 2 Images to AI Tagger')

    def test_context_menu_action_is_disabled_without_a_selection(self):
        self.list_view.selectionModel().clearSelection()
        self.app.processEvents()
        self.assertFalse(self.list_view.send_to_tagger_action.isEnabled())

    def test_the_signal_carries_the_selected_images(self):
        self.select(0, 1)
        received = []
        self.list_view.send_to_tagger_requested.connect(received.append)
        self.list_view.send_selected_images_to_tagger()
        self.assertEqual(len(received), 1)
        self.assertEqual([index.row() for index in received[0]], [0, 1])

    def test_sending_sets_the_scope_of_the_tagger(self):
        self.select(0)
        self.main_window.send_images_to_ai_tagger([])
        self.assertEqual(
            self.main_window.llm_tagger.settings_form.scope_combo_box
            .currentText(),
            'Selected images')

    def test_the_tagger_tags_the_given_images(self):
        """The tagger is started for the given images only."""
        from PySide6.QtCore import Qt

        from tagging.tagger import TagMode, TagOrder, Tagger, TaggerSettings
        from tagging.vocabulary import Vocabulary

        class StubClient:
            def __init__(self):
                self.calls = []

            def complete(self, prompt, image_path):
                self.calls.append(Path(image_path))
                return '1girl, smiling', 'stop'

        client = StubClient()
        settings = TaggerSettings(mode=TagMode.RETAG, order=TagOrder.RANK,
                                  dry_run=True)
        tagger = Tagger(client, Vocabulary(self.root), settings)
        for row in (0, 1):
            index = self.main_window.image_list_model.index(row, 0)
            image = self.main_window.image_list_model.data(
                index, Qt.ItemDataRole.UserRole)
            tagger.tag_image(image.path, image.tags)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual([path.name for path in client.calls],
                         ['i0.jpg', 'i1.jpg'])


if __name__ == '__main__':
    unittest.main()

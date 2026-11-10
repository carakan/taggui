"""Tests for the UI scale setting and the setting tooltips.

The features come from the upstream `jhc13/taggui` commits:
- `8b2c252` adds a "UI scale (%)" setting that scales the whole GUI via
  `QT_SCALE_FACTOR`,
- `c6f65a6` adds a hover tooltip to every setting.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402


def count_help_labels(layout) -> int:
    """The number of "(?)" help labels in a layout, at any depth."""
    count = 0
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        if widget is not None:
            if isinstance(widget, QLabel) and widget.text() == '(?)':
                count += 1
            elif widget.layout() is not None:
                count += count_help_labels(widget.layout())
        elif item.layout() is not None:
            count += count_help_labels(item.layout())
    return count


class UiScaleTest(unittest.TestCase):
    """The UI scale setting."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        from utils.settings import get_settings

        self.settings = get_settings()
        self.original_value = self.settings.value(
            'ui_scale_percent', defaultValue=100, type=int)
        self.original_env = os.environ.pop('QT_SCALE_FACTOR', None)

    def tearDown(self):
        self.settings.setValue('ui_scale_percent', self.original_value)
        self.settings.sync()
        os.environ.pop('QT_SCALE_FACTOR', None)
        if self.original_env is not None:
            os.environ['QT_SCALE_FACTOR'] = self.original_env

    def test_the_default_is_100_percent(self):
        from utils.settings import DEFAULT_SETTINGS

        self.assertEqual(DEFAULT_SETTINGS['ui_scale_percent'], 100)

    def test_the_scale_factor_is_set_from_the_setting(self):
        import run_gui

        self.settings.setValue('ui_scale_percent', 150)
        self.settings.sync()
        run_gui.apply_ui_scale()
        self.assertEqual(os.environ.get('QT_SCALE_FACTOR'), '1.5')

    def test_the_scale_factor_is_not_set_at_100_percent(self):
        import run_gui

        self.settings.setValue('ui_scale_percent', 100)
        self.settings.sync()
        run_gui.apply_ui_scale()
        self.assertIsNone(os.environ.get('QT_SCALE_FACTOR'))

    def test_the_setting_has_a_spin_box(self):
        from dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(None)
        labels = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertIn('UI scale (%)', labels)

    def test_the_spin_box_has_the_expected_range(self):
        from PySide6.QtWidgets import QSpinBox

        from dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(None)
        ranges = [(spin_box.minimum(), spin_box.maximum())
                  for spin_box in dialog.findChildren(QSpinBox)]
        self.assertIn((50, 300), ranges)


class SettingTooltipsTest(unittest.TestCase):
    """The hover tooltips of the settings."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])

    def test_the_help_label_has_a_tooltip(self):
        from utils.big_widgets import create_help_label

        help_label = create_help_label('What this setting does.')
        self.assertEqual(help_label.toolTip(), 'What this setting does.')

    def test_the_label_with_help_has_a_text_and_a_help_label(self):
        from utils.big_widgets import label_with_help

        widget = label_with_help('Server URL', 'Where the server is.')
        labels = widget.findChildren(QLabel)
        self.assertEqual([label.text() for label in labels],
                         ['Server URL', '(?)'])
        self.assertEqual(labels[1].toolTip(), 'Where the server is.')

    def test_the_checkbox_with_help_keeps_the_check_box(self):
        from utils.big_widgets import checkbox_with_help
        from utils.settings_widgets import SettingsBigCheckBox

        check_box = SettingsBigCheckBox(key='test_tooltip_check_box',
                                         default=False, text='A setting')
        widget = checkbox_with_help(check_box, 'What it does.')
        self.assertIs(widget.findChild(type(check_box)), check_box)
        self.assertEqual(widget.findChildren(QLabel)[0].toolTip(),
                         'What it does.')

    def test_every_setting_of_the_tagger_has_a_help_label(self):
        """Each row of the tagger settings has a "(?)" label."""
        from widgets.llm_tagger import LlmTaggerSettingsForm

        form = LlmTaggerSettingsForm()
        help_labels = count_help_labels(form)
        # The server, tagging and options forms all have their rows
        # documented.
        self.assertGreaterEqual(help_labels, 19)


if __name__ == '__main__':
    unittest.main()

"""Tests for the overlay on the large image.

The overlay shows the dimensions of the selected images and the tags
that were added and removed in their captions. Only the first few tags
of a diff are shown; the rest is behind a link that shows the whole
diff when it is clicked.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))
sys.path.insert(0, str(Path(__file__).parent))

# The tests use settings of their own, to keep away from the ones
# of the user.
import settings_isolation  # noqa: E402,F401

from PySide6.QtWidgets import QApplication  # noqa: E402

from utils.git_info import CaptionDiff  # noqa: E402
from widgets.image_info_overlay import (MAX_TAGS_SHOWN,  # noqa: E402
                                        ImageInfo, ImageInfoGroup,
                                        ImageInfoOverlay)


class OverlayTest(unittest.TestCase):
    """The lines of the overlay."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.overlay = ImageInfoOverlay()
        self.overlay.set_max_width(400)

    def make_entry(self, added=None, removed=None, is_new=False):
        return ImageInfo(
            name='photo.jpg', dimensions=(100, 200),
            diff=CaptionDiff(is_modified=True, is_new=is_new,
                             added_tags=added or [],
                             removed_tags=removed or []))

    def set_entries(self, *entries):
        self.overlay.set_info(ImageInfoGroup(entries=list(entries)))
        self.overlay.resize(self.overlay.sizeHint())

    def texts(self):
        """The text of the lines of the overlay."""
        return [line.text for entry in self.overlay.get_lines()
                for line in entry]

    def test_the_name_and_the_size_are_shown(self):
        self.set_entries(self.make_entry())
        self.assertEqual(self.texts()[0], 'photo.jpg — 100 × 200')

    def test_only_the_first_tags_are_shown(self):
        tags = [f'tag{index}' for index in range(10)]
        self.set_entries(self.make_entry(added=tags))
        texts = self.texts()
        self.assertIn('+ ' + ', '.join(tags[:MAX_TAGS_SHOWN]), texts)
        self.assertIn('+4 more', texts)
        self.assertNotIn('+ ' + ', '.join(tags), texts)

    def test_the_link_shows_the_whole_diff(self):
        tags = [f'tag{index}' for index in range(10)]
        self.set_entries(self.make_entry(added=tags))
        self.overlay.toggle(0)
        texts = self.texts()
        self.assertIn('+ ' + ', '.join(tags), texts)
        self.assertNotIn('+4 more', texts)
        self.assertIn('show less', texts)

    def test_the_link_folds_the_diff_back(self):
        tags = [f'tag{index}' for index in range(10)]
        self.set_entries(self.make_entry(added=tags))
        self.overlay.toggle(0)
        self.overlay.toggle(0)
        self.assertIn('+4 more', self.texts())

    def test_a_short_diff_has_no_link(self):
        self.set_entries(self.make_entry(added=['a', 'b']))
        self.assertNotIn('show less', self.texts())
        self.assertEqual(len(self.overlay.action_rects), 0)

    def test_the_removed_tags_are_shown_too(self):
        tags = [f'old{index}' for index in range(10)]
        self.set_entries(self.make_entry(removed=tags))
        self.assertIn('- ' + ', '.join(tags[:MAX_TAGS_SHOWN]), self.texts())
        self.assertIn('+4 more', self.texts())

    def test_the_link_is_found_at_its_place(self):
        tags = [f'tag{index}' for index in range(10)]
        self.set_entries(self.make_entry(added=tags))
        self.overlay.layout_lines()
        self.assertEqual(len(self.overlay.action_rects), 1)
        rect, action, entry_index = self.overlay.action_rects[0]
        self.assertEqual(action, 'expand')
        self.assertEqual(entry_index, 0)
        self.assertEqual(self.overlay.action_at(rect.x() + 1, rect.y() + 1),
                         ('expand', 0))
        # A place that is not on the link does nothing.
        self.assertIsNone(self.overlay.action_at(rect.x() - 30, rect.y()))

    def test_the_text_is_folded_to_the_width(self):
        # The text must not be cut off by the edge of the image.
        tags = [f'averylongtagname{index}' for index in range(10)]
        self.set_entries(self.make_entry(added=tags))
        self.assertLessEqual(self.overlay.width(), self.overlay.max_width)

    def test_a_new_caption_is_shown(self):
        self.set_entries(self.make_entry(is_new=True))
        self.assertIn('new caption (not in git)', self.texts())


if __name__ == '__main__':
    unittest.main()

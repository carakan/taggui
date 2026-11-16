"""An overlay on the large image with the details of the selected images.

The overlay shows the dimensions of every selected image and, when the
dataset is a git repository and the caption file of an image is changed,
the tags that were added and removed since the committed version.

Only the first few tags of a diff are shown. The rest is behind a `+N
more` link, which shows the whole diff when it is clicked.
"""

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from utils.git_info import CaptionDiff

# The colors of the added and the removed tags.
ADDED_COLOR = QColor(126, 211, 133)
REMOVED_COLOR = QColor(240, 113, 120)
TEXT_COLOR = QColor(235, 235, 235)
NAME_COLOR = QColor(180, 190, 210)
LINK_COLOR = QColor(130, 190, 255)
BACKGROUND_COLOR = QColor(0, 0, 0, 170)
PADDING = 10
LINE_SPACING = 4
ENTRY_SPACING = 8
MAX_TAGS_SHOWN = 6
# The width the overlay gets when nothing else is known.
DEFAULT_MAX_WIDTH = 520


@dataclass
class ImageInfo:
    """The information shown for one image."""
    name: str
    dimensions: tuple[int, int] | None = None
    diff: CaptionDiff | None = None
    # Whether the image is the one shown in the large image.
    is_current: bool = False


@dataclass
class ImageInfoGroup:
    """The information of a group of images, one group per selection."""
    entries: list[ImageInfo] = field(default_factory=list)
    hidden_count: int = 0


@dataclass
class OverlayLine:
    """One line of the overlay."""
    text: str
    color: QColor
    # The action the line does when it is clicked.
    action: str | None = None
    # The entry the line belongs to.
    entry_index: int = -1


class ImageInfoOverlay(QWidget):
    """Shows the dimensions and the caption changes over the image."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = ImageInfoGroup()
        self.max_width = DEFAULT_MAX_WIDTH
        # The entries whose diff is shown in full.
        self.expanded: set[int] = set()
        # The place of the lines that do something when they are clicked.
        self.action_rects: list[tuple[QRect, str, int]] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setSizePolicy(QSizePolicy.Policy.Minimum,
                           QSizePolicy.Policy.Minimum)

    def set_info(self, group: ImageInfoGroup):
        """Sets the information to show and updates the overlay."""
        self.group = group
        self.updateGeometry()
        self.update()

    def clear(self):
        self.set_info(ImageInfoGroup())

    def set_max_width(self, width: int):
        """The width the overlay may take."""
        self.max_width = max(100, width)

    def toggle(self, entry_index: int):
        """Shows the whole diff of an entry, or folds it back."""
        if entry_index in self.expanded:
            self.expanded.discard(entry_index)
        else:
            self.expanded.add(entry_index)
        self.updateGeometry()
        self.update()

    def action_at(self, x: int, y: int) -> tuple[str, int] | None:
        """The action of the line at a point, when there is one.

        The point is in the coordinates of the overlay.
        """
        for rect, action, entry_index in self.action_rects:
            if rect.contains(x, y):
                return action, entry_index
        return None

    def get_lines(self) -> list[list[OverlayLine]]:
        """The lines of the overlay, grouped per image."""
        lines: list[list[OverlayLine]] = []
        for index, entry in enumerate(self.group.entries):
            entry_lines: list[OverlayLine] = []
            width, height = entry.dimensions if entry.dimensions else (None,
                                                                       None)
            size_text = (f'{width} × {height}' if entry.dimensions
                         else 'unknown size')
            name_color = TEXT_COLOR if entry.is_current else NAME_COLOR
            entry_lines.append(OverlayLine(f'{entry.name} — {size_text}',
                                           name_color))
            diff = entry.diff
            if diff is not None and diff.is_modified:
                if diff.is_new:
                    entry_lines.append(OverlayLine(
                        'new caption (not in git)', ADDED_COLOR))
                else:
                    entry_lines.extend(self.get_diff_lines(
                        diff.added_tags, ADDED_COLOR, index, 'added'))
                    entry_lines.extend(self.get_diff_lines(
                        diff.removed_tags, REMOVED_COLOR, index, 'removed'))
            lines.append(entry_lines)
        if self.group.hidden_count:
            lines.append([OverlayLine(
                f'+{self.group.hidden_count} more image(s)', NAME_COLOR)])
        return lines

    def get_diff_lines(self, tags: list[str], color: QColor, index: int,
                       kind: str) -> list[OverlayLine]:
        """The lines of the added or the removed tags of an entry.

        Only the first few tags are shown. The rest is behind a link that
        shows the whole list when it is clicked.
        """
        if not tags:
            return []
        prefix = '+ ' if kind == 'added' else '- '
        expanded = index in self.expanded
        if len(tags) <= MAX_TAGS_SHOWN or expanded:
            lines = [OverlayLine(prefix + ', '.join(tags), color)]
            if expanded and len(tags) > MAX_TAGS_SHOWN:
                lines.append(OverlayLine('show less', LINK_COLOR, 'collapse',
                                          index))
            return lines
        lines = [OverlayLine(prefix + ', '.join(tags[:MAX_TAGS_SHOWN]),
                              color)]
        lines.append(OverlayLine(f'+{len(tags) - MAX_TAGS_SHOWN} more',
                                  LINK_COLOR, 'expand', index))
        return lines

    def get_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSize(max(8, font.pointSize() - 1))
        return font

    def wrap(self, text: str, metrics: QFontMetrics,
              max_width: int) -> list[str]:
        """The text in the lines that fit the width."""
        if metrics.horizontalAdvance(text) <= max_width:
            return [text]
        lines: list[str] = []
        current = ''
        for word in text.split(' '):
            candidate = f'{current} {word}' if current else word
            if metrics.horizontalAdvance(candidate) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            # A word that is longer than the width is cut in pieces.
            while metrics.horizontalAdvance(word) > max_width:
                cut = len(word)
                while (cut > 1
                       and metrics.horizontalAdvance(word[:cut])
                       > max_width):
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        if current:
            lines.append(current)
        return lines

    def layout_lines(self) -> list[list[tuple[str, QColor, str | None, int,
                                             int]]]:
        """The lines of the overlay as they are drawn, folded to the width
        that is available.

        Every line comes with the place it is drawn at. The place of the
        lines that do something when they are clicked is kept, so that a
        click can be matched with them.
        """
        metrics = QFontMetrics(self.get_font())
        max_width = max(100, self.max_width - PADDING * 2)
        laid_out = []
        self.action_rects = []
        y = PADDING
        for entry_lines in self.get_lines():
            entry_out = []
            for line in entry_lines:
                for part in self.wrap(line.text, metrics, max_width):
                    entry_out.append((part, line.color, line.action,
                                      line.entry_index, y))
                    if line.action:
                        width = metrics.horizontalAdvance(part)
                        self.action_rects.append(
                            (QRect(PADDING, y, width, metrics.height()),
                             line.action, line.entry_index))
                    y += metrics.height() + LINE_SPACING
            # The space between the last line of an entry and the next
            # one is the spacing of the lines, so that the entries are
            # not too close to each other.
            y += ENTRY_SPACING - LINE_SPACING
            laid_out.append(entry_out)
        return laid_out

    def sizeHint(self):
        lines = self.layout_lines()
        if not lines:
            return super().sizeHint()
        metrics = QFontMetrics(self.get_font())
        width = 0
        height = PADDING * 2
        for entry_lines in lines:
            for text, _color, _action, _index, _y in entry_lines:
                width = max(width, metrics.horizontalAdvance(text))
            height += len(entry_lines) * metrics.height()
            height += (len(entry_lines) - 1) * LINE_SPACING
            height += ENTRY_SPACING
        height -= ENTRY_SPACING
        return QSize(width + PADDING * 2, height + PADDING * 2)

    def paintEvent(self, event):
        lines = self.layout_lines()
        if not lines:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BACKGROUND_COLOR)
        painter.drawRoundedRect(QRect(0, 0, self.width(), self.height()), 6, 6)
        metrics = QFontMetrics(self.get_font())
        painter.setFont(self.get_font())
        for entry_lines in lines:
            for text, color, action, _entry_index, y in entry_lines:
                painter.setPen(QPen(color))
                width = metrics.horizontalAdvance(text)
                painter.drawText(PADDING, y + metrics.ascent(), text)
                if action:
                    painter.drawLine(PADDING, y + metrics.ascent() + 2,
                                     PADDING + width, y + metrics.ascent() + 2)


def get_caption_path(image_path: Path) -> Path:
    """The caption file of an image."""
    return Path(image_path).with_suffix('.txt')

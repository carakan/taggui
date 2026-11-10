"""An overlay on the large image with the details of the selected images.

The overlay shows the dimensions of every selected image and, when the
dataset is a git repository and the caption file of an image is changed,
the tags that were added and removed since the committed version.
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
BACKGROUND_COLOR = QColor(0, 0, 0, 170)
PADDING = 10
LINE_SPACING = 4
ENTRY_SPACING = 8
MAX_TAGS_SHOWN = 6


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
    # The number of images of the group that are not shown.
    hidden_count: int = 0


class ImageInfoOverlay(QWidget):
    """Shows the dimensions and the caption changes over the image."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = ImageInfoGroup()
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

    def get_lines(self) -> list[list[tuple[str, QColor]]]:
        """The lines of the overlay, grouped per image."""
        lines: list[list[tuple[str, QColor]]] = []
        for entry in self.group.entries:
            entry_lines: list[tuple[str, QColor]] = []
            width, height = entry.dimensions if entry.dimensions else (None,
                                                                       None)
            size_text = (f'{width} × {height}' if entry.dimensions
                         else 'unknown size')
            name_color = TEXT_COLOR if entry.is_current else NAME_COLOR
            entry_lines.append((f'{entry.name} — {size_text}', name_color))
            diff = entry.diff
            if diff is not None and diff.is_modified:
                if diff.is_new:
                    entry_lines.append(('new caption (not in git)',
                                        ADDED_COLOR))
                else:
                    if diff.added_tags:
                        added = diff.added_tags[:MAX_TAGS_SHOWN]
                        text = '+ ' + ', '.join(added)
                        if len(diff.added_tags) > MAX_TAGS_SHOWN:
                            text += (f' +{len(diff.added_tags) - MAX_TAGS_SHOWN}'
                                     ' more')
                        entry_lines.append((text, ADDED_COLOR))
                    if diff.removed_tags:
                        removed = diff.removed_tags[:MAX_TAGS_SHOWN]
                        text = '- ' + ', '.join(removed)
                        if len(diff.removed_tags) > MAX_TAGS_SHOWN:
                            text += (f' -{len(diff.removed_tags) - MAX_TAGS_SHOWN}'
                                     ' more')
                        entry_lines.append((text, REMOVED_COLOR))
            lines.append(entry_lines)
        if self.group.hidden_count:
            lines.append([(f'+{self.group.hidden_count} more image(s)',
                           NAME_COLOR)])
        return lines

    def get_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSize(max(8, font.pointSize() - 1))
        return font

    def sizeHint(self):
        lines = self.get_lines()
        if not lines:
            return super().sizeHint()
        metrics = QFontMetrics(self.get_font())
        width = 0
        height = PADDING * 2
        for entry_lines in lines:
            for text, _ in entry_lines:
                width = max(width, metrics.horizontalAdvance(text))
            height += len(entry_lines) * metrics.height()
            height += (len(entry_lines) - 1) * LINE_SPACING
            height += ENTRY_SPACING
        height -= ENTRY_SPACING
        return QSize(width + PADDING * 2, height + PADDING * 2)

    def paintEvent(self, event):
        lines = self.get_lines()
        if not lines:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BACKGROUND_COLOR)
        painter.drawRoundedRect(QRect(0, 0, self.width(), self.height()), 6, 6)
        metrics = QFontMetrics(self.get_font())
        painter.setFont(self.get_font())
        y = PADDING
        for entry_lines in lines:
            for text, color in entry_lines:
                painter.setPen(QPen(color))
                painter.drawText(PADDING, y + metrics.ascent(), text)
                y += metrics.height() + LINE_SPACING
            y += ENTRY_SPACING


def get_caption_path(image_path: Path) -> Path:
    """The caption file of an image."""
    return Path(image_path).with_suffix('.txt')

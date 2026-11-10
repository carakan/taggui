from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QWidget)

from utils.settings import DEFAULT_SETTINGS, get_settings


def create_help_label(tooltip: str) -> QLabel:
    """
    A small "?" label that shows `tooltip` on hover, for appending next to
    a setting's name to explain what it does.
    """
    help_label = QLabel('(?)')
    help_label.setToolTip(tooltip)
    help_label.setStyleSheet('color: palette(link);')
    help_label.setCursor(Qt.CursorShape.WhatsThisCursor)
    return help_label


def label_with_help(text: str, tooltip: str) -> QWidget:
    """
    A form-row label: `text` followed by a help icon that shows `tooltip`
    on hover.
    """
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(QLabel(text))
    layout.addWidget(create_help_label(tooltip))
    return container


def checkbox_with_help(check_box: QCheckBox, tooltip: str) -> QWidget:
    """
    A check box followed by a help icon that shows `tooltip` on hover.
    """
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(check_box)
    layout.addWidget(create_help_label(tooltip))
    return container


class BigPushButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        new_size = self.sizeHint() * 1.5
        self.setFixedSize(new_size)


class TallPushButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        new_height = int(self.sizeHint().height() * 1.5)
        self.setFixedHeight(new_height)


class BigCheckBox(QCheckBox):
    def __init__(self, text: str | None = None):
        super().__init__(text)
        settings = get_settings()
        font_size = settings.value(
            'font_size', defaultValue=DEFAULT_SETTINGS['font_size'], type=int)
        new_size = font_size * 1.5
        self.setStyleSheet(
            f'QCheckBox::indicator '
            f'{{ width: {new_size}px; height: {new_size}px; }}')


class HorizontalLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Raised)

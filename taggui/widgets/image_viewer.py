from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint, QSize, Qt, Slot
from PySide6.QtGui import QImageReader, QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image
from widgets.image_info_overlay import (ImageInfo, ImageInfoGroup,
                                        ImageInfoOverlay)


class ImageLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.image_path = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        # This allows the label to shrink.
        self.setMinimumSize(QSize(1, 1))

    def resizeEvent(self, event: QResizeEvent):
        """Reload the image whenever the label is resized."""
        if self.image_path:
            self.load_image(self.image_path)

    def load_image(self, image_path: Path):
        self.image_path = image_path
        image_reader = QImageReader(str(image_path))
        # Rotate the image according to the orientation tag.
        image_reader.setAutoTransform(True)
        pixmap = QPixmap.fromImageReader(image_reader)
        pixmap.setDevicePixelRatio(self.devicePixelRatio())
        pixmap = pixmap.scaled(
            self.size() * pixmap.devicePixelRatio(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(pixmap)


class ImageViewer(QWidget):
    """The large image, with an overlay showing its details."""

    def __init__(self, proxy_image_list_model: ProxyImageListModel):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        self.image_label = ImageLabel()
        self.overlay = ImageInfoOverlay(self.image_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.image_label)
        self.image_label.installEventFilter(self)

    def eventFilter(self, watched, event):
        """Keeps the overlay in the top left corner of the image and handles
        the clicks on it."""
        if watched is self.image_label:
            if event.type() == event.Type.Resize:
                self.position_overlay()
            elif event.type() == event.Type.MouseButtonPress:
                self.handle_overlay_click(event.pos())
        return super().eventFilter(watched, event)

    def handle_overlay_click(self, position: QPoint):
        """Clicks the line of the overlay that does something.

        The overlay is transparent for the mouse, so the click arrives
        here.
        """
        action = self.overlay.action_at(
            position.x() - self.overlay.x(),
            position.y() - self.overlay.y())
        if action is None:
            return
        _action, entry_index = action
        self.overlay.toggle(entry_index)
        self.position_overlay()

    def position_overlay(self):
        """Places the overlay in the top left corner of the image."""
        # The overlay takes the width that is left of the image, so that
        # its text is folded instead of cut.
        self.overlay.set_max_width(self.image_label.width() - 24)
        self.overlay.resize(self.overlay.sizeHint())
        self.overlay.move(12, 12)

    @Slot()
    def load_image(self, proxy_image_index: QModelIndex):
        image: Image = self.proxy_image_list_model.data(
            proxy_image_index, Qt.ItemDataRole.UserRole)
        self.image_label.load_image(image.path)
        self.position_overlay()

    def set_overlay_info(self, entries: list[ImageInfo],
                         hidden_count: int = 0):
        """Sets the information shown in the overlay."""
        self.overlay.set_info(ImageInfoGroup(entries=entries,
                                             hidden_count=hidden_count))
        self.position_overlay()

    def clear_overlay_info(self):
        self.overlay.clear()
        self.position_overlay()

"""A dialog for picking tags out of the tags of a dataset.

The dialog shows the tags of a dataset folder with a checkbox for each of
them, so that a set of tags can be chosen with the mouse. It is the GUI
counterpart of the interactive tag pickers of `lora_tagger.py`.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

# The role that holds the tag of a list item.
TAG_ROLE = Qt.ItemDataRole.UserRole


class TagPickerDialog(QDialog):
    """Lets the user pick tags out of a ranked list of tags.

    The tags are shown with the number of images they appear in, most
    frequent first. A tag that is already stored is shown checked and
    disabled, so that the state of the list is visible.
    """

    def __init__(self, parent, title: str, description: str,
                 items: list[tuple[str, int]],
                 stored_tags: set[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 620)
        self.items = items
        self.stored_tags = stored_tags or set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel('Filter'))
        self.filter_line_edit = QLineEdit()
        self.filter_line_edit.setPlaceholderText('Filter tags')
        self.filter_line_edit.setClearButtonEnabled(True)
        filter_layout.addWidget(self.filter_line_edit, stretch=1)
        layout.addLayout(filter_layout)
        buttons_layout = QHBoxLayout()
        self.select_all_button = QPushButton('Select All')
        self.select_all_button.clicked.connect(lambda: self.set_all_checked(
            True))
        self.select_none_button = QPushButton('Select None')
        self.select_none_button.clicked.connect(lambda: self.set_all_checked(
            False))
        self.selection_count_label = QLabel()
        buttons_layout.addWidget(self.select_all_button)
        buttons_layout.addWidget(self.select_none_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.selection_count_label)
        layout.addLayout(buttons_layout)
        self.tag_list = QListWidget()
        self.tag_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.tag_list.setUniformItemSizes(True)
        layout.addWidget(self.tag_list)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.filter_line_edit.textChanged.connect(self.apply_filter)
        self.populate()
        self.update_selection_count()

    def populate(self):
        """Fills the list with the tags."""
        self.tag_list.clear()
        for tag, count in self.items:
            item = QListWidgetItem(f'{tag}  ({count})')
            item.setData(TAG_ROLE, tag)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if tag in self.stored_tags:
                # A tag that is already stored is shown checked and cannot
                # be unchecked.
                item.setCheckState(Qt.CheckState.Checked)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.tag_list.addItem(item)
        self.apply_filter(self.filter_line_edit.text())

    def apply_filter(self, filter_text: str):
        """Hides the tags that do not match the filter."""
        filter_text = filter_text.strip().lower()
        for row in range(self.tag_list.count()):
            item = self.tag_list.item(row)
            tag = item.data(TAG_ROLE)
            item.setHidden(bool(filter_text)
                           and filter_text not in tag.lower())
        self.update_selection_count()

    def set_all_checked(self, is_checked: bool):
        """Checks or unchecks the tags that are shown."""
        state = (Qt.CheckState.Checked if is_checked
                 else Qt.CheckState.Unchecked)
        for row in range(self.tag_list.count()):
            item = self.tag_list.item(row)
            if item.isHidden():
                continue
            # A tag that is already stored cannot be changed.
            if not item.flags() & Qt.ItemFlag.ItemIsEnabled:
                continue
            item.setCheckState(state)
        self.update_selection_count()

    def update_selection_count(self):
        """Shows how many tags are checked."""
        count = len(self.get_checked_tags())
        self.selection_count_label.setText(f'{count} selected')

    def get_checked_tags(self) -> list[str]:
        """The tags that are checked, in the order of the list."""
        tags = []
        for row in range(self.tag_list.count()):
            item = self.tag_list.item(row)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            tag = item.data(TAG_ROLE)
            if tag not in self.stored_tags:
                tags.append(tag)
        return tags

"""Dock widget with the dataset utilities.

The panel generates the ignore tags and the base tags of a dataset folder
out of the tags that the dataset already uses. It is the GUI counterpart
of the `--ignore-tags` and `--save-basetags` options of `lora_tagger.py`.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QComboBox, QDialog, QDockWidget, QFormLayout,
                               QLabel, QMessageBox, QVBoxLayout, QWidget)

from dialogs.tag_picker_dialog import TagPickerDialog
from models.image_list_model import ImageListModel
from tagging.vocabulary import (Vocabulary, append_basetags,
                                append_ignore_tags, count_tags,
                                get_dataset_folders_from_images,
                                get_most_common_first_tag)
from utils.big_widgets import TallPushButton
from utils.image import Image


class Utilities(QDockWidget):
    """Generates the ignore tags and the base tags of a dataset."""

    def __init__(self, image_list_model: ImageListModel):
        super().__init__()
        self.image_list_model = image_list_model
        self.directory_path: Path | None = None

        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('utilities')
        self.setWindowTitle('Utilities')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)

        self.folder_combo_box = QComboBox()
        self.folder_combo_box.currentTextChanged.connect(
            self.update_description)
        self.generate_ignore_tags_button = TallPushButton(
            'Generate Ignore Tags')
        self.generate_ignore_tags_button.clicked.connect(
            self.generate_ignore_tags)
        self.generate_base_tags_button = TallPushButton(
            'Generate Base Tags')
        self.generate_base_tags_button.clicked.connect(self.generate_base_tags)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        form = QFormLayout()
        form.addRow('Dataset folder', self.folder_combo_box)
        layout.addLayout(form)
        layout.addWidget(self.description_label)
        layout.addWidget(self.generate_ignore_tags_button)
        layout.addWidget(self.generate_base_tags_button)
        layout.addStretch()
        self.setWidget(container)
        self.set_directory_path(None)

    def set_directory_path(self, directory_path: Path | None):
        """Points the panel at a dataset and lists its folders."""
        self.directory_path = Path(directory_path) if directory_path else None
        self.folder_combo_box.blockSignals(True)
        self.folder_combo_box.clear()
        if self.directory_path is not None:
            for folder in self.get_folders():
                self.folder_combo_box.addItem(self.get_folder_label(folder))
        self.folder_combo_box.blockSignals(False)
        self.update_description()

    def get_folder_label(self, folder: Path) -> str:
        """The name of a folder, relative to the dataset root."""
        if self.directory_path is None:
            return folder.name
        try:
            return str(folder.relative_to(self.directory_path))
        except ValueError:
            return str(folder)

    def get_folders(self) -> list[Path]:
        """The dataset folders of the loaded dataset."""
        if self.directory_path is None:
            return []
        return get_dataset_folders_from_images(self.image_list_model.images,
                                               self.directory_path)

    def get_current_folder(self) -> Path | None:
        """The folder the utilities are applied to."""
        if self.directory_path is None:
            return None
        folders = self.get_folders()
        index = self.folder_combo_box.currentIndex()
        if 0 <= index < len(folders):
            return folders[index]
        return folders[0] if folders else None

    def get_folder_images(self, folder: Path) -> list[Image]:
        """The images of a dataset folder."""
        return [image for image in self.image_list_model.images
                if image.path.parent == folder]

    @Slot()
    def refresh(self):
        """Updates the description of the panel.

        The list of folders only changes when the directory is reloaded,
        so it is not rebuilt here.
        """
        self.update_description()

    @Slot()
    def update_description(self):
        """Shows what the panel will work on."""
        folder = self.get_current_folder()
        if folder is None:
            self.description_label.setText('Load a directory first.')
            self.generate_ignore_tags_button.setEnabled(False)
            self.generate_base_tags_button.setEnabled(False)
            return
        self.generate_ignore_tags_button.setEnabled(True)
        self.generate_base_tags_button.setEnabled(True)
        images = self.get_folder_images(folder)
        counts, caption_count = count_tags([image.tags for image in images])
        trigger = get_most_common_first_tag([image.tags for image in images])
        self.description_label.setText(
            f'{folder.name}: {caption_count} caption(s), '
            f'{len(counts)} unique tag(s).')
        if trigger:
            self.description_label.setText(
                self.description_label.text()
                + f'\nTrigger word: {trigger}')

    def get_ranked_tags(self, folder: Path) -> list[tuple[str, int]]:
        """The tags of a folder, most frequent first.

        The tags with the same count are sorted alphabetically, like the
        ranked list of the reference script.
        """
        images = self.get_folder_images(folder)
        counts, _ = count_tags([image.tags for image in images])
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    def get_trigger(self, folder: Path) -> str:
        """The trigger word of a folder.

        The trigger is the first tag of the captions. The name of the
        folder is also treated as the trigger, because the reference
        script uses it as such.
        """
        images = self.get_folder_images(folder)
        trigger = get_most_common_first_tag([image.tags for image in images])
        return trigger or folder.name.lower()

    def get_skip_tags(self, folder: Path) -> set[str]:
        """The tags that are never offered: the trigger and the name of
        the folder."""
        return {self.get_trigger(folder), folder.name.lower()}

    def get_stored_ignore_tags(self, folder: Path) -> set[str]:
        """The tags of a folder that are already ignored."""
        vocabulary = Vocabulary(self.dataset_root)
        return vocabulary.ignore_tags(folder)

    def get_stored_base_tags(self, folder: Path) -> set[str]:
        """The tags of a folder that are already base tags."""
        vocabulary = Vocabulary(self.dataset_root)
        return set(vocabulary.basetags(folder))

    @property
    def dataset_root(self) -> Path:
        """The root of the dataset, the directory that holds the folders."""
        if self.directory_path is None:
            return Path.cwd()
        return self.directory_path

    @Slot()
    def generate_ignore_tags(self):
        """Picks the tags to ignore and records them in the dataset."""
        folder = self.get_current_folder()
        if folder is None:
            return
        stored = self.get_stored_ignore_tags(folder)
        skip = self.get_skip_tags(folder)
        items = [(tag, count) for tag, count in self.get_ranked_tags(folder)
                 if tag not in skip]
        if not items:
            QMessageBox.information(
                self, 'No Tags',
                'There are no tags to choose from in this folder.')
            return
        dialog = TagPickerDialog(
            parent=self,
            title='Generate Ignore Tags',
            description=('The tags that are checked are never added to a '
                         'caption. They are saved in the `.ignoretags` file '
                         f'of {self.dataset_root.name}, under the section '
                         f'#{folder.name.lower()}.'),
            items=items, stored_tags=stored)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        tags = set(dialog.get_checked_tags())
        if not tags:
            QMessageBox.information(
                self, 'Nothing Selected',
                'No tags were selected — nothing was written.')
            return
        added = append_ignore_tags(self.dataset_root, folder, tags)
        if not added:
            QMessageBox.information(
                self, 'Already Recorded',
                'All of the selected tags are already ignored.')
            return
        QMessageBox.information(
            self, 'Ignore Tags Saved',
            f'{len(added)} tag(s) were added to the ignore list of '
            f'{folder.name}:\n{", ".join(added)}')
        self.update_description()

    @Slot()
    def generate_base_tags(self):
        """Picks the concept tags of a folder and saves them."""
        folder = self.get_current_folder()
        if folder is None:
            return
        stored = self.get_stored_base_tags(folder)
        # The tags that are already ignored are not offered as base tags,
        # because a tag cannot be both.
        skip = self.get_skip_tags(folder) | self.get_stored_ignore_tags(folder)
        items = [(tag, count) for tag, count in self.get_ranked_tags(folder)
                 if tag not in skip]
        if not items:
            QMessageBox.information(
                self, 'No Tags',
                'There are no tags to choose from in this folder.')
            return
        dialog = TagPickerDialog(
            parent=self,
            title='Generate Base Tags',
            description=('The base tags are the concept vocabulary of the '
                         'dataset. They are sent to the model with every '
                         'image, which keeps the terminology consistent. '
                         f'They are saved in the `.basetags` file of '
                         f'{folder.name}.'),
            items=items, stored_tags=stored)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        tags = dialog.get_checked_tags()
        if not tags:
            QMessageBox.information(
                self, 'Nothing Selected',
                'No tags were selected — nothing was written.')
            return
        added = append_basetags(folder, tags)
        if not added:
            QMessageBox.information(
                self, 'Already Recorded',
                'All of the selected tags are already base tags.')
            return
        QMessageBox.information(
            self, 'Base Tags Saved',
            f'{len(added)} tag(s) were added to the base tags of '
            f'{folder.name}:\n{", ".join(added)}')
        self.update_description()

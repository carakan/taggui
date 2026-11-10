"""Dialog for reviewing and editing the dataset vocabulary.

The vocabulary is the `.ignoretags` / `.basetags` files of a dataset: the
tags that are never tagged and the concept tags that are suggested to the
model. It is the GUI counterpart of the `--show-meta`, `--clean`,
`--save-basetags` and `--ignore-tags` options of `lora_tagger.py`.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout)

from tagging.vocabulary import (Vocabulary, append_basetags,
                                append_ignore_tags, parse_ignore_file,
                                parse_tag_file)


class VocabularyDialog(QDialog):
    """Shows the ignore and base tags of the loaded dataset.

    The ignore tags are never added to a caption; the base tags are the
    concept vocabulary of the dataset, suggested to the model.
    """

    def __init__(self, parent, dataset_root: Path):
        super().__init__(parent)
        self.dataset_root = Path(dataset_root)
        self.vocabulary = Vocabulary(self.dataset_root)
        self.setWindowTitle('Dataset Vocabulary')
        self.setMinimumSize(700, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        root_label = QLabel(f'Dataset root: {self.dataset_root}')
        root_label.setWordWrap(True)
        layout.addWidget(root_label)
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel('Folder'))
        self.folder_combo_box = QComboBox()
        self.folders = self.get_folders()
        for folder in self.folders:
            self.folder_combo_box.addItem(folder.name)
        folder_layout.addWidget(self.folder_combo_box, stretch=1)
        layout.addLayout(folder_layout)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)
        form = QFormLayout()
        self.ignore_list = QListWidget()
        self.base_tag_list = QListWidget()
        form.addRow('Ignore tags', self.ignore_list)
        form.addRow('Base tags', self.base_tag_list)
        layout.addLayout(form)
        self.add_buttons_layout = QHBoxLayout()
        self.add_to_ignore_button = QPushButton('Ignore Selected Tag')
        self.add_to_ignore_button.clicked.connect(
            self.add_selected_tag_to_ignore)
        self.add_to_base_button = QPushButton('Save Selected Tag as Base Tag')
        self.add_to_base_button.clicked.connect(
            self.add_selected_tag_to_basetags)
        self.remove_ignore_button = QPushButton('Remove Selected Ignore Tag')
        self.remove_ignore_button.clicked.connect(
            self.remove_selected_ignore_tag)
        self.add_buttons_layout.addWidget(self.add_to_ignore_button)
        self.add_buttons_layout.addWidget(self.add_to_base_button)
        self.add_buttons_layout.addWidget(self.remove_ignore_button)
        layout.addLayout(self.add_buttons_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)
        self.folder_combo_box.currentTextChanged.connect(self.reload)
        self.reload()

    def get_folders(self) -> list[Path]:
        """The dataset folders of the root: the folders holding images, or
        the root itself when the images live directly in it."""
        folders = self.vocabulary.dataset_folders()
        return folders or [self.dataset_root]

    def get_current_folder(self) -> Path:
        """The folder whose vocabulary is shown."""
        index = self.folder_combo_box.currentIndex()
        if 0 <= index < len(self.folders):
            return self.folders[index]
        return self.dataset_root

    def reload(self):
        folder = self.get_current_folder()
        meta = self.vocabulary.folder_meta(folder)
        self.source_label.setText(
            f'Ignore tags: {len(meta["global_ignore"])} global + '
            f'{len(meta["section_ignore"])} section + '
            f'{len(meta["file_ignore"])} folder file = '
            f'{len(meta["ignore"])} merged\n'
            f'Base tags: {len(meta["root_basetags"])} root + '
            f'{len(meta["folder_basetags"])} folder = '
            f'{len(meta["basetags"])} merged')
        self.ignore_list.clear()
        for tag in sorted(meta['ignore']):
            self.ignore_list.addItem(QListWidgetItem(tag))
        self.base_tag_list.clear()
        for tag in meta['basetags']:
            self.base_tag_list.addItem(QListWidgetItem(tag))

    def get_selected_tag(self) -> str:
        item = self.base_tag_list.currentItem()
        if item is None:
            QMessageBox.information(
                self, 'No Tag Selected',
                'Select a base tag first.')
            return ''
        return item.text()

    def add_selected_tag_to_ignore(self):
        tag = self.get_selected_tag()
        if not tag:
            return
        added = append_ignore_tags(self.dataset_root, self.get_current_folder(),
                                    {tag})
        if not added:
            QMessageBox.information(
                self, 'Already Ignored',
                f'"{tag}" is already ignored.')
            return
        self.vocabulary = Vocabulary(self.dataset_root)
        self.reload()

    def add_selected_tag_to_basetags(self):
        tag = self.get_selected_tag()
        if not tag:
            return
        added = append_basetags(self.get_current_folder(), [tag])
        if not added:
            QMessageBox.information(
                self, 'Already a Base Tag',
                f'"{tag}" is already a base tag.')
            return
        self.vocabulary = Vocabulary(self.dataset_root)
        self.reload()

    def remove_selected_ignore_tag(self):
        item = self.ignore_list.currentItem()
        if item is None:
            QMessageBox.information(
                self, 'No Tag Selected',
                'Select an ignore tag first.')
            return
        tag = item.text()
        if not self.remove_ignore_tag(tag):
            QMessageBox.warning(
                self, 'Could Not Remove Tag',
                f'"{tag}" could not be removed. It may be defined in the '
                'global block of the root .ignoretags file.')
            return
        self.vocabulary = Vocabulary(self.dataset_root)
        self.reload()

    def remove_ignore_tag(self, tag: str) -> bool:
        """Removes a tag from the ignore list.

        A tag in the global block of the root file is left alone, because
        it applies to the whole dataset.
        """
        if tag in self.vocabulary.global_tags:
            return False
        ignore_path = self.dataset_root / '.ignoretags'
        global_tags, sections = parse_ignore_file(ignore_path)
        if tag not in sections.get(self.get_current_folder().name.lower(),
                                   []):
            # The tag may come from the folder's own ignore file.
            folder_path = self.get_current_folder() / '.ignoretags'
            if tag not in parse_tag_file(folder_path):
                return False
            self.remove_tag_from_file(folder_path, tag)
            return True
        self.remove_tag_from_section(ignore_path,
                                     self.get_current_folder().name.lower(),
                                     tag)
        return True

    def remove_tag_from_file(self, path: Path, tag: str):
        """Removes a tag from a tag file, keeping the other lines."""
        if not path.exists():
            return
        lines = path.read_text().splitlines()
        kept = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                parts = [part.strip() for part in stripped.split(',')]
                remaining = [part for part in parts if part.lower() != tag]
                if len(remaining) != len(parts):
                    if remaining:
                        kept.append(', '.join(remaining))
                    continue
            kept.append(line)
        path.write_text('\n'.join(kept) + '\n')

    def remove_tag_from_section(self, path: Path, section_name: str, tag: str):
        """Removes a tag from a `#section` of the root ignore file."""
        if not path.exists():
            return
        lines = path.read_text().splitlines()
        kept = []
        in_section = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                header = stripped[1:]
                if header and not header.startswith(' '):
                    in_section = header.lower() == section_name
                kept.append(line)
                continue
            if in_section and stripped:
                parts = [part.strip() for part in stripped.split(',')]
                remaining = [part for part in parts if part.lower() != tag]
                if len(remaining) != len(parts):
                    if remaining:
                        kept.append(', '.join(remaining))
                    continue
            kept.append(line)
        path.write_text('\n'.join(kept) + '\n')

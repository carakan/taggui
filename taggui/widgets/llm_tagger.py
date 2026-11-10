"""Dock widget that tags images with a local, OpenAI-compatible vision LLM.

Replaces the former auto-captioner: no machine-learning framework is
needed, the tags come from a local llama.cpp server running a vision model
such as Pixtral.
"""

import sys
from collections import Counter
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt, Signal, Slot
from PySide6.QtGui import QFontMetrics, QTextCursor
from PySide6.QtWidgets import (QAbstractScrollArea, QDockWidget, QFormLayout,
                               QFrame, QLabel, QMessageBox, QPlainTextEdit,
                               QProgressBar, QScrollArea, QVBoxLayout, QWidget)

from dialogs.audit_log_dialog import AuditLogDialog
from dialogs.prompt_template_dialog import (PromptTemplateDialog,
                                             get_prompt_template)
from dialogs.vocabulary_dialog import VocabularyDialog
from models.image_list_model import ImageListModel
from tagging.audit import AuditLog
from tagging.client import (DEFAULT_API_KEY, DEFAULT_BASE_URL, DEFAULT_MAX_TOKENS,
                            DEFAULT_MODEL, DEFAULT_REPEAT_PENALTY,
                            DEFAULT_TEMPERATURE, DEFAULT_TIMEOUT, LlmClient)
from tagging.tagger import (TagMode, TagOrder, Tagger, TaggerSettings,
                            modified_caption_files)
from tagging.tagging_thread import TaggingThread
from tagging.vocabulary import Vocabulary
from utils.big_widgets import (TallPushButton, checkbox_with_help,
                               label_with_help)
from utils.settings_widgets import (FocusedScrollSettingsComboBox,
                                    FocusedScrollSettingsDoubleSpinBox,
                                    FocusedScrollSettingsSpinBox,
                                    SettingsBigCheckBox, SettingsLineEdit)
from widgets.image_list import ImageList


def set_text_edit_height(text_edit: QPlainTextEdit, line_count: int):
    """
    Set the height of a text edit to the height of a given number of lines.
    """
    document = text_edit.document()
    font_metrics = QFontMetrics(document.defaultFont())
    margins = text_edit.contentsMargins()
    height = int(font_metrics.lineSpacing() * line_count
                 + margins.top() + margins.bottom()
                 + document.documentMargin() * 2
                 + text_edit.frameWidth() * 2)
    text_edit.setFixedHeight(height)


class TagScope(str, Enum):
    """Which images a tagging run covers."""
    SELECTED = 'Selected images'
    FILTERED = 'Filtered images'
    ALL = 'All images'


class LlmTaggerSettingsForm(QVBoxLayout):
    """The settings of a tagging run."""

    def __init__(self):
        super().__init__()
        self.server_form = QFormLayout()
        self.server_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapAllRows)
        self.server_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.base_url_line_edit = SettingsLineEdit(key='llm_tagger_base_url',
                                                   default=DEFAULT_BASE_URL)
        self.base_url_line_edit.setClearButtonEnabled(True)
        self.api_key_line_edit = SettingsLineEdit(key='llm_tagger_api_key',
                                                  default=DEFAULT_API_KEY)
        self.api_key_line_edit.setClearButtonEnabled(True)
        self.api_key_line_edit.setEchoMode(
            self.api_key_line_edit.EchoMode.Password)
        self.model_line_edit = SettingsLineEdit(key='llm_tagger_model',
                                                default=DEFAULT_MODEL)
        self.model_line_edit.setClearButtonEnabled(True)
        self.server_form.addRow(
            label_with_help(
                'Server URL',
                'The URL of the OpenAI-compatible vision model server, such '
                'as a llama.cpp server running Pixtral.'),
            self.base_url_line_edit)
        self.server_form.addRow(
            label_with_help(
                'API key',
                'The bearer token sent to the server. A server without '
                'authentication ignores it.'),
            self.api_key_line_edit)
        self.server_form.addRow(
            label_with_help(
                'Model',
                'The name of the model to use, as the server knows it.'),
            self.model_line_edit)
        self.addLayout(self.server_form)

        self.tagging_form = QFormLayout()
        self.tagging_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapAllRows)
        self.tagging_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.mode_combo_box = FocusedScrollSettingsComboBox(
            key='llm_tagger_mode')
        self.mode_combo_box.addItems(list(TagMode))
        self.order_combo_box = FocusedScrollSettingsComboBox(
            key='llm_tagger_order')
        self.order_combo_box.addItems(list(TagOrder))
        self.trigger_line_edit = SettingsLineEdit(key='llm_tagger_trigger')
        self.trigger_line_edit.setClearButtonEnabled(True)
        self.trigger_line_edit.setPlaceholderText(
            'First tag of the caption (default)')
        self.max_tags_spin_box = FocusedScrollSettingsSpinBox(
            key='llm_tagger_max_tags', default=35, minimum=1, maximum=999)
        self.max_tokens_spin_box = FocusedScrollSettingsSpinBox(
            key='llm_tagger_max_tokens', default=DEFAULT_MAX_TOKENS,
            minimum=1, maximum=99999)
        self.temperature_spin_box = FocusedScrollSettingsDoubleSpinBox(
            key='llm_tagger_temperature', default=DEFAULT_TEMPERATURE,
            minimum=0.01, maximum=2)
        self.temperature_spin_box.setSingleStep(0.01)
        self.repeat_penalty_spin_box = FocusedScrollSettingsDoubleSpinBox(
            key='llm_tagger_repeat_penalty', default=DEFAULT_REPEAT_PENALTY,
            minimum=1, maximum=2)
        self.repeat_penalty_spin_box.setSingleStep(0.01)
        self.timeout_spin_box = FocusedScrollSettingsSpinBox(
            key='llm_tagger_timeout', default=DEFAULT_TIMEOUT, minimum=1,
            maximum=3600)
        self.tagging_form.addRow(
            label_with_help(
                'Mode',
                'How the generated tags are combined with the existing ones: '
                'replaced, appended, kept as they are, and so on.'),
            self.mode_combo_box)
        self.tagging_form.addRow(
            label_with_help(
                'Tag order',
                'The order of the tags in the caption, such as by '
                'frequency, alphabetically, or by the order the model '
                'generated them.'),
            self.order_combo_box)
        self.tagging_form.addRow(
            label_with_help(
                'Trigger word',
                'The trigger word of the dataset. It is added to the '
                'caption separately, so that the model does not have to '
                'repeat it.'),
            self.trigger_line_edit)
        self.tagging_form.addRow(
            label_with_help(
                'Maximum tags',
                'The maximum number of tags to keep per image.'),
            self.max_tags_spin_box)
        self.tagging_form.addRow(
            label_with_help(
                'Maximum tokens',
                'The maximum number of tokens the model generates. Too low '
                'can cut the tags off mid-list.'),
            self.max_tokens_spin_box)
        self.tagging_form.addRow(
            label_with_help(
                'Temperature',
                'How random the generation is. Lower is more focused, '
                'higher is more random. 0 is the most deterministic.'),
            self.temperature_spin_box)
        self.tagging_form.addRow(
            label_with_help(
                'Repeat penalty',
                'Penalizes tokens that already appeared in the caption, to '
                'discourage repetition. 1 disables this.'),
            self.repeat_penalty_spin_box)
        self.tagging_form.addRow(
            label_with_help(
                'Timeout (s)',
                'How long to wait for the server to answer a single '
                'image, in seconds.'),
            self.timeout_spin_box)
        self.addLayout(self.tagging_form)

        self.options_form = QFormLayout()
        self.options_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapAllRows)
        self.options_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.scope_combo_box = FocusedScrollSettingsComboBox(
            key='llm_tagger_scope')
        self.scope_combo_box.addItems(list(TagScope))
        self.skip_tagged_check_box = SettingsBigCheckBox(
            key='llm_tagger_skip_tagged', default=False,
            text='Skip images that already have tags')
        self.resume_check_box = SettingsBigCheckBox(
            key='llm_tagger_resume', default=False,
            text='Resume: skip captions already changed in git')
        self.preserve_vocab_check_box = SettingsBigCheckBox(
            key='llm_tagger_preserve_vocab', default=True,
            text='Keep local vocabulary when pruning')
        self.dry_run_check_box = SettingsBigCheckBox(
            key='llm_tagger_dry_run', default=False,
            text='Dry run (do not write captions)')
        self.audit_log_check_box = SettingsBigCheckBox(
            key='llm_tagger_audit_log', default=False,
            text='Write an audit log')
        self.idle_seconds_spin_box = FocusedScrollSettingsSpinBox(
            key='llm_tagger_idle_seconds', default=8, minimum=0, maximum=600)
        self.limit_spin_box = FocusedScrollSettingsSpinBox(
            key='llm_tagger_limit', default=0, minimum=0, maximum=99999)
        self.options_form.addRow(
            label_with_help(
                'Images',
                'Which images a run covers: the selected ones, the ones '
                'that pass the filter, or all of them.'),
            self.scope_combo_box)
        self.options_form.addRow(checkbox_with_help(
            self.skip_tagged_check_box,
            'Skip the images that already have tags, so that only the '
            'untagged ones are tagged.'))
        self.options_form.addRow(checkbox_with_help(
            self.resume_check_box,
            'Skip the captions that are not changed in git, to continue a '
            'run that was interrupted.'))
        self.options_form.addRow(checkbox_with_help(
            self.preserve_vocab_check_box,
            'Keep the local words that the model does not know, when the '
            'tags are pruned.'))
        self.options_form.addRow(checkbox_with_help(
            self.dry_run_check_box,
            'Show what would be written to the caption files, without '
            'writing anything.'))
        self.options_form.addRow(checkbox_with_help(
            self.audit_log_check_box,
            'Keep a detailed log of the run — the prompt sent to the '
            'model, the raw and parsed response, every filter stage and '
            'the merge decisions — and show it when the run is over.'))
        self.options_form.addRow(
            label_with_help(
                'Idle pause (s)',
                'How long to wait after every few images, to let the '
                'server cool down.'),
            self.idle_seconds_spin_box)
        self.options_form.addRow(
            label_with_help(
                'Image limit (0 = all)',
                'The maximum number of images to tag in a run. 0 tags all '
                'of them.'),
            self.limit_spin_box)
        self.addLayout(self.options_form)

        self.vocabulary_form = QFormLayout()
        self.vocabulary_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapAllRows)
        self.vocabulary_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.vocabulary_path_label = QLabel()
        self.vocabulary_path_label.setWordWrap(True)
        self.vocabulary_form.addRow(
            label_with_help(
                'Vocabulary',
                'The words that the dataset uses. The model is asked to '
                'use them instead of inventing its own.'),
            self.vocabulary_path_label)
        self.addLayout(self.vocabulary_form)
        self.addStretch()

    def get_tagger_settings(self) -> TaggerSettings:
        mode = TagMode(self.mode_combo_box.currentText())
        order = TagOrder(self.order_combo_box.currentText())
        return TaggerSettings(
            mode=mode,
            order=order,
            max_tags=self.max_tags_spin_box.value(),
            max_tokens=self.max_tokens_spin_box.value(),
            temperature=self.temperature_spin_box.value(),
            repeat_penalty=self.repeat_penalty_spin_box.value(),
            timeout=self.timeout_spin_box.value(),
            trigger=self.trigger_line_edit.text().strip(),
            template=get_prompt_template(),
            dry_run=self.dry_run_check_box.isChecked(),
            skip_tagged=self.skip_tagged_check_box.isChecked(),
            resume=self.resume_check_box.isChecked(),
            preserve_vocab=self.preserve_vocab_check_box.isChecked(),
            limit=self.limit_spin_box.value(),
            idle_every=3,
            idle_seconds=self.idle_seconds_spin_box.value())


class LlmTagger(QDockWidget):
    """Tags images with the local vision LLM."""
    tags_generated = Signal(QModelIndex, list)

    def __init__(self, image_list_model: ImageListModel,
                 image_list: ImageList):
        super().__init__()
        self.image_list_model = image_list_model
        self.image_list = image_list
        self.is_tagging = False
        self.tagging_thread = None
        self.replace_last_console_text_edit_block = False
        self.directory_path: Path | None = None

        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('llm_tagger')
        self.setWindowTitle('AI Tagger')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)

        self.start_cancel_button = TallPushButton('Start Tagging')
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat('%v / %m images tagged (%p%)')
        self.progress_bar.hide()
        self.console_text_edit = QPlainTextEdit()
        set_text_edit_height(self.console_text_edit, 4)
        self.console_text_edit.setReadOnly(True)
        self.console_text_edit.hide()
        self.settings_form = LlmTaggerSettingsForm()
        self.prompt_template_button = TallPushButton('Show Prompt Template')
        self.vocabulary_button = TallPushButton('Edit Dataset Vocabulary')
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.start_cancel_button)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.console_text_edit)
        layout.addWidget(self.prompt_template_button)
        layout.addWidget(self.vocabulary_button)
        layout.addLayout(self.settings_form)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(container)
        self.setWidget(scroll_area)

        self.start_cancel_button.clicked.connect(self.start_or_cancel_tagging)
        self.prompt_template_button.clicked.connect(
            self.show_prompt_template_dialog)
        self.vocabulary_button.clicked.connect(self.show_vocabulary_dialog)

    def set_directory_path(self, directory_path: Path | None):
        """The dataset root, used to find the vocabulary files."""
        self.directory_path = directory_path
        if directory_path is None:
            self.settings_form.vocabulary_path_label.setText('No directory')
            return
        vocabulary = Vocabulary(directory_path)
        global_count = len(vocabulary.global_tags)
        section_count = sum(len(tags) for tags in vocabulary.sections.values())
        base_count = len(vocabulary.root_basetags)
        self.settings_form.vocabulary_path_label.setText(
            f'{directory_path}<br>{global_count} global ignore tag(s), '
            f'{section_count} section tag(s), {base_count} base tag(s)')

    @Slot()
    def show_audit_log_dialog(self, audit: AuditLog | None):
        """Shows the audit log of the finished run."""
        if audit is None:
            return
        dialog = AuditLogDialog(parent=self, audit=audit,
                                directory=self.directory_path)
        dialog.exec()

    @Slot()
    def show_prompt_template_dialog(self):
        dialog = PromptTemplateDialog(parent=self)
        dialog.exec()

    @Slot()
    def show_vocabulary_dialog(self):
        if self.directory_path is None:
            QMessageBox.information(
                self, 'No Directory',
                'Load a directory first to edit its vocabulary.')
            return
        dialog = VocabularyDialog(parent=self,
                                  dataset_root=self.directory_path)
        dialog.exec()
        self.set_directory_path(self.directory_path)

    @Slot()
    def start_or_cancel_tagging(self):
        if self.is_tagging:
            self.tagging_thread.is_canceled = True
            self.start_cancel_button.setEnabled(False)
            self.start_cancel_button.setText('Canceling Tagging...')
        else:
            self.start_tagging()

    def set_is_tagging(self, is_tagging: bool):
        self.is_tagging = is_tagging
        button_text = 'Cancel Tagging' if is_tagging else 'Start Tagging'
        self.start_cancel_button.setText(button_text)

    @Slot(str)
    def update_console_text_edit(self, text: str):
        text = text.strip()
        if not text:
            return
        if self.console_text_edit.isHidden():
            self.console_text_edit.show()
        if self.replace_last_console_text_edit_block:
            self.replace_last_console_text_edit_block = False
            self.console_text_edit.moveCursor(QTextCursor.MoveOperation.End)
            self.console_text_edit.moveCursor(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor)
            self.console_text_edit.textCursor().removeSelectedText()
            self.console_text_edit.textCursor().deletePreviousChar()
        self.console_text_edit.appendPlainText(text)

    def set_scope(self, scope: TagScope):
        """Sets the images that a run covers."""
        self.settings_form.scope_combo_box.setCurrentText(scope.value)

    def get_image_indices(self, scope: TagScope) -> list[QModelIndex]:
        """The image indices covered by a run of the given scope."""
        if scope == TagScope.SELECTED:
            return self.image_list.get_selected_image_indices()
        if scope == TagScope.FILTERED:
            proxy_model = self.image_list.list_view.model()
            return [proxy_model.mapToSource(index)
                    for index in range(proxy_model.rowCount())]
        return [self.image_list_model.index(row, 0)
                for row in range(self.image_list_model.rowCount())]

    def get_dataset_root(self, image_indices: list[QModelIndex]) -> Path:
        """The directory the vocabulary files are read from."""
        if self.directory_path is not None:
            return self.directory_path
        folders = {self.image_list_model.data(index, Qt.ItemDataRole.UserRole)
                   .path.parent for index in image_indices}
        if len(folders) == 1:
            return folders.pop()
        return Path.cwd()

    @Slot()
    def start_tagging(self):
        """Starts a tagging run over the images of the current scope."""
        image_indices = self.get_image_indices(
            TagScope(self.settings_form.scope_combo_box.currentText()))
        self.start_tagging_images(image_indices)

    def start_tagging_images(self, image_indices: list[QModelIndex]):
        """Starts a tagging run over the given images.

        The images are tagged with the settings of the panel, whatever the
        scope is set to.
        """
        settings = self.settings_form.get_tagger_settings()
        if not image_indices:
            QMessageBox.information(
                self, 'No Images',
                'There are no images to tag in the current scope.')
            return
        if settings.skip_tagged:
            image_indices = [
                index for index in image_indices
                if not self.image_list_model.data(index,
                                                 Qt.ItemDataRole.UserRole).tags]
        if settings.resume:
            dataset_root = self.get_dataset_root(image_indices)
            modified = modified_caption_files(dataset_root)
            if not modified:
                print('No modified caption files found in git — nothing to '
                      'resume.')
            else:
                image_indices = [
                    index for index in image_indices
                    if not self.is_caption_modified(index, dataset_root,
                                                    modified)]
        if settings.limit:
            image_indices = image_indices[:settings.limit]
        if not image_indices:
            QMessageBox.information(
                self, 'No Images',
                'Every image in the current scope already has tags.')
            return
        client = LlmClient(
            base_url=self.settings_form.base_url_line_edit.text().strip(),
            api_key=self.settings_form.api_key_line_edit.text().strip(),
            model=self.settings_form.model_line_edit.text().strip(),
            timeout=settings.timeout,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
            repeat_penalty=settings.repeat_penalty)
        if not client.is_reachable():
            reply = QMessageBox.critical(
                self, 'Server Not Reachable',
                f'The model server at {client.base_url} is not reachable. '
                'Start it and try again.',
                QMessageBox.StandardButton.Ok)
            return
        dataset_root = self.get_dataset_root(image_indices)
        vocabulary = Vocabulary(dataset_root)
        counts = self.get_tag_counts()
        audit = (AuditLog()
                 if self.settings_form.audit_log_check_box.isChecked()
                 else None)
        tagger = Tagger(client, vocabulary, settings, counts, audit)
        self.set_is_tagging(True)
        self.progress_bar.setRange(0, len(image_indices))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.tagging_thread = TaggingThread(
            self, self.image_list_model, image_indices, tagger, settings,
            audit)
        self.tagging_thread.text_outputted.connect(
            self.update_console_text_edit)
        self.tagging_thread.clear_console_text_edit_requested.connect(
            self.console_text_edit.clear)
        self.tagging_thread.tags_generated.connect(self.tags_generated)
        self.tagging_thread.progress_bar_update_requested.connect(
            self.progress_bar.setValue)
        self.tagging_thread.run_finished.connect(
            lambda *_: self.set_is_tagging(False))
        self.tagging_thread.run_finished.connect(
            lambda *_: self.progress_bar.hide())
        self.tagging_thread.run_finished.connect(
            lambda *_: self.show_audit_log_dialog(audit))
        self.tagging_thread.finished.connect(restore_stdout_and_stderr)
        self.tagging_thread.finished.connect(
            lambda: self.start_cancel_button.setEnabled(True))
        # Redirect `stdout` and `stderr` so that the outputs are displayed in
        # the console text edit.
        sys.stdout = self.tagging_thread
        sys.stderr = self.tagging_thread
        self.tagging_thread.start()

    def is_caption_modified(self, image_index: QModelIndex, dataset_root: Path,
                             modified: set[str]) -> bool:
        """Whether the caption file of an image is already modified in git."""
        image = self.image_list_model.data(image_index,
                                           Qt.ItemDataRole.UserRole)
        try:
            relative_path = image.path.with_suffix('.txt').relative_to(
                dataset_root)
        except ValueError:
            return False
        return str(relative_path) in modified

    def get_tag_counts(self) -> dict[str, int]:
        """How often each tag appears in the loaded images."""
        counts: Counter = Counter()
        for image in self.image_list_model.images:
            counts.update(set(image.tags))
        return dict(counts)

    @Slot()
    def restore_stdout_and_stderr(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


@Slot()
def restore_stdout_and_stderr():
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

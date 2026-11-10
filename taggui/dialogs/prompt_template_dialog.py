"""Dialog that shows (and optionally overrides) the tagging prompt."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel,
                               QMessageBox, QPlainTextEdit, QPushButton,
                               QVBoxLayout)

from tagging.prompt import TAG_PROMPT_TEMPLATE
from utils.settings import get_settings

PROMPT_TEMPLATE_KEY = 'llm_tagger_prompt_template'
COPY_BUTTON_TEXT = 'Copy to Clipboard'
RESET_BUTTON_TEXT = 'Reset to Default'


def get_prompt_template() -> str:
    """The prompt template in use: the user override, or the default."""
    settings = get_settings()
    template = settings.value(PROMPT_TEMPLATE_KEY, defaultValue='', type=str)
    return template or TAG_PROMPT_TEMPLATE


def set_prompt_template(template: str) -> None:
    """Stores a prompt template override (an empty string restores the
    default)."""
    settings = get_settings()
    settings.setValue(PROMPT_TEMPLATE_KEY, template)


class PromptTemplateDialog(QDialog):
    """Shows the full prompt sent to the model.

    The template contains the `{trigger}` and `{max_tags}` placeholders,
    which are replaced for every image. The template can be overridden;
    the default is restored with the reset button.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Prompt Template')
        self.setMinimumSize(700, 600)
        settings = get_settings()
        custom_template = settings.value(PROMPT_TEMPLATE_KEY, defaultValue='',
                                         type=str)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        placeholder_label = QLabel(
            'The placeholders <code>{trigger}</code> and '
            '<code>{max_tags}</code> are replaced for every image. '
            'Edit the text to override the default template.')
        placeholder_label.setWordWrap(True)
        layout.addWidget(placeholder_label)
        self.template_text_edit = QPlainTextEdit()
        self.template_text_edit.setPlainText(custom_template
                                             or TAG_PROMPT_TEMPLATE)
        self.template_text_edit.setTabChangesFocus(True)
        layout.addWidget(self.template_text_edit)
        self.is_modified_label = QLabel()
        layout.addWidget(self.is_modified_label)
        buttons_layout = QVBoxLayout()
        copy_button = QPushButton(COPY_BUTTON_TEXT)
        copy_button.clicked.connect(self.copy_to_clipboard)
        reset_button = QPushButton(RESET_BUTTON_TEXT)
        reset_button.clicked.connect(self.reset_to_default)
        buttons_layout.addWidget(copy_button)
        buttons_layout.addWidget(reset_button)
        layout.addLayout(buttons_layout)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.update_modified_label()

    def update_modified_label(self):
        if self.template_text_edit.toPlainText() == TAG_PROMPT_TEMPLATE:
            self.is_modified_label.setText('Using the default template.')
        else:
            self.is_modified_label.setText('Using a modified template.')

    def copy_to_clipboard(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.template_text_edit.toPlainText())
        QMessageBox.information(self, 'Copied',
                                'The prompt template was copied to the '
                                'clipboard.')

    def reset_to_default(self):
        self.template_text_edit.setPlainText(TAG_PROMPT_TEMPLATE)
        self.update_modified_label()

    def save(self):
        template = self.template_text_edit.toPlainText()
        if template.strip() != TAG_PROMPT_TEMPLATE and '{trigger}' not in template:
            reply = QMessageBox.warning(
                self, 'Invalid Template',
                'The template does not contain the {trigger} placeholder, so '
                'the model is not told which trigger word to leave out. Save '
                'it anyway?',
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
            if reply != QMessageBox.StandardButton.Save:
                return
        set_prompt_template(template)
        self.accept()

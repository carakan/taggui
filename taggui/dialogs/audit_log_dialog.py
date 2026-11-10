"""Dialog that shows the audit log of a tagging run.

The log holds the same lines the `--logs` option of `lora_tagger.py` writes
to its `lora_tagger_<stamp>.log` file: the full prompt sent to the model,
the raw and parsed response, every filter stage, the merge decisions and
the final result.
"""

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                               QLabel, QPlainTextEdit, QPushButton,
                               QVBoxLayout)

from tagging.audit import AuditLog

COPY_BUTTON_TEXT = 'Copy to Clipboard'
SAVE_BUTTON_TEXT = 'Save to File...'


class AuditLogDialog(QDialog):
    """Shows the audit log of a tagging run."""

    def __init__(self, parent=None, audit: AuditLog | None = None,
                 directory: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle('Audit Log')
        self.setMinimumSize(800, 600)
        self.audit = audit if audit is not None else AuditLog()
        self.directory = directory
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        description_label = QLabel(
            'The audit log of the run: the prompt sent to the model, the '
            'raw and parsed response, every filter stage and the merge '
            'decisions.')
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        self.log_text_edit = QPlainTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_text_edit.setPlainText(self.audit.text())
        layout.addWidget(self.log_text_edit)
        buttons_layout = QVBoxLayout()
        copy_button = QPushButton(COPY_BUTTON_TEXT)
        copy_button.clicked.connect(self.copy_to_clipboard)
        save_button = QPushButton(SAVE_BUTTON_TEXT)
        save_button.clicked.connect(self.save_to_file)
        buttons_layout.addWidget(copy_button)
        buttons_layout.addWidget(save_button)
        layout.addLayout(buttons_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def copy_to_clipboard(self):
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.audit.text())

    def save_to_file(self):
        """Writes the log to a file, like the `--logs` option of the script."""
        if self.directory is not None:
            default_path = str(self.audit.default_path(self.directory))
        else:
            default_path = str(self.audit.default_path(Path.cwd()))
        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Save Audit Log', default_path, 'Log files (*.log);;'
            'All files (*)')
        if not file_path:
            return
        try:
            self.audit.save(Path(file_path))
        except OSError as exception:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, 'Error',
                                 f'Failed to save the audit log: {exception}')

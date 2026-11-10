"""Audit log of a tagging run.

The same lines the `--logs` option of `lora_tagger.py` writes to its
`lora_tagger_<stamp>.log` file: the full prompt sent to the model, the raw
and parsed response, every filter stage, the merge decisions and the final
result.

The lines are collected in memory, so that the app can show them in a
dialog. They can also be saved to a file.
"""

import time
from pathlib import Path

# The width of the header lines.
WIDTH = 128


def header_line(text: str) -> str:
    """A header line that fills the width with dashes."""
    text = f'── {text} '
    return text + '─' * max(0, WIDTH - len(text))


class AuditLog:
    """The audit lines of a tagging run."""

    def __init__(self):
        self.lines: list[str] = []

    def write(self, message: str = ''):
        """Appends a line."""
        self.lines.append(message)

    def write_list(self, label: str, items: list):
        """Appends a line listing the items of a group."""
        self.write(f'    {label} ({len(items)}): '
                   f'{", ".join(items) or "(none)"}')

    def header(self, text: str):
        """Appends a header line."""
        self.write(header_line(text))

    def text(self) -> str:
        """The whole log as text."""
        return '\n'.join(self.lines)

    def save(self, path: Path) -> Path:
        """Writes the log to a file."""
        path = Path(path)
        path.write_text(self.text() + '\n', encoding='utf-8')
        return path

    def default_path(self, directory: Path) -> Path:
        """The path the log is saved to by default, next to the dataset."""
        stamp = time.strftime('%Y%m%d-%H%M%S')
        return Path(directory) / f'lora_tagger_{stamp}.log'

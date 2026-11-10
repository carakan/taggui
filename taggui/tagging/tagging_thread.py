"""Background worker that tags images with the local LLM."""

import time

from PySide6.QtCore import QModelIndex, QThread, Qt, Signal

from models.image_list_model import ImageListModel
from tagging.tagger import TagResult, Tagger, TaggerSettings
from utils.image import Image


class TaggingThread(QThread):
    """Tags images one by one and reports the result for each of them."""
    text_outputted = Signal(str)
    clear_console_text_edit_requested = Signal()
    # The image index and the new tags.
    tags_generated = Signal(QModelIndex, list)
    progress_bar_update_requested = Signal(int)
    run_finished = Signal(int, int)

    def __init__(self, parent, image_list_model: ImageListModel,
                 image_indices: list[QModelIndex], tagger: Tagger,
                 settings: TaggerSettings):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.image_indices = image_indices
        self.tagger = tagger
        self.settings = settings
        self.is_error = False
        self.is_canceled = False

    def run(self):
        try:
            self.run_tagging()
        except Exception:
            self.is_error = True
            raise

    def run_tagging(self):
        image_count = len(self.image_indices)
        succeeded = 0
        self.clear_console_text_edit_requested.emit()
        print(f'Tagging {image_count} '
              f'{"image" if image_count == 1 else "images"} with '
              f'{self.tagger.client.model}...')
        start_time = time.perf_counter()
        for i, image_index in enumerate(self.image_indices):
            if self.is_canceled:
                print('Canceled tagging.')
                return
            image: Image = self.image_list_model.data(
                image_index, Qt.ItemDataRole.UserRole)
            result: TagResult = self.tagger.tag_image(image.path, image.tags)
            if result.is_success:
                succeeded += 1
                if not self.settings.dry_run:
                    self.tags_generated.emit(image_index, result.tags)
                print(f'{image.path.name}: {", ".join(result.tags)}')
            else:
                print(f'{image.path.name}: ERROR — {result.error}')
            self.progress_bar_update_requested.emit(i + 1)
            if (not self.settings.dry_run and self.settings.idle_every
                    and (i + 1) % self.settings.idle_every == 0
                    and i + 1 < image_count):
                print(f'Idle {self.settings.idle_seconds}s...')
                time.sleep(self.settings.idle_seconds)
        elapsed = time.perf_counter() - start_time
        print(f'Finished tagging {succeeded}/{image_count} images in '
              f'{elapsed:.1f}s'
              + (' (dry run — nothing written)' if self.settings.dry_run
                 else ''))
        self.run_finished.emit(succeeded, image_count)

    def write(self, text: str):
        """Lets the thread stand in for `sys.stdout`."""
        self.text_outputted.emit(text)

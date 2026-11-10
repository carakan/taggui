"""Background worker that tags images with the local LLM."""

import time

from PySide6.QtCore import QModelIndex, QThread, Qt, Signal

from models.image_list_model import ImageListModel
from tagging.audit import AuditLog
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
                 settings: TaggerSettings, audit: AuditLog | None = None):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.image_indices = image_indices
        self.tagger = tagger
        self.settings = settings
        self.audit = audit
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
        failed: list[str] = []
        old_tag_sum = 0
        new_tag_sum = 0
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
                old_tag_sum += result.old_tag_count
                new_tag_sum += len(result.tags)
                if not self.settings.dry_run:
                    self.tags_generated.emit(image_index, result.tags)
                print(f'{image.path.name}: {", ".join(result.tags)}')
            else:
                failed.append(str(image.path))
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
        if self.audit is not None:
            self.write_run_summary(succeeded, image_count, failed, elapsed,
                                   old_tag_sum, new_tag_sum)
        self.run_finished.emit(succeeded, image_count)

    def write_run_summary(self, succeeded: int, image_count: int,
                          failed: list[str], elapsed: float,
                          old_tag_sum: int, new_tag_sum: int):
        """The summary of the run, at the end of the audit log."""
        minutes, seconds = divmod(int(elapsed), 60)
        self.audit.header('RUN SUMMARY')
        self.audit.write(f'  result: {succeeded}/{image_count} succeeded, '
                         f'{len(failed)} failed')
        duration = f'{minutes}m{seconds:02d}s'
        if image_count:
            duration += f' (~{elapsed / image_count:.1f}s/image)'
        self.audit.write(f'  duration: {duration}')
        if succeeded:
            self.audit.write(f'  tags: avg {old_tag_sum / succeeded:.1f} -> '
                             f'{new_tag_sum / succeeded:.1f} per image')
        for image_path in failed:
            self.audit.write(f'  failed: {image_path}')

    def write(self, text: str):
        """Lets the thread stand in for `sys.stdout`."""
        self.text_outputted.emit(text)

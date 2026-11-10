import argparse
import logging
import os
import sys
import traceback
import warnings

from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QApplication, QMessageBox

from utils.settings import DEFAULT_SETTINGS, get_settings
from widgets.main_window import MainWindow


def parse_arguments():
    """The command line options of the application."""
    parser = argparse.ArgumentParser(
        description='Tag manager and captioner for image datasets.')
    parser.add_argument(
        '--logs', action='store_true',
        help='write an audit log of the tagging runs: the full prompt sent '
             'to the model, the raw and parsed response, every filter '
             'stage, the ignore-tag drops and the final result. The log is '
             'shown when the run is over, and can be saved to a file.')
    return parser.parse_args()


def apply_ui_scale():
    """
    Set `QT_SCALE_FACTOR` from the saved UI scale setting, if any. Must run
    before `QApplication` is constructed, since Qt only reads this
    environment variable at that point.
    """
    settings = get_settings()
    ui_scale_percent = settings.value(
        'ui_scale_percent', defaultValue=DEFAULT_SETTINGS['ui_scale_percent'],
        type=int)
    if ui_scale_percent != 100:
        os.environ['QT_SCALE_FACTOR'] = str(ui_scale_percent / 100)


def suppress_warnings():
    """Suppress all warnings when not in a development environment."""
    environment = os.getenv('TAGGUI_ENVIRONMENT')
    if environment == 'development':
        print('Running in development environment.')
        return
    # The `exifread` module logs a warning for every image without Exif
    # tags, which floods the log.
    logging.getLogger('exifread').setLevel(logging.ERROR)
    logging.basicConfig(level=logging.ERROR)
    warnings.simplefilter('ignore')


def run_gui(write_audit_log: bool = False):
    apply_ui_scale()
    app = QApplication([])
    # The application name is shown in the taskbar.
    app.setApplicationName('TagGUI')
    # The application display name is shown in the title bar.
    app.setApplicationDisplayName('TagGUI')
    app.setStyle('Fusion')
    # Disable the allocation limit to allow loading large images.
    QImageReader.setAllocationLimit(0)
    main_window = MainWindow(app)
    main_window.set_audit_log_enabled(write_audit_log)
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    suppress_warnings()
    arguments = parse_arguments()
    try:
        run_gui(arguments.logs)
    except Exception as exception:
        settings = get_settings()
        settings.clear()
        error_message_box = QMessageBox()
        error_message_box.setWindowTitle('Error')
        error_message_box.setIcon(QMessageBox.Icon.Critical)
        error_message_box.setText(str(exception))
        error_message_box.setDetailedText(traceback.format_exc())
        error_message_box.exec()
        raise exception

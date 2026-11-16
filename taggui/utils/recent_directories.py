"""The list of the directories that were opened last.

The list is kept between the runs, so that the datasets of the user are
one click away. The most recent directory comes first.
"""

from pathlib import Path

from utils.settings import get_settings

SETTINGS_KEY = 'recent_directories'
# The number of directories that are kept.
MAXIMUM = 10


def get_recent_directories() -> list[Path]:
    """The directories that were opened last, most recent first."""
    settings = get_settings()
    paths = settings.value(SETTINGS_KEY, defaultValue=[], type=list)
    return [Path(path) for path in paths]


def add_recent_directory(path: Path) -> list[Path]:
    """Puts a directory at the top of the list and saves the list.

    A directory that is already in the list moves to the top instead of
    being added twice.
    """
    path = Path(path).resolve()
    paths = [directory for directory in get_recent_directories()
             if directory != path]
    paths.insert(0, path)
    paths = paths[:MAXIMUM]
    get_settings().setValue(SETTINGS_KEY,
                            [str(directory) for directory in paths])
    return paths


def remove_missing_directories() -> list[Path]:
    """Drops the directories that are gone from the list.

    A directory on a disk that is not connected any more is of no use.
    Returns the directories that are left.
    """
    paths = get_recent_directories()
    existing = [directory for directory in paths if directory.is_dir()]
    if len(existing) != len(paths):
        get_settings().setValue(SETTINGS_KEY,
                                [str(directory) for directory in existing])
    return existing


def clear_recent_directories() -> None:
    """Empties the list."""
    get_settings().setValue(SETTINGS_KEY, [])

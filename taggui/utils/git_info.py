"""Git information about the caption files of a dataset.

The caption files of a dataset are usually kept in a git repository, so the
committed version of a caption can be compared with the current one. The
difference is shown as the tags that were added and the tags that were
removed, which is more useful for tagging than a text diff of a caption
that is a single line of comma-separated tags.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# How long the cached git state stays valid, in seconds. The state changes
# while the captions are edited, so it must not be cached for long.
CACHE_TTL_SECONDS = 2.0


@dataclass
class CaptionDiff:
    """The difference between a caption file and its committed version."""
    # Whether the caption differs from the committed version.
    is_modified: bool = False
    # Whether the caption file is not tracked by git at all.
    is_new: bool = False
    # The tags that the current caption has and the committed one does not.
    added_tags: list[str] = field(default_factory=list)
    # The tags that the committed caption has and the current one does not.
    removed_tags: list[str] = field(default_factory=list)


def split_tags(text: str) -> list[str]:
    """Splits a caption file into tags.

    The caption files hold the tags separated by commas; some tools write
    one tag per line instead, so both are accepted.
    """
    tags: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        for part in line.split(','):
            tag = ' '.join(part.split())
            if tag and tag not in tags:
                tags.append(tag)
    return tags


def find_repository_root(directory: Path) -> Path | None:
    """The root of the git repository holding the directory.

    Returns None when the directory is not in a git repository or git is
    not installed.
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=directory, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    # The root is resolved, because git reports the real path of the
    # repository, which can differ from the given path by a symbolic link.
    return Path(root).resolve() if root else None


def get_relative_path(path: Path, root: Path) -> Path | None:
    """The path relative to the root, or None when it is outside.

    Both paths are resolved, because a symbolic link in the path (such as
    `/var` on macOS) would otherwise make the comparison fail.
    """
    try:
        return Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return None


def get_modified_paths(repository_root: Path) -> set[str]:
    """The paths of the files that git reports as changed.

    The paths are relative to the repository root and are returned for the
    whole repository, so one call covers the whole dataset.
    """
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'], cwd=repository_root,
            capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return set()
    if result.returncode != 0:
        return set()
    paths = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].split(' -> ')[-1].strip('"')
        if path:
            paths.add(path)
    return paths


def get_head_tags(repository_root: Path, caption_path: Path) -> list[str] | None:
    """The tags of the committed version of a caption file.

    Returns None when the file is not tracked by git or git has no version
    of it.
    """
    relative_path = get_relative_path(caption_path, repository_root)
    if relative_path is None:
        return None
    try:
        result = subprocess.run(
            ['git', 'show', f'HEAD:{relative_path}'], cwd=repository_root,
            capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return split_tags(result.stdout)


def get_head_tags_batch(repository_root: Path,
                        caption_paths: list[Path]) -> dict[Path,
                                                         list[str] | None]:
    """The committed tags of many caption files, in one git call.

    A caption file that git does not know about maps to None. The paths
    outside the repository are left out of the result.
    """
    result: dict[Path, list[str] | None] = {}
    # Maps the query of a path to the path, so that the answers of git can
    # be matched to the files they belong to.
    path_by_query: dict[str, Path] = {}
    queries: list[str] = []
    for caption_path in caption_paths:
        relative_path = get_relative_path(caption_path, repository_root)
        if relative_path is None:
            continue
        result[caption_path] = None
        query = f'HEAD:{relative_path}'
        path_by_query[query] = caption_path
        queries.append(query)
    if not queries:
        return result
    try:
        process = subprocess.run(
            ['git', 'cat-file', '--batch'], cwd=repository_root,
            input=('\n'.join(queries) + '\n').encode(),
            capture_output=True)
    except (FileNotFoundError, OSError):
        return result
    if process.returncode != 0:
        return result
    # The output of `--batch` is a header line per query, followed by the
    # content of the object and a newline. The content is read by its size
    # in bytes, because it can hold any number of lines.
    output = process.stdout
    position = 0
    for query in queries:
        header_end = output.find(b'\n', position)
        if header_end == -1:
            break
        header = output[position:header_end].decode('utf-8', errors='replace')
        position = header_end + 1
        caption_path = path_by_query.get(query)
        if caption_path is None or ' missing' in header:
            continue
        parts = header.split()
        if len(parts) < 3:
            continue
        try:
            size = int(parts[2])
        except ValueError:
            continue
        content = output[position:position + size]
        position += size + 1
        result[caption_path] = split_tags(content.decode('utf-8',
                                                         errors='replace'))
    return result


def compute_diff(head_tags: list[str] | None,
                 current_tags: list[str]) -> CaptionDiff:
    """The tags that were added and removed since the committed version."""
    if head_tags is None:
        # The file is not tracked by git, so all of its tags are new.
        return CaptionDiff(is_modified=bool(current_tags), is_new=True,
                           added_tags=list(current_tags))
    head_tag_set = set(head_tags)
    current_tag_set = set(current_tags)
    added = [tag for tag in current_tags if tag not in head_tag_set]
    removed = [tag for tag in head_tags if tag not in current_tag_set]
    return CaptionDiff(is_modified=bool(added or removed),
                       added_tags=added, removed_tags=removed)


class GitCaptionState:
    """The git state of a dataset, with a short-lived cache.

    The state is read once per dataset and reused for a couple of seconds,
    so that selecting images does not spawn a git process every time.
    """

    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory else None
        self.repository_root: Path | None = None
        self.modified_paths: set[str] = set()
        self._head_tags_cache: dict[Path, list[str] | None] = {}
        self._loaded_at = 0.0

    def set_directory(self, directory: Path | None):
        """Points the state at another directory and drops the cache."""
        self.directory = Path(directory) if directory else None
        self.invalidate()

    def invalidate(self):
        """Forces the git state to be read again."""
        self._loaded_at = 0.0
        self._head_tags_cache.clear()

    def refresh(self, force: bool = False):
        """Reads the git state of the dataset."""
        import time
        now = time.monotonic()
        if not force and self.directory is not None \
                and now - self._loaded_at < CACHE_TTL_SECONDS:
            return
        self._loaded_at = now
        self._head_tags_cache.clear()
        if self.directory is None or not self.directory.exists():
            self.repository_root = None
            self.modified_paths = set()
            return
        self.repository_root = find_repository_root(self.directory)
        self.modified_paths = (get_modified_paths(self.repository_root)
                                if self.repository_root else set())

    def is_modified(self, caption_path: Path, force: bool = False) -> bool:
        """Whether the caption file is changed according to git."""
        self.refresh(force=force)
        if self.repository_root is None:
            return False
        relative_path = get_relative_path(caption_path, self.repository_root)
        if relative_path is None:
            return False
        return str(relative_path) in self.modified_paths

    def get_diff(self, caption_path: Path,
                 current_tags: list[str]) -> CaptionDiff:
        """The difference between the caption file and its committed
        version."""
        self.refresh()
        if self.repository_root is None:
            return CaptionDiff()
        if not self.is_modified(caption_path):
            return CaptionDiff()
        head_tags = self._head_tags_cache.get(caption_path)
        if caption_path not in self._head_tags_cache:
            head_tags = get_head_tags(self.repository_root, caption_path)
            self._head_tags_cache[caption_path] = head_tags
        return compute_diff(head_tags, current_tags)

    def get_diffs(self, caption_paths: list[Path],
                  current_tags: dict[Path, list[str]],
                  force: bool = False) -> dict[Path, CaptionDiff]:
        """The differences of many caption files, in one git call.

        The files that git does not report as changed are left out of the
        result. `force` reads the git state even when it is still cached.
        """
        self.refresh(force=force)
        diffs: dict[Path, CaptionDiff] = {}
        if self.repository_root is None:
            return diffs
        changed_paths = []
        for caption_path in caption_paths:
            relative_path = get_relative_path(caption_path,
                                             self.repository_root)
            if relative_path is None:
                continue
            if str(relative_path) in self.modified_paths:
                changed_paths.append(caption_path)
        if not changed_paths:
            return diffs
        head_tags = get_head_tags_batch(self.repository_root, changed_paths)
        for caption_path in changed_paths:
            diffs[caption_path] = compute_diff(
                head_tags.get(caption_path),
                current_tags.get(caption_path, []))
        return diffs

"""Vocabulary files (`.ignoretags` / `.basetags`) for a dataset.

Ported from `lora_tagger.py`. The dataset root holds a `.ignoretags` file
whose global block applies to every folder, plus one `#folder` section per
dataset folder. Each folder may also hold its own `.ignoretags` and
`.basetags` files, and the root may hold a `.basetags` file.
"""

import re
from pathlib import Path


def parse_tag_file(path: Path) -> list[str]:
    """Reads a tag file in comma-separated and/or row-based (one tag per
    line) format; lines may be mixed. '#' starts a comment line."""
    tags: list[str] = []
    if not path.exists():
        return tags
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(',') if ',' in line else [line]
        for tag in parts:
            tag = re.sub(r'\s+', ' ', tag.strip().lower())
            if tag and tag not in tags:
                tags.append(tag)
    return tags


def parse_ignore_file(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Parses a `.ignoretags` file into (global_tags, {folder_name: tags}).

    Lines before the first section header are global. '#name' (no space
    after the hash) starts a section; a header may list several
    comma-separated folder names and a folder named in several blocks gets
    the UNION of them. '# comment' (hash followed by space) is a plain
    comment.
    """
    global_tags: list[str] = []
    sections: dict[str, list[str]] = {}
    current = global_tags
    block_names: list[str] = []
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                header = line[1:]
                if header and not header.startswith(' '):
                    block_names = [name.strip().lower()
                                   for name in header.split(',')
                                   if name.strip()]
                    if block_names:
                        for name in block_names:
                            sections.setdefault(name, [])
                        current = sections[block_names[0]]
                continue
            parts = line.split(',') if ',' in line else [line]
            for tag in parts:
                tag = re.sub(r'\s+', ' ', tag.strip().lower())
                if not tag:
                    continue
                if block_names:
                    for name in block_names:
                        tag_list = sections[name]
                        if tag not in tag_list:
                            tag_list.append(tag)
                elif tag not in current:
                    current.append(tag)
    return global_tags, sections


class Vocabulary:
    """The merged ignore/base tag vocabulary of a dataset root.

    `root` is the dataset root (the directory holding the dataset folders
    and the root-level `.ignoretags` / `.basetags` files).
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.global_tags, self.sections = parse_ignore_file(
            self.root / '.ignoretags')
        self.root_basetags = parse_tag_file(self.root / '.basetags')
        self._folder_cache: dict[str, dict[str, object]] = {}

    def folder_meta(self, folder: Path) -> dict[str, object]:
        """All ignore/base tag sources for a folder, merged and broken down:
        global root .ignoretags, root #folder section, <folder>/.ignoretags,
        root .basetags, <folder>/.basetags."""
        folder = Path(folder)
        key = str(folder)
        if key in self._folder_cache:
            return self._folder_cache[key]
        section_ignore = self.sections.get(folder.name.lower(), [])
        if folder == self.root:
            # The root file holds the global block and the folder sections;
            # it contributes no folder-level tags of its own.
            file_ignore = []
        else:
            file_ignore = parse_tag_file(folder / '.ignoretags')
        folder_basetags = parse_tag_file(folder / '.basetags')
        ignore = set(self.global_tags) | set(section_ignore) | set(file_ignore)
        basetags = list(self.root_basetags)
        for tag in folder_basetags:
            if tag not in basetags:
                basetags.append(tag)
        meta = {
            'global_ignore': self.global_tags,
            'section_ignore': section_ignore,
            'file_ignore': file_ignore,
            'root_basetags': self.root_basetags,
            'folder_basetags': folder_basetags,
            'ignore': ignore,
            'basetags': basetags,
        }
        self._folder_cache[key] = meta
        return meta

    def ignore_tags(self, folder: Path) -> set[str]:
        return self.folder_meta(folder)['ignore']

    def basetags(self, folder: Path) -> list[str]:
        return self.folder_meta(folder)['basetags']

    def global_tag_counts(self) -> dict[str, int]:
        """Counts how often each tag appears across the whole dataset.

        Each caption file contributes each of its tags once.
        """
        counts: dict[str, int] = {}
        for folder in self.dataset_folders():
            for tag_file_path in folder.glob('*.txt'):
                tags = parse_tag_file(tag_file_path)
                for tag in set(tags):
                    counts[tag] = counts.get(tag, 0) + 1
        return counts

    def dataset_folders(self) -> list[Path]:
        """The dataset folders of the root: direct subdirectories holding
        images."""
        if not self.root.is_dir():
            return []
        folders = [path for path in self.root.iterdir()
                   if path.is_dir() and not path.name.startswith('.')
                   and any(path.glob('*.jpg'))]
        return sorted(folders)


def count_tags(tag_lists: list[list[str]]) -> tuple[dict[str, int], int]:
    """Counts the tags of a list of captions.

    Every caption contributes each of its tags once, so a tag that appears
    in every caption of a folder has the count of the folder. Returns the
    counts and the number of captions.
    """
    counts: dict[str, int] = {}
    for tags in tag_lists:
        for tag in {tag.lower() for tag in tags}:
            counts[tag] = counts.get(tag, 0) + 1
    return counts, len(tag_lists)


def get_most_common_first_tag(tag_lists: list[list[str]]) -> str:
    """The most common first tag of the captions, the trigger word.

    An empty string when the captions are empty.
    """
    counts: dict[str, int] = {}
    for tags in tag_lists:
        if not tags:
            continue
        tag = tags[0].lower()
        counts[tag] = counts.get(tag, 0) + 1
    if not counts:
        return ''
    return max(counts, key=lambda tag: counts[tag])


def get_dataset_folders_from_images(images: list, root: Path) -> list[Path]:
    """The dataset folders of the root, from the loaded images.

    A dataset folder is a directory that holds images. The root itself is
    a dataset folder when it holds images directly.
    """
    root = Path(root)
    folders = {Path(image.path).parent for image in images}
    folders = {folder for folder in folders
               if folder == root or root in folder.parents}
    return sorted(folders)


def append_ignore_tags(root: Path, folder: Path, tags: set[str]) -> list[str]:
    """Appends tags to the root `.ignoretags` under a `#folder` section.

    Returns the tags that were actually added (tags already known from any
    source are skipped).
    """
    root = Path(root)
    folder = Path(folder)
    ignore_path = root / '.ignoretags'
    global_tags, sections = parse_ignore_file(ignore_path)
    known = set(global_tags)
    known.update(sections.get(folder.name.lower(), []))
    known.update(parse_tag_file(folder / '.ignoretags'))
    new = sorted(tags - known)
    if not new:
        return []
    existing_text = ignore_path.read_text() if ignore_path.exists() else ''
    with ignore_path.open('a') as file:
        if existing_text and not existing_text.endswith('\n'):
            file.write('\n')
        file.write(f'#{folder.name.lower()}\n' + ', '.join(new) + '\n')
    return new


def append_basetags(folder: Path, tags: list[str]) -> list[str]:
    """Appends tags to `<folder>/.basetags`, one per row.

    Returns the tags that were actually added.
    """
    folder = Path(folder)
    path = folder / '.basetags'
    existing = parse_tag_file(path)
    new = [tag for tag in tags if tag not in existing]
    if not new:
        return []
    existing_text = path.read_text() if path.exists() else ''
    with path.open('a') as file:
        if existing_text and not existing_text.endswith('\n'):
            file.write('\n')
        file.write('\n'.join(new) + '\n')
    return new

"""The tagging engine: turns an image into a caption using the local LLM.

Ported from the retag loop of `lora_tagger.py`. The engine is deliberately
free of any Qt dependency so that it can be tested without a GUI.
"""

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from tagging.client import LlmClient, LlmError
from tagging.prompt import build_prompt
from tagging.rules import (PROMPT_WHITELIST, clean_tag_list, filter_tags,
                           is_degenerate, merge_tags, order_tags)
from tagging.vocabulary import Vocabulary


class TagMode(str, Enum):
    """How the model response is combined with the existing caption."""
    # Additive: the new tags are added to the existing ones.
    RETAG = 'Retag (add to existing tags)'
    # Rebuild the caption from the image alone.
    PRUNE = 'Prune (rebuild from image)'


class TagOrder(str, Enum):
    """How the tags of a caption are ordered."""
    RANK = 'By frequency'
    ALPHA = 'Alphabetical'


@dataclass
class TaggerSettings:
    """The parameters of a tagging run."""
    mode: TagMode = TagMode.RETAG
    order: TagOrder = TagOrder.RANK
    max_tags: int = 35
    max_tokens: int = 400
    temperature: float = 0.2
    repeat_penalty: float = 1.15
    timeout: int = 300
    trigger: str = ''
    template: str | None = None
    dry_run: bool = False
    # Skip images that already have tags.
    skip_tagged: bool = False
    # Skip images whose caption file is already modified in git, to resume an
    # interrupted run.
    resume: bool = False
    # Rebuild the caption from the image, but keep up to 10 dataset-local
    # terms of the old caption as protected vocabulary.
    preserve_vocab: bool = True
    limit: int = 0
    idle_every: int = 3
    idle_seconds: int = 8


@dataclass
class TagResult:
    """The outcome of tagging one image."""
    tags: list[str] = field(default_factory=list)
    raw_response: str = ''
    prompt: str = ''
    is_success: bool = False
    error: str = ''
    # Tags that were dropped while merging, for the run log.
    dropped: list[str] = field(default_factory=list)


def git_modified_txt(root: Path) -> set[str]:
    """Repo-relative paths of .txt files already modified vs git HEAD.

    Used to resume an interrupted run, like the `--continue` option of
    `lora_tagger.py`. Returns an empty set when the root is not a git
    repository.
    """
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain', '--', '*.txt'],
            cwd=root, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return set()
    modified = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].split(' -> ')[-1].strip('"')
        if path.endswith('.txt'):
            modified.add(path)
    return modified


def modified_caption_files(root: Path) -> set[str]:
    """The caption files of the dataset root that are already modified in
    git.

    Used to resume an interrupted run, like the `--continue` option of
    `lora_tagger.py`. Returns an empty set when the root is not a git
    repository or git is not installed.
    """
    return git_modified_txt(Path(root))


class Tagger:
    """Tags images with the local vision LLM.

    The trigger word is the first tag of the existing caption; when the
    caption is empty the name of the image folder is used instead.
    """

    def __init__(self, client: LlmClient, vocabulary: Vocabulary,
                 settings: TaggerSettings | None = None,
                 counts: dict[str, int] | None = None):
        self.client = client
        self.vocabulary = vocabulary
        self.settings = settings or TaggerSettings()
        self.counts = counts if counts is not None else {}

    def get_trigger(self, image_path: Path, existing_tags: list[str]) -> str:
        if self.settings.trigger:
            return self.settings.trigger
        if existing_tags:
            return existing_tags[0]
        return Path(image_path).parent.name.lower()

    def get_anchors(self, existing_tags: list[str], trigger: str) -> list[str]:
        """Up to 7 of the most frequent existing tags, used as ground-truth
        context for the model."""
        return sorted((tag for tag in existing_tags if tag != trigger),
                      key=lambda tag: -self.counts.get(tag, 0))[:7]

    def get_preserve(self, existing_tags: list[str], trigger: str,
                     basetags: list[str], ignore: set[str]) -> list[str]:
        """Up to 10 dataset-local terms of the old caption that are
        protected from being lost when the caption is rebuilt."""
        if not self.settings.preserve_vocab:
            return []
        return [tag for tag in existing_tags
                if tag != trigger and tag not in basetags and tag not in ignore
                ][:10]

    def build_prompt(self, image_path: Path, existing_tags: list[str],
                     trigger: str, basetags: list[str], anchors: list[str],
                     preserve: list[str]) -> str:
        return build_prompt(
            trigger=trigger,
            max_tags=self.settings.max_tags,
            template=self.settings.template,
            basetags=basetags,
            anchors=anchors,
            preserve=preserve,
            prune=self.settings.mode == TagMode.PRUNE)

    def request_tags(self, prompt: str, image_path: Path,
                     whitelist: set[str],
                     preserve: set[str]) -> tuple[list[str], str, str]:
        """Runs one model request and returns (tags, raw response, error).

        A degenerate response is retried once; an empty response is an
        error, in which case the old caption is kept.
        """
        error = ''
        raw = ''
        for attempt in range(2):
            try:
                raw, finish_reason = self.client.complete(prompt, image_path)
            except LlmError as exception:
                error = str(exception)
                return [], raw, error
            tags = clean_tag_list(raw, word_cap=3)
            if finish_reason == 'length' and tags:
                # The response was cut off; the last tag may be truncated.
                tags = tags[:-1]
            tags = filter_tags(tags, prompt, whitelist, preserve)
            if len(tags) > self.settings.max_tags:
                tags = tags[:self.settings.max_tags]
            if tags and not is_degenerate(tags):
                return tags, raw, ''
            error = 'empty or degenerate response from model'
        return [], raw, error

    def tag_image(self, image_path: Path,
                  existing_tags: list[str] | None = None) -> TagResult:
        """Tags one image and returns the new caption tags."""
        image_path = Path(image_path)
        existing_tags = list(existing_tags or [])
        folder = image_path.parent
        meta = self.vocabulary.folder_meta(folder)
        basetags = meta['basetags']
        ignore = meta['ignore']
        trigger = self.get_trigger(image_path, existing_tags)
        prune = self.settings.mode == TagMode.PRUNE
        anchors = self.get_anchors(existing_tags, trigger)
        preserve = (self.get_preserve(existing_tags, trigger, basetags, ignore)
                    if prune else [])
        prompt = self.build_prompt(image_path, existing_tags, trigger,
                                   basetags, anchors, preserve)
        # Tags that are allowed to echo the prompt text: the vocabulary
        # lists and the count/framing tags the prompt itself mentions.
        whitelist = (set(PROMPT_WHITELIST) | set(basetags) | set(anchors)
                     | set(preserve))
        tags, raw, error = self.request_tags(prompt, image_path, whitelist,
                                             set(preserve))
        if error:
            return TagResult(raw_response=raw, prompt=prompt, is_success=False,
                             error=error)
        merged = merge_tags(trigger, tags, existing_tags, ignore, prune)
        order = ('alpha' if self.settings.order == TagOrder.ALPHA else 'rank')
        final = order_tags(trigger, merged, order, self.counts)
        dropped = [tag for tag in existing_tags if tag not in final]
        return TagResult(tags=final, raw_response=raw, prompt=prompt,
                         is_success=True, dropped=dropped)

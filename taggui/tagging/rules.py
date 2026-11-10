"""Pure tagging rules ported from `lora_tagger.py`.

Everything here is deterministic and side-effect free: parsing a raw model
response, filtering it, folding color chains, merging it with the existing
caption and ordering the result.
"""

import re

ARTIFACT_RE = re.compile(r"<\|[^|]*\|>|</?assistant>?|<\/?s>|\[/?INST\]")
ROLE_WORDS = {'user', 'assistant', 'system'}
PERSON_COUNT_RE = re.compile(
    r"^\d+\+?(?:girls?|boys?|women|woman|men|man|children|child|"
    r"people|persons?|kids?|babies|baby)$")
ORIGIN_TAG_RE = re.compile(
    r"^(spanish|latin|latina|latino|mexican|peruvian|argentine|argentinian|"
    r"brazilian|chilean|colombian|venezuelan|ecuadorian|american|european|"
    r"african|asian|indigenous|native)-")
BARE_COLOR_RE = re.compile(
    r"^(?:(?:light|dark|bright|pale|deep)\s+)?"
    r"(?:red|blue|green|yellow|black|white|pink|purple|orange|brown|gr[ae]y|"
    r"beige|gold(?:en)?|silver|violet|turquoise|magenta|cyan|teal|maroon|"
    r"navy|olive|coral|salmon|khaki|cream|ivory|lavender|lilac|tan|bronze|"
    r"copper|multicolored|colorful)$")
QUALITY_TAG_RE = re.compile(
    r"^(?:best|high|highly|highest|ultra|super|top|good|very|extremely)"
    r"[ -]?(?:quality|res(?:olution)?|detail(?:ed)?|score|rating|aesthetic)"
    r"|^masterpiece$|^\d+k$|^hd$|^uhd$|^hdr$|^absurdres$|^highres$"
    r"|^award[ -]?winning$|^official[ -]?art$|^very[ -]?aesthetic$"
    r"|^photorealistic$|^realistic$"
    r"|^(?:professional|amateur|candid|stock)[ -]?(?:photo|photography)?$"
    r"|^(?:photo|photograph|photography|picture|image|footage|video|"
    r"watermark|text|logo)s?$")

# House color rule: multi-color garments get ONE hyphenated tag with the
# colors in alphabetical order ("black-red dress"). COLOR_WORDS feeds the
# deterministic normalizer below; keep in sync with BARE_COLOR_RE.
COLOR_WORDS = frozenset(
    "red blue green yellow black white pink purple orange brown gray grey "
    "beige gold golden silver violet turquoise magenta cyan teal maroon "
    "navy olive coral salmon khaki cream ivory lavender lilac tan bronze "
    "copper".split())
COLOR_MODIFIERS = frozenset("light dark bright pale deep".split())
GARMENT_NOUNS = frozenset(
    "dress gown skirt blouse shirt top jacket vest corset bodice poncho "
    "shawl cape coat robe suit uniform costume outfit pants trousers "
    "shorts hat scarf sash boots".split())

# Tags the prompt itself mentions; a response that echoes them is dropped
# unless the tag is in the whitelist.
PROMPT_WHITELIST = frozenset(
    {'1girl', '2girls', '3girls', '1boy', '2boys', 'full body',
     'looking at viewer', 'upper body', 'standing'})


def word_stem(word: str) -> str:
    return word.rstrip('s')


def extract_answer(text: str) -> str:
    """Strips the chat template markers from a raw model response."""
    for marker in ('<|im_start|>assistant', '[/INST]'):
        if marker in text:
            text = text.rsplit(marker, 1)[1]
    return text


def clean_tag_list(text: str, word_cap: int = 0) -> list[str]:
    """Parses a raw model response into a list of tags.

    Removes chat artifacts, role words, over-long tags, tags with too many
    words and malformed count tags, and enforces the one-count-tag rule.
    `word_cap` limits how often the same word stem may appear.
    """
    text = extract_answer(text)
    text = ARTIFACT_RE.sub('', text)
    text = text.replace('\n', ', ')
    seen, tags = set(), []
    word_count: dict[str, int] = {}
    count_seen = False
    for raw in text.split(','):
        tag = raw.strip().strip('.').strip('"').strip("'").lower()
        tag = re.sub(r'\s+', ' ', tag)
        if not (tag and tag not in seen and tag not in ROLE_WORDS
                and len(tag) < 60 and len(tag.split()) <= 6
                and not tag.startswith('-') and not tag.endswith(':')
                and '(' not in tag and ')' not in tag
                and (not tag[0].isdigit() or PERSON_COUNT_RE.match(tag))):
            continue
        if PERSON_COUNT_RE.match(tag):
            count_match = re.match(r'^(\d+)\+?(girls?|boys?)$', tag)
            if not count_match or count_seen:
                continue
            n, word = int(count_match.group(1)), count_match.group(2)
            if (n == 1) != (word in ('girl', 'boy')):
                continue
            count_seen = True
        words = tag.split()
        if word_cap and any(word_count.get(word_stem(w), 0) >= word_cap
                            for w in words):
            continue
        for w in words:
            stem = word_stem(w)
            word_count[stem] = word_count.get(stem, 0) + 1
        seen.add(tag)
        tags.append(tag)
    return tags


def is_degenerate(tags: list[str]) -> bool:
    """True for an over-long or repetitive response (one word dominating)."""
    if len(tags) > 60:
        return True
    word_count: dict[str, int] = {}
    for tag in tags:
        for word in tag.split():
            stem = word_stem(word)
            word_count[stem] = word_count.get(stem, 0) + 1
    return bool(word_count) and max(word_count.values()) > 8


def _fold_colors(parts: list[str]) -> list[str] | None:
    """Folds hyphen/space-split tag-head parts into color tokens (modifiers
    join the following color). Returns the token list, or None if any part
    is not a color/modifier."""
    tokens: list[str] = []
    for part in parts:
        if part in COLOR_MODIFIERS:
            tokens.append(part)
        elif part in COLOR_WORDS:
            if tokens and tokens[-1] in COLOR_MODIFIERS:
                tokens[-1] += f' {part}'
            else:
                tokens.append(part)
        else:
            return None
    return tokens


def is_bare_color_chain(tag: str) -> bool:
    """Single-word tag whose hyphen parts are ALL colors/modifiers
    ('black-red', 'light-blue') — never a valid caption on its own: colors
    must be attached to the garment word."""
    if ' ' in tag or '-' not in tag:
        return False
    parts = tag.split('-')
    return bool(_fold_colors(parts)) and len(parts) >= 2


def _color_tokens(parts: list[str]) -> list[str] | None:
    """Color tokens for a multi-color head, else None."""
    tokens = _fold_colors(parts)
    return tokens if tokens and len(tokens) >= 2 else None


def is_color_garment_tag(tag: str) -> bool:
    """True for '<colors> <garment>' tags (single or multi color) — the
    house-enforced shape. Used to spare them from the prompt-echo filter:
    the COLOR RULE's own examples live in the prompt text, so a legitimate
    tag can collide with them."""
    head, sep, noun = tag.rpartition(' ')
    parts = ([p for chunk in head.split('-') for p in chunk.split()]
             if sep else [])
    return (bool(sep) and noun.lower() in GARMENT_NOUNS
            and bool(_fold_colors(parts)))


def normalize_color_order(tags: list[str]) -> list[str]:
    """Enforces the alphabetical color rule on multi-color garment tags:
    'red-black dress' -> 'black-red dress'. Single-color tags, non-garment
    nouns ('blue-green eyes') and hyphen chains that aren't all colors
    ('off-shoulder dress') pass through untouched. Duplicates collapse."""
    out, seen = [], set()
    for tag in tags:
        if is_bare_color_chain(tag):
            continue
        head, sep, noun = tag.rpartition(' ')
        parts = ([p for chunk in head.split('-') for p in chunk.split()]
                 if sep else [])
        tokens = _color_tokens(parts) if len(parts) >= 2 else None
        if tokens and noun.lower() in GARMENT_NOUNS:
            tag = '-'.join(t.replace(' ', '-')
                           for t in sorted(tokens, key=str.lower)) + ' ' + noun
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _is_plain_garment(tag: str) -> bool:
    """Garment tag that has no color attached yet ('skirt', 'pleated
    skirt', 'off-shoulder dress' yes; 'black-red dress' no)."""
    head, sep, noun = tag.rpartition(' ')
    if noun.lower() not in GARMENT_NOUNS:
        return False
    if not sep:
        return True
    parts = [p for chunk in head.split('-') for p in chunk.split()]
    return not _fold_colors(parts)


def attach_color_chains(tags: list[str]) -> list[str]:
    """Folds bare hyphenated color chains into the garment they belong to:
    ['black-red', 'skirt'] -> ['black-red skirt']. A chain is NEVER kept
    on its own — it attaches to the first colorable garment without a
    color yet; with no such garment it is dropped."""
    chains = [t for t in tags if is_bare_color_chain(t)]
    if not chains:
        return list(tags)
    for chain in chains:
        garment_index = next((i for i, t in enumerate(tags)
                              if _is_plain_garment(t)), None)
        if garment_index is None:
            break
        chain_index = tags.index(chain)
        tags.pop(chain_index)
        if chain_index < garment_index:
            garment_index -= 1
        tags[garment_index] = f'{chain} {tags[garment_index]}'
    return [t for t in tags if not is_bare_color_chain(t)]


def filter_tags(tags: list[str], prompt: str, whitelist: set[str],
                preserve: set[str]) -> list[str]:
    """Applies the house filters to a parsed model response.

    Drops prompt echoes, invented origin labels, quality/meta tags, bare
    color words and underscores. Returns the surviving tags.
    """
    # The protected vocabulary is allowed to echo the prompt text and to
    # keep its origin label.
    allowed = whitelist | preserve

    def keep(tag: str) -> bool:
        if not (tag not in prompt.lower() or tag in allowed
                or is_color_garment_tag(tag)):
            return False
        if not (tag in preserve or not ORIGIN_TAG_RE.match(tag)):
            return False
        if QUALITY_TAG_RE.match(tag):
            return False
        if not (not BARE_COLOR_RE.match(tag) or tag in allowed):
            return False
        if is_bare_color_chain(tag):
            return False
        if '_' in tag:
            return False
        return True

    return [tag for tag in tags if keep(tag)]


def merge_tags(trigger: str, new: list[str], existing: list[str],
               ignore: set[str], prune: bool) -> list[str]:
    """Merges the model response with the existing caption.

    In prune mode only the new tags survive (the caption is rebuilt from
    the image). Otherwise the existing tags are kept, except the ones in
    the ignore list and a count tag that the response replaced.
    """
    merged = [t for t in new if t not in ignore]
    if not prune:
        has_count_tag = any(PERSON_COUNT_RE.match(t) for t in merged)
        for tag in existing:
            if has_count_tag and PERSON_COUNT_RE.match(tag):
                continue
            if tag in ignore:
                continue
            if tag != trigger and tag not in merged:
                merged.append(tag)
    merged = [t for t in merged if t != trigger]
    return normalize_color_order(attach_color_chains(merged))


def order_tags(trigger: str, body: list[str], order: str,
               counts: dict[str, int]) -> list[str]:
    """Sorts the tag body (rank or alpha) and enforces the alphabetical
    color rule on multi-color garment tags. The trigger always comes
    first."""
    body = normalize_color_order(body)
    if order == 'alpha':
        body.sort()
    else:
        body.sort(key=lambda t: -counts.get(t, 0))
    return ([trigger] + body) if trigger else body


def parse_tag_text(text: str) -> list[str]:
    """Splits a caption file into tags.

    Accepts comma-separated and row-based (one tag per line) formats and
    mixes them freely; '#' starts a comment line.
    """
    tags: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(',') if ',' in line else [line]
        for tag in parts:
            tag = re.sub(r'\s+', ' ', tag.strip().lower())
            if tag and tag not in tags:
                tags.append(tag)
    return tags


def format_tag_text(tags: list[str], separator: str = ', ') -> str:
    """Formats tags back into a caption file."""
    return separator.join(tags)

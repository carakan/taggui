"""Token counting for captions, using the CLIP tokenizer.

The tokenizer is loaded with the `tokenizers` library directly, so no
machine-learning framework is needed to count tokens.
"""

from pathlib import Path

from tokenizers import Tokenizer

from utils.utils import get_resource_path

TOKENIZER_DIRECTORY_PATH = Path('clip-vit-base-patch32')
TOKENIZER_FILE_NAME = 'tokenizer.json'
# The `<|startoftext|>` and `<|endoftext|>` tokens are added by the
# tokenizer and are not part of the caption.
SPECIAL_TOKEN_COUNT = 2


class TokenCounter:
    """Counts the tokens of a caption."""

    def __init__(self, tokenizer_directory_path: Path = TOKENIZER_DIRECTORY_PATH):
        tokenizer_path = (get_resource_path(tokenizer_directory_path)
                          / TOKENIZER_FILE_NAME)
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))

    def count_tokens(self, text: str) -> int:
        """The number of tokens of the text, without the special tokens."""
        return len(self.tokenizer.encode(text).ids) - SPECIAL_TOKEN_COUNT

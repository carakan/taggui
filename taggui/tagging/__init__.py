"""Tagging engine that talks to a local, OpenAI-compatible vision LLM.

Ported from the standalone `lora_tagger.py` script; the pure rules live in
`rules.py`, the prompt templates in `prompt.py` and the vocabulary
(`.ignoretags` / `.basetags`) handling in `vocabulary.py`.
"""

from tagging.client import LlmClient, LlmError, server_reachable
from tagging.prompt import (ANCHOR_HINT, BASETAG_HINT, PRESERVE_HINT,
                             TAG_PROMPT_TEMPLATE, build_prompt)
from tagging.tagger import (TagResult, Tagger, TaggerSettings, TagMode,
                            TagOrder)

__all__ = [
    'ANCHOR_HINT',
    'BASETAG_HINT',
    'LlmClient',
    'LlmError',
    'PRESERVE_HINT',
    'TAG_PROMPT_TEMPLATE',
    'TagMode',
    'TagOrder',
    'TagResult',
    'Tagger',
    'TaggerSettings',
    'build_prompt',
    'server_reachable',
]

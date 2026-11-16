"""Tagging engine that talks to a vision LLM.

The local llama.cpp server is the default target; the hosted providers are
reached with their own API. Ported from the standalone `lora_tagger.py`
script; the pure rules live in `rules.py`, the prompt templates in
`prompt.py` and the vocabulary (`.ignoretags` / `.basetags`) handling in
`vocabulary.py`.
"""

from tagging.client import (AnthropicClient, GeminiClient, LlmClient,
                            LlmError, Provider, create_client,
                            provider_api_key, server_reachable)
from tagging.prompt import (ANCHOR_HINT, BASETAG_HINT, PRESERVE_HINT,
                             TAG_PROMPT_TEMPLATE, build_prompt)
from tagging.tagger import (TagResult, Tagger, TaggerSettings, TagMode,
                            TagOrder)

__all__ = [
    'ANCHOR_HINT',
    'BASETAG_HINT',
    'AnthropicClient',
    'GeminiClient',
    'LlmClient',
    'LlmError',
    'PRESERVE_HINT',
    'Provider',
    'TAG_PROMPT_TEMPLATE',
    'TagMode',
    'TagOrder',
    'TagResult',
    'Tagger',
    'TaggerSettings',
    'build_prompt',
    'create_client',
    'provider_api_key',
    'server_reachable',
]

"""Clients for the vision LLM providers.

The default target is a local llama.cpp server running Pixtral, which
exposes an OpenAI-compatible `/v1/chat/completions` endpoint. The hosted
providers are reached with their own API: Anthropic Claude and Google
Gemini speak a different protocol than OpenAI does.

Only the standard library is used, so the app does not depend on an HTTP
client library.
"""

import base64
import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_BASE_URL = 'http://127.0.0.1:8080/v1'
# The API key of the local server. It is read from the environment, so that
# no key has to be committed to the repository. The servers that do not
# require an authentication ignore it.
DEFAULT_API_KEY = os.environ.get('LLAMACPP_API_KEY', '')
DEFAULT_MODEL = 'pixtral'
DEFAULT_TIMEOUT = 300
DEFAULT_MAX_TOKENS = 400
DEFAULT_TEMPERATURE = 0.2
DEFAULT_REPEAT_PENALTY = 1.15
RETRY_COUNT = 3
RETRY_BACKOFF_SECONDS = 2


class Provider(str, Enum):
    """The service the model runs on."""
    LOCAL = 'Local (llama.cpp)'
    OPENAI = 'OpenAI (GPT)'
    ANTHROPIC = 'Anthropic (Claude)'
    GOOGLE = 'Google (Gemini)'
    OPENAI_COMPATIBLE = 'OpenAI-compatible'


@dataclass(frozen=True)
class ProviderPreset:
    """The defaults of a provider.

    The API is the protocol the provider speaks: 'openai' for the
    OpenAI-compatible `/chat/completions`, 'anthropic' for the messages
    endpoint, 'gemini' for generateContent.
    """
    base_url: str
    model: str
    api_key_env: str
    api: str = 'openai'
    # The repeat penalty is a llama.cpp parameter. The other services
    # reject a request that carries an argument they do not know.
    repeat_penalty: bool = False


PROVIDER_PRESETS = {
    Provider.LOCAL: ProviderPreset(
        base_url=DEFAULT_BASE_URL, model=DEFAULT_MODEL,
        api_key_env='LLAMACPP_API_KEY', api='openai', repeat_penalty=True),
    Provider.OPENAI: ProviderPreset(
        base_url='https://api.openai.com/v1', model='gpt-5.2',
        api_key_env='OPENAI_API_KEY'),
    Provider.ANTHROPIC: ProviderPreset(
        base_url='https://api.anthropic.com/v1', model='claude-sonnet-4-6',
        api_key_env='ANTHROPIC_API_KEY', api='anthropic'),
    Provider.GOOGLE: ProviderPreset(
        base_url='https://generativelanguage.googleapis.com/v1beta',
        model='gemini-2.5-flash', api_key_env='GEMINI_API_KEY', api='gemini'),
    Provider.OPENAI_COMPATIBLE: ProviderPreset(
        base_url='', model='', api_key_env=''),
}


def provider_api_key(provider: Provider) -> str:
    """The API key of a provider, read from the environment."""
    env_name = PROVIDER_PRESETS[provider].api_key_env
    return os.environ.get(env_name, '') if env_name else ''


class LlmError(Exception):
    """Raised when the model server cannot be reached or returns an error."""


def server_reachable(base_url: str = DEFAULT_BASE_URL,
                     timeout: float = 1.5) -> bool:
    """TCP preflight for the model server — fail fast instead of timing out
    per image."""
    url = urlparse(base_url)
    port = url.port or (443 if url.scheme == 'https' else 80)
    try:
        with socket.create_connection((url.hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


def image_mime_type(image_path: Path) -> str:
    """The media type of an image file."""
    suffix = Path(image_path).suffix.lower()
    return {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.webp': 'image/webp',
            '.bmp': 'image/bmp', '.tif': 'image/tiff',
            '.tiff': 'image/tiff'}.get(suffix, 'image/jpeg')


def encode_image_base64(image_path: Path) -> str:
    """Encodes an image file as base64, without the data URL prefix."""
    return base64.b64encode(Path(image_path).read_bytes()).decode()


def encode_image(image_path: Path) -> str:
    """Encodes an image file as a base64 data URL."""
    return (f'data:{image_mime_type(image_path)};base64,'
            f'{encode_image_base64(image_path)}')


class LlmClient:
    """Sends chat completion requests with an image to the model server.

    This is the OpenAI-compatible protocol, which the local llama.cpp
    server and the hosted OpenAI-compatible services use.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 api_key: str = DEFAULT_API_KEY,
                 model: str = DEFAULT_MODEL,
                 timeout: int = DEFAULT_TIMEOUT,
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 temperature: float = DEFAULT_TEMPERATURE,
                 repeat_penalty: float = DEFAULT_REPEAT_PENALTY,
                 send_repeat_penalty: bool = True):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.repeat_penalty = repeat_penalty
        self.send_repeat_penalty = send_repeat_penalty

    def is_reachable(self) -> bool:
        return server_reachable(self.base_url)

    def endpoint(self) -> str:
        """The URL the request goes to."""
        return f'{self.base_url}/chat/completions'

    def request_headers(self) -> dict:
        """The headers of the request."""
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers

    def build_payload(self, prompt: str, image_path: Path) -> dict:
        payload = {
            'model': self.model,
            'messages': [{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url',
                     'image_url': {'url': encode_image(image_path)}},
                ],
            }],
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
        }
        if self.send_repeat_penalty:
            payload['repeat_penalty'] = self.repeat_penalty
        return payload

    def _post(self, payload: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(RETRY_COUNT):
            body = json.dumps(payload).encode()
            try:
                request = urllib.request.Request(
                    self.endpoint(), data=body, headers=self.request_headers())
                with urllib.request.urlopen(request,
                                            timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                last_error = error
                detail = error.read().decode('utf-8', errors='replace')
                if error.code < 500:
                    # A client error will not get better by retrying.
                    if ('max_completion_tokens' in detail
                            and 'max_tokens' in payload):
                        # The newest OpenAI models take the token limit
                        # under another name. The request goes out again
                        # with it.
                        payload = dict(payload)
                        payload['max_completion_tokens'] = (
                            payload.pop('max_tokens'))
                        continue
                    raise LlmError(f'HTTP {error.code}: {detail}') from error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = error
            if attempt < RETRY_COUNT - 1:
                import time
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        raise LlmError(str(last_error) if last_error else 'request failed')

    def complete(self, prompt: str, image_path: Path) -> tuple[str, str]:
        """Runs one completion and returns (raw response, finish reason)."""
        data = self._post(self.build_payload(prompt, image_path))
        try:
            choice = data['choices'][0]
            content = choice['message']['content']
        except (KeyError, IndexError, TypeError) as error:
            raise LlmError(f'unexpected response: {data}') from error
        return content, choice.get('finish_reason', '')


class AnthropicClient(LlmClient):
    """Anthropic Claude, with its own message format."""

    def endpoint(self) -> str:
        return f'{self.base_url}/messages'

    def request_headers(self) -> dict:
        headers = {'Content-Type': 'application/json',
                   'anthropic-version': '2023-06-01'}
        if self.api_key:
            headers['x-api-key'] = self.api_key
        return headers

    def build_payload(self, prompt: str, image_path: Path) -> dict:
        return {
            'model': self.model,
            'max_tokens': self.max_tokens,
            # Anthropic takes the temperature from 0 to 1.
            'temperature': min(self.temperature, 1.0),
            'messages': [{
                'role': 'user',
                'content': [
                    {'type': 'image',
                     'source': {'type': 'base64',
                                'media_type': image_mime_type(image_path),
                                'data': encode_image_base64(image_path)}},
                    {'type': 'text', 'text': prompt},
                ],
            }],
        }

    def complete(self, prompt: str, image_path: Path) -> tuple[str, str]:
        data = self._post(self.build_payload(prompt, image_path))
        try:
            blocks = data['content']
            content = ''.join(block.get('text', '') for block in blocks
                              if block.get('type') == 'text')
        except (KeyError, IndexError, TypeError) as error:
            raise LlmError(f'unexpected response: {data}') from error
        # Anthropic calls the length stop reason 'max_tokens'.
        reason = data.get('stop_reason', '')
        if reason == 'max_tokens':
            reason = 'length'
        return content, reason


class GeminiClient(LlmClient):
    """Google Gemini, with its own content format."""

    def endpoint(self) -> str:
        return f'{self.base_url}/models/{self.model}:generateContent'

    def request_headers(self) -> dict:
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['x-goog-api-key'] = self.api_key
        return headers

    def build_payload(self, prompt: str, image_path: Path) -> dict:
        return {
            'contents': [{
                'role': 'user',
                'parts': [
                    {'inlineData': {'mimeType': image_mime_type(image_path),
                                    'data': encode_image_base64(image_path)}},
                    {'text': prompt},
                ],
            }],
            'generationConfig': {
                'maxOutputTokens': self.max_tokens,
                'temperature': self.temperature,
            },
        }

    def complete(self, prompt: str, image_path: Path) -> tuple[str, str]:
        data = self._post(self.build_payload(prompt, image_path))
        try:
            candidate = data['candidates'][0]
            content = ''.join(part.get('text', '')
                              for part in candidate['content']['parts'])
        except (KeyError, IndexError, TypeError) as error:
            raise LlmError(f'unexpected response: {data}') from error
        reason = candidate.get('finishReason', '')
        if reason == 'MAX_TOKENS':
            reason = 'length'
        return content, reason


API_CLIENTS = {
    'openai': LlmClient,
    'anthropic': AnthropicClient,
    'gemini': GeminiClient,
}


def create_client(provider: Provider = Provider.LOCAL, base_url: str = '',
                  api_key: str = '', model: str = '', **kwargs) -> LlmClient:
    """The client of a provider.

    The empty arguments fall back to the defaults of the provider.
    """
    preset = PROVIDER_PRESETS[provider]
    client_class = API_CLIENTS[preset.api]
    return client_class(
        base_url=base_url or preset.base_url,
        api_key=api_key,
        model=model or preset.model,
        send_repeat_penalty=preset.repeat_penalty,
        **kwargs)

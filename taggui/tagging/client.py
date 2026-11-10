"""Client for a local, OpenAI-compatible vision LLM server.

The default target is a llama.cpp server running Pixtral, which exposes an
OpenAI-compatible `/v1/chat/completions` endpoint. Only the standard
library is used, so the app does not depend on an HTTP client library.
"""

import base64
import json
import os
import socket
import urllib.error
import urllib.request
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


def encode_image(image_path: Path) -> str:
    """Encodes an image file as a base64 data URL."""
    image_bytes = Path(image_path).read_bytes()
    suffix = Path(image_path).suffix.lower()
    mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                 '.png': 'image/png', '.webp': 'image/webp',
                 '.bmp': 'image/bmp', '.tif': 'image/tiff',
                 '.tiff': 'image/tiff'}.get(suffix, 'image/jpeg')
    encoded = base64.b64encode(image_bytes).decode()
    return f'data:{mime_type};base64,{encoded}'


class LlmClient:
    """Sends chat completion requests with an image to the model server."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 api_key: str = DEFAULT_API_KEY,
                 model: str = DEFAULT_MODEL,
                 timeout: int = DEFAULT_TIMEOUT,
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 temperature: float = DEFAULT_TEMPERATURE,
                 repeat_penalty: float = DEFAULT_REPEAT_PENALTY):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.repeat_penalty = repeat_penalty

    def is_reachable(self) -> bool:
        return server_reachable(self.base_url)

    def build_payload(self, prompt: str, image_path: Path) -> dict:
        return {
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
            'repeat_penalty': self.repeat_penalty,
        }

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload).encode()
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        last_error: Exception | None = None
        for attempt in range(RETRY_COUNT):
            try:
                request = urllib.request.Request(
                    f'{self.base_url}/chat/completions',
                    data=body, headers=headers)
                with urllib.request.urlopen(request,
                                            timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                last_error = error
                detail = error.read().decode('utf-8', errors='replace')
                if error.code < 500:
                    # A client error will not get better by retrying.
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

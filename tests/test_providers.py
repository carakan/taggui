"""Tests for the model providers.

The local llama.cpp server is the default. The hosted providers speak
another protocol, and the request and the answer of each one are
checked here.
"""

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))
sys.path.insert(0, str(Path(__file__).parent))

# The tests use settings of their own, to keep away from the ones
# of the user.
import settings_isolation  # noqa: E402,F401

from tagging.client import (AnthropicClient, GeminiClient,  # noqa: E402
                            LlmClient, Provider, PROVIDER_PRESETS,
                            create_client, provider_api_key)

REQUESTS = []


class ProviderPresetTest(unittest.TestCase):
    """The defaults of the providers."""

    def test_the_local_server_is_the_first_provider(self):
        self.assertIs(list(Provider)[0], Provider.LOCAL)

    def test_the_local_preset_keeps_the_llama_cpp_server(self):
        preset = PROVIDER_PRESETS[Provider.LOCAL]
        self.assertEqual(preset.base_url, 'http://127.0.0.1:8080/v1')
        self.assertEqual(preset.model, 'pixtral')
        self.assertTrue(preset.repeat_penalty)

    def test_the_hosted_providers_do_not_send_the_repeat_penalty(self):
        # The repeat penalty is a llama.cpp parameter. The other services
        # reject a request that carries an argument they do not know.
        for provider in (Provider.OPENAI, Provider.ANTHROPIC,
                         Provider.GOOGLE, Provider.OPENAI_COMPATIBLE):
            self.assertFalse(PROVIDER_PRESETS[provider].repeat_penalty,
                             provider)

    def test_the_provider_of_the_api_key_is_the_environment(self):
        self.assertEqual(PROVIDER_PRESETS[Provider.OPENAI].api_key_env,
                         'OPENAI_API_KEY')
        self.assertEqual(PROVIDER_PRESETS[Provider.ANTHROPIC].api_key_env,
                         'ANTHROPIC_API_KEY')
        self.assertEqual(PROVIDER_PRESETS[Provider.GOOGLE].api_key_env,
                         'GEMINI_API_KEY')


class CreateClientTest(unittest.TestCase):
    """The client of a provider."""

    def test_the_local_provider_uses_the_openai_protocol(self):
        client = create_client(Provider.LOCAL)
        self.assertIs(type(client), LlmClient)
        self.assertEqual(client.base_url, 'http://127.0.0.1:8080/v1')
        self.assertEqual(client.model, 'pixtral')

    def test_anthropic_gets_its_own_client(self):
        client = create_client(Provider.ANTHROPIC)
        self.assertIs(type(client), AnthropicClient)
        self.assertEqual(client.base_url, 'https://api.anthropic.com/v1')
        self.assertEqual(client.model, 'claude-sonnet-4-6')

    def test_google_gets_its_own_client(self):
        client = create_client(Provider.GOOGLE)
        self.assertIs(type(client), GeminiClient)
        self.assertEqual(client.model, 'gemini-2.5-flash')

    def test_the_given_values_win_over_the_defaults(self):
        client = create_client(Provider.OPENAI, base_url='https://x/v1',
                               model='gpt-4o-mini', api_key='k')
        self.assertEqual(client.base_url, 'https://x/v1')
        self.assertEqual(client.model, 'gpt-4o-mini')
        self.assertEqual(client.api_key, 'k')

    def test_the_api_key_of_a_provider_is_empty_without_the_environment(self):
        # The environment of the test run has no key.
        self.assertEqual(provider_api_key(Provider.OPENAI), '')


class PayloadTest(unittest.TestCase):
    """The request that goes to the provider."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.image_path = Path(self.directory.name) / 'photo.jpg'
        self.image_path.write_bytes(b'\xff\xd8\xff\xe0fakejpeg')

    def tearDown(self):
        self.directory.cleanup()

    def test_the_local_request_carries_the_repeat_penalty(self):
        client = create_client(Provider.LOCAL)
        payload = client.build_payload('tag it', self.image_path)
        self.assertEqual(payload['repeat_penalty'], 1.15)

    def test_the_openai_request_does_not_carry_the_repeat_penalty(self):
        client = create_client(Provider.OPENAI)
        payload = client.build_payload('tag it', self.image_path)
        self.assertNotIn('repeat_penalty', payload)
        self.assertEqual(payload['model'], 'gpt-5.2')
        self.assertEqual(payload['max_tokens'], 400)

    def test_the_anthropic_request_carries_the_image_as_a_base64_block(self):
        client = create_client(Provider.ANTHROPIC)
        payload = client.build_payload('tag it', self.image_path)
        content = payload['messages'][0]['content']
        self.assertEqual(content[0]['type'], 'image')
        self.assertEqual(content[0]['source']['type'], 'base64')
        self.assertEqual(content[0]['source']['media_type'], 'image/jpeg')
        self.assertEqual(content[1], {'type': 'text', 'text': 'tag it'})
        self.assertNotIn('repeat_penalty', payload)

    def test_the_anthropic_temperature_stays_at_one_or_below(self):
        # Anthropic takes the temperature from 0 to 1.
        client = create_client(Provider.ANTHROPIC, temperature=1.8)
        payload = client.build_payload('tag it', self.image_path)
        self.assertEqual(payload['temperature'], 1.0)

    def test_the_anthropic_request_goes_to_the_messages_endpoint(self):
        client = create_client(Provider.ANTHROPIC)
        self.assertEqual(client.endpoint(),
                         'https://api.anthropic.com/v1/messages')
        headers = client.request_headers()
        self.assertEqual(headers['anthropic-version'], '2023-06-01')

    def test_the_gemini_request_carries_the_image_as_inline_data(self):
        client = create_client(Provider.GOOGLE)
        payload = client.build_payload('tag it', self.image_path)
        parts = payload['contents'][0]['parts']
        self.assertEqual(parts[0]['inlineData']['mimeType'], 'image/jpeg')
        self.assertEqual(parts[1], {'text': 'tag it'})
        self.assertEqual(payload['generationConfig']['maxOutputTokens'], 400)

    def test_the_gemini_request_goes_to_the_model_endpoint(self):
        client = create_client(Provider.GOOGLE)
        self.assertEqual(
            client.endpoint(),
            'https://generativelanguage.googleapis.com/v1beta/models/'
            'gemini-2.5-flash:generateContent')


class MockHandler(BaseHTTPRequestHandler):
    """Answers with the canned response of the protocol under test."""

    response = {}
    status = 200

    def do_POST(self):
        length = int(self.headers['Content-Length'])
        body = json.loads(self.rfile.read(length))
        REQUESTS.append({'body': body,
                         'headers': {name.lower(): value
                                     for name, value in self.headers.items()}})
        encoded = json.dumps(self.response).encode()
        self.send_response(self.status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        pass


class ProviderRequestTest(unittest.TestCase):
    """The request and the answer of each provider."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), MockHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.base_url = f'http://127.0.0.1:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        REQUESTS.clear()
        self.directory = tempfile.TemporaryDirectory()
        self.image_path = Path(self.directory.name) / 'photo.jpg'
        self.image_path.write_bytes(b'\xff\xd8\xff\xe0fakejpeg')

    def tearDown(self):
        self.directory.cleanup()

    def test_the_anthropic_answer_is_read(self):
        MockHandler.response = {
            'content': [{'type': 'text', 'text': '1girl, smiling'}],
            'stop_reason': 'end_turn'}
        MockHandler.status = 200
        client = AnthropicClient(base_url=self.base_url, api_key='key',
                                 model='claude-sonnet-4-6')
        content, reason = client.complete('tag it', self.image_path)
        self.assertEqual(content, '1girl, smiling')
        self.assertEqual(reason, 'end_turn')
        self.assertEqual(REQUESTS[0]['headers']['x-api-key'], 'key')

    def test_the_anthropic_length_stop_reason_is_translated(self):
        # The tagging drops the last tag of a truncated answer, and it
        # looks for the 'length' reason.
        MockHandler.response = {
            'content': [{'type': 'text', 'text': '1girl, smiling'}],
            'stop_reason': 'max_tokens'}
        MockHandler.status = 200
        client = AnthropicClient(base_url=self.base_url, model='claude')
        _content, reason = client.complete('tag it', self.image_path)
        self.assertEqual(reason, 'length')

    def test_the_gemini_answer_is_read(self):
        MockHandler.response = {
            'candidates': [{'content': {'parts': [{'text': '1girl, smiling'}]},
                            'finishReason': 'STOP'}]}
        MockHandler.status = 200
        client = GeminiClient(base_url=self.base_url, api_key='key',
                              model='gemini-2.5-flash')
        content, reason = client.complete('tag it', self.image_path)
        self.assertEqual(content, '1girl, smiling')
        self.assertEqual(reason, 'STOP')
        self.assertEqual(REQUESTS[0]['headers']['x-goog-api-key'], 'key')

    def test_the_gemini_length_stop_reason_is_translated(self):
        MockHandler.response = {
            'candidates': [{'content': {'parts': [{'text': '1girl'}]},
                            'finishReason': 'MAX_TOKENS'}]}
        MockHandler.status = 200
        client = GeminiClient(base_url=self.base_url, model='gemini')
        _content, reason = client.complete('tag it', self.image_path)
        self.assertEqual(reason, 'length')

    def test_the_openai_token_limit_falls_back_to_the_new_name(self):
        # The newest OpenAI models take the limit under another name, and
        # reject the request that carries the old one.
        MockHandler.response = {
            'error': {'message': "Unsupported parameter: 'max_tokens' is not"
                                 ' supported with this model. Use'
                                 " 'max_completion_tokens' instead."}}
        MockHandler.status = 400
        client = LlmClient(base_url=self.base_url, model='gpt-5.2')
        with self.assertRaises(Exception):
            client.complete('tag it', self.image_path)
        # The request went out a second time, with the other name.
        self.assertEqual(len(REQUESTS), 2)
        self.assertIn('max_tokens', REQUESTS[0]['body'])
        self.assertNotIn('max_tokens', REQUESTS[1]['body'])
        self.assertIn('max_completion_tokens', REQUESTS[1]['body'])


class ProviderFormTest(unittest.TestCase):
    """The provider picker of the settings form."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        from utils.settings import get_settings
        self.app = QApplication.instance() or QApplication([])
        self.settings = get_settings()
        self._saved = self._snapshot()
        self._clear_settings()
        from widgets.llm_tagger import LlmTaggerSettingsForm
        self.form = LlmTaggerSettingsForm()

    def tearDown(self):
        self._clear_settings()
        self._restore()

    def _keys(self):
        keys = ['llm_tagger_provider']
        for provider in Provider:
            for field in ('base_url', 'model', 'api_key'):
                keys.append(f'llm_tagger_{field}_{provider.name.lower()}')
        # The settings of the first version, which the local provider
        # takes over.
        for field in ('base_url', 'model', 'api_key'):
            keys.append(f'llm_tagger_{field}')
        return keys

    def _snapshot(self):
        """The values of the settings, to put them back after the test."""
        return {key: self.settings.value(key) for key in self._keys()}

    def _restore(self):
        """Puts the settings of the user back."""
        for key, value in self._saved.items():
            if value is None:
                self.settings.remove(key)
            else:
                self.settings.setValue(key, value)

    def _clear_settings(self):
        for key in self._keys():
            self.settings.remove(key)

    def test_the_local_server_is_the_default(self):
        self.assertEqual(self.form.get_provider(), Provider.LOCAL)
        self.assertEqual(self.form.base_url_line_edit.text(),
                         'http://127.0.0.1:8080/v1')
        self.assertEqual(self.form.model_line_edit.text(), 'pixtral')

    def test_picking_a_provider_brings_its_url_and_model(self):
        self.form.provider_combo_box.setCurrentText(Provider.ANTHROPIC.value)
        self.assertEqual(self.form.get_provider(), Provider.ANTHROPIC)
        self.assertEqual(self.form.base_url_line_edit.text(),
                         'https://api.anthropic.com/v1')
        self.assertEqual(self.form.model_line_edit.text(),
                         'claude-sonnet-4-6')

    def test_the_fields_of_a_provider_are_kept_apart(self):
        self.form.base_url_line_edit.setText('http://127.0.0.1:9090/v1')
        self.form.provider_combo_box.setCurrentText(Provider.OPENAI.value)
        self.assertEqual(self.form.base_url_line_edit.text(),
                         'https://api.openai.com/v1')
        self.form.provider_combo_box.setCurrentText(Provider.LOCAL.value)
        self.assertEqual(self.form.base_url_line_edit.text(),
                         'http://127.0.0.1:9090/v1')

    def test_the_api_key_of_a_provider_is_the_one_of_the_environment(self):
        self.form.provider_combo_box.setCurrentText(Provider.OPENAI.value)
        self.assertEqual(self.form.api_key_line_edit.text(),
                         provider_api_key(Provider.OPENAI))

    def test_the_repeat_penalty_is_off_for_the_other_providers(self):
        # It is a llama.cpp parameter; the other services do not know it.
        self.assertTrue(self.form.repeat_penalty_spin_box.isEnabled())
        self.form.provider_combo_box.setCurrentText(Provider.OPENAI.value)
        self.assertFalse(self.form.repeat_penalty_spin_box.isEnabled())
        self.form.provider_combo_box.setCurrentText(Provider.LOCAL.value)
        self.assertTrue(self.form.repeat_penalty_spin_box.isEnabled())


if __name__ == '__main__':
    unittest.main()

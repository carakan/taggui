"""End-to-end test of the tagging pipeline against a mock model server.

The mock server speaks the same OpenAI-compatible API as the llama.cpp
server, so the real HTTP client, payload building and response parsing are
exercised without a model.
"""

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))

from tagging.client import LlmClient  # noqa: E402
from tagging.tagger import TagMode, Tagger, TaggerSettings  # noqa: E402
from tagging.vocabulary import Vocabulary  # noqa: E402

REQUESTS = []


class MockHandler(BaseHTTPRequestHandler):
    """Answers a chat completion with a canned tag list."""

    response_tags = '1girl, smiling, solo'

    def do_POST(self):
        length = int(self.headers['Content-Length'])
        body = json.loads(self.rfile.read(length))
        REQUESTS.append(body)
        payload = {
            'choices': [{
                'index': 0,
                'message': {'role': 'assistant',
                            'content': self.response_tags},
                'finish_reason': 'stop',
            }],
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        pass


class MockServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), MockHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.base_url = (f'http://127.0.0.1:{cls.server.server_address[1]}/v1')

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        REQUESTS.clear()
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.image_path = self.root / 'photo.jpg'
        self.image_path.write_bytes(b'\xff\xd8\xff\xe0fakejpeg')

    def tearDown(self):
        self.directory.cleanup()

    def make_tagger(self, settings=None):
        client = LlmClient(base_url=self.base_url, api_key='test',
                            model='pixtral')
        vocabulary = Vocabulary(self.root)
        return Tagger(client, vocabulary, settings or TaggerSettings())

    def test_server_is_reachable(self):
        client = LlmClient(base_url=self.base_url)
        self.assertTrue(client.is_reachable())

    def test_unreachable_server_is_reported(self):
        client = LlmClient(base_url='http://127.0.0.1:1/v1')
        self.assertFalse(client.is_reachable())

    def test_tag_image_against_the_mock_server(self):
        tagger = self.make_tagger()
        result = tagger.tag_image(self.image_path, ['mytrigger'])
        self.assertTrue(result.is_success)
        self.assertEqual(result.tags,
                         ['mytrigger', '1girl', 'smiling', 'solo'])
        self.assertEqual(len(REQUESTS), 1)
        request = REQUESTS[0]
        self.assertEqual(request['model'], 'pixtral')
        content = request['messages'][0]['content']
        self.assertIn('mytrigger', content[0]['text'])
        self.assertTrue(content[1]['image_url']['url'].startswith(
            'data:image/jpeg;base64,'))

    def test_prune_mode_against_the_mock_server(self):
        settings = TaggerSettings(mode=TagMode.PRUNE)
        tagger = self.make_tagger(settings)
        result = tagger.tag_image(self.image_path,
                                  ['mytrigger', 'old dress'])
        self.assertTrue(result.is_success)
        self.assertEqual(result.tags, ['mytrigger', '1girl', 'smiling',
                                        'solo'])


if __name__ == '__main__':
    unittest.main()

"""Tests for the audit log of a tagging run.

The log holds the same lines the `--logs` option of `lora_tagger.py` writes
to its `lora_tagger_<stamp>.log` file.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))

from tagging.audit import AuditLog, header_line  # noqa: E402


class AuditLogTest(unittest.TestCase):
    """The audit log itself."""

    def test_the_log_starts_empty(self):
        self.assertEqual(AuditLog().text(), '')

    def test_a_line_is_written(self):
        audit = AuditLog()
        audit.write('hello')
        self.assertEqual(audit.text(), 'hello')

    def test_an_empty_line_is_written(self):
        audit = AuditLog()
        audit.write('hello')
        audit.write()
        self.assertEqual(audit.text(), 'hello\n')

    def test_a_list_is_written_with_its_count(self):
        audit = AuditLog()
        audit.write_list('kept existing', ['solo', 'dress'])
        self.assertEqual(audit.text(),
                         '    kept existing (2): solo, dress')

    def test_an_empty_list_is_written_as_none(self):
        audit = AuditLog()
        audit.write_list('kept existing', [])
        self.assertEqual(audit.text(), '    kept existing (0): (none)')

    def test_the_header_line_fills_the_width(self):
        line = header_line('AUDIT')
        self.assertTrue(line.startswith('── AUDIT '))
        self.assertEqual(len(line), 128)

    def test_the_log_is_saved_to_a_file(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = AuditLog()
            audit.write('hello')
            path = audit.save(Path(directory) / 'audit.log')
            self.assertEqual(path.read_text(encoding='utf-8'), 'hello\n')

    def test_the_default_path_is_next_to_the_dataset(self):
        audit = AuditLog()
        path = audit.default_path(Path('/dataset'))
        self.assertEqual(path.parent, Path('/dataset'))
        self.assertTrue(path.name.startswith('lora_tagger_'))
        self.assertTrue(path.name.endswith('.log'))


class AuditLogContentTest(unittest.TestCase):
    """The content of the audit log of a run."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'i0.jpg').write_bytes(b'\xff\xd8\xff\xe0fake')
        (self.root / 'i0.txt').write_text('mytrigger, solo')

    def tearDown(self):
        self.directory.cleanup()

    def make_tagger(self, audit, response='1girl, standing, smiling'):
        from tagging.client import LlmClient
        from tagging.tagger import Tagger, TaggerSettings
        from tagging.vocabulary import Vocabulary

        class StubClient:
            model = 'pixtral'
            base_url = 'http://127.0.0.1:8080/v1'

            def complete(self, prompt, image_path):
                return response, 'stop'

        return Tagger(StubClient(), Vocabulary(self.root), TaggerSettings(),
                      {}, audit)

    def test_the_log_holds_the_prompt_and_the_response(self):
        audit = AuditLog()
        tagger = self.make_tagger(audit)
        tagger.tag_image(self.root / 'i0.jpg', ['mytrigger', 'solo'])
        log = audit.text()
        self.assertIn('AUDIT', log)
        self.assertIn('REQUEST', log)
        self.assertIn('prompt sent', log)
        self.assertIn('RESPONSE', log)
        self.assertIn('1girl, standing, smiling', log)
        self.assertIn('MERGE', log)
        self.assertIn('FINAL ORDER', log)
        self.assertIn('RESULT:', log)

    def test_the_log_holds_the_vocabulary_of_the_image(self):
        audit = AuditLog()
        tagger = self.make_tagger(audit)
        tagger.tag_image(self.root / 'i0.jpg', ['mytrigger', 'solo'])
        log = audit.text()
        self.assertIn('trigger: mytrigger', log)
        self.assertIn('existing tags (2): mytrigger, solo', log)
        self.assertIn('basetags sent as vocabulary:', log)
        self.assertIn('ignore vocabulary:', log)

    def test_the_log_holds_the_filter_stages(self):
        # The quality tags are not in the prompt text, so that they reach
        # the quality-tag rule instead of the prompt-echo guard, which runs
        # first.
        audit = AuditLog()
        tagger = self.make_tagger(
            audit, response='1girl, official art, long_hair, smiling')
        tagger.tag_image(self.root / 'i0.jpg', ['mytrigger', 'solo'])
        log = audit.text()
        self.assertIn("filter 'quality-tag rule'", log)
        self.assertIn('official art', log)
        self.assertIn("filter 'underscore'", log)
        self.assertIn('long_hair', log)
        self.assertIn('after filters', log)

    def test_the_prompt_echo_guard_drops_the_tags_of_the_prompt(self):
        # "best quality" is mentioned in the prompt, so the prompt-echo
        # guard drops it, as in the script.
        audit = AuditLog()
        tagger = self.make_tagger(
            audit, response='1girl, best quality, smiling')
        tagger.tag_image(self.root / 'i0.jpg', ['mytrigger', 'solo'])
        log = audit.text()
        self.assertIn("filter 'prompt-echo guard", log)
        self.assertIn('best quality', log)

    def test_the_log_holds_the_merge_accounting(self):
        audit = AuditLog()
        tagger = self.make_tagger(audit)
        tagger.tag_image(self.root / 'i0.jpg', ['mytrigger', 'solo'])
        log = audit.text()
        self.assertIn('kept existing', log)
        self.assertIn('solo', log)
        self.assertIn('merged result', log)

    def test_no_log_is_written_without_an_audit_log(self):
        from tagging.tagger import Tagger, TaggerSettings
        from tagging.vocabulary import Vocabulary

        class StubClient:
            model = 'pixtral'
            base_url = 'http://127.0.0.1:8080/v1'

            def complete(self, prompt, image_path):
                return '1girl, smiling', 'stop'

        tagger = Tagger(StubClient(), Vocabulary(self.root), TaggerSettings())
        result = tagger.tag_image(self.root / 'i0.jpg', ['mytrigger', 'solo'])
        self.assertTrue(result.is_success)
        self.assertIsNone(tagger.audit)

    def test_the_run_summary_holds_the_counts(self):
        from tagging.tagging_thread import TaggingThread

        audit = AuditLog()
        thread = TaggingThread.__new__(TaggingThread)
        thread.audit = audit
        thread.write_run_summary(2, 3, ['/dataset/bad.jpg'], 65.0, 4, 12)
        log = audit.text()
        self.assertIn('RUN SUMMARY', log)
        self.assertIn('result: 2/3 succeeded, 1 failed', log)
        self.assertIn('failed: /dataset/bad.jpg', log)
        self.assertIn('tags: avg 2.0 -> 6.0 per image', log)


if __name__ == '__main__':
    unittest.main()

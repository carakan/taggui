"""Tests for the tagging engine.

The tests never contact a model server: a stub client returns canned
responses, so the whole pipeline can be checked offline.

Run with: python3 -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'taggui'))

from tagging.client import LlmClient, LlmError, encode_image  # noqa: E402
from tagging.prompt import TAG_PROMPT_TEMPLATE, build_prompt  # noqa: E402
from tagging.rules import (attach_color_chains, clean_tag_list,  # noqa: E402
                           filter_tags, is_bare_color_chain,
                           is_color_garment_tag, is_degenerate, merge_tags,
                           normalize_color_order, order_tags, parse_tag_text)
from tagging.tagger import (TagMode, TagOrder, Tagger,  # noqa: E402
                            TaggerSettings)
from tagging.vocabulary import (Vocabulary, append_basetags,  # noqa: E402
                                append_ignore_tags, parse_ignore_file,
                                parse_tag_file)


class StubClient:
    """A client that returns canned responses instead of calling a server."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[tuple[str, Path]] = []

    def complete(self, prompt: str, image_path: Path):
        self.calls.append((prompt, Path(image_path)))
        if not self.responses:
            raise LlmError('no stub response left')
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response, 'stop'


class RulesTest(unittest.TestCase):
    def test_clean_tag_list_parses_comma_separated_tags(self):
        self.assertEqual(
            clean_tag_list('1girl, smiling, solo'),
            ['1girl', 'smiling', 'solo'])

    def test_clean_tag_list_removes_role_words_and_artifacts(self):
        self.assertEqual(clean_tag_list('assistant\n1girl'), ['1girl'])
        self.assertEqual(clean_tag_list('user\n1girl'), ['1girl'])

    def test_clean_tag_list_keeps_only_one_count_tag(self):
        self.assertEqual(clean_tag_list('1girl, 2boys'), ['1girl'])

    def test_clean_tag_list_drops_mismatched_count_tag(self):
        self.assertEqual(clean_tag_list('2girl, solo'), ['solo'])

    def test_clean_tag_list_drops_number_glued_to_word(self):
        self.assertEqual(clean_tag_list('1fan, 2hats, solo'), ['solo'])

    def test_clean_tag_list_enforces_word_cap(self):
        self.assertEqual(clean_tag_list('red hair, blue hair, green hair',
                                        word_cap=2),
                         ['red hair', 'blue hair'])

    def test_is_degenerate_detects_repeated_word(self):
        self.assertTrue(is_degenerate(['red hair'] * 9))
        self.assertFalse(is_degenerate(['1girl', 'smiling', 'solo']))

    def test_bare_color_chain_is_detected(self):
        self.assertTrue(is_bare_color_chain('black-red'))
        self.assertFalse(is_bare_color_chain('cross-laced'))
        self.assertFalse(is_bare_color_chain('black-red dress'))

    def test_color_garment_tag_is_detected(self):
        self.assertTrue(is_color_garment_tag('black-red dress'))
        self.assertFalse(is_color_garment_tag('black-red'))
        self.assertFalse(is_color_garment_tag('blue-green eyes'))

    def test_normalize_color_order_sorts_colors_alphabetically(self):
        self.assertEqual(normalize_color_order(['red-black dress']),
                         ['black-red dress'])
        self.assertEqual(normalize_color_order(['red-black-white dress']),
                         ['black-red-white dress'])

    def test_normalize_color_order_leaves_other_tags_untouched(self):
        self.assertEqual(normalize_color_order(['off-shoulder dress']),
                         ['off-shoulder dress'])
        self.assertEqual(normalize_color_order(['blue-green eyes']),
                         ['blue-green eyes'])

    def test_attach_color_chains_folds_chain_into_garment(self):
        self.assertEqual(attach_color_chains(['black-red', 'skirt']),
                         ['black-red skirt'])

    def test_attach_color_chains_drops_chain_without_garment(self):
        self.assertEqual(attach_color_chains(['black-red', 'smiling']),
                         ['smiling'])

    def test_filter_tags_drops_quality_and_origin_tags(self):
        prompt = build_prompt('trigger', 35)
        tags = filter_tags(['best quality', 'masterpiece',
                             'spanish-dance', '1girl'], prompt,
                            {'1girl'}, set())
        self.assertEqual(tags, ['1girl'])

    def test_filter_tags_drops_prompt_echo(self):
        prompt = build_prompt('trigger', 35)
        tags = filter_tags(['lowercase', 'single spaces', '1girl'], prompt,
                            {'1girl'}, set())
        self.assertEqual(tags, ['1girl'])

    def test_filter_tags_keeps_whitelisted_prompt_echo(self):
        prompt = build_prompt('trigger', 35)
        tags = filter_tags(['1girl', 'standing'], prompt,
                            {'1girl', 'standing'}, set())
        self.assertEqual(tags, ['1girl', 'standing'])

    def test_filter_tags_keeps_preserve_origin_tag(self):
        prompt = build_prompt('trigger', 35)
        tags = filter_tags(['spanish-dance'], prompt, set(),
                            {'spanish-dance'})
        self.assertEqual(tags, ['spanish-dance'])

    def test_filter_tags_drops_underscore_tag(self):
        prompt = build_prompt('trigger', 35)
        self.assertEqual(filter_tags(['long_hair'], prompt, set(), set()), [])

    def test_merge_tags_keeps_existing_tags(self):
        merged = merge_tags('trigger', ['1girl', 'smiling'],
                            ['trigger', 'dress'], set(), prune=False)
        self.assertEqual(merged, ['1girl', 'smiling', 'dress'])

    def test_merge_tags_drops_ignored_tags(self):
        merged = merge_tags('trigger', ['1girl', 'smiling'],
                            ['trigger', 'dress'], {'smiling'}, prune=False)
        self.assertEqual(merged, ['1girl', 'dress'])

    def test_merge_tags_prune_drops_existing_tags(self):
        merged = merge_tags('trigger', ['1girl', 'smiling'],
                            ['trigger', 'dress'], set(), prune=True)
        self.assertEqual(merged, ['1girl', 'smiling'])

    def test_merge_tags_replaces_count_tag(self):
        merged = merge_tags('trigger', ['2girls'],
                            ['trigger', '1girl', 'dress'], set(),
                            prune=False)
        self.assertEqual(merged, ['2girls', 'dress'])

    def test_order_tags_keeps_trigger_first_and_sorts_by_count(self):
        ordered = order_tags('trigger', ['a', 'b', 'c'], 'rank',
                              {'a': 1, 'b': 5, 'c': 3})
        self.assertEqual(ordered, ['trigger', 'b', 'c', 'a'])

    def test_order_tags_sorts_alphabetically(self):
        ordered = order_tags('trigger', ['c', 'a', 'b'], 'alpha', {})
        self.assertEqual(ordered, ['trigger', 'a', 'b', 'c'])

    def test_parse_tag_text_supports_rows_and_commas(self):
        self.assertEqual(parse_tag_text('1girl\nsmiling, solo'),
                         ['1girl', 'smiling', 'solo'])
        self.assertEqual(parse_tag_text('# comment\n1girl, solo'),
                         ['1girl', 'solo'])


class PromptTest(unittest.TestCase):
    def test_template_contains_placeholders(self):
        self.assertIn('{trigger}', TAG_PROMPT_TEMPLATE)
        self.assertIn('{max_tags}', TAG_PROMPT_TEMPLATE)

    def test_build_prompt_replaces_placeholders(self):
        prompt = build_prompt('mytrigger', 20)
        self.assertIn('"mytrigger"', prompt)
        self.assertIn('At most 20 tags.', prompt)
        self.assertNotIn('{trigger}', prompt)
        self.assertNotIn('{max_tags}', prompt)

    def test_build_prompt_appends_basetag_hint(self):
        prompt = build_prompt('mytrigger', 35, basetags=['poncho'])
        self.assertIn('poncho', prompt)
        self.assertIn('Concept-specific tags', prompt)

    def test_build_prompt_skips_anchors_in_prune_mode(self):
        prompt = build_prompt('mytrigger', 35, anchors=['dress'],
                               prune=True)
        self.assertNotIn('Already verified for this image', prompt)

    def test_build_prompt_appends_preserve_hint_in_prune_mode(self):
        prompt = build_prompt('mytrigger', 35, preserve=['zarzuela'],
                               prune=True)
        self.assertIn('zarzuela', prompt)
        self.assertIn('Dataset-local vocabulary', prompt)


class VocabularyTest(unittest.TestCase):
    def test_parse_tag_file_reads_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.basetags'
            path.write_text('poncho\n# comment\nzarzuela\n')
            self.assertEqual(parse_tag_file(path), ['poncho', 'zarzuela'])

    def test_parse_ignore_file_reads_global_and_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.ignoretags'
            # A section header has no space after the hash; '# comment' is a
            # plain comment.
            path.write_text('watermark\n#folder one\nred dress\n'
                            '#folder one, folder two\nblue dress\n')
            global_tags, sections = parse_ignore_file(path)
            self.assertEqual(global_tags, ['watermark'])
            self.assertEqual(sections['folder one'],
                             ['red dress', 'blue dress'])
            self.assertEqual(sections['folder two'], ['blue dress'])

    def test_folder_meta_merges_all_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'myfolder'
            folder.mkdir()
            (root / '.ignoretags').write_text('watermark\n#myfolder\n'
                                              'red dress\n')
            (root / '.basetags').write_text('poncho\n')
            (folder / '.ignoretags').write_text('logo\n')
            (folder / '.basetags').write_text('zarzuela\n')
            vocabulary = Vocabulary(root)
            meta = vocabulary.folder_meta(folder)
            self.assertEqual(meta['ignore'],
                             {'watermark', 'red dress', 'logo'})
            self.assertEqual(meta['basetags'], ['poncho', 'zarzuela'])

    def test_append_ignore_tags_skips_known_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'myfolder'
            folder.mkdir()
            (root / '.ignoretags').write_text('watermark\n')
            added = append_ignore_tags(root, folder, {'watermark', 'logo'})
            self.assertEqual(added, ['logo'])
            global_tags, sections = parse_ignore_file(root / '.ignoretags')
            self.assertEqual(sections['myfolder'], ['logo'])

    def test_append_basetags_appends_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'myfolder'
            folder.mkdir()
            self.assertEqual(append_basetags(folder, ['poncho']),
                             ['poncho'])
            self.assertEqual(append_basetags(folder, ['poncho']), [])
            self.assertEqual(parse_tag_file(folder / '.basetags'),
                             ['poncho'])

    def test_root_section_does_not_apply_to_the_root_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.ignoretags').write_text('watermark\n#myfolder\n'
                                              'red dress\n')
            vocabulary = Vocabulary(root)
            root_meta = vocabulary.folder_meta(root)
            self.assertEqual(root_meta['ignore'], {'watermark'})

    def test_dataset_folders_lists_folders_with_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'withimages').mkdir()
            (root / 'withimages' / 'a.jpg').write_bytes(b'x')
            (root / 'empty').mkdir()
            vocabulary = Vocabulary(root)
            self.assertEqual([folder.name
                              for folder in vocabulary.dataset_folders()],
                             ['withimages'])


class TaggerTest(unittest.TestCase):
    def make_tagger(self, responses, settings=None, root=None):
        self.client = StubClient(responses)
        vocabulary = Vocabulary(root) if root else Vocabulary(Path('/nonexistent'))
        return Tagger(self.client, vocabulary,
                      settings or TaggerSettings())

    def test_tag_image_returns_trigger_first(self):
        tagger = self.make_tagger(['1girl, smiling, solo'])
        result = tagger.tag_image(Path('/tmp/photo.jpg'), ['mytrigger'])
        self.assertTrue(result.is_success)
        self.assertEqual(result.tags, ['mytrigger', '1girl', 'smiling',
                                        'solo'])

    def test_tag_image_uses_folder_name_as_trigger_when_no_tags(self):
        tagger = self.make_tagger(['1girl, smiling'])
        result = tagger.tag_image(Path('/tmp/dataset/photo.jpg'), [])
        self.assertEqual(result.tags[0], 'dataset')

    def test_tag_image_merges_with_existing_tags(self):
        tagger = self.make_tagger(['1girl, smiling'])
        result = tagger.tag_image(Path('/tmp/photo.jpg'),
                                  ['mytrigger', 'dress'])
        self.assertEqual(result.tags,
                         ['mytrigger', '1girl', 'smiling', 'dress'])

    def test_prune_mode_drops_existing_tags(self):
        settings = TaggerSettings(mode=TagMode.PRUNE)
        tagger = self.make_tagger(['1girl, smiling'], settings)
        result = tagger.tag_image(Path('/tmp/photo.jpg'),
                                  ['mytrigger', 'dress'])
        self.assertEqual(result.tags, ['mytrigger', '1girl', 'smiling'])

    def test_failed_request_keeps_the_old_caption(self):
        tagger = self.make_tagger([LlmError('connection refused')])
        result = tagger.tag_image(Path('/tmp/photo.jpg'), ['mytrigger'])
        self.assertFalse(result.is_success)
        self.assertEqual(result.tags, [])
        self.assertIn('connection refused', result.error)

    def test_empty_response_is_an_error(self):
        tagger = self.make_tagger(['', ''])
        result = tagger.tag_image(Path('/tmp/photo.jpg'), ['mytrigger'])
        self.assertFalse(result.is_success)

    def test_trigger_override_is_used(self):
        settings = TaggerSettings(trigger='custom')
        tagger = self.make_tagger(['1girl'], settings)
        result = tagger.tag_image(Path('/tmp/photo.jpg'), ['mytrigger'])
        self.assertEqual(result.tags[0], 'custom')

    def test_alphabetical_order(self):
        settings = TaggerSettings(order=TagOrder.ALPHA)
        tagger = self.make_tagger(['solo, smiling, 1girl'], settings)
        result = tagger.tag_image(Path('/tmp/photo.jpg'), ['mytrigger'])
        self.assertEqual(result.tags, ['mytrigger', '1girl', 'smiling',
                                        'solo'])

    def test_ignored_tags_are_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'myfolder'
            folder.mkdir()
            (root / '.ignoretags').write_text('# myfolder\nsmiling\n')
            tagger = self.make_tagger(['1girl, smiling'], root=root)
            result = tagger.tag_image(folder / 'photo.jpg', ['mytrigger'])
            self.assertEqual(result.tags, ['mytrigger', '1girl'])

    def test_basetags_are_sent_to_the_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'myfolder'
            folder.mkdir()
            (root / '.basetags').write_text('poncho\n')
            tagger = self.make_tagger(['1girl, poncho'], root=root)
            tagger.tag_image(folder / 'photo.jpg', ['mytrigger'])
            prompt = self.client.calls[0][0]
            self.assertIn('Concept-specific tags', prompt)
            self.assertIn('poncho', prompt)

    def test_anchors_are_sent_to_the_model(self):
        tagger = self.make_tagger(['1girl'])
        tagger.counts = {'dress': 10}
        tagger.tag_image(Path('/tmp/photo.jpg'), ['mytrigger', 'dress'])
        prompt = self.client.calls[0][0]
        self.assertIn('Already verified for this image', prompt)
        self.assertIn('dress', prompt)

    def test_preserve_list_protects_local_terms(self):
        settings = TaggerSettings(mode=TagMode.PRUNE)
        tagger = self.make_tagger(['1girl, zarzuela'], settings)
        tagger.tag_image(Path('/tmp/photo.jpg'), ['mytrigger', 'zarzuela'])
        prompt = self.client.calls[0][0]
        self.assertIn('Dataset-local vocabulary', prompt)
        self.assertIn('zarzuela', prompt)


class ClientTest(unittest.TestCase):
    def test_build_payload_sends_the_prompt_and_the_image(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / 'photo.jpg'
            image_path.write_bytes(b'\xff\xd8\xff\xe0fakejpeg')
            client = LlmClient(base_url='http://127.0.0.1:9/v1',
                               api_key='key', model='pixtral')
            payload = client.build_payload('my prompt', image_path)
            self.assertEqual(payload['model'], 'pixtral')
            content = payload['messages'][0]['content']
            self.assertEqual(content[0], {'type': 'text', 'text': 'my prompt'})
            self.assertTrue(content[1]['image_url']['url'].startswith(
                'data:image/jpeg;base64,'))

    def test_encode_image_uses_the_right_mime_type(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / 'photo.png'
            image_path.write_bytes(b'fake')
            self.assertTrue(encode_image(image_path).startswith(
                'data:image/png;base64,'))


if __name__ == '__main__':
    unittest.main()

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / 'tools'))
SPEC = importlib.util.spec_from_file_location('phrase_builder', PROJECT / 'tools/build_phrase_supplement.py')
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class PhraseSupplementTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'characters.tsv').write_text('1\t你\t20041\t0\t1\n2\t好\t18440\t0\t1\n')
        (root / 'phrases').mkdir()
        source = root / 'source.json'
        document = {'format_version': 1, 'scope': 'experimental_monophonic_full_pinyin',
                    'source_sha256': {}, 'words': [
                        {'text': '你好', 'pinyin': ['ni', 'hao'], 'sources': ['小词库.json']}]}
        source.write_text(json.dumps(document))
        return source, document

    def test_rebuild_removes_stale_buckets_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _ = self.fixture(root)
            first = BUILDER.build(source, root)
            expected = (root / 'phrase_supplement/nh.tsv').read_bytes()
            (root / 'phrase_supplement/zz.tsv').write_text('stale')
            self.assertEqual(BUILDER.build(source, root), first)
            self.assertEqual((root / 'phrase_supplement/nh.tsv').read_bytes(), expected)
            self.assertFalse((root / 'phrase_supplement/zz.tsv').exists())

    def test_rejects_duplicate_existing_unmapped_and_polyphonic_words(self):
        for failure in ('duplicate', 'base', 'unmapped', 'polyphonic'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, document = self.fixture(root)
                if failure == 'duplicate':
                    document['words'] *= 2
                elif failure == 'base':
                    (root / 'phrases/nh.tsv').write_text('2\t你好\t1,2\t1\t1\n')
                elif failure == 'unmapped':
                    document['words'][0]['pinyin'][0] = 'li'
                else:
                    with (root / 'characters.tsv').open('a') as stream:
                        stream.write('3\t你\t19777\t0\t1\n')
                source.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    BUILDER.build(source, root)


if __name__ == '__main__':
    unittest.main()

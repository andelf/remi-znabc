import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('supplement', PROJECT / 'tools/build_supplement.py')
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def record(character='槃', readings=None, shapes=None, suffix='33'):
    return {'character': character, 'pinyin': readings or ['pan'], 'shapes': shapes or [],
            'suffix': suffix, 'source': 'manual', 'suffix_source': 'manual'}


class SupplementTests(unittest.TestCase):
    def test_export_scope_and_manual_override(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'review.sqlite3'
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute('CREATE TABLE characters (character TEXT, position INTEGER, payload TEXT)')
                connection.execute('CREATE TABLE reviews (character TEXT, payload TEXT)')
                for index, (character, common, base) in enumerate(
                        [('槃', True, False), ('喆', True, False), ('㛃', True, False),
                         ('你', True, True), ('垚', False, False)]):
                    row = {'character': character, 'missing_common': common, 'in_base': base,
                           'recovery': dict(record(character), status='approved')}
                    connection.execute('INSERT INTO characters VALUES (?, ?, ?)', (character, index, json.dumps(row)))
                connection.execute('INSERT INTO reviews VALUES (?, ?)',
                                   ('喆', json.dumps(dict(record('喆'), status='excluded'))))
                connection.execute('INSERT INTO reviews VALUES (?, ?)',
                                   ('槃', json.dumps(dict(record(), status='pending'))))
            exported = BUILDER.export_reviews(database)
            self.assertEqual([row['character'] for row in exported['characters']], ['㛃'])

    def test_stable_codes_polyphony_and_unsupported_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'characters.tsv').write_text('10164\t你\t19985\t50\t255\n')
            source = root / 'source.json'
            rows = [record(shapes=['335734', '335734']), record('垈', ['dai', 'tae'], ['32171'], '32')]
            source.write_text(json.dumps({'format_version': 1, 'scope': 'approved_missing_common', 'characters': rows}))
            manifest = BUILDER.build(source, root)
            first = (root / 'supplement/characters.tsv').read_bytes()
            self.assertEqual((manifest['characters'], manifest['readings'], manifest['shape_relationships']), (2, 2, 2))
            self.assertEqual(manifest['unsupported_readings'][0]['pinyin'], 'tae')
            self.assertEqual((root / 'supplement/shapes/3.tsv').read_text().count('335734'), 1)
            source.write_text(json.dumps({'format_version': 1, 'scope': 'approved_missing_common', 'characters': rows[::-1]}))
            BUILDER.build(source, root)
            self.assertEqual((root / 'supplement/characters.tsv').read_bytes(), first)
            with self.assertRaises(ValueError):
                rows[0]['character'] = '你'
                source.write_text(json.dumps({'format_version': 1, 'scope': 'approved_missing_common', 'characters': rows}))
                BUILDER.build(source, root)

    def test_pinyin_only_and_ambiguous_shapes_do_not_invent_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'characters.tsv').write_text('')
            source = root / 'source.json'
            rows = [record('㛃', ['jie'], suffix=''), record('尢', ['you', 'wang'], ['27316', '136'], '')]
            source.write_text(json.dumps({'format_version': 1, 'scope': 'approved_missing_common', 'characters': rows}))
            manifest = BUILDER.build(source, root)
            self.assertEqual(manifest['readings'], 3)
            self.assertEqual(manifest['pinyin_only'], ['㛃'])
            self.assertEqual(manifest['without_suffix'], ['㛃', '尢'])
            for line in (root / 'supplement/characters.tsv').read_text().splitlines():
                self.assertEqual(line.split('\t')[3], '0')

    def test_shipped_data_rebuild_is_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'characters.tsv').write_bytes((PROJECT / 'rime/znabc_data/characters.tsv').read_bytes())
            manifest = BUILDER.build(PROJECT / 'data/character_supplement.json', root)
            self.assertEqual((manifest['characters'], manifest['readings']), (1242, 1660))
            for path in (root / 'supplement').rglob('*'):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (PROJECT / 'rime/znabc_data' / path.relative_to(root)).read_bytes())


if __name__ == '__main__':
    unittest.main()

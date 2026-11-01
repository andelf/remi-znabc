import csv
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from review_server import (ReviewHandler, build_catalog, classify_recovery, initialize_database,
                           suffix_text, validate_review)


def recovery_row(character='槃', shapes=('335734',), in_base=False):
    return {'character': character, 'in_base': in_base, 'current': [], 'current_shapes': [],
            'extension': [{'pinyin': 'pan', 'shape': shape, 'sections': ['shape', 'pinyin']}
                          for shape in shapes]}


class RecoveryTests(unittest.TestCase):
    def test_consistent_indexes_and_unique_prefix_restore_automatically(self):
        row = recovery_row(shapes=('335734', '33573'))
        classify_recovery(row)
        self.assertEqual(row['recovery']['status'], 'approved')
        self.assertEqual(row['recovery']['pinyin'], ['pan'])
        self.assertEqual(row['recovery']['suffix'], '33')
        self.assertEqual(row['recovery']['source'], 'original_recovery')
        self.assertEqual(row['recovery']['suffix_source'], 'derived_unique_prefix')
        self.assertFalse(row['recovery']['shape_verified'])

    def test_existing_summary_is_preserved_despite_alternate_prefix(self):
        row = recovery_row('比', shapes=('1635', '6135'), in_base=True)
        row['current'] = [{'pinyin': 'bi', 'suffix': '16'}]
        classify_recovery(row)
        self.assertIsNone(row['recovery'])
        self.assertEqual(row['suffix_suggestion'], '')
        self.assertEqual(row['current'][0]['suffix'], '16')

    def test_ambiguous_prefix_restores_original_values_but_stays_pending(self):
        row = recovery_row(shapes=('335734', '435734'))
        classify_recovery(row)
        self.assertEqual(row['recovery']['status'], 'pending')
        self.assertEqual(row['recovery']['suffix'], '')
        self.assertEqual(row['recovery']['shapes'], ['335734', '435734'])
        self.assertIn('多个笔形前缀', row['recovery_issue'])

    def test_one_sided_mismatched_and_invalid_records_are_not_adopted(self):
        for mismatch in ['one-sided', 'mismatched-pair', 'invalid']:
            with self.subTest(mismatch=mismatch):
                row = recovery_row()
                if mismatch == 'invalid':
                    row['extension_invalid'] = True
                else:
                    row['extension'][0]['sections'] = ['shape']
                    if mismatch == 'mismatched-pair':
                        row['extension'].append({'pinyin': 'ban', 'shape': '335734', 'sections': ['pinyin']})
                classify_recovery(row)
                self.assertIsNone(row['recovery'])
                self.assertTrue(row['recovery_issue'])

    def test_missing_original_and_one_digit_summary(self):
        row = recovery_row(shapes=())
        classify_recovery(row)
        self.assertIsNone(row['recovery'])
        self.assertEqual(suffix_text(0x80), '8')
        self.assertEqual(suffix_text(0x32), '32')
        self.assertEqual(suffix_text(0), '')
        row = recovery_row(shapes=('8',))
        classify_recovery(row)
        self.assertEqual(row['recovery']['suffix'], '8')

    def test_catalog_reads_original_summary_and_dual_indexes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'shapes').mkdir()
            (root / 'characters.tsv').write_text('1\t口\t65\t128\t200\n', encoding='utf-8')
            (root / 'manifest.json').write_text('{"project_version":"test"}')
            (root / 'missing_common_characters.tsv').write_text(
                'character\tcorpus_pinyin\texamples\tcorpus_word_count\n槃\tpan\t涅槃\t1\n', encoding='utf-8')
            (root / 'extension-table.csv').write_text(
                'character,section,pinyin,shape_code,status\n槃,shape,pan,335734,ok\n槃,pinyin,pan,335734,ok\n', encoding='utf-8')
            catalog, metadata = build_catalog(root, root, root, root)
            rows = {row['character']: row for row in catalog}
            self.assertEqual(rows['口']['current'][0]['suffix'], '8')
            self.assertEqual(rows['槃']['recovery']['suffix'], '33')


class QuietHandler(ReviewHandler):
    def log_message(self, *args):
        pass


class ReviewServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / 'review.sqlite3'
        self.catalog = [{'character': '喆'}, {'character': '燚'}]
        initialize_database(self.database, self.catalog, {'base_version': 'test'})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.server.database = self.database
        self.server.assets = Path(__file__).resolve().parents[1] / 'designs/character-review'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def request(self, route, body=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        request = Request(self.base_url + route, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    def review(self, revision=0, **changes):
        return dict({'revision': revision, 'status': 'approved', 'pinyin': ['zhe'],
                     'suffix': '', 'shapes': [], 'shape_verified': False, 'notes': ''}, **changes)

    def test_save_history_and_persistence_after_catalog_reload(self):
        route = '/api/reviews/' + quote('喆')
        status, body = self.request(route, self.review())
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['review']['revision'], 1)
        status, body = self.request(route, self.review(1, notes='核对依据\n第二行'))
        self.assertEqual(status, 200)
        initialize_database(self.database, self.catalog, {'base_version': 'next'})
        status, body = self.request('/api/catalog')
        self.assertEqual(json.loads(body)['items'][0]['review']['revision'], 2)
        status, body = self.request('/api/history?character=' + quote('喆'))
        self.assertEqual([row['revision'] for row in json.loads(body)['items']], [2, 1])

    def test_stale_revision_does_not_overwrite_or_add_history(self):
        route = '/api/reviews/' + quote('喆')
        self.request(route, self.review())
        self.assertEqual(self.request(route, self.review(notes='stale'))[0], 409)
        status, body = self.request('/api/history?character=' + quote('喆'))
        self.assertEqual(len(json.loads(body)['items']), 1)

    def test_exports_include_only_saved_reviews_and_filter_status(self):
        notes = '一行\t两列\n三行'
        self.request('/api/reviews/' + quote('喆'), self.review(notes=notes))
        self.request('/api/reviews/' + quote('燚'), self.review(status='deferred', pinyin=[]))
        status, body = self.request('/api/export')
        self.assertEqual([row['character'] for row in json.loads(body)['items']], ['喆'])
        status, body = self.request('/api/export?status=all&format=tsv')
        rows = list(csv.DictReader(io.StringIO(body.decode('utf-8-sig')), delimiter='\t'))
        self.assertEqual(len(rows), 2)
        self.assertEqual(next(row for row in rows if row['character'] == '喆')['notes'], notes)

    def test_validation_and_unknown_character(self):
        route = '/api/reviews/' + quote('喆')
        for changes in [{'pinyin': []}, {'suffix': '9'}, {'shapes': ['1234567']},
                        {'shape_verified': True}, {'status': []}, {'revision': True}]:
            with self.subTest(changes=changes):
                payload = self.review()
                payload.update(changes)
                self.assertEqual(self.request(route, payload)[0], 400)
        self.assertEqual(self.request('/api/reviews/' + quote('无'), self.review())[0], 404)
        self.assertEqual(validate_review(self.review(pinyin=['LÜ', 'lu:', 'lü']))['pinyin'], ['lv'])

    def test_rejects_cross_origin_mutations(self):
        status, body = self.request('/api/reviews/' + quote('喆'), self.review(), origin='http://example.com')
        self.assertEqual(status, 403)

    def test_recovery_exports_and_manual_override_survive_reseed(self):
        row = recovery_row()
        classify_recovery(row)
        initialize_database(self.database, [row], {'base_version': 'test'})
        status, body = self.request('/api/export')
        automatic = json.loads(body)['items'][0]
        self.assertEqual(automatic['character'], '槃')
        self.assertEqual(automatic['source'], 'original_recovery')
        self.assertEqual(automatic['revision'], 0)
        status, body = self.request('/api/history?character=' + quote('槃'))
        self.assertEqual(json.loads(body)['items'], [])
        status, body = self.request('/api/reviews/' + quote('槃'), self.review(status='excluded'))
        self.assertEqual(status, 200)
        initialize_database(self.database, [row], {'base_version': 'next'})
        status, body = self.request('/api/export')
        self.assertEqual(json.loads(body)['items'], [])
        status, body = self.request('/api/export?status=all')
        manual = json.loads(body)['items'][0]
        self.assertEqual(manual['source'], 'manual')
        self.assertEqual(manual['status'], 'excluded')
        self.assertEqual(manual['revision'], 1)

    def test_manual_new_shapes_derive_suffix_but_ambiguous_shapes_do_not(self):
        route = '/api/reviews/' + quote('喆')
        status, body = self.request(route, self.review(shapes=['3235', '32355']))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['review']['suffix'], '32')
        self.assertEqual(json.loads(body)['review']['suffix_source'], 'derived_unique_prefix')
        status, body = self.request(route, self.review(1, shapes=['3235', '6335']))
        self.assertEqual(json.loads(body)['review']['suffix'], '')
        status, body = self.request(route, self.review(2, shapes=['3235'], suffix='63'))
        self.assertEqual(json.loads(body)['review']['suffix'], '63')


if __name__ == '__main__':
    unittest.main()

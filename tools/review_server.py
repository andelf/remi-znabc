import argparse
from collections import defaultdict
from contextlib import closing, contextmanager
import csv
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, unquote, urlsplit


PROJECT = Path(__file__).resolve().parent.parent
TOKENS = ['ZH', 'SH', 'CH', 'ING', 'AI', 'AN', 'ANG', 'AO', 'EI', 'EN',
          'ENG', 'IA', 'IAN', 'IANG', 'IAO', 'IE', 'IN', 'IU', 'ONG', 'OU',
          'UA', 'UAI', 'UAN', 'UE', 'UN', 'UENG', 'UI', 'UO', 'UANG', 'ER', 'IONG']
STATUSES = {'pending', 'approved', 'deferred', 'excluded'}


@contextmanager
def connect_database(database):
    with closing(sqlite3.connect(database, timeout=10)) as connection:
        with connection:
            yield connection


def syllable(packed):
    return ''.join(TOKENS[value - 1] if 0 < value <= len(TOKENS) else chr(value)
                   for value in (packed // 256, packed % 256) if value).lower()


def read_tsv(filename):
    if not filename.is_file():
        return []
    with filename.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def suffix_text(packed):
    return format(packed, 'x').rstrip('0') if packed else ''


def unique_shape_suffix(shapes):
    prefixes = {shape[:2] for shape in shapes}
    return next(iter(prefixes)) if len(prefixes) == 1 else ''


def classify_recovery(row):
    row['recovery'] = None
    row['recovery_issue'] = ''
    row['suffix_suggestion'] = ''
    if row['in_base']:
        return
    records = row['extension']
    if not records:
        if row.get('extension_invalid'):
            row['recovery_issue'] = '原版记录存在解析异常，需要人工核对。'
        return
    shapes = sorted({record['shape'] for record in records} | set(row['current_shapes']))
    prefixes = sorted({shape[:2] for shape in shapes})
    row['suffix_suggestion'] = unique_shape_suffix(shapes)
    if row.get('extension_invalid') or any(set(record['sections']) != {'shape', 'pinyin'} for record in records):
        row['recovery_issue'] = '原版记录存在异常或双索引不一致，需要人工核对。'
        return
    ambiguous = len(prefixes) != 1
    row['recovery'] = {
        'status': 'pending' if ambiguous else 'approved',
        'pinyin': sorted({record['pinyin'] for record in records}),
        'suffix': row['suffix_suggestion'], 'shapes': shapes,
        'shape_verified': False, 'notes': '', 'source': 'original_recovery',
        'suffix_source': 'ambiguous' if ambiguous else 'derived_unique_prefix',
        'revision': 0, 'updated_at': None,
    }
    if ambiguous:
        row['recovery_issue'] = '原版拼音与笔形已恢复，但有多个笔形前缀，需要确定音形后缀：' + '、'.join(prefixes)


def build_catalog(data_dir, comparison_dir, export_dir, lexicon_dir):
    entries = {}

    def entry(character):
        if character not in entries:
            entries[character] = {
                'character': character, 'unicode': f'U+{ord(character):04X}',
                'in_base': False, 'missing_common': False, 'missing_corpus': False,
                'current': [], 'current_shapes': [], 'corpus_pinyin': [],
                'examples': [], 'word_count': 0, 'extension': [], 'strokes': [],
                'reading_gap': [],
            }
        return entries[character]

    for line in (data_dir / 'characters.tsv').read_text(encoding='utf-8').splitlines():
        code, character, packed, shape, weight = line.split('\t')
        row = entry(character)
        row['in_base'] = True
        row['current'].append({'code': int(code), 'pinyin': syllable(int(packed)),
                               'suffix': suffix_text(int(shape)),
                               'weight': int(weight)})
    for filename, flag in [('missing_common_characters.tsv', 'missing_common'),
                           ('missing_corpus_characters.tsv', 'missing_corpus')]:
        for source in read_tsv(comparison_dir / filename):
            row = entry(source['character'])
            row[flag] = True
            row['corpus_pinyin'] = source['corpus_pinyin'].split()
            row['examples'] = source['examples'].split()
            row['word_count'] = int(source['corpus_word_count'])
    for source in read_tsv(comparison_dir / 'missing_character_readings.tsv'):
        row = entry(source['character'])
        row['reading_gap'].append(source['pinyin'])
        row['corpus_pinyin'] = sorted(set(row['corpus_pinyin'] + [source['pinyin']]))
        row['examples'] = list(dict.fromkeys(row['examples'] + source['examples'].split()))[:12]
    for file in sorted((data_dir / 'shapes').glob('*.tsv')):
        for line in file.read_text(encoding='utf-8').splitlines():
            shape, character = line.split('\t')
            if character in entries and shape not in entries[character]['current_shapes']:
                entries[character]['current_shapes'].append(shape)
    extension_file = export_dir / 'extension-table.csv'
    extension = defaultdict(dict)
    if extension_file.is_file():
        with extension_file.open(encoding='utf-8', newline='') as stream:
            for source in csv.DictReader(stream):
                character = source['character']
                if character not in entries:
                    continue
                pinyin, shape = source['pinyin'], source['shape_code']
                if (source['status'] != 'ok' or source['section'] not in {'shape', 'pinyin'}
                        or not re.fullmatch('[a-z]{1,6}', pinyin) or not re.fullmatch('[1-8]{1,6}', shape)):
                    entries[character]['extension_invalid'] = True
                    continue
                candidate = extension[character].setdefault((pinyin, shape),
                    {'pinyin': pinyin, 'shape': shape, 'sections': []})
                if source['section'] not in candidate['sections']:
                    candidate['sections'].append(source['section'])
        for character, candidates in extension.items():
            entries[character]['extension'] = list(candidates.values())
    stroke_file = lexicon_dir / 'EncodeTable/stroke.json'
    if stroke_file.is_file():
        for source in json.loads(stroke_file.read_text(encoding='utf-8')):
            character = source['token']
            if character in entries:
                entries[character]['strokes'] = list(dict.fromkeys(
                    ''.join(code) for code in source.get('encode', []) if code))
    for row in entries.values():
        classify_recovery(row)
    ordered = sorted(entries.values(), key=lambda row: (
        not row['missing_common'], row['in_base'], -row['word_count'], row['character']))
    metadata = {'base_version': json.loads((data_dir / 'manifest.json').read_text())['project_version'],
                'comparison_available': (comparison_dir / 'missing_common_characters.tsv').is_file(),
                'extension_available': extension_file.is_file(), 'stroke_available': stroke_file.is_file()}
    return ordered, metadata


def initialize_database(database, catalog, metadata):
    database.parent.mkdir(parents=True, exist_ok=True)
    with connect_database(database) as connection:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS characters (
                character TEXT PRIMARY KEY, position INTEGER NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews (
                character TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                updated_at TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY, character TEXT NOT NULL, revision INTEGER NOT NULL,
                updated_at TEXT NOT NULL, payload TEXT NOT NULL,
                UNIQUE(character, revision)
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        connection.execute('DELETE FROM characters')
        connection.executemany('INSERT INTO characters VALUES (?, ?, ?)',
            [(row['character'], index, json.dumps(row, ensure_ascii=False)) for index, row in enumerate(catalog)])
        connection.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?)',
                           ('catalog', json.dumps(metadata, ensure_ascii=False)))


def validate_review(body):
    if not isinstance(body, dict):
        raise ValueError('请求必须是 JSON 对象')
    status, readings = body.get('status'), body.get('pinyin')
    if not isinstance(status, str) or status not in STATUSES:
        raise ValueError('无效的核对状态')
    if not isinstance(readings, list) or len(readings) > 20 or not all(isinstance(value, str) for value in readings):
        raise ValueError('拼音必须是数组，最多 20 个读音')
    readings = list(dict.fromkeys(value.strip().lower().replace('u:', 'v').replace('ü', 'v') for value in readings if value.strip()))
    if any(not re.fullmatch('[a-z]{1,6}', value) for value in readings):
        raise ValueError('请使用不带声调的全拼，ü 用 v 表示，每个读音 1～6 个字母')
    if status == 'approved' and not readings:
        raise ValueError('确认前至少填写一个核对过的拼音；形码可以留空')
    suffix, shapes = body.get('suffix', ''), body.get('shapes', [])
    if not isinstance(suffix, str) or (suffix and not re.fullmatch('[1-8]{1,2}', suffix)):
        raise ValueError('音形后缀须为 1～2 位数字 1～8，或留空')
    if not isinstance(shapes, list) or len(shapes) > 30 or any(
            not isinstance(value, str) or not re.fullmatch('[1-8]{1,6}', value) for value in shapes):
        raise ValueError('纯笔形码每组为 1～6 位数字 1～8')
    notes, verified = body.get('notes', ''), body.get('shape_verified', False)
    if not isinstance(notes, str) or len(notes) > 2000 or type(verified) is not bool:
        raise ValueError('备注最多 2000 字；形码核对标记须为布尔值')
    if verified and not (suffix or shapes):
        raise ValueError('尚未填写形码，不能标记为形码已核对')
    if type(body.get('revision')) is not int or body['revision'] < 0:
        raise ValueError('缺少有效的修改版本，请刷新页面')
    return {'status': status, 'pinyin': readings, 'suffix': suffix,
            'shapes': list(dict.fromkeys(shapes)), 'shape_verified': verified, 'notes': notes,
            'source': 'manual', 'suffix_source': 'manual' if suffix else 'none'}


def save_review(database, character, body):
    payload = validate_review(body)
    with connect_database(database) as connection:
        connection.execute('BEGIN IMMEDIATE')
        stored = connection.execute('SELECT payload FROM characters WHERE character=?', (character,)).fetchone()
        if not stored:
            raise LookupError('字表中没有这个字')
        row = json.loads(stored[0])
        if not row.get('in_base'):
            derived = unique_shape_suffix(payload['shapes'])
            if derived and not payload['suffix']:
                payload['suffix'] = derived
            if derived and payload['suffix'] == derived:
                payload['suffix_source'] = 'derived_unique_prefix'
        previous = connection.execute('SELECT revision FROM reviews WHERE character=?', (character,)).fetchone()
        revision = previous[0] if previous else 0
        if revision != body['revision']:
            raise FileExistsError('这个字已在另一页面修改，请刷新后重试；当前页面内容尚未写入')
        updated = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
        encoded = json.dumps(payload, ensure_ascii=False)
        connection.execute('INSERT OR REPLACE INTO reviews VALUES (?, ?, ?, ?)',
                           (character, revision + 1, updated, encoded))
        connection.execute('INSERT INTO history(character, revision, updated_at, payload) VALUES (?, ?, ?, ?)',
                           (character, revision + 1, updated, encoded))
    return dict(payload, revision=revision + 1, updated_at=updated)


def load_reviews(connection):
    return {character: dict({'source': 'manual', 'suffix_source': 'manual'}, **json.loads(payload),
                            revision=revision, updated_at=updated)
            for character, revision, updated, payload in connection.execute(
                'SELECT character, revision, updated_at, payload FROM reviews')}


def load_effective_reviews(connection):
    records = {}
    for character, payload in connection.execute('SELECT character, payload FROM characters'):
        recovery = json.loads(payload).get('recovery')
        if recovery:
            records[character] = recovery
    records.update(load_reviews(connection))
    return records


class ReviewHandler(BaseHTTPRequestHandler):
    def send_bytes(self, data, content_type, status=200, filename=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, data, status=200, filename=None):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode('utf-8'),
                        'application/json; charset=utf-8', status, filename)

    def do_GET(self):
        request = urlsplit(self.path)
        query = parse_qs(request.query)
        assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                  '/style.css': ('style.css', 'text/css')}
        if request.path in assets:
            filename, mime = assets[request.path]
            self.send_bytes((self.server.assets / filename).read_bytes(), mime + '; charset=utf-8')
            return
        with connect_database(self.server.database) as connection:
            if request.path == '/api/catalog':
                reviews = load_reviews(connection)
                rows = []
                for character, payload in connection.execute('SELECT character, payload FROM characters ORDER BY position'):
                    row = json.loads(payload)
                    row['review'] = reviews.get(character)
                    rows.append(row)
                metadata = json.loads(connection.execute('SELECT value FROM metadata WHERE key="catalog"').fetchone()[0])
                self.send_json({'items': rows, 'metadata': dict(metadata, database=str(self.server.database))})
                return
            if request.path == '/api/history':
                character = query.get('character', [''])[0]
                rows = [dict(json.loads(payload), revision=revision, updated_at=updated)
                        for revision, updated, payload in connection.execute(
                            'SELECT revision, updated_at, payload FROM history WHERE character=? ORDER BY revision DESC',
                            (character,))]
                self.send_json({'items': rows})
                return
            if request.path == '/api/export':
                scope, file_format = query.get('status', ['approved'])[0], query.get('format', ['json'])[0]
                if scope not in STATUSES | {'all'} or file_format not in {'json', 'tsv'}:
                    self.send_json({'error': '无效的导出格式或状态'}, 400)
                    return
                reviews = load_effective_reviews(connection)
                rows = [dict(review, character=character, unicode=f'U+{ord(character):04X}')
                        for character, review in sorted(reviews.items()) if scope == 'all' or review['status'] == scope]
                if file_format == 'json':
                    self.send_json({'format_version': 2, 'scope': scope,
                                    'exported_at': datetime.now(timezone.utc).isoformat(), 'items': rows},
                                   filename='znabc-character-reviews.json')
                else:
                    stream = io.StringIO(newline='')
                    writer = csv.writer(stream, delimiter='\t')
                    writer.writerow(['character', 'unicode', 'status', 'pinyin', 'suffix', 'shapes',
                                     'shape_verified', 'notes', 'revision', 'updated_at', 'source', 'suffix_source'])
                    for row in rows:
                        writer.writerow([row['character'], row['unicode'], row['status'], ' '.join(row['pinyin']),
                                         row['suffix'], ' '.join(row['shapes']), int(row['shape_verified']),
                                         row['notes'], row['revision'], row['updated_at'], row['source'], row['suffix_source']])
                    self.send_bytes(stream.getvalue().encode('utf-8-sig'), 'text/tab-separated-values; charset=utf-8',
                                    filename='znabc-character-reviews.tsv')
                return
        self.send_json({'error': '页面不存在'}, 404)

    def do_POST(self):
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            self.send_json({'error': '不接受其他站点的写入请求'}, 403)
            return
        request = urlsplit(self.path)
        prefix = '/api/reviews/'
        if not request.path.startswith(prefix):
            self.send_json({'error': '接口不存在'}, 404)
            return
        character = unquote(request.path[len(prefix):])
        if len(character) != 1:
            self.send_json({'error': '每次只核对一个字符'}, 400)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 65536:
                raise ValueError('无效的请求大小')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('请使用 JSON 提交')
            body = json.loads(self.rfile.read(length))
            result = save_review(self.server.database, character, body)
        except FileExistsError as error:
            self.send_json({'error': str(error)}, 409)
        except LookupError as error:
            self.send_json({'error': str(error)}, 404)
        except (ValueError, UnicodeDecodeError) as error:
            self.send_json({'error': str(error)}, 400)
        except sqlite3.Error:
            self.send_json({'error': '数据库写入失败，修改尚未保存，请重试'}, 500)
        else:
            self.send_json({'review': result})


def main():
    arguments = argparse.ArgumentParser(description='智能 ABC 字表核对台，本地 SQLite 保存，运行时仅需 Python 标准库')
    arguments.add_argument('--host', default='0.0.0.0')
    arguments.add_argument('--port', type=int, default=8765)
    arguments.add_argument('--database', type=Path, default=PROJECT / '.cache/character-review/review.sqlite3')
    arguments.add_argument('--data-dir', type=Path, default=PROJECT / 'rime/znabc_data')
    arguments.add_argument('--comparison-dir', type=Path, default=PROJECT.parent / 'analysis/lexicon-comparison')
    arguments.add_argument('--export-dir', type=Path, default=PROJECT.parent / 'analysis/export')
    arguments.add_argument('--lexicon-dir', type=Path, default=Path('/data/lexicon'))
    options = arguments.parse_args()
    catalog, metadata = build_catalog(options.data_dir, options.comparison_dir, options.export_dir, options.lexicon_dir)
    initialize_database(options.database, catalog, metadata)
    server = ThreadingHTTPServer((options.host, options.port), ReviewHandler)
    server.database = options.database.resolve()
    server.assets = PROJECT / 'designs/character-review'
    print(f'字表核对台：http://{options.host}:{server.server_port}', flush=True)
    print(f'SQLite：{server.database}；载入 {len(catalog)} 个字；不会修改 Rime 安装。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

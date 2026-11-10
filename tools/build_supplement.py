import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3


PROJECT = Path(__file__).resolve().parent.parent
TOKENS = ['zh', 'sh', 'ch', 'ing', 'ai', 'an', 'ang', 'ao', 'ei', 'en',
          'eng', 'ia', 'ian', 'iang', 'iao', 'ie', 'in', 'iu', 'ong', 'ou',
          'ua', 'uai', 'uan', 'ue', 'un', 'ueng', 'ui', 'uo', 'uang', 'er', 'iong']


def pack_pinyin(text):
    if not isinstance(text, str) or not re.fullmatch('[a-z]{1,6}', text):
        raise ValueError('读音必须是小写全拼')
    match = re.match('zh|sh|ch|[bpmfdtnlgkhjqxrzcsyw]', text)
    initial, final = (match[0], text[match.end():]) if match else ('', text)
    if not final:
        if initial in ('m', 'n'):
            return ord(initial.upper()) * 256
        raise ValueError('不能以简拼登记新增读音')
    if final == 'v' and initial in ('j', 'q', 'x'):
        final = 'u'

    def value(token):
        if token in TOKENS:
            return TOKENS.index(token) + 1
        if len(token) == 1 and token in 'aeiouv':
            return ord(token.upper())
        raise ValueError('现有音节解析器不支持该读音')

    if not initial:
        return value(final) * 256
    high = TOKENS.index(initial) + 1 if len(initial) == 2 else ord(initial.upper())
    return high * 256 + value(final)


def export_reviews(database):
    connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        connection.execute('BEGIN')
        reviews = {character: json.loads(payload) for character, payload in
                   connection.execute('SELECT character, payload FROM reviews')}
        result = []
        for payload, in connection.execute('SELECT payload FROM characters ORDER BY position'):
            row = json.loads(payload)
            review = reviews.get(row['character']) or row.get('recovery')
            if row['in_base'] or not row['missing_common'] or not review or review['status'] != 'approved':
                continue
            result.append({'character': row['character'], **{key: review[key] for key in
                           ('pinyin', 'suffix', 'shapes', 'source', 'suffix_source')}})
        return {'format_version': 1, 'scope': 'approved_missing_common',
                'characters': sorted(result, key=lambda row: row['character'])}
    finally:
        connection.close()


def build(source, data_dir):
    raw = source.read_bytes()
    document = json.loads(raw)
    if document.get('format_version') != 1 or document.get('scope') != 'approved_missing_common':
        raise ValueError('不支持的补充字表格式或范围')
    base = {line.split('\t')[1] for line in (data_dir / 'characters.tsv').read_text().splitlines()}
    seen, readings, shapes, rejected, sources = set(), [], set(), [], Counter()
    pinyin_only, without_suffix = [], []
    for row in sorted(document['characters'], key=lambda item: item['character']):
        character = row['character']
        if len(character) != 1 or character in seen or character in base or 0xD800 <= ord(character) <= 0xDFFF:
            raise ValueError(f'补充字重复、已在基础表或字符无效：{character!r}')
        if row['source'] not in ('manual', 'original_recovery') or not row['pinyin']:
            raise ValueError(f'缺少确认来源或读音：{character}')
        suffix = row['suffix']
        if suffix and not re.fullmatch('[1-8]{1,2}', suffix):
            raise ValueError(f'音形后缀无效：{character}')
        valid = []
        for pinyin in sorted(set(row['pinyin'])):
            try:
                packed = pack_pinyin(pinyin)
            except ValueError as error:
                rejected.append({'character': character, 'pinyin': pinyin, 'reason': str(error)})
                continue
            code = 0x100000000 + ord(character) * 65536 + packed
            valid.append((code, character, packed, int(suffix.ljust(2, '0'), 16) if suffix else 0, 0))
        if not valid:
            raise ValueError(f'没有可输入的读音，不能导入：{character}')
        for shape in row['shapes']:
            if not re.fullmatch('[1-8]{1,6}', shape):
                raise ValueError(f'纯笔形码无效：{character}')
            shapes.add((shape, character))
        if not row['shapes']:
            pinyin_only.append(character)
        if not suffix:
            without_suffix.append(character)
        readings.extend(valid)
        seen.add(character)
        sources[row['source']] += 1
    manifest = {'format_version': 1, 'characters': len(seen), 'readings': len(readings),
                'shape_relationships': len(shapes), 'sources': dict(sources),
                'pinyin_only': pinyin_only, 'without_suffix': without_suffix,
                'unsupported_readings': rejected, 'source_sha256': hashlib.sha256(raw).hexdigest(),
                'priority': 'After all original matches; bare initials omit supplements except exact full readings such as m.',
                'code_format': '0x100000000 + Unicode scalar * 65536 + packed pinyin; stable per character/reading.'}
    output = data_dir / 'supplement'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'characters.tsv').write_text(''.join('\t'.join(map(str, row)) + '\n' for row in readings), encoding='utf-8')
    (output / 'shapes').mkdir(exist_ok=True)
    for initial in '12345678':
        (output / 'shapes' / f'{initial}.tsv').write_text(
            ''.join(f'{shape}\t{character}\n' for shape, character in sorted(shapes) if shape[0] == initial), encoding='utf-8')
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    arguments = argparse.ArgumentParser(description='从已确认的常用缺字生成独立补充字库，不改变原版字表')
    arguments.add_argument('--source', type=Path, default=PROJECT / 'data/character_supplement.json')
    arguments.add_argument('--data-dir', type=Path, default=PROJECT / 'rime/znabc_data')
    arguments.add_argument('--database', type=Path, help='可选：先从核对数据库导出已确认常用缺字')
    options = arguments.parse_args()
    if options.database:
        document = export_reviews(options.database)
        options.source.parent.mkdir(parents=True, exist_ok=True)
        options.source.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(build(options.source, options.data_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

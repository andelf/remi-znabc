import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct
import sys


PROJECT = Path(__file__).resolve().parent.parent
WORKSPACE = PROJECT.parent
sys.path.insert(0, str(WORKSPACE / 'analysis'))

from znabc_formats import BaseTables
from build_special_data import build as build_special


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join('\t'.join(str(value) for value in row) + '\n' for row in rows), encoding='utf-8')


def build(source, destination):
    tables = BaseTables(source)
    destination.mkdir(parents=True, exist_ok=True)
    frequency = tables.ovl[0x10040:0x111A0]
    if frequency[8:16] != b'TXLN1994':
        raise ValueError('Unsupported frequency header')
    _, primary_frequencies, alternate_frequencies = struct.unpack_from('<3H', frequency)
    characters = []
    for row in tables.character_rows():
        if row['status'] != 'syllable':
            continue
        code = int(row['internal_code'], 16)
        packed = int(row['packed_pinyin'], 16)
        encoded = bytes.fromhex(row['character_bytes_hex'])
        offset = (encoded[0] - 0xB0) * 94 + encoded[1] - 0xA1
        shape = tables.ovl[0x111E0 + offset]
        if code < 0x8000:
            index = code - 0x2020
            weight = frequency[16 + index] if index < primary_frequencies else 32
        else:
            index = (code - 0x8000) // 2
            address = 16 + primary_frequencies + index
            weight = frequency[address] if index < alternate_frequencies and address < len(frequency) else (0 if index < alternate_frequencies else 32)
        characters.append((code, row['character'], packed, shape, weight))
    write_rows(destination / 'characters.tsv', characters)
    phrases = defaultdict(list)
    phrase_count = 0
    for order, row in enumerate(tables.phrase_rows()):
        syllables = row['pinyin'].split()
        key = syllables[0][0] + syllables[1][0]
        codes = ','.join(str(int(code, 16)) for code in row['internal_codes'].split())
        phrases[key].append((row['length'], row['text'], codes, row['weight_byte'], order))
        phrase_count += 1
    for key, rows in phrases.items():
        write_rows(destination / 'phrases' / f'{key}.tsv', rows)
    shapes = defaultdict(list)
    for row in tables.shape_rows():
        if row['status'] == 'ok':
            shapes[row['shape_code'][0]].append((row['shape_code'], row['character']))
    for key, rows in shapes.items():
        write_rows(destination / 'shapes' / f'{key}.tsv', rows)
    manifest = {
        'format_version': 1,
        'project_version': '0.3.1',
        'source_sha256': {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                          for name in ['winabcnt.ime', 'Winabc.ovl', 'Winabc.cwd']},
        'characters': len(characters),
        'phrases': phrase_count,
        'phrase_buckets': len(phrases),
        'shape_relationships': sum(len(rows) for rows in shapes.values()),
        'scope': 'Recovered base dictionaries and static frequencies; personal learning is stored separately in znabc_user.userdb.',
    }
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description='Build Rime ABC data from the recovered original sample')
    parser.add_argument('--source', type=Path, default=WORKSPACE / 'znabc-5.23-1203-extracted/payload')
    parser.add_argument('--output', type=Path, default=PROJECT / 'rime/znabc_data')
    arguments = parser.parse_args()
    build_special(arguments.source, arguments.output)
    print(json.dumps(build(arguments.source, arguments.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

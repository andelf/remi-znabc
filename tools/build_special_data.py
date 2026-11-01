import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct


PROJECT = Path(__file__).resolve().parent.parent


def read_virtual(raw, address, size):
    header = struct.unpack_from('<I', raw, 0x3C)[0]
    image_base = struct.unpack_from('<I', raw, header + 52)[0]
    sections = header + 24 + struct.unpack_from('<H', raw, header + 20)[0]
    for index in range(struct.unpack_from('<H', raw, header + 6)[0]):
        position = sections + index * 40
        virtual_size, virtual_start, raw_size, raw_start = struct.unpack_from('<4I', raw, position + 8)
        relative = address - image_base - virtual_start
        if 0 <= relative and relative + size <= min(virtual_size, raw_size):
            return raw[raw_start + relative:raw_start + relative + size]
    raise ValueError(f'原版地址无法映射：{address:#x}')


def write_rows(filename, rows):
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(''.join('\t'.join(map(str, row)) + '\n' for row in rows), encoding='utf-8')


def affix_records(table):
    result, position = [], 0
    while position + 2 <= len(table):
        length, direction = table[position:position + 2]
        position += 2
        if length == 0 and direction == 0:
            if position != len(table):
                raise ValueError('附加成分表结束标记之后有多余数据')
            return result
        if length not in (2, 4) or direction not in (1, 2, 3) or position + length > len(table):
            raise ValueError('附加成分记录边界或方向异常')
        codes = struct.unpack_from('<' + 'H' * (length // 2), table, position)
        result.append((direction, ','.join(map(str, codes))))
        position += length
    raise ValueError('附加成分表缺少结束标记')


def extension_records(raw):
    offsets = struct.unpack_from('<36I', raw, 20)
    if offsets[0] != 164 or offsets[-1] != len(raw) or list(offsets) != sorted(offsets):
        raise ValueError('扩展字库索引边界异常')
    indexes = {'shape': defaultdict(set), 'pinyin': defaultdict(set)}
    invalid = set()
    ordered = []
    shape_orders = {}
    position = offsets[0]
    for order, record in enumerate(raw[offsets[0]:].split(b'\r\n')):
        if not record:
            continue
        section = 'shape' if position < offsets[8] else 'pinyin'
        identity = record[:2]
        fields = record[3:].split(b',') if record[2:3] == b',' else []
        if len(fields) == 2:
            shape, pinyin = fields if section == 'shape' else fields[::-1]
        else:
            shape, pinyin = b'', b''
        if not re.fullmatch(rb'[1-8]{1,6}', shape) or not re.fullmatch(rb'[a-z]{1,48}', pinyin):
            invalid.add(identity)
        else:
            pair = pinyin.decode('ascii'), shape.decode('ascii')
            indexes[section][identity].add(pair)
            if section == 'pinyin':
                ordered.append((identity, *pair, order))
            else:
                shape_orders.setdefault((identity, pair[1]), order)
        position += len(record) + 2
    if position != len(raw):
        raise ValueError('扩展字库记录未完整覆盖文件')
    result, seen = [], set()
    rejected = invalid | {
        identity for identity in indexes['shape'].keys() | indexes['pinyin'].keys()
        if ({pair[1] for pair in indexes['shape'][identity]} != {pair[1] for pair in indexes['pinyin'][identity]}
            or not indexes['shape'][identity] <= indexes['pinyin'][identity])}
    for identity, pinyin, shape, order in ordered:
        if identity in rejected or (identity, pinyin, shape) in seen:
            continue
        seen.add((identity, pinyin, shape))
        result.append((identity.decode('gb18030'), pinyin, shape, order, shape_orders[(identity, shape)]))
    return result, len(rejected)


def build(source, destination):
    raw = (source / 'winabcnt.ime').read_bytes()
    affixes = affix_records(read_virtual(raw, 0x623200, 748))
    if len(affixes) != 182:
        raise ValueError('不支持的原版附加成分表')
    write_rows(destination / 'affixes.tsv', affixes)
    table = read_virtual(raw, 0x623160, 159)
    quantity = [(table[index], table[index + 1:index + 3].decode('gbk')) for index in range(0, len(table), 3)]
    if dict(quantity).get(1) != '壹' or dict(quantity).get(ord('N')) != '年':
        raise ValueError('不支持的原版数量词表')
    write_rows(destination / 'quantity.tsv', quantity)
    symbols = {}
    for zone in range(1, 10):
        rows = []
        for position in range(1, 95):
            encoded = bytes([0xA0 + zone, 0xA0 + position])
            try:
                character = encoded.decode('gb2312')
            except UnicodeDecodeError:
                continue
            rows.append((character, encoded.hex()))
        write_rows(destination / 'symbols' / f'{zone}.tsv', rows)
        symbols[str(zone)] = len(rows)
    extension = (source / 'winabcx.ovl').read_bytes()
    records, rejected = extension_records(extension)
    letters, shapes = defaultdict(list), defaultdict(list)
    for character, pinyin, shape, order, shape_order in records:
        letters[pinyin[0]].append((character, pinyin, shape, order))
        shapes[shape[0]].append((character, pinyin, shape, shape_order))
    for initial in 'abcdefghijklmnopqrstuvwxyz':
        write_rows(destination / 'gbk' / f'{initial}.tsv', letters[initial])
    for initial in '12345678':
        write_rows(destination / 'gbk_shapes' / f'{initial}.tsv', sorted(shapes[initial], key=lambda row: row[3]))
    manifest = {
        'format_version': 1, 'quantity_entries': len(quantity), 'symbols': symbols,
        'affix_entries': len(affixes), 'affix_table_address': '0x623200',
        'extension_records': len(records), 'extension_characters': len({row[0] for row in records}),
        'rejected_extension_identities': rejected,
        'source_sha256': {'winabcnt.ime': hashlib.sha256(raw).hexdigest(),
                          'winabcx.ovl': hashlib.sha256(extension).hexdigest()},
        'scope': 'Original affix records, quantity mapping and consistent dual-index extension records; symbols in GB2312 byte order.',
        'unicode_mapping': 'GB18030 for original extension byte identities, including private-use mappings.',
    }
    (destination / 'special_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description='导出原版数量词、GBK 扩展单字和 GB2312 符号运行数据')
    parser.add_argument('--source', type=Path, default=PROJECT.parent / 'znabc-5.23-1203-extracted/payload')
    parser.add_argument('--output', type=Path, default=PROJECT / 'rime/znabc_data')
    arguments = parser.parse_args()
    print(json.dumps(build(arguments.source, arguments.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

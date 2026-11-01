import argparse
import json
from pathlib import Path
import random
import subprocess
import struct
import sys


PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT.parent / 'analysis'))

from segmentation_probe import SegmentationProbe
from znabc_formats import BaseTables
from verify_native import NativeProbe


def main():
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--lua', required=True)
    options = arguments.parse_args()
    tables = BaseTables(PROJECT.parent / 'znabc-5.23-1203-extracted/payload')
    probe = SegmentationProbe(tables)
    quantity_probe = NativeProbe(tables)
    quantity_inputs = [prefix + character for prefix in ('i', 'I')
                       for character in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ$+-*/']
    quantity_inputs += ['i', 'I', 'i123', 'I123', 'i1b2s3', 'I1b2s3', 'i2006n6y3sr', 'iqk', 'i12.5']
    quantity_process = subprocess.run([options.lua, str(PROJECT / 'tests/quantity_dump.lua'), str(PROJECT)],
                                      input='\n'.join(quantity_inputs) + '\n', text=True, capture_output=True, check=True)
    quantity_results = quantity_process.stdout.splitlines()
    assert len(quantity_results) == len(quantity_inputs)
    for text, actual in zip(quantity_inputs, quantity_results):
        quantity_probe.machine.mem_write(0x621045, text.encode('ascii') + b'\0')
        quantity_probe.write_integer(0x621042, len(text), 2)
        result = quantity_probe.call(0x613578, (2 if text[0] == 'I' else 3,))
        size = quantity_probe.integer(0x622F54)
        expected = bytes(quantity_probe.machine.mem_read(0x6266C0, size)).decode('gbk') if result == 1 else '<invalid>'
        assert actual == expected, (text, expected, actual)
    syllables = sorted({row['pinyin'] for row in tables.character_rows() if row['status'] == 'syllable'})
    examples = [item['input'] for item in json.loads((PROJECT.parent / 'analysis/evidence/segmentation-verification.json').read_text())['segmentation']]
    examples += syllables
    generator = random.Random(20261031)
    for index in range(600):
        pieces = [generator.choice(syllables) + generator.choice(['', '', '1', '32', '63', '123', "'"])
                  for position in range(generator.randint(1, 4))]
        examples.append(''.join(pieces))
    process = subprocess.run([options.lua, str(PROJECT / 'tests/parser_dump.lua'), str(PROJECT)],
                             input='\n'.join(examples) + '\n', text=True, capture_output=True, check=True)
    lines = process.stdout.splitlines()
    assert len(lines) == len(examples), (len(lines), len(examples), process.stderr)
    for text, line in zip(examples, lines):
        probe.write_integer(0x6281CC, 0)
        original = probe.segment(text)['segments']
        expected = [[unit['end'], int(unit['phonetic'], 16), unit['initial'], int(unit['shape'], 16), unit['flags']]
                    for unit in original]
        actual = [[int(value) for value in item.split(',')] for item in line.split(';') if item]
        assert actual == expected, (text, expected, actual)
    probe.machine.mem_write(0x62D8E0, tables.ovl[0x10040:0x111A0])
    character_queries = ['shi', 'shi8', 'shi81', 'shi7', 'ni32', 'hao63', 'ke15', 'ke18',
                         'a', 'e', 'o', 'sh', 's', 'n', 'n3', 's1', 'zhong', 'chang', 'xing', 'zh']
    phrase_queries = ['nihao', 'ni32hao63', 'nh', 'zhongguo', 'shijie', 'beijing', 'renmin',
                      'xianggang', "xi'an", "chang'an", 'zhongguorenmin', 'n3h6']
    queries = character_queries + phrase_queries
    process = subprocess.run([options.lua, str(PROJECT / 'tests/engine_dump.lua'), str(PROJECT)],
                             input='\n'.join(queries) + '\n', text=True, capture_output=True, check=True)
    phrase_rows = list(tables.phrase_rows())
    compared_phrases = 0
    for text, line in zip(queries, process.stdout.splitlines()):
        values = line.split('\t')
        probe.write_integer(0x6281CC, 0)
        units = probe.segment(text)['segments']
        probe.write_integer(0x6281D4, 0)
        if text in character_queries:
            probe.call(0x61644B, (0,))
            probe.call(0x614AB0)
            count = probe.integer(0x622F60)
            expected = [f'{probe.integer(0x6266C0 + index * 2, 2)}:{probe.integer(0x62B2A0 + index, 1)}' for index in range(count)]
            assert values[0] == 'character' and int(values[1]) == units[0]['end']
            assert values[2:] == expected, (text, expected[:12], values[2:14], len(expected), len(values) - 2)
        else:
            key = ''.join(tables.syllable(int(unit['phonetic'], 16))[0] for unit in units[:2])
            width = len(units)
            rows = [row for row in phrase_rows if row['length'] == width and ''.join(part[0] for part in row['pinyin'].split()[:2]) == key]
            data = b''.join(bytes.fromhex(row['raw_record_hex']) for row in rows)
            probe.machine.mem_write(0x20000000, data or b'\0')
            probe.write_integer(0x62C068, width)
            probe.write_integer(0x622F60, 0)
            probe.write_integer(0x62C070, 0, 2)
            probe.write_integer(0x62EC90, 0, 2)
            probe.write_integer(0x627360, 0, 1)
            probe.call(0x6167E0, (0x20000000, 0x20000000 + len(data), 0))
            count = probe.integer(0x622F60)
            if count == 0:
                continue
            probe.call(0x616977)
            expected = []
            for index in range(count):
                codes = struct.unpack('<' + 'H' * width, probe.machine.mem_read(0x6266C0 + index * width * 2, width * 2))
                expected.append(','.join(str(code) for code in codes) + ':' + str(probe.integer(0x62B2A0 + index * 4, 1)))
            assert values[0] == 'phrase' and int(values[1]) == units[-1]['end'], text
            assert values[2:] == expected, (text, expected[:12], values[2:14])
            compared_phrases += 1
    print(json.dumps({'passed': True, 'parser_original_x86_comparisons': len(examples),
                      'character_candidate_queries': len(character_queries), 'phrase_candidate_queries': compared_phrases,
                      'quantity_original_x86_comparisons': len(quantity_inputs)}, indent=2))


if __name__ == '__main__':
    main()


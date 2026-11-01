import argparse
from pathlib import Path
import struct
import subprocess
import sys


PROJECT = Path(__file__).resolve().parent.parent


def main():
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--lua', required=True)
    options = arguments.parse_args()
    sys.path.insert(0, str(PROJECT.parent / 'analysis'))
    from segmentation_probe import SegmentationProbe
    from znabc_formats import BaseTables, read_virtual

    tables = BaseTables(PROJECT.parent / 'znabc-5.23-1203-extracted/payload')
    characters = {int(row['internal_code'], 16): row for row in tables.character_rows()}
    exported = []
    cases = []
    blob = read_virtual(tables.ime, 0x623200, 748)
    position = 0
    while blob[position:position + 2] != b'\0\0':
        length, direction = blob[position:position + 2]
        codes = struct.unpack_from('<' + 'H' * (length // 2), blob, position + 2)
        exported.append(str(direction) + '\t' + ','.join(map(str, codes)))
        spelling = "'".join(characters[code]['pinyin'] for code in codes)
        for mask in (1, 2):
            if mask == 2 or len(codes) == 1:
                cases.append((mask, spelling, len(codes)))
        position += length + 2
    assert (PROJECT / 'rime/znabc_data/affixes.tsv').read_text().splitlines() == exported
    cases.extend((2, text, 1) for text in ('de1', 'de3', 'de38', 'de8', 'dei'))
    process = subprocess.run([options.lua, str(PROJECT / 'tests/affix_dump.lua'), str(PROJECT)],
                             input=''.join(f'{mask}\t{text}\n' for mask, text, width in cases),
                             text=True, capture_output=True, check=True)
    actual = process.stdout.splitlines()
    assert len(actual) == len(cases)
    probe = SegmentationProbe(tables)
    for (mask, text, width), result in zip(cases, actual):
        probe.write_integer(0x6281CC, 0)
        probe.segment(text)
        probe.write_integer(0x627364, 0)
        probe.write_integer(0x62C068, width)
        probe.write_integer(0x6281D0, 0)
        probe.write_integer(0x6281D4, width)
        probe.write_integer(0x62B6D4, mask, 1)
        probe.write_integer(0x627408, 0, 1)
        probe.write_integer(0x62EF99, 0, 1)
        probe.call(0x616C1F)
        size = probe.integer(0x627364)
        expected = ','.join(map(str, struct.unpack('<' + 'H' * (size // 2),
                              probe.machine.mem_read(0x62C040, size)))) if size else '-'
        assert result == expected, (mask, text, expected, result)
    print(f'Original affix table: {len(exported)} records; native matcher comparisons: {len(cases)} passed')


if __name__ == '__main__':
    main()

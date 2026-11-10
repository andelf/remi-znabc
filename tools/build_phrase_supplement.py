import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from build_supplement import pack_pinyin


PROJECT = Path(__file__).resolve().parent.parent
SOURCE_FILES = ('小词库.json', '专业性词汇/IT.json')


def character_table(data_dir):
    result = defaultdict(dict)
    for path in (data_dir / 'characters.tsv', data_dir / 'supplement/characters.tsv'):
        if path.exists():
            for line in path.read_text().splitlines():
                code, text, packed, *_ = line.split('\t')
                result[text].setdefault(int(packed), int(code))
    return result


def import_lexicon(root, data_dir, lua):
    characters = character_table(data_dir)
    base = {line.split('\t')[1] for path in (data_dir / 'phrases').glob('*.tsv')
            for line in path.read_text().splitlines()}
    base_codes = [line.split('\t')[2] for path in sorted((data_dir / 'phrases').glob('*.tsv'))
                  for line in path.read_text().splitlines()]
    variants, sources, hashes = defaultdict(set), defaultdict(set), {}
    for name in SOURCE_FILES:
        raw = (root / name).read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        for row in json.loads(raw):
            text = row['token']
            sources[text].add(name)
            for reading in row['encode']:
                variants[text].add(tuple(reading))
    counts, words = Counter(), []
    for text in sorted(variants):
        if text in base:
            counts['already_in_base'] += 1
            continue
        if not 2 <= len(text) <= 9:
            counts['length'] += 1
            continue
        if len(variants[text]) != 1:
            counts['multiple_word_readings'] += 1
            continue
        reading = next(iter(variants[text]))
        if len(reading) != len(text):
            counts['unaligned_reading'] += 1
            continue
        try:
            packed = [pack_pinyin(part) for part in reading]
        except ValueError:
            counts['unsupported_reading'] += 1
            continue
        if any(value not in characters[character] for character, value in zip(text, packed)):
            counts['missing_character_reading'] += 1
            continue
        if any(len(characters[character]) != 1 for character in text):
            counts['polyphonic_character'] += 1
            continue
        words.append({'text': text, 'pinyin': list(reading), 'sources': sorted(sources[text])})
    script = '''package.path = arg[1] .. "/rime/lua/?.lua;" .. package.path
local parser = require("znabc.parser")
local Engine = require("znabc.engine")
local engine = Engine.new(arg[2])
local protected = {}
for line in io.lines() do
  local kind, input = line:match("^(%a)\\t(.*)$")
  local expected
  if kind == "B" then
    local reading, packed = {}, {}
    for value in input:gmatch("%d+") do
      local character = engine.dictionary.characters[tonumber(value)]
      reading[#reading + 1] = parser.syllable(character.packed)
      packed[#packed + 1] = character.packed
    end
    input, expected = table.concat(reading), table.concat(packed, ",")
  end
  local units, consumed = parser.parse(input)
  local packed = {}
  for _, unit in ipairs(units) do packed[#packed + 1] = unit.packed end
  local actual = table.concat(packed, ",")
  if kind == "B" then
    if expected ~= actual or consumed ~= #input then protected[input] = true end
  else
    print(protected[input] and "protected" or consumed .. "\\t" .. actual)
  end
end
'''
    with tempfile.TemporaryDirectory() as directory:
        probe = Path(directory) / 'probe.lua'
        probe.write_text(script)
        output = subprocess.run([str(lua), str(probe), str(PROJECT), str(data_dir)], check=True, text=True,
                                input=''.join('B\t' + codes + '\n' for codes in base_codes) +
                                ''.join('N\t' + ''.join(row['pinyin']) + '\n' for row in words),
                                capture_output=True).stdout.splitlines()
    if len(output) != len(words):
        raise ValueError('解析器检查结果不完整')
    accepted = []
    for row, actual in zip(words, output):
        expected = str(len(''.join(row['pinyin']))) + '\t' + ','.join(
            str(pack_pinyin(part)) for part in row['pinyin'])
        if actual == expected:
            accepted.append(row)
        elif actual == 'protected':
            counts['protected_base_segmentation'] += 1
        else:
            counts['ambiguous_continuous_pinyin'] += 1
    return {'format_version': 1, 'scope': 'experimental_monophonic_full_pinyin',
            'source_repository': 'skrik2/lexicon', 'source_sha256': hashes,
            'selection': '小词库和 IT；排除原词、多读音字词、缺失读音、连续全拼歧义和原词切分冲突；未逐词人工校对',
            'excluded': dict(sorted(counts.items())), 'words': accepted}


def build(source, data_dir):
    raw = source.read_bytes()
    document = json.loads(raw)
    if document.get('format_version') != 1 or document.get('scope') != 'experimental_monophonic_full_pinyin':
        raise ValueError('不支持的补充词表格式')
    characters = character_table(data_dir)
    base = {line.split('\t')[1] for path in (data_dir / 'phrases').glob('*.tsv')
            for line in path.read_text().splitlines()}
    buckets, seen = defaultdict(list), set()
    for order, row in enumerate(sorted(document['words'], key=lambda item: item['text'])):
        text, reading = row['text'], row['pinyin']
        if text in seen or text in base or not 2 <= len(text) <= 9 or len(reading) != len(text):
            raise ValueError(f'重复、原库已有或长度无效：{text}')
        if not row['sources'] or any(name not in SOURCE_FILES for name in row['sources']):
            raise ValueError(f'来源无效：{text}')
        codes = []
        for character, part in zip(text, reading):
            packed = pack_pinyin(part)
            if len(characters[character]) != 1 or packed not in characters[character]:
                raise ValueError(f'字码缺失或读音不唯一：{text}')
            codes.append(characters[character][packed])
        key = ''.join(part[0] for part in reading[:2])
        buckets[key].append(f'{len(text)}\t{text}\t{",".join(map(str, codes))}\t0\t{order}\n')
        seen.add(text)
    destination = data_dir / 'phrase_supplement'
    destination.mkdir(exist_ok=True)
    for old in destination.glob('*.tsv'):
        old.unlink()
    for key, lines in sorted(buckets.items()):
        (destination / f'{key}.tsv').write_text(''.join(lines))
    manifest = {'format_version': 1, 'source_sha256': hashlib.sha256(raw).hexdigest(),
                'phrases': len(seen), 'buckets': len(buckets), 'source_files': document['source_sha256'],
                'policy': 'experimental; full-input full-pinyin only; base candidates first; no frequency claims'}
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description='构建保守筛选的实验补充词库')
    parser.add_argument('--source', type=Path, default=PROJECT / 'data/phrase_supplement.json')
    parser.add_argument('--data-dir', type=Path, default=PROJECT / 'rime/znabc_data')
    parser.add_argument('--lexicon', type=Path)
    parser.add_argument('--lua', type=Path)
    options = parser.parse_args()
    if options.lexicon:
        if not options.lua:
            parser.error('--lexicon 需要 --lua，以实际解析器验证连续全拼')
        document = import_lexicon(options.lexicon, options.data_dir, options.lua)
        options.source.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(build(options.source, options.data_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

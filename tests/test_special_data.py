import importlib.util
from pathlib import Path
import struct
import unittest


PROJECT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('special_data', PROJECT / 'tools/build_special_data.py')
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def extension(shape_rows, pinyin_rows):
    shapes = b''.join(row + b'\r\n' for row in shape_rows)
    pinyin = b''.join(row + b'\r\n' for row in pinyin_rows)
    boundary = 164 + len(shapes)
    offsets = [164] * 8 + [boundary] * 27 + [boundary + len(pinyin)]
    return bytes(20) + struct.pack('<36I', *offsets) + shapes + pinyin


class SpecialDataTests(unittest.TestCase):
    def test_affixes_preserve_order_codes_and_direction(self):
        table = bytes.fromhex('0201cc800202e6800402142056200000')
        self.assertEqual(BUILDER.affix_records(table), [(1, '32972'), (2, '32998'), (2, '8212,8278')])

    def test_affixes_reject_truncated_or_invalid_records(self):
        for table in (b'', bytes.fromhex('0201cc80'), bytes.fromhex('0204cc800000'),
                      bytes.fromhex('040214200000'), bytes.fromhex('00000000')):
            with self.subTest(table=table), self.assertRaises(ValueError):
                BUILDER.affix_records(table)

    def test_extra_readings_preserve_pinyin_order_and_shape_order(self):
        character = '行'.encode('gbk')
        another = '可'.encode('gbk')
        raw = extension([character + b',332,hang', another + b',1512,ke'],
                        [another + b',ke,1512', character + b',xing,332', character + b',hang,332',
                         character + b',xing,332'])
        rows, rejected = BUILDER.extension_records(raw)
        self.assertEqual(rejected, 0)
        self.assertEqual([row[:3] for row in rows], [('可', 'ke', '1512'), ('行', 'xing', '332'), ('行', 'hang', '332')])
        self.assertLess(rows[1][4], rows[0][4])
        self.assertEqual(rows[1][4], rows[2][4])

    def test_conflicting_or_one_sided_records_are_excluded(self):
        character = '行'.encode('gbk')
        for shapes, pinyin in [([character + b',332,hang'], [character + b',hang,333']),
                               ([character + b',332,hang'], [character + b',xing,332']),
                               ([], [character + b',xing,332']),
                               ([character + b',332,hang'], [])]:
            self.assertEqual(BUILDER.extension_records(extension(shapes, pinyin)), ([], 1))

    def test_malformed_record_excludes_same_character(self):
        character = '行'.encode('gbk')
        raw = extension([character + b',332,hang', character + b',9,hang'], [character + b',hang,332'])
        self.assertEqual(BUILDER.extension_records(raw), ([], 1))

    def test_bad_boundaries_and_unterminated_record_are_rejected(self):
        raw = bytearray(extension([b'\xb0\xa1,123,a'], [b'\xb0\xa1,a,123']))
        struct.pack_into('<I', raw, 20, 165)
        with self.assertRaises(ValueError):
            BUILDER.extension_records(bytes(raw))
        raw = bytearray(extension([b'\xb0\xa1,123,a'], [b'\xb0\xa1,a,123'])[:-2])
        struct.pack_into('<I', raw, 160, len(raw))
        with self.assertRaises(ValueError):
            BUILDER.extension_records(bytes(raw))


if __name__ == '__main__':
    unittest.main()

import importlib.util
from pathlib import Path
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('znabc_install', PROJECT / 'tools/install.py')
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallerTests(unittest.TestCase):
    def test_preserves_existing_patch_and_other_schemas(self):
        original = 'patch:\n  menu/page_size: 5\n  schema_list:\n    - schema: luna_pinyin\n'
        result = INSTALLER.enable_schema(original)
        self.assertIn(original, result)
        self.assertIn('schema_list/@next', result)
        self.assertEqual(INSTALLER.enable_schema(result), result)

    def test_handles_empty_and_flow_empty_patch(self):
        self.assertIn('schema: znabc', INSTALLER.enable_schema(''))
        self.assertIn('schema: znabc', INSTALLER.enable_schema('patch: {}\n'))
        with self.assertRaises(ValueError):
            INSTALLER.enable_schema('patch: {menu/page_size: 5}\n')
        with self.assertRaises(ValueError):
            INSTALLER.enable_schema('patch:\n  schema_list/@next:\n    schema: other_schema\n')

    def test_dry_run_backups_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / 'source', root / 'user'
            (source / 'znabc_data').mkdir(parents=True)
            (source / 'znabc_data/manifest.json').write_text('{}')
            (source / 'znabc.schema.yaml').write_text('new schema')
            destination.mkdir()
            (destination / 'znabc.schema.yaml').write_text('old schema')
            original = 'patch:\n  menu/page_size: 5\n'
            (destination / 'default.custom.yaml').write_text(original)
            (destination / 'znabc_user.userdb').mkdir()
            (destination / 'znabc_user.userdb/record').write_bytes(b'personal words')
            INSTALLER.install(source, destination, dry_run=True)
            self.assertEqual((destination / 'znabc.schema.yaml').read_text(), 'old schema')
            self.assertFalse((destination / '.znabc-backups').exists())
            count, backup = INSTALLER.install(source, destination)
            self.assertEqual(count, 3)
            self.assertEqual((backup / 'znabc.schema.yaml').read_text(), 'old schema')
            self.assertEqual((backup / 'default.custom.yaml').read_text(), original)
            self.assertEqual(INSTALLER.install(source, destination)[0], 0)
            self.assertEqual((destination / 'znabc_user.userdb/record').read_bytes(), b'personal words')


if __name__ == '__main__':
    unittest.main()

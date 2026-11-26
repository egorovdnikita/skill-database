import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('sync_skills', Path(__file__).resolve().parents[1] / 'scripts/sync-skills.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ReconciliationTests(unittest.TestCase):
    def test_cloud_edit_imported(self):
        self.assertEqual(m.choose(m.digest(b'base'), b'base', b'cloud'), b'cloud')
    def test_local_edit_exported(self):
        self.assertEqual(m.choose(m.digest(b'base'), b'local', b'base'), b'local')
    def test_same_parallel_edit_accepted(self):
        self.assertEqual(m.choose(m.digest(b'base'), b'new', b'new'), b'new')
    def test_parallel_edits_rejected(self):
        with self.assertRaises(RuntimeError):m.choose(m.digest(b'base'), b'local', b'cloud')
    def test_unknown_baseline_never_overwrites(self):
        with self.assertRaises(RuntimeError):m.choose(None, b'local', b'cloud')
    def test_secret_rejected(self):
        with self.assertRaises(RuntimeError):m.validate('concepts', b'---\nname: concepts\n---\nghp_'+b'a'*30)
    def test_personal_email_rejected(self):
        with self.assertRaises(RuntimeError):m.validate('database', b'---\nname: database\n---\nperson@private.test')
    def test_demo_email_allowed(self):
        m.validate('database', b'---\nname: database\n---\nperson@example.com')

if __name__ == '__main__':unittest.main()

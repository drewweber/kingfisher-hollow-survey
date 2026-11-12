import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts.verify_preview_csv import verify


class PreviewCSVTests(unittest.TestCase):
    def put(self, root, text):
        path = root / 'assets' / f'moth-frequency-{hashlib.sha256(text.encode()).hexdigest()[:16]}.csv'
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
        return path

    def test_allows_generated_aggregate_and_empty_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.put(root, 'date,once,twice,three_plus,total\n2026-11-11,211,111,567,889\n')
            self.put(root, 'date,once,twice,three_plus,total\n')
            self.assertEqual(verify(root), 2)

    def test_rejects_other_csv_names_and_locations(self):
        for name in ['private.csv', 'private.CSV', 'moth-frequency-0123456789abcdef.csv', 'assets/other.csv']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_text('secret\n')
                with self.assertRaises(ValueError):
                    verify(root)

    def test_rejects_hash_mismatch_and_nonaggregate_content(self):
        header = 'date,once,twice,three_plus,total\n'
        for text in ['date,user,location\n2026-11-11,name,place\n',
                     header + '2026-11-11,1,2,3,7\n',
                     header + '2026-11-11,-1,2,3,4\n',
                     header + '2026-11-11,1,2,3,6,extra\n',
                     header + '2026-11-11,1,2,3,6\n2026-11-10,1,2,3,6\n']:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.put(root, text)
                with self.assertRaises(ValueError):
                    verify(root)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.put(root, header)
            path.write_text(header + '2026-11-11,1,2,3,6\n')
            with self.assertRaises(ValueError):
                verify(root)

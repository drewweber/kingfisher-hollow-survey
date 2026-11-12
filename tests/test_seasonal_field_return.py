import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import field_guide


class FieldReturnTests(unittest.TestCase):
    def test_return_script_is_local_fingerprinted_and_in_the_offline_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'index.html').write_text('<script src="__SEASONAL_RETURN_SCRIPT__"></script>')
            filename, contents = field_guide._copy_seasonal_return(output)
            self.assertIn(hashlib.sha256(contents).hexdigest()[:12], filename)
            self.assertIn(f'./{filename}', (output / 'index.html').read_text())
            manifest = field_guide._offline_asset_manifest(output, ['./index.html', f'./{filename}'])
            self.assertEqual(len(manifest), 2)
            self.assertEqual((output / filename).read_bytes(), contents)


if __name__ == '__main__':
    unittest.main()

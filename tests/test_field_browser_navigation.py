"""The field shell must share current survey routes and survive offline packaging."""
import hashlib
import json
import shutil
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import report


class FieldBrowserNavigationTests(unittest.TestCase):
    def test_browser_header_uses_shared_routes_and_current_destination(self):
        markup = report.nav('field', include_skip=False)
        self.assertIn('href="/field/" aria-current="page"', markup)
        self.assertIn('href="/life-list/"', markup)
        self.assertIn('href="#results-heading"', markup)
        for mode, config in report.VIEW_CONFIG.items():
            self.assertIn(f'href="{config["route"]}"', markup)
        self.assertNotIn('id="skip-link"', markup)
        self.assertEqual(markup.count('<nav '), 1)

    def test_renderer_loads_with_only_src_on_the_import_path(self):
        result = subprocess.run([
            sys.executable, "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import field_guide; print(field_guide._browser_navigation_html())",
            str(ROOT / "src"),
        ], cwd=tempfile.gettempdir(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('href="/life-list/"', result.stdout)

    def test_builder_includes_every_navigation_asset_in_verified_offline_package(self):
        builder = report.field_guide
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(builder, 'collect_targets', return_value=([], {}, [])), \
                patch.object(builder, 'resolve_taxa', return_value={}), \
                patch.object(builder, '_latest_data_sync', return_value='2026-11-16'), \
                patch.object(builder, '_database_sha256', return_value='fixture'):
            out = Path(temp) / 'field'
            builder.build(output_dir=out)
            worker = (out / 'service-worker.js').read_text()
            assets = json.loads(worker.split('const ASSETS = ', 1)[1].split(';', 1)[0])
            paths = {asset['path'] for asset in assets}
            self.assertIn('./browser-navigation.js', paths)
            self.assertTrue(any(path.startswith('./survey-navigation.') for path in paths))
            for asset in assets:
                path = out / ('index.html' if asset['path'] == './' else asset['path'])
                self.assertEqual(asset['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertNotIn('__BROWSER_NAVIGATION__', (out / 'index.html').read_text())

    def test_shared_controller_and_rendered_routes_are_versioned_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'field'
            shutil.copytree(report.field_guide.APP_SOURCE, out)
            filename, version_bytes = report.field_guide._copy_browser_navigation(out)
            page = (out / 'index.html').read_text()
            self.assertNotIn('__BROWSER_NAVIGATION__', page)
            self.assertNotIn('__SURVEY_NAV_SCRIPT__', page)
            self.assertIn(f'src="./{filename}"', page)
            self.assertIn(report.nav('field', include_skip=False).encode(), version_bytes)
            controller = (ROOT / 'assets/survey-navigation.js').read_text()
            self.assertEqual((out / filename).read_text(), controller)
            self.assertIn(controller, report.scripts('all'))
            manifest = report.field_guide._offline_asset_manifest(out, [
                './index.html', f'./{filename}', './browser-navigation.js', './styles.css'])
            old_version = report.field_guide._offline_cache_version(manifest)
            (out / 'index.html').write_text(page.replace('Inventory', 'Updated inventory'))
            changed = report.field_guide._offline_asset_manifest(out, [
                './index.html', f'./{filename}', './browser-navigation.js', './styles.css'])
            self.assertNotEqual(old_version, report.field_guide._offline_cache_version(changed))


if __name__ == '__main__':
    unittest.main()

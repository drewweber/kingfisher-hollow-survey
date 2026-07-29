import tempfile
import unittest
from pathlib import Path
from unittest import mock

import report

social_export = report.social_export


class SocialExportBuildTests(unittest.TestCase):
    def test_build_writes_route_and_versioned_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp)
            with mock.patch.object(social_export, "PUBLIC_DIR", public):
                output = social_export.build()

            self.assertEqual(output, public / "tools" / "social-export" / "index.html")
            html = output.read_text(encoding="utf-8")
            self.assertIn("Social Media Export", html)
            self.assertNotIn("__ASSET_VERSION__", html)
            self.assertTrue((public / "assets" / "social-export.css").exists())
            self.assertTrue((public / "assets" / "social-export.js").exists())
            self.assertTrue(
                (public / "assets" / "social-export-render.js").exists()
            )

    def test_page_exposes_accessible_controls_and_browser_zip_export(self):
        html = (social_export.SOURCE_DIR / "index.html").read_text(encoding="utf-8")
        script = (social_export.SOURCE_DIR / "app.js").read_text(encoding="utf-8")
        for control in (
            "date-from",
            "date-to",
            "taxon-group",
            "observer",
            "output-format",
            "grid-size",
            "maximum-slides",
            "include-cover",
            "include-labels",
            "theme",
        ):
            self.assertIn(f'id="{control}"', html)
        self.assertIn('role="status"', html)
        self.assertIn('role="alert"', html)
        self.assertIn('aria-labelledby="photo-dialog-title"', html)
        self.assertIn("renderCarouselZip(", script)
        self.assertIn("downloadBlob(result.zip", script)
        self.assertIn("social-export-render.js?v=", script)


if __name__ == "__main__":
    unittest.main()

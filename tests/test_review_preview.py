import tempfile
import unittest
from pathlib import Path

from scripts.prepare_review_preview import prepare


class ReviewPreviewTests(unittest.TestCase):
    def test_review_keeps_links_local_and_field_manifest_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp)
            page = public / "index.html"
            page.write_text('<head></head><body><a href="https://survey.kingfisher-hollow.com/moths/">Moths</a></body>')
            field = public / "field"
            field.mkdir()
            offline = field / "index.html"
            offline.write_bytes(b"offline manifest content")
            url = "https://moth-page-2026-11-12.kingfisher-survey.pages.dev"
            self.assertEqual(prepare(public, url), 1)
            self.assertIn(url + '/moths/', page.read_text())
            self.assertIn("Review preview", page.read_text())
            self.assertEqual(offline.read_bytes(), b"offline manifest content")
            first = page.read_bytes(), (public / "_headers").read_bytes()
            prepare(public, url)
            self.assertEqual(first, (page.read_bytes(), (public / "_headers").read_bytes()))

    def test_live_refresh_rejects_before_writing_any_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp)
            page = public / "index.html"
            page.write_text('<head></head><body></body>')
            (public / "log.html").write_text('<button id="trigger-update">Update</button>')
            with self.assertRaises(ValueError):
                prepare(public, "https://review.kingfisher-survey.pages.dev")
            self.assertEqual(page.read_text(), '<head></head><body></body>')

    def test_rejects_production_or_malformed_destinations(self):
        with tempfile.TemporaryDirectory() as tmp:
            for url in ["https://survey.kingfisher-hollow.com", "https://kingfisher-survey.pages.dev",
                        "https://review.kingfisher-survey.pages.dev.evil.test", "http://review.kingfisher-survey.pages.dev",
                        "https://review.kingfisher-survey.pages.dev/moths/", "https://user@review.kingfisher-survey.pages.dev"]:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    prepare(Path(tmp), url)


if __name__ == "__main__":
    unittest.main()

"""Static page serving on a temporary static/ folder (spec tests 28-30)."""

import tempfile
import unittest
from pathlib import Path

from server import static


class StaticTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.static_dir = self.base / "static"
        self.static_dir.mkdir()
        (self.static_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
        (self.static_dir / "styles.css").write_text("body{}", encoding="utf-8")
        (self.static_dir / "app.js").write_text("// js", encoding="utf-8")
        # A file next to static/ that must never be reachable.
        (self.base / "secret.txt").write_text("secret", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def read(self, url_path):
        return static.read_static(url_path, self.static_dir)


class PageTests(StaticTestCase):
    def test_root_serves_index_html_as_html(self):
        body, content_type = self.read("/")
        self.assertEqual(body, b"<!doctype html>")
        self.assertEqual(content_type, "text/html; charset=utf-8")


class AssetTests(StaticTestCase):
    def test_css_has_text_css_type(self):
        body, content_type = self.read("/static/styles.css")
        self.assertEqual(body, b"body{}")
        self.assertEqual(content_type, "text/css; charset=utf-8")

    def test_js_has_javascript_type(self):
        body, content_type = self.read("/static/app.js")
        self.assertEqual(body, b"// js")
        self.assertEqual(content_type, "text/javascript; charset=utf-8")

    def test_missing_file_is_none(self):
        self.assertIsNone(self.read("/static/missing.js"))

    def test_parent_reference_is_none(self):
        self.assertIsNone(self.read("/static/../secret.txt"))
        self.assertIsNone(self.read("/static/%2e%2e/secret.txt"))

    def test_nested_path_is_none(self):
        self.assertIsNone(self.read("/static/sub/styles.css"))

    def test_unknown_top_level_path_is_none(self):
        self.assertIsNone(self.read("/index.html"))
        self.assertIsNone(self.read("/static/"))

    def test_symlink_outside_static_is_none(self):
        link = self.static_dir / "link.txt"
        try:
            link.symlink_to(self.base / "secret.txt")
        except OSError:
            self.skipTest("symlinks are not available here")
        self.assertIsNone(self.read("/static/link.txt"))


if __name__ == "__main__":
    unittest.main()

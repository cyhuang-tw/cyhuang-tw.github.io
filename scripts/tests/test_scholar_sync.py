import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import scholar_sync


def fixture(name):
    with io.open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as fh:
        return fh.read()


class TestParseListing(unittest.TestCase):
    def test_finds_all_rows(self):
        entries = scholar_sync.parse_listing(fixture("profile.html"))
        self.assertEqual(len(entries), 16)

    def test_row_fields(self):
        entries = scholar_sync.parse_listing(fixture("profile.html"))
        by_id = dict((e.scholar_id, e) for e in entries)
        entry = by_id["1Xfc3ikAAAAJ:Se3iqnhoufwC"]
        self.assertTrue(entry.title.startswith("Dynamic-superb phase-2"))
        self.assertEqual(entry.year, "2025")

    def test_captcha_page_raises(self):
        with self.assertRaises(scholar_sync.FetchError):
            scholar_sync.parse_listing("<html><body>Please show you're not a robot</body></html>")

    def test_empty_page_raises(self):
        with self.assertRaises(scholar_sync.FetchError):
            scholar_sync.parse_listing("<html><body><p>nothing here</p></body></html>")


class TestParseDetail(unittest.TestCase):
    def test_extracts_fields(self):
        detail = scholar_sync.parse_detail(fixture("detail.html"))
        self.assertTrue(detail["authors"].startswith("Chien-yu Huang, Wei-Chih Chen, Shu-wen Yang"))
        self.assertEqual(detail["date"], "2025/4")
        self.assertEqual(detail["venue"], "International Conference on Learning Representations 2025")


if __name__ == "__main__":
    unittest.main()

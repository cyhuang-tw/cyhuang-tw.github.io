import io
import os
import sys
import unittest
from unittest import mock

import requests

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

    def test_row_without_title_link_is_skipped(self):
        html = (
            "<table><tbody id=\"gsc_a_b\">"
            "<tr class=\"gsc_a_tr\"><td class=\"gsc_a_t\">"
            "<span>No title link on this row</span>"
            "</td><td class=\"gsc_a_y\"><span class=\"gsc_a_h\">2019</span></td></tr>"
            "<tr class=\"gsc_a_tr\"><td class=\"gsc_a_t\">"
            "<a href=\"/citations?view_op=view_citation&amp;hl=en&amp;user=U&amp;citation_for_view=U:REAL\" "
            "class=\"gsc_a_at\">Real Paper</a>"
            "</td><td class=\"gsc_a_y\"><span class=\"gsc_a_h\">2020</span></td></tr>"
            "</tbody></table>"
        )
        entries = scholar_sync.parse_listing(html)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "Real Paper")

    def test_row_without_year_defaults_to_empty_string(self):
        html = (
            "<table><tbody id=\"gsc_a_b\">"
            "<tr class=\"gsc_a_tr\"><td class=\"gsc_a_t\">"
            "<a href=\"/citations?view_op=view_citation&amp;hl=en&amp;user=U&amp;citation_for_view=U:NOYEAR\" "
            "class=\"gsc_a_at\">Paper Without A Year</a>"
            "</td><td class=\"gsc_a_y\"></td></tr>"
            "</tbody></table>"
        )
        entries = scholar_sync.parse_listing(html)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].year, "")

    def test_embedded_grecaptcha_reference_does_not_raise(self):
        html = (
            "<script>window.grecaptcha = window.grecaptcha || {};</script>"
            "<table><tbody id=\"gsc_a_b\">"
            "<tr class=\"gsc_a_tr\"><td class=\"gsc_a_t\">"
            "<a href=\"/citations?view_op=view_citation&amp;hl=en&amp;user=U&amp;citation_for_view=U:REAL\" "
            "class=\"gsc_a_at\">Real Paper</a>"
            "</td><td class=\"gsc_a_y\"><span class=\"gsc_a_h\">2021</span></td></tr>"
            "</tbody></table>"
        )
        entries = scholar_sync.parse_listing(html)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "Real Paper")


class TestParseDetail(unittest.TestCase):
    def test_extracts_fields(self):
        detail = scholar_sync.parse_detail(fixture("detail.html"))
        self.assertTrue(detail["authors"].startswith("Chien-yu Huang, Wei-Chih Chen, Shu-wen Yang"))
        self.assertEqual(detail["date"], "2025/4")
        self.assertEqual(detail["venue"], "International Conference on Learning Representations 2025")

    def test_missing_field_defaults_to_empty_string(self):
        html = (
            "<div><div class=\"gsc_oci_field\">Authors</div>"
            "<div class=\"gsc_oci_value\">Jane Doe</div></div>"
        )
        detail = scholar_sync.parse_detail(html)
        self.assertEqual(detail["authors"], "Jane Doe")
        self.assertEqual(detail["date"], "")
        self.assertEqual(detail["venue"], "")

    def test_duplicate_field_label_keeps_first_value(self):
        html = (
            "<div><div class=\"gsc_oci_field\">Conference</div>"
            "<div class=\"gsc_oci_value\">First Venue</div></div>"
            "<div><div class=\"gsc_oci_field\">Conference</div>"
            "<div class=\"gsc_oci_value\">Second Venue</div></div>"
        )
        detail = scholar_sync.parse_detail(html)
        self.assertEqual(detail["venue"], "First Venue")


class TestFetch(unittest.TestCase):
    def test_non_200_status_raises_fetch_error(self):
        fake_response = mock.Mock(status_code=404, text="Not Found")
        with mock.patch("scholar_sync.requests.get", return_value=fake_response) as mock_get:
            with self.assertRaises(scholar_sync.FetchError):
                scholar_sync.fetch("https://scholar.google.com/citations?user=U")
            mock_get.assert_called_once()

    def test_timeout_is_wrapped_as_fetch_error(self):
        with mock.patch(
            "scholar_sync.requests.get",
            side_effect=requests.exceptions.Timeout("Read timed out."),
        ):
            with self.assertRaises(scholar_sync.FetchError) as cm:
                scholar_sync.fetch("https://scholar.google.com/citations?user=U")
            self.assertIn("Read timed out.", str(cm.exception))

    def test_connection_error_is_wrapped_as_fetch_error(self):
        with mock.patch(
            "scholar_sync.requests.get",
            side_effect=requests.exceptions.ConnectionError("Name or service not known"),
        ):
            with self.assertRaises(scholar_sync.FetchError) as cm:
                scholar_sync.fetch("https://scholar.google.com/citations?user=U")
            self.assertIn("Name or service not known", str(cm.exception))


if __name__ == "__main__":
    unittest.main()

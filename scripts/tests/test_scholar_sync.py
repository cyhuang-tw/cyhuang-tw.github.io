import glob
import io
import os
import re
import sys
import unittest
from unittest import mock

import requests
import yaml

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


import shutil
import tempfile


class TestMatching(unittest.TestCase):
    def test_normalize_ignores_case_and_punctuation(self):
        self.assertEqual(
            scholar_sync.normalize_title("Dynamic-SUPERB Phase-2: A Benchmark"),
            scholar_sync.normalize_title("Dynamic-superb phase-2: a benchmark"),
        )

    def test_site_titles_reads_front_matter(self):
        tmp = tempfile.mkdtemp()
        try:
            with io.open(os.path.join(tmp, "a.md"), "w", encoding="utf-8") as fh:
                fh.write('---\ntitle: "Defending Your Voice"\nvenue: x\n---\n')
            titles = scholar_sync.site_titles(tmp)
            self.assertEqual(titles, set([scholar_sync.normalize_title("Defending your voice")]))
        finally:
            shutil.rmtree(tmp)

    def test_load_ignore_reads_titles(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "ignore.yml")
            with io.open(path, "w", encoding="utf-8") as fh:
                fh.write('- title: "Some Old Paper"\n  reason: "not mine"\n')
            self.assertEqual(
                scholar_sync.load_ignore(path),
                set([scholar_sync.normalize_title("some old paper")]),
            )
        finally:
            shutil.rmtree(tmp)

    def test_load_ignore_missing_file_is_empty(self):
        self.assertEqual(scholar_sync.load_ignore("/nonexistent/ignore.yml"), set())

    def test_find_new_excludes_known(self):
        entries = [
            scholar_sync.Entry("a", "Known Paper", "2024"),
            scholar_sync.Entry("b", "Brand New Paper", "2026"),
        ]
        known = set([scholar_sync.normalize_title("known paper")])
        new = scholar_sync.find_new(entries, known)
        self.assertEqual([e.title for e in new], ["Brand New Paper"])

    def test_frozen_profile_against_frozen_site_titles(self):
        # Ruling 1 override: the brief's test of the same name read the LIVE
        # _publications/ directory and hard-coded "3 new papers". That count
        # goes stale the moment the automation's own first PR merges new
        # entries, permanently failing CI. Instead both sides are frozen
        # fixtures: profile.html (16 Scholar rows) and site_titles.txt (today's
        # 13 site titles, extracted once from _publications/*.md).
        entries = scholar_sync.parse_listing(fixture("profile.html"))
        with io.open(os.path.join(HERE, "fixtures", "site_titles.txt"), encoding="utf-8") as fh:
            known = set(scholar_sync.normalize_title(line) for line in fh if line.strip())
        new = scholar_sync.find_new(entries, known)
        titles = sorted(e.title for e in new)
        self.assertEqual(len(titles), 3)
        self.assertTrue(any("Causal tracing" in t for t in titles))
        self.assertTrue(any("PlanRAG-Audio" in t for t in titles))
        self.assertTrue(any("cross-lingual" in t for t in titles))


class TestPublicationAuthorIntegrity(unittest.TestCase):
    """Guards a fragility in publication-authors.html left in place by design.

    That include applies Liquid's `replace`, which matches substrings with no
    word boundaries: a mistyped co_first name silently renders nothing, and a
    name that happens to be a substring of a different co-author's name would
    get wrapped by mistake. The include itself was verified byte-identical
    and is not being touched; this test turns both failure modes into a loud,
    diagnosable test failure instead.

    Reads the LIVE _publications/ directory on purpose (unlike the frozen
    test above): this property must keep holding as entries are added, so
    freezing it would stop it from ever catching a real typo.
    """

    OWNER = "Chien-yu Huang"

    def _front_matter(self, path):
        with io.open(path, encoding="utf-8") as fh:
            text = fh.read()
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match, "%s: no YAML front matter block found" % path)
        return yaml.safe_load(match.group(1)) or {}

    def test_owner_and_co_first_names_are_exact_author_tokens(self):
        repo = os.path.dirname(os.path.dirname(HERE))
        pub_dir = os.path.join(repo, "_publications")
        paths = sorted(glob.glob(os.path.join(pub_dir, "*.md")))
        self.assertTrue(paths, "no publication files found in %s" % pub_dir)
        for path in paths:
            data = self._front_matter(path)
            authors = data.get("authors") or ""
            tokens = [token.strip() for token in authors.split(",")]
            names = [self.OWNER] + list(data.get("co_first") or [])
            for name in names:
                matches = [token for token in tokens if token == name]
                self.assertEqual(
                    len(matches),
                    1,
                    "%s: expected exactly one author token equal to %r, found %d "
                    "(tokens=%r)" % (path, name, len(matches), tokens),
                )
            for token in tokens:
                if token in names:
                    continue
                for name in names:
                    self.assertNotIn(
                        name,
                        token,
                        "%s: author token %r unexpectedly contains %r as a "
                        "substring" % (path, token, name),
                    )


class TestStub(unittest.TestCase):
    def test_venue_slug_known(self):
        self.assertEqual(scholar_sync.venue_slug("ICASSP 2024 - IEEE Conference"), "icassp")
        self.assertEqual(
            scholar_sync.venue_slug("International Conference on Learning Representations 2025"),
            "iclr",
        )
        self.assertEqual(scholar_sync.venue_slug("2021 IEEE Spoken Language Technology Workshop"), "slt")

    def test_venue_slug_unknown_is_arxiv(self):
        self.assertEqual(scholar_sync.venue_slug(""), "arxiv")
        self.assertEqual(scholar_sync.venue_slug("Some Unlisted Venue"), "arxiv")

    def test_title_slug_drops_stopwords(self):
        self.assertEqual(
            scholar_sync.title_slug("Causal tracing of audio-text fusion in large audio language models"),
            "causal-tracing-audio-text",
        )

    def test_parse_date_precision(self):
        self.assertEqual(scholar_sync.parse_date("2025/4"), ("2025-04-01", 2))
        self.assertEqual(scholar_sync.parse_date("2025/4/24"), ("2025-04-24", 3))
        self.assertEqual(scholar_sync.parse_date("2026"), ("2026-01-01", 1))

    def test_render_stub(self):
        entry = scholar_sync.Entry("1Xfc3ikAAAAJ:abc", "Causal tracing of audio-text fusion", "2026")
        detail = {"authors": "A Author, Chien-yu Huang, B Author", "date": "2026/1", "venue": ""}
        filename, content = scholar_sync.render_stub(entry, detail)
        self.assertEqual(filename, "2026-arxiv-causal-tracing-audio-text.md")
        self.assertIn('authors: "A Author, Chien-yu Huang, B Author"', content)
        self.assertIn("permalink: /publication/2026-arxiv-causal-tracing-audio-text", content)
        self.assertIn("date: 2026-01-01", content)
        self.assertIn("# scholar_id: 1Xfc3ikAAAAJ:abc", content)
        self.assertNotIn("<u>", content)
        self.assertNotIn("co_first:", content)


if __name__ == "__main__":
    unittest.main()

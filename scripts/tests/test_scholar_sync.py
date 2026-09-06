import glob
import io
import json
import os
import re
import subprocess
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

    def test_venue_slug_taslp(self):
        self.assertEqual(
            scholar_sync.venue_slug("IEEE Transactions on Audio, Speech and Language Processing"),
            "taslp",
        )

    def test_venue_slug_naacl_coling_icml(self):
        self.assertEqual(
            scholar_sync.venue_slug(
                "Proceedings of the 2019 Conference of the North American Chapter of the "
                "Association for Computational Linguistics: Human Language Technologies"
            ),
            "naacl",
        )
        self.assertEqual(
            scholar_sync.venue_slug("Proceedings of the 28th International Conference on Computational Linguistics"),
            "coling",
        )
        self.assertEqual(
            scholar_sync.venue_slug("Proceedings of the 37th International Conference on Machine Learning"),
            "icml",
        )

    def test_title_slug_drops_stopwords(self):
        self.assertEqual(
            scholar_sync.title_slug("Causal tracing of audio-text fusion in large audio language models"),
            "causal-tracing-audio-text",
        )

    def test_parse_date_precision(self):
        self.assertEqual(scholar_sync.parse_date("2025/4"), ("2025-04-01", 2))
        self.assertEqual(scholar_sync.parse_date("2025/4/24"), ("2025-04-24", 3))
        self.assertEqual(scholar_sync.parse_date("2026"), ("2026-01-01", 1))

    def test_parse_date_non_numeric_component_falls_back_to_sentinel(self):
        self.assertEqual(scholar_sync.parse_date("circa 2020"), ("1900-01-01", 1))

    def test_parse_date_precision_clamped_to_three(self):
        self.assertEqual(scholar_sync.parse_date("2026/1/2/3"), ("2026-01-02", 3))

    def _front_matter(self, content):
        match = re.match(r"^---\n(.*?)\n---\n", content, re.S)
        self.assertIsNotNone(match, "no YAML front matter block found in:\n%s" % content)
        return yaml.safe_load(match.group(1))

    def test_render_stub_escapes_double_quote_in_title(self):
        entry = scholar_sync.Entry("id:1", 'A "Novel" Approach', "2026")
        detail = {"authors": "A Author", "date": "2026/1", "venue": ""}
        _, content = scholar_sync.render_stub(entry, detail)
        data = self._front_matter(content)
        self.assertEqual(data["title"], 'A "Novel" Approach')

    def test_render_stub_escapes_double_quote_in_authors(self):
        entry = scholar_sync.Entry("id:2", "Some Title", "2026")
        detail = {"authors": 'A "Nickname" Author, B Author', "date": "2026/1", "venue": ""}
        _, content = scholar_sync.render_stub(entry, detail)
        data = self._front_matter(content)
        self.assertEqual(data["authors"], 'A "Nickname" Author, B Author')

    def test_render_stub_escapes_double_quote_in_venue(self):
        entry = scholar_sync.Entry("id:3", "Some Title", "2026")
        detail = {"authors": "A Author", "date": "2026/1", "venue": 'Proceedings of "Special" Workshop'}
        _, content = scholar_sync.render_stub(entry, detail)
        data = self._front_matter(content)
        self.assertEqual(data["venue"], 'Proceedings of "Special" Workshop')

    def test_render_stub_escapes_backslash_before_quote(self):
        # Escaping order matters: backslash must be escaped first, or a value
        # ending in a backslash right before an embedded quote would produce
        # a corrupt escape sequence instead of valid YAML.
        entry = scholar_sync.Entry("id:4", r'Title with \ and "quote"', "2026")
        detail = {"authors": "A Author", "date": "2026/1", "venue": ""}
        _, content = scholar_sync.render_stub(entry, detail)
        data = self._front_matter(content)
        self.assertEqual(data["title"], 'Title with \\ and "quote"')

    def test_render_stub_empty_authors_gets_distinct_todo(self):
        entry = scholar_sync.Entry("id:5", "Some Title", "2026")
        detail = {"authors": "", "date": "2026/1", "venue": ""}
        _, content = scholar_sync.render_stub(entry, detail)
        self.assertIn("Scholar returned no authors for this entry", content)
        self.assertNotIn("verify the list is complete, Scholar truncates long ones", content)
        data = self._front_matter(content)
        self.assertEqual(data["authors"], "")

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


class TestPullRequest(unittest.TestCase):
    def test_pr_body_contains_machine_marker(self):
        entry = scholar_sync.Entry("1Xfc3ikAAAAJ:abc", "Brand New Paper", "2026")
        body = scholar_sync.pr_body([(entry, "2026-arxiv-brand-new-paper.md")])
        marker = "<!-- scholar-sync: %s -->" % scholar_sync.normalize_title("Brand New Paper")
        self.assertIn(marker, body)
        self.assertIn("2026-arxiv-brand-new-paper.md", body)
        self.assertIn("co_first", body)

    def test_pr_marker_round_trips(self):
        entry = scholar_sync.Entry("x", "Brand New Paper", "2026")
        body = scholar_sync.pr_body([(entry, "f.md")])
        found = scholar_sync.PR_MARKER_RE.findall(body)
        self.assertEqual(found, [scholar_sync.normalize_title("Brand New Paper")])


class TestOpenPrTitles(unittest.TestCase):
    """`open_pr_titles()` shells out to `gh pr list` (read-only). Both
    branches are mocked at `subprocess.check_output` so no real `gh` process
    ever runs and no network call is made."""

    def test_extracts_markers_from_open_pr_bodies(self):
        marker = scholar_sync.normalize_title("Brand New Paper")
        payload = json.dumps(
            [
                {"body": "intro text\n<!-- scholar-sync: %s -->\n" % marker},
                {"body": "an unrelated open PR with no marker"},
            ]
        )
        with mock.patch(
            "scholar_sync.subprocess.check_output", return_value=payload
        ) as mock_co:
            titles = scholar_sync.open_pr_titles()
        self.assertEqual(titles, set([marker]))
        mock_co.assert_called_once()
        args, kwargs = mock_co.call_args
        self.assertEqual(
            args[0], ["gh", "pr", "list", "--state", "open", "--limit", "50", "--json", "body"]
        )

    def test_degrades_to_empty_set_when_gh_exits_nonzero(self):
        with mock.patch(
            "scholar_sync.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, ["gh"]),
        ):
            self.assertEqual(scholar_sync.open_pr_titles(), set())

    def test_degrades_to_empty_set_when_gh_is_missing(self):
        with mock.patch(
            "scholar_sync.subprocess.check_output",
            side_effect=OSError("gh: command not found"),
        ):
            self.assertEqual(scholar_sync.open_pr_titles(), set())


class TestMain(unittest.TestCase):
    """Exercises main()'s wiring end to end: the --dry-run guard's position,
    the union of the three `known` sets, and the per-entry degrade-on-
    FetchError path. Every function that could touch the network, the real
    `_publications/` directory, or a real git/gh process is mocked; any
    write goes to a temp directory instead."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _patch_common(
        self,
        entries,
        detail=None,
        site_titles=None,
        ignore=None,
        pr_titles=None,
        fetch_side_effect=None,
    ):
        """Patch every collaborator of main() except `run()`, which each
        test patches itself so it can assert on the recorded calls."""
        if detail is None:
            detail = {"authors": "A Author", "date": "2026/1", "venue": ""}
        if site_titles is None:
            site_titles = set()
        if ignore is None:
            ignore = set()
        if pr_titles is None:
            pr_titles = set()

        patches = [
            mock.patch.object(scholar_sync, "PUB_DIR", self.tmp),
            mock.patch.object(scholar_sync, "parse_listing", return_value=entries),
            mock.patch.object(scholar_sync, "parse_detail", return_value=detail),
            mock.patch.object(scholar_sync, "site_titles", return_value=site_titles),
            mock.patch.object(scholar_sync, "load_ignore", return_value=ignore),
            mock.patch.object(scholar_sync, "open_pr_titles", return_value=pr_titles),
        ]
        if fetch_side_effect is not None:
            patches.append(mock.patch.object(scholar_sync, "fetch", side_effect=fetch_side_effect))
        else:
            patches.append(mock.patch.object(scholar_sync, "fetch", return_value="<html></html>"))
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_dry_run_never_calls_run_and_writes_no_files(self):
        entries = [scholar_sync.Entry("U:new1", "Brand New Paper", "2026")]
        self._patch_common(entries)
        with mock.patch.object(scholar_sync, "run") as mock_run:
            rc = scholar_sync.main(["--dry-run"])
        self.assertEqual(rc, 0)
        mock_run.assert_not_called()
        self.assertEqual(os.listdir(self.tmp), [])

    def test_known_set_is_the_union_of_site_ignore_and_open_pr_titles(self):
        # One entry's title is "known" via each of the three sources; only
        # the entry with no match anywhere should survive find_new(). This
        # asserts on what main() itself actually wrote to disk, not on a
        # `known` set the test recomputes itself — dropping any one term
        # from main()'s union line (site_titles(...) | load_ignore(...) |
        # open_pr_titles(...)) would let that source's "known" entry leak
        # through find_new() and be written as an extra file, which the
        # os.listdir assertion below would then catch.
        site_only = scholar_sync.Entry("U:site", "Site Title Paper", "2020")
        ignore_only = scholar_sync.Entry("U:ignore", "Ignored Title Paper", "2021")
        pr_only = scholar_sync.Entry("U:pr", "Open Pr Title Paper", "2022")
        brand_new = scholar_sync.Entry("U:new", "Brand New Paper", "2026")
        entries = [site_only, ignore_only, pr_only, brand_new]
        self._patch_common(
            entries,
            site_titles=set([scholar_sync.normalize_title(site_only.title)]),
            ignore=set([scholar_sync.normalize_title(ignore_only.title)]),
            pr_titles=set([scholar_sync.normalize_title(pr_only.title)]),
        )
        # Non-dry-run: `run` is mocked so no real git/gh process executes,
        # but the write loop (and therefore the known-set filtering that
        # gates it) runs for real.
        with mock.patch.object(scholar_sync, "run"):
            rc = scholar_sync.main([])
        self.assertEqual(rc, 0)
        self.assertEqual(os.listdir(self.tmp), ["2026-arxiv-brand-new-paper.md"])

    def test_happy_path_calls_run_with_expected_commands_in_order(self):
        entries = [scholar_sync.Entry("U:new1", "Brand New Paper", "2026")]
        self._patch_common(entries)
        with mock.patch.object(scholar_sync, "run") as mock_run:
            rc = scholar_sync.main([])
        self.assertEqual(rc, 0)
        self.assertEqual(mock_run.call_count, 5)
        calls = [c.args[0] for c in mock_run.call_args_list]

        self.assertEqual(calls[0][:3], ["git", "checkout", "-B"])
        branch = calls[0][3]
        self.assertTrue(branch.startswith(scholar_sync.BRANCH_PREFIX))

        self.assertEqual(calls[1], ["git", "add", "_publications"])
        self.assertEqual(calls[2][:2], ["git", "commit"])
        self.assertEqual(calls[3], ["git", "push", "origin", branch])

        gh_call = calls[4]
        self.assertEqual(gh_call[:3], ["gh", "pr", "create"])
        self.assertIn("--head", gh_call)
        self.assertEqual(gh_call[gh_call.index("--head") + 1], branch)

        # Not dry-run: the draft file was actually written, under the temp
        # PUB_DIR only.
        self.assertEqual(os.listdir(self.tmp), ["2026-arxiv-brand-new-paper.md"])

    def test_detail_fetch_error_degrades_entry_to_blank_stub_without_aborting(self):
        entries = [scholar_sync.Entry("U:new1", "Brand New Paper", "2026")]

        def fetch_side_effect(url):
            if "view_op=view_citation" in url:
                raise scholar_sync.FetchError("detail blocked")
            return "<html></html>"

        self._patch_common(entries, fetch_side_effect=fetch_side_effect)
        with mock.patch.object(scholar_sync, "run") as mock_run:
            rc = scholar_sync.main([])
        self.assertEqual(rc, 0)

        # The batch was not aborted: the git/gh sequence still ran.
        mock_run.assert_called()

        written = os.listdir(self.tmp)
        self.assertEqual(len(written), 1)
        with io.open(os.path.join(self.tmp, written[0]), encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("Scholar returned no authors for this entry", content)
        self.assertIn('authors: ""', content)
        self.assertIn('venue: "Preprint"', content)

    def test_listing_fetch_error_propagates_out_of_main(self):
        def fetch_side_effect(url):
            raise scholar_sync.FetchError("listing blocked")

        with mock.patch.object(scholar_sync, "fetch", side_effect=fetch_side_effect), \
             mock.patch.object(scholar_sync, "run") as mock_run:
            with self.assertRaises(scholar_sync.FetchError):
                scholar_sync.main([])
        mock_run.assert_not_called()


class TestGitFailureHandling(unittest.TestCase):
    """A mid-sequence git/gh failure must produce a clear diagnostic naming
    the branch and the failed step, and exit non-zero, rather than a bare
    traceback or a swallowed failure."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_git_push_failure_reports_branch_and_step_and_exits_nonzero(self):
        entries = [scholar_sync.Entry("U:new1", "Brand New Paper", "2026")]
        patches = [
            mock.patch.object(scholar_sync, "PUB_DIR", self.tmp),
            mock.patch.object(scholar_sync, "parse_listing", return_value=entries),
            mock.patch.object(
                scholar_sync,
                "parse_detail",
                return_value={"authors": "A Author", "date": "2026/1", "venue": ""},
            ),
            mock.patch.object(scholar_sync, "site_titles", return_value=set()),
            mock.patch.object(scholar_sync, "load_ignore", return_value=set()),
            mock.patch.object(scholar_sync, "open_pr_titles", return_value=set()),
            mock.patch.object(scholar_sync, "fetch", return_value="<html></html>"),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        def run_side_effect(args):
            if args[:2] == ["git", "push"]:
                raise subprocess.CalledProcessError(1, args)
            return None

        stderr = io.StringIO()
        with mock.patch.object(scholar_sync, "run", side_effect=run_side_effect) as mock_run, \
             mock.patch("sys.stderr", stderr):
            rc = scholar_sync.main([])

        self.assertEqual(rc, 1)
        steps_attempted = [c.args[0][:2] for c in mock_run.call_args_list]
        self.assertIn(["git", "push"], steps_attempted)
        # The sequence must stop at the failed step: gh pr create never runs.
        self.assertNotIn(["gh", "pr"], steps_attempted)

        message = stderr.getvalue()
        self.assertIn("git push origin", message)
        self.assertIn(scholar_sync.BRANCH_PREFIX, message)
        self.assertIn("nothing was", message.lower())

    def test_git_binary_missing_reports_branch_and_step_and_exits_nonzero(self):
        # OSError (FileNotFoundError is a subclass) is what subprocess raises
        # when the executable itself is not on PATH -- a different failure
        # mode than a CalledProcessError, and one that must produce the same
        # kind of clear diagnostic rather than a bare traceback.
        entries = [scholar_sync.Entry("U:new1", "Brand New Paper", "2026")]
        patches = [
            mock.patch.object(scholar_sync, "PUB_DIR", self.tmp),
            mock.patch.object(scholar_sync, "parse_listing", return_value=entries),
            mock.patch.object(
                scholar_sync,
                "parse_detail",
                return_value={"authors": "A Author", "date": "2026/1", "venue": ""},
            ),
            mock.patch.object(scholar_sync, "site_titles", return_value=set()),
            mock.patch.object(scholar_sync, "load_ignore", return_value=set()),
            mock.patch.object(scholar_sync, "open_pr_titles", return_value=set()),
            mock.patch.object(scholar_sync, "fetch", return_value="<html></html>"),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        def run_side_effect(args):
            if args[:2] == ["git", "checkout"]:
                raise OSError("[Errno 2] No such file or directory: 'git'")
            return None

        stderr = io.StringIO()
        with mock.patch.object(scholar_sync, "run", side_effect=run_side_effect) as mock_run, \
             mock.patch("sys.stderr", stderr):
            rc = scholar_sync.main([])

        self.assertEqual(rc, 1)
        # The sequence must stop at the first (failed) step: nothing past
        # "git checkout" is attempted.
        steps_attempted = [c.args[0][:2] for c in mock_run.call_args_list]
        self.assertEqual(steps_attempted, [["git", "checkout"]])

        message = stderr.getvalue()
        self.assertIn("git checkout -B", message)
        self.assertIn(scholar_sync.BRANCH_PREFIX, message)
        self.assertIn("No such file or directory", message)


if __name__ == "__main__":
    unittest.main()

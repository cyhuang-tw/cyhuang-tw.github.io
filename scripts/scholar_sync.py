#!/usr/bin/env python3
"""Check Google Scholar for publications that are not on the site yet."""

import glob
import io
import os
import re
from collections import namedtuple

import requests
import yaml
from bs4 import BeautifulSoup

SCHOLAR_USER = "1Xfc3ikAAAAJ"
PROFILE_URL = (
    "https://scholar.google.com/citations"
    "?user={user}&hl=en&cstart=0&pagesize=100"
)
DETAIL_URL = (
    "https://scholar.google.com/citations"
    "?view_op=view_citation&hl=en&user={user}&citation_for_view={cid}"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
BLOCK_MARKERS = (r"\bcaptcha\b", "unusual traffic", "not a robot")

Entry = namedtuple("Entry", "scholar_id title year")


class FetchError(Exception):
    """Raised when Scholar cannot be read. Never treat this as 'no new papers'."""


def fetch(url):
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    except requests.RequestException as exc:
        raise FetchError("Scholar request failed: %s" % exc)
    if response.status_code != 200:
        raise FetchError("Scholar returned HTTP %s for %s" % (response.status_code, url))
    return response.text


def parse_listing(html):
    lowered = html.lower()
    for marker in BLOCK_MARKERS:
        if re.search(marker, lowered):
            raise FetchError("Scholar returned a block page (matched %r)" % marker)
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for row in soup.select("tr.gsc_a_tr"):
        link = row.select_one("a.gsc_a_at")
        if link is None:
            continue
        match = re.search(r"citation_for_view=([^&]+)", link.get("href", ""))
        year_el = row.select_one(".gsc_a_h")
        entries.append(
            Entry(
                match.group(1) if match else "",
                link.get_text(strip=True),
                year_el.get_text(strip=True) if year_el else "",
            )
        )
    if not entries:
        raise FetchError("No publication rows found. The page layout changed or the request was blocked.")
    return entries


def parse_detail(html):
    soup = BeautifulSoup(html, "html.parser")
    detail = {"authors": "", "date": "", "venue": ""}
    keys = {
        "authors": "authors",
        "publication date": "date",
        "conference": "venue",
        "journal": "venue",
        "book": "venue",
        "source": "venue",
    }
    for field in soup.select(".gsc_oci_field"):
        value = field.find_next_sibling("div", class_="gsc_oci_value")
        if value is None:
            continue
        target = keys.get(field.get_text(strip=True).lower())
        if target and not detail[target]:
            detail[target] = value.get_text(strip=True)
    return detail


def normalize_title(title):
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def site_titles(pub_dir):
    titles = set()
    for path in glob.glob(os.path.join(pub_dir, "*.md")):
        with io.open(path, encoding="utf-8") as fh:
            text = fh.read()
        match = re.search(r'^title:\s*"(.*?)"\s*$', text, re.M)
        if match:
            titles.add(normalize_title(match.group(1)))
    return titles


def load_ignore(path):
    if not os.path.exists(path):
        return set()
    with io.open(path, encoding="utf-8") as fh:
        items = yaml.safe_load(fh) or []
    return set(normalize_title(item["title"]) for item in items if item.get("title"))


def find_new(entries, known):
    return [e for e in entries if normalize_title(e.title) not in known]


VENUE_SLUGS = (
    ("icassp", "icassp"),
    ("interspeech", "interspeech"),
    ("learning representations", "iclr"),
    ("iclr", "iclr"),
    ("spoken language technology", "slt"),
    ("automatic speech recognition and understanding", "asru"),
    ("neural information processing", "neurips"),
    # NAACL needles must be checked before the ACL needle below: NAACL's full
    # name ("... North American Chapter of the Association for Computational
    # Linguistics ...") also contains the ACL substring, and the first
    # matching tuple wins regardless of where the match falls in the string.
    ("north american chapter", "naacl"),
    ("naacl", "naacl"),
    ("association for computational linguistics", "acl"),
    ("empirical methods", "emnlp"),
    ("transactions on audio, speech and language processing", "taslp"),
    ("transactions on audio, speech, and language processing", "taslp"),
    ("taslp", "taslp"),
    ("international conference on computational linguistics", "coling"),
    ("coling", "coling"),
    ("international conference on machine learning", "icml"),
    ("icml", "icml"),
)
STOPWORDS = frozenset(
    ["a", "an", "the", "of", "for", "and", "with", "on", "in", "to", "via", "towards", "toward"]
)


def yaml_dq_escape(value):
    """Escape a third-party string for safe interpolation inside a YAML
    double-quoted scalar ("..."). Backslash MUST be escaped before the quote,
    or a value ending in a backslash would swallow the closing quote."""
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def venue_slug(venue):
    lowered = (venue or "").lower()
    for needle, slug in VENUE_SLUGS:
        if needle in lowered:
            return slug
    return "arxiv"


def title_slug(title, words=3):
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", (title or "").lower()).split()
    kept = [w for w in cleaned if w not in STOPWORDS]
    return "-".join(kept[:words]) or "untitled"


def parse_date(text):
    parts = [p for p in (text or "").split("/") if p.strip()]
    if not parts:
        return ("1900-01-01", 1)
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
    except ValueError:
        # Scholar dates are not always clean slash-separated digits (e.g. a
        # scraped "circa 2020"). Degrade to the same sentinel used for empty
        # input rather than let this escape as an uncaught exception.
        return ("1900-01-01", 1)
    precision = min(len(parts), 3)
    return ("%04d-%02d-%02d" % (year, month, day), precision)


def render_stub(entry, detail):
    venue = detail.get("venue") or ""
    stem = "%s-%s-%s" % (entry.year or "0000", venue_slug(venue), title_slug(entry.title))
    iso_date, precision = parse_date(detail.get("date") or entry.year)
    date_note = "" if precision == 3 else "  # TODO: Scholar gave %r; missing parts defaulted" % (
        detail.get("date") or entry.year
    )
    authors = detail.get("authors") or ""
    authors_todo = (
        "verify the list is complete, Scholar truncates long ones"
        if authors
        else "Scholar returned no authors for this entry; fill in manually"
    )
    lines = [
        "---",
        'title: "%s"  # TODO: fix capitalisation, Scholar lowercases titles' % yaml_dq_escape(entry.title),
        'authors: "%s"  # TODO: %s' % (yaml_dq_escape(authors), authors_todo),
        "collection: publications",
        "permalink: /publication/%s" % stem,
        "excerpt: ''",
        "date: %s%s" % (iso_date, date_note),
        'venue: "%s"  # TODO: verify' % yaml_dq_escape(venue or "Preprint"),
        "paperurl: ''  # TODO: fill in",
        "# TODO: if you are a co-first author, add a co_first list here",
        "# scholar_id: %s" % entry.scholar_id,
        "---",
        "",
    ]
    return (stem + ".md", "\n".join(lines))

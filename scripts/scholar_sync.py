#!/usr/bin/env python3
"""Check Google Scholar for publications that are not on the site yet."""

import re
from collections import namedtuple

import requests
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

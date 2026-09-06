#!/usr/bin/env python3
"""Check Google Scholar for publications that are not on the site yet."""

import argparse
import datetime
import glob
import io
import json
import os
import re
import subprocess
import sys
import time
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


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB_DIR = os.path.join(REPO_ROOT, "_publications")
IGNORE_PATH = os.path.join(REPO_ROOT, "scripts", "scholar_ignore.yml")
BRANCH_PREFIX = "scholar-update/"
# 每次執行都用不同的分支名稱。如果重複使用同一個分支，
# 第二次執行的 force push 會刪掉第一個 PR 裡面的草稿檔。
PR_MARKER_RE = re.compile(r"<!-- scholar-sync: (.*?) -->")


def open_pr_titles():
    try:
        raw = subprocess.check_output(
            ["gh", "pr", "list", "--state", "open", "--limit", "50", "--json", "body"],
            cwd=REPO_ROOT,
            universal_newlines=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return set()
    found = set()
    for item in json.loads(raw):
        found.update(PR_MARKER_RE.findall(item.get("body") or ""))
    return found


def pr_body(created):
    lines = [
        "Found on the Google Scholar profile but missing from `_publications/`.",
        "",
        "Each entry below is a draft. Check every `TODO` comment before merging.",
        "",
    ]
    for entry, filename in created:
        lines.append("### %s" % entry.title)
        lines.append("")
        lines.append("- File: `_publications/%s`" % filename)
        lines.append("- Scholar year: %s" % (entry.year or "unknown"))
        lines.append("- Check the title capitalisation. Scholar lowercases titles.")
        lines.append("- Check the author list is complete, and add a `co_first` list if needed.")
        lines.append("- Fill in `paperurl`, and add `repo` if there is code.")
        lines.append("- Check the filename and `permalink` match how you name papers.")
        lines.append("")
        lines.append("<!-- scholar-sync: %s -->" % normalize_title(entry.title))
        lines.append("")
    lines.append("If a paper here should never appear on the site, add it to")
    lines.append("`scripts/scholar_ignore.yml` and close this pull request.")
    return "\n".join(lines)


def run(args):
    subprocess.check_call(args, cwd=REPO_ROOT)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    options = parser.parse_args(argv)

    entries = parse_listing(fetch(PROFILE_URL.format(user=SCHOLAR_USER)))
    print("Scholar entries: %d" % len(entries))

    known = site_titles(PUB_DIR) | load_ignore(IGNORE_PATH) | open_pr_titles()
    new = find_new(entries, known)
    if not new:
        print("No new publications.")
        return 0
    print("New publications: %d" % len(new))

    created = []
    for index, entry in enumerate(new):
        if index:
            time.sleep(2)
        try:
            detail = parse_detail(
                fetch(DETAIL_URL.format(user=SCHOLAR_USER, cid=entry.scholar_id))
            )
        except FetchError as error:
            print("  detail fetch failed for %r: %s" % (entry.title, error))
            detail = {"authors": "", "date": entry.year, "venue": ""}
        filename, content = render_stub(entry, detail)
        print("  %s" % filename)
        if not options.dry_run:
            with io.open(os.path.join(PUB_DIR, filename), "w", encoding="utf-8") as fh:
                fh.write(content)
        created.append((entry, filename))

    if options.dry_run:
        print("\n--dry-run: nothing written.")
        print(pr_body(created))
        return 0

    branch = BRANCH_PREFIX + datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    run(["git", "checkout", "-B", branch])
    run(["git", "add", "_publications"])
    run(["git", "commit", "-m", "Add draft entries for %d new publication(s)" % len(created)])
    run(["git", "push", "origin", branch])
    run(
        [
            "gh", "pr", "create",
            "--base", "master",
            "--head", branch,
            "--title", "Add %d new publication(s) from Google Scholar" % len(created),
            "--body", pr_body(created),
        ]
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as error:
        sys.stderr.write("FETCH FAILED: %s\n" % error)
        sys.stderr.write("This is NOT the same as 'no new papers'. No pull request was opened.\n")
        sys.exit(1)
